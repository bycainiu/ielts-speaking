from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.feedback_coach_agent import FeedbackCoachAgent, FeedbackCoachAnswer, FeedbackCoachInput
from app.agents.fluency_scorer_agent import FluencyCoherenceScorerAgent, FluencyCoherenceScorerInput, FluencyScoringTurn
from app.agents.grammar_scorer_agent import GrammarScorerAgent, GrammarScorerInput, GrammarScoringTurn
from app.agents.lexical_scorer_agent import LexicalResourceScorerAgent, LexicalResourceScorerInput, LexicalScoringTurn
from app.agents.pronunciation_scorer_agent import (
    PronunciationEvidenceInput,
    PronunciationScorerAgent,
    PronunciationScorerInput,
    PronunciationScoringTurn,
)
from app.agents.score_calibrator import CalibrationAnchorSample, ScoreCalibrator, ScoreCalibratorInput
from app.agents.score_reviewer_agent import ScoreReviewerAgent, ScoreReviewerInput
from app.mcp.report_mcp import CriterionScoreInput, ScoreReportInput
from app.mcp.speech_metrics_mcp import TurnAudioMetrics
from app.protocols.ag_ui_events import build_event, new_run_id
from app.protocols.schemas import AgentResponse
from app.rag.chunk_schema import ScoringCriterion


class ScoreSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_state: dict[str, Any] = Field(default_factory=dict)
    rubric_descriptors: dict[ScoringCriterion, list[str]] = Field(default_factory=dict)
    anchor_samples: list[CalibrationAnchorSample] = Field(default_factory=list)
    topic_keywords: list[str] = Field(default_factory=list)
    model_run_id: str | None = None


class ScoringWorkflow:
    workflow_version = "scoring_workflow.v1"

    def __init__(
        self,
        fluency_scorer: FluencyCoherenceScorerAgent | None = None,
        lexical_scorer: LexicalResourceScorerAgent | None = None,
        grammar_scorer: GrammarScorerAgent | None = None,
        pronunciation_scorer: PronunciationScorerAgent | None = None,
        reviewer: ScoreReviewerAgent | None = None,
        calibrator: ScoreCalibrator | None = None,
        feedback_coach: FeedbackCoachAgent | None = None,
    ) -> None:
        self.fluency_scorer = fluency_scorer or FluencyCoherenceScorerAgent()
        self.lexical_scorer = lexical_scorer or LexicalResourceScorerAgent()
        self.grammar_scorer = grammar_scorer or GrammarScorerAgent()
        self.pronunciation_scorer = pronunciation_scorer or PronunciationScorerAgent()
        self.reviewer = reviewer or ScoreReviewerAgent()
        self.calibrator = calibrator or ScoreCalibrator()
        self.feedback_coach = feedback_coach or FeedbackCoachAgent()

    def score_session(self, session_id: str, request: ScoreSessionRequest) -> AgentResponse:
        run_id = new_run_id()
        state = deepcopy(request.session_state)
        state.setdefault("session_id", session_id)
        state["status"] = "scoring"

        answers = normalize_answers(state)
        if not answers:
            state["scoring_error"] = "no_scorable_answers"
            return AgentResponse(
                run_id=run_id,
                events=[
                    build_event(
                        "error.recoverable",
                        session_id,
                        run_id,
                        {
                            "error": "no_scorable_answers",
                            "message": "没有可评分回答，请先提交至少一轮 ASR 转写。",
                            "retry_node": "scoring_workflow",
                        },
                    )
                ],
                state=state,
                next_action="retry_current_node",
            )

        criteria = self._score_dimensions(session_id, answers, request)
        dimension_events = [
            build_event(
                "scoring.dimension_completed",
                session_id,
                run_id,
                {
                    "criterion": criterion,
                    "band": score.band,
                    "confidence": score.confidence,
                    "evidence_count": len(score.evidence),
                },
            )
            for criterion, score in criteria.items()
        ]

        review = self.reviewer.review(ScoreReviewerInput(session_id=session_id, criteria=criteria))
        review_event = build_event(
            "scoring.review_completed",
            session_id,
            run_id,
            {
                "status": review.status,
                "finding_count": len(review.findings),
                "reviewer_notes": review.reviewer_notes,
            },
        )
        state["score_review"] = review.model_dump(mode="json")
        if review.status != "accepted":
            state["scoring_error"] = "review_requested_rescore"
            return AgentResponse(
                run_id=run_id,
                events=[
                    *dimension_events,
                    review_event,
                    build_event(
                        "error.recoverable",
                        session_id,
                        run_id,
                        {
                            "error": "review_requested_rescore",
                            "message": "评分复核要求重新评分，请重试当前评分节点。",
                            "reviewer_notes": review.reviewer_notes,
                            "retry_node": "scoring_workflow",
                        },
                    ),
                ],
                state=state,
                next_action="retry_current_node",
            )

        calibration = self.calibrator.calibrate(
            ScoreCalibratorInput(
                session_id=session_id,
                criteria=review.reviewed_criteria,
                anchor_samples=request.anchor_samples,
            )
        )
        raw_report = {
            "workflow_version": self.workflow_version,
            "review": review.raw_output,
            "calibration": calibration.raw_output,
            "calibration_adjustments": [item.model_dump(mode="json") for item in calibration.adjustments],
        }
        report = ScoreReportInput(
            session_id=session_id,
            overall_band=overall_band(calibration.calibrated_criteria),
            confidence=overall_confidence(calibration.calibrated_criteria),
            criteria=calibration.calibrated_criteria,
            reviewer_notes=review.reviewer_notes,
            model_run_id=request.model_run_id or run_id,
            raw_report=raw_report,
        )
        feedback = self.feedback_coach.generate(
            FeedbackCoachInput(
                session_id=session_id,
                score_report=report,
                answers=[feedback_answer(answer) for answer in answers],
                user_background=user_background_from_state(state),
            )
        )
        report = report.model_copy(
            update={
                "next_practice_plan": feedback.next_practice_plan,
                "raw_report": {
                    **raw_report,
                    "feedback": feedback.raw_output,
                    "feedback_summary": feedback.summary,
                },
            }
        )
        state["status"] = "scored"
        state["score_report"] = report.model_dump(mode="json", exclude_none=True)
        state["score_calibration"] = calibration.model_dump(mode="json")
        state["feedback_summary"] = feedback.summary
        state["feedback_items"] = [item.model_dump(mode="json") for item in feedback.feedback_items]
        state["reference_answers"] = [item.model_dump(mode="json", exclude_none=True) for item in feedback.reference_answers]

        return AgentResponse(
            run_id=run_id,
            events=[
                *dimension_events,
                review_event,
                build_event(
                    "report.ready",
                    session_id,
                    run_id,
                    {
                        "overall_band": report.overall_band,
                        "confidence": report.confidence,
                        "criteria": {
                            criterion: {
                                "band": score.band,
                                "confidence": score.confidence,
                                "evidence_count": len(score.evidence),
                            }
                            for criterion, score in report.criteria.items()
                        },
                        "calibration_status": calibration.status,
                        "feedback_count": len(feedback.feedback_items),
                        "reference_answer_count": len(feedback.reference_answers),
                        "next_practice_plan_count": len(report.next_practice_plan),
                        "disclaimer": report.disclaimer,
                    },
                ),
            ],
            state=state,
            next_action="finish_session",
        )

    def _score_dimensions(
        self,
        session_id: str,
        answers: list[dict[str, Any]],
        request: ScoreSessionRequest,
    ) -> dict[ScoringCriterion, CriterionScoreInput]:
        anchor_ids = anchor_ids_by_criterion(request.anchor_samples)
        descriptors = request.rubric_descriptors
        fluency = self.fluency_scorer.score(
            FluencyCoherenceScorerInput(
                session_id=session_id,
                turns=[fluency_turn(answer) for answer in answers],
                rubric_descriptors=descriptors.get("fluency_coherence", []),
                anchor_sample_ids=anchor_ids.get("fluency_coherence", []),
            )
        )
        lexical = self.lexical_scorer.score(
            LexicalResourceScorerInput(
                session_id=session_id,
                turns=[lexical_turn(answer) for answer in answers],
                rubric_descriptors=descriptors.get("lexical_resource", []),
                anchor_sample_ids=anchor_ids.get("lexical_resource", []),
                topic_keywords=topic_keywords_for(request, answers),
            )
        )
        grammar = self.grammar_scorer.score(
            GrammarScorerInput(
                session_id=session_id,
                turns=[grammar_turn(answer) for answer in answers],
                rubric_descriptors=descriptors.get("grammatical_range_accuracy", []),
                anchor_sample_ids=anchor_ids.get("grammatical_range_accuracy", []),
            )
        )
        pronunciation = self.pronunciation_scorer.score(
            PronunciationScorerInput(
                session_id=session_id,
                turns=[pronunciation_turn(answer) for answer in answers],
                rubric_descriptors=descriptors.get("pronunciation", []),
                anchor_sample_ids=anchor_ids.get("pronunciation", []),
            )
        )
        return {
            "fluency_coherence": fluency.to_report_criterion(),
            "lexical_resource": lexical.to_report_criterion(),
            "grammatical_range_accuracy": grammar.to_report_criterion(),
            "pronunciation": pronunciation.to_report_criterion(),
        }


def normalize_answers(state: dict[str, Any]) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    for index, item in enumerate(state.get("answers") or []):
        if not isinstance(item, dict):
            continue
        transcript = first_text(item, "asr_text", "transcript", "answer_text", "text")
        if not transcript:
            continue
        turn_id = first_text(item, "turn_id") or f"answer_{index + 1}"
        normalized = dict(item)
        normalized["turn_id"] = turn_id
        normalized["transcript"] = transcript
        answers.append(normalized)
    return answers


def fluency_turn(answer: dict[str, Any]) -> FluencyScoringTurn:
    return FluencyScoringTurn(
        turn_id=answer["turn_id"],
        transcript=answer["transcript"],
        question_text=first_text(answer, "question_text"),
        part=normalize_part(answer.get("part")),
        metrics=metrics_from_answer(answer),
    )


def lexical_turn(answer: dict[str, Any]) -> LexicalScoringTurn:
    return LexicalScoringTurn(
        turn_id=answer["turn_id"],
        transcript=answer["transcript"],
        question_text=first_text(answer, "question_text"),
        topic=answer_topic(answer),
        part=normalize_part(answer.get("part")),
    )


def grammar_turn(answer: dict[str, Any]) -> GrammarScoringTurn:
    return GrammarScoringTurn(
        turn_id=answer["turn_id"],
        transcript=answer["transcript"],
        question_text=first_text(answer, "question_text"),
        part=normalize_part(answer.get("part")),
    )


def pronunciation_turn(answer: dict[str, Any]) -> PronunciationScoringTurn:
    return PronunciationScoringTurn(
        turn_id=answer["turn_id"],
        transcript=answer["transcript"],
        question_text=first_text(answer, "question_text"),
        part=normalize_part(answer.get("part")),
        metrics=metrics_from_answer(answer),
        pronunciation_evidence=pronunciation_evidence_from_answer(answer),
    )


def feedback_answer(answer: dict[str, Any]) -> FeedbackCoachAnswer:
    return FeedbackCoachAnswer(
        turn_id=answer["turn_id"],
        transcript=answer["transcript"],
        question_text=first_text(answer, "question_text"),
        part=normalize_part(answer.get("part")),
        topic=answer_topic(answer),
        topic_guidance=answer.get("topic_guidance") if isinstance(answer.get("topic_guidance"), dict) else {},
    )


def metrics_from_answer(answer: dict[str, Any]) -> TurnAudioMetrics | None:
    raw = answer.get("speech_metrics") or answer.get("metrics") or {}
    if not isinstance(raw, dict):
        raw = {}
    payload = dict(raw)
    payload.setdefault("turn_id", answer["turn_id"])
    if answer.get("audio_asset_id") is not None:
        payload.setdefault("audio_asset_id", answer.get("audio_asset_id"))
    if answer.get("asr_confidence") is not None:
        payload.setdefault("asr_confidence", answer.get("asr_confidence"))
    return TurnAudioMetrics.model_validate(payload) if payload else None


def pronunciation_evidence_from_answer(answer: dict[str, Any]) -> PronunciationEvidenceInput | None:
    raw = answer.get("pronunciation_evidence")
    if not isinstance(raw, dict):
        return None
    payload = dict(raw)
    payload.setdefault("turn_id", answer["turn_id"])
    return PronunciationEvidenceInput.model_validate(payload)


def anchor_ids_by_criterion(anchors: list[CalibrationAnchorSample]) -> dict[ScoringCriterion, list[str]]:
    grouped: dict[ScoringCriterion, list[str]] = {}
    for anchor in anchors:
        grouped.setdefault(anchor.criterion, []).append(anchor.anchor_sample_id)
    return grouped


def topic_keywords_for(request: ScoreSessionRequest, answers: list[dict[str, Any]]) -> list[str]:
    keywords = list(request.topic_keywords)
    for answer in answers:
        guidance = answer.get("topic_guidance")
        if isinstance(guidance, dict):
            keywords.extend(str(item) for item in guidance.get("vocabulary") or [])
        topic = answer_topic(answer)
        if topic:
            keywords.append(topic)
    deduped: list[str] = []
    for keyword in keywords:
        text = str(keyword).strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


def answer_topic(answer: dict[str, Any]) -> str | None:
    topic = first_text(answer, "topic")
    if topic:
        return topic
    topic_ids = answer.get("topic_ids")
    if isinstance(topic_ids, list) and topic_ids:
        return str(topic_ids[0])
    return None


def user_background_from_state(state: dict[str, Any]) -> dict[str, Any]:
    for key in ("user_background", "background", "profile"):
        value = state.get(key)
        if isinstance(value, dict):
            return value
    return {}


def overall_band(criteria: dict[ScoringCriterion, CriterionScoreInput]) -> float:
    average = sum(score.band for score in criteria.values()) / len(criteria)
    return clamp_half_band(average)


def overall_confidence(criteria: dict[ScoringCriterion, CriterionScoreInput]) -> float:
    return round(sum(score.confidence for score in criteria.values()) / len(criteria), 3)


def normalize_part(value: Any) -> int | None:
    if value is None:
        return None
    try:
        part = int(value)
    except (TypeError, ValueError):
        return None
    return part if part in {1, 2, 3} else None


def first_text(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def clamp_half_band(value: float) -> float:
    rounded = round(value * 2) / 2
    return max(0.0, min(9.0, rounded))
