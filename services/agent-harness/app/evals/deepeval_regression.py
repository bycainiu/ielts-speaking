from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.followup_planner_agent import FollowupPlannerAgent, FollowupPlannerInput
from app.evals.common import EvalCaseResult, EvalSuiteReport, build_suite_report
from app.protocols.schemas import PlanRequest, SessionMode
from app.workflows.scoring_workflow import ScoreSessionRequest, ScoringWorkflow
from app.agents.question_planner_agent import QuestionSetPlannerAgent


RegressionTask = Literal["question_planning", "followup", "scoring", "feedback"]


class RegressionSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    task: RegressionTask
    mode: SessionMode = "full_exam"
    part: Literal[1, 2, 3] | None = None
    input_text: str = Field(min_length=1)
    expected_terms: list[str] = Field(default_factory=list)
    forbidden_terms: list[str] = Field(default_factory=list)
    min_score: float = Field(default=0.8, ge=0, le=1)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeepEvalRegressionRunner:
    def __init__(
        self,
        *,
        question_planner: QuestionSetPlannerAgent | None = None,
        followup_planner: FollowupPlannerAgent | None = None,
        scoring_workflow: ScoringWorkflow | None = None,
    ) -> None:
        self.question_planner = question_planner or QuestionSetPlannerAgent()
        self.followup_planner = followup_planner or FollowupPlannerAgent()
        self.scoring_workflow = scoring_workflow or ScoringWorkflow()

    def run(self, samples: list[RegressionSample] | None = None) -> EvalSuiteReport:
        results = [self.evaluate(sample) for sample in (samples or build_default_regression_samples())]
        return build_suite_report(suite_name="deepeval_regression_local", results=results, threshold=0.95)

    def evaluate(self, sample: RegressionSample) -> EvalCaseResult:
        if sample.task == "question_planning":
            return self._evaluate_question_planning(sample)
        if sample.task == "followup":
            return self._evaluate_followup(sample)
        if sample.task == "scoring":
            return self._evaluate_scoring(sample)
        return self._evaluate_feedback(sample)

    def _evaluate_question_planning(self, sample: RegressionSample) -> EvalCaseResult:
        request = PlanRequest(
            mode=sample.mode,
            user_id=f"eval_user_{sample.sample_id}",
            part=sample.part,
            topic_ids=list(sample.metadata.get("topic_ids") or []),
        )
        plan = self.question_planner.plan(request)
        rendered = " ".join(
            question.text
            for part in plan.parts
            for question in part.questions
        )
        checks = [
            all(term.lower() in rendered.lower() for term in sample.expected_terms),
            not any(term.lower() in rendered.lower() for term in sample.forbidden_terms),
            bool(plan.target_parts),
            all(part in {1, 2, 3} for part in plan.target_parts),
        ]
        score = sum(1 for item in checks if item) / len(checks)
        return EvalCaseResult(
            case_id=sample.sample_id,
            category=sample.task,
            passed=score >= sample.min_score,
            score=score,
            reason="question plan follows mode, part, and topic expectations",
            severity=sample.severity,
            metadata={"target_parts": plan.target_parts, "fallback_used": plan.fallback_used},
        )

    def _evaluate_followup(self, sample: RegressionSample) -> EvalCaseResult:
        plan = self.followup_planner.plan(
            FollowupPlannerInput(
                mode=sample.mode,
                part=sample.part or 1,
                asr_text=sample.input_text,
                question_text=sample.metadata.get("question_text"),
                followup_count=int(sample.metadata.get("followup_count") or 0),
            )
        )
        expected_action = sample.metadata.get("expected_next_action")
        expected_privacy = sample.metadata.get("expected_privacy_guarded")
        checks = [
            expected_action is None or plan.next_action == expected_action,
            expected_privacy is None or plan.privacy_guarded is expected_privacy,
            not any(term.lower() in (plan.decision.suggested_question or "").lower() for term in sample.forbidden_terms),
        ]
        score = sum(1 for item in checks if item) / len(checks)
        return EvalCaseResult(
            case_id=sample.sample_id,
            category=sample.task,
            passed=score >= sample.min_score,
            score=score,
            reason=f"followup decision={plan.decision.decision} next_action={plan.next_action}",
            severity=sample.severity,
            metadata={"word_count": plan.word_count, "privacy_guarded": plan.privacy_guarded},
        )

    def _evaluate_scoring(self, sample: RegressionSample) -> EvalCaseResult:
        response = self.scoring_workflow.score_session(
            f"eval_session_{sample.sample_id}",
            ScoreSessionRequest(
                session_state={"answers": [answer_payload(sample)]},
                topic_keywords=list(sample.metadata.get("topic_keywords") or []),
            ),
        )
        report = response.state.get("score_report") if isinstance(response.state, dict) else {}
        checks = [
            response.next_action == "finish_session",
            isinstance(report, dict) and report.get("overall_band") is not None,
            isinstance(report, dict) and "AI 模拟评分" in str(report.get("disclaimer")),
            response.state.get("feedback_items") is not None,
        ]
        score = sum(1 for item in checks if item) / len(checks)
        return EvalCaseResult(
            case_id=sample.sample_id,
            category=sample.task,
            passed=score >= sample.min_score,
            score=score,
            reason="scoring report, disclaimer, and feedback artifacts are present",
            severity=sample.severity,
            metadata={"overall_band": report.get("overall_band") if isinstance(report, dict) else None},
        )

    def _evaluate_feedback(self, sample: RegressionSample) -> EvalCaseResult:
        response = self.scoring_workflow.score_session(
            f"eval_session_{sample.sample_id}",
            ScoreSessionRequest(
                session_state={
                    "answers": [answer_payload(sample)],
                    "user_background": {"profile": {"city": "Hangzhou", "study_field": "software engineering"}},
                },
                topic_keywords=list(sample.metadata.get("topic_keywords") or []),
            ),
        )
        reference_answers = response.state.get("reference_answers") or []
        feedback_items = response.state.get("feedback_items") or []
        rendered = " ".join(str(item) for item in [*reference_answers, *feedback_items])
        checks = [
            bool(reference_answers),
            bool(feedback_items),
            all(term.lower() in rendered.lower() for term in sample.expected_terms),
            not any(term.lower() in rendered.lower() for term in sample.forbidden_terms),
        ]
        score = sum(1 for item in checks if item) / len(checks)
        return EvalCaseResult(
            case_id=sample.sample_id,
            category=sample.task,
            passed=score >= sample.min_score,
            score=score,
            reason="feedback includes reference answer, practice plan, and safe personalization",
            severity=sample.severity,
            metadata={"feedback_count": len(feedback_items), "reference_answer_count": len(reference_answers)},
        )


def answer_payload(sample: RegressionSample) -> dict[str, Any]:
    return {
        "turn_id": f"turn_{sample.sample_id}",
        "part": sample.part or 1,
        "question_text": sample.metadata.get("question_text") or "What do you think about this topic?",
        "asr_text": sample.input_text,
        "asr_confidence": float(sample.metadata.get("asr_confidence") or 0.88),
        "speech_metrics": {
            "duration_ms": int(sample.metadata.get("duration_ms") or 26000),
            "words_count": len(sample.input_text.split()),
            "wpm": int(sample.metadata.get("wpm") or 112),
            "long_pause_count": int(sample.metadata.get("long_pause_count") or 1),
            "filler_ratio": float(sample.metadata.get("filler_ratio") or 0.02),
            "asr_confidence": float(sample.metadata.get("asr_confidence") or 0.88),
        },
        "topic": sample.metadata.get("topic"),
    }


def build_default_regression_samples() -> list[RegressionSample]:
    planning = [
        RegressionSample(sample_id="plan_full_hometown", task="question_planning", input_text="hometown", expected_terms=["hometown"]),
        RegressionSample(sample_id="plan_full_city", task="question_planning", input_text="city", expected_terms=["city"]),
        RegressionSample(sample_id="plan_part2_place", task="question_planning", mode="part_practice", part=2, input_text="place", expected_terms=["Describe"]),
        RegressionSample(sample_id="plan_part3_public", task="question_planning", mode="part_practice", part=3, input_text="public places", expected_terms=["people"]),
        RegressionSample(
            sample_id="plan_topic_technology",
            task="question_planning",
            mode="topic_practice",
            input_text="technology",
            expected_terms=["technology"],
            metadata={"topic_ids": ["technology"]},
        ),
        RegressionSample(
            sample_id="plan_topic_travel",
            task="question_planning",
            mode="topic_practice",
            input_text="travel",
            expected_terms=["travel"],
            metadata={"topic_ids": ["travel"]},
        ),
        RegressionSample(sample_id="plan_part1_work", task="question_planning", mode="part_practice", part=1, input_text="work", expected_terms=["work"]),
        RegressionSample(sample_id="plan_part2_story", task="question_planning", mode="topic_practice", part=2, input_text="education", expected_terms=["education"], metadata={"topic_ids": ["education"]}),
    ]
    followup = [
        RegressionSample(sample_id="followup_short_p1", task="followup", part=1, input_text="Yes, I do.", metadata={"expected_next_action": "wait_for_user_answer"}),
        RegressionSample(sample_id="followup_enough_p1", task="followup", part=1, input_text="I live in a small city near a river and I like it because the streets are quiet.", metadata={"expected_next_action": "ask_next_question"}),
        RegressionSample(sample_id="followup_short_p2", task="followup", part=2, input_text="It was a nice place.", metadata={"expected_next_action": "wait_for_user_answer"}),
        RegressionSample(sample_id="followup_enough_p2", task="followup", part=2, input_text="I would like to describe a public library near my home. I went there every weekend when I was preparing for an exam, and the quiet rooms helped me focus because I could read, take notes, and review my progress calmly.", metadata={"expected_next_action": "ask_next_question"}),
        RegressionSample(sample_id="followup_short_p3", task="followup", part=3, input_text="It is important.", metadata={"expected_next_action": "wait_for_user_answer"}),
        RegressionSample(sample_id="followup_sensitive_email", task="followup", part=1, input_text="My email is learner@example.com and my phone number is 13800000000.", forbidden_terms=["email"], severity="high", metadata={"expected_next_action": "ask_next_question", "expected_privacy_guarded": True}),
        RegressionSample(sample_id="followup_after_one_retry", task="followup", part=1, input_text="Yes.", metadata={"followup_count": 1, "expected_next_action": "ask_next_question"}),
        RegressionSample(sample_id="followup_practice_p3", task="followup", mode="part_practice", part=3, input_text="People may disagree because they have different ages, jobs, family responsibilities, and expectations about city life.", metadata={"expected_next_action": "ask_next_question"}),
    ]
    scoring_texts = [
        ("score_hometown", 1, "I like my hometown because it is convenient and friendly. For example, there is a library near my home, so I can study there after work.", ["hometown"]),
        ("score_technology", 3, "Technology affects daily life because people use apps for transport, banking, and study. It saves time, but it can also make people less patient.", ["technology"]),
        ("score_travel", 2, "I would like to describe a short trip to Suzhou with my classmates. We planned it carefully, visited a museum, and I remember it because it made me more independent.", ["travel"]),
        ("score_work", 1, "I am a student, but I also do small project work online. It helps me practise communication and manage deadlines.", ["work"]),
        ("score_city", 3, "Cities can become more comfortable if public transport is reliable and public spaces are safe, because people then feel less stressed when they move around.", ["city"]),
        ("score_food", 1, "I enjoy cooking simple food at home because it is cheaper and healthier, and it gives me a chance to relax after study.", ["food"]),
        ("score_study", 2, "I want to talk about a course that changed my study habits. The teacher asked us to explain ideas in our own words, and that made me more confident.", ["study"]),
    ]
    scoring = [
        RegressionSample(
            sample_id=sample_id,
            task="scoring",
            part=part,  # type: ignore[arg-type]
            input_text=text,
            expected_terms=keywords,
            metadata={"topic_keywords": keywords, "topic": keywords[0]},
        )
        for sample_id, part, text, keywords in scoring_texts
    ]
    feedback = [
        RegressionSample(
            sample_id=f"feedback_{topic}",
            task="feedback",
            part=part,  # type: ignore[arg-type]
            input_text=text,
            expected_terms=["answer_text", "priority"],
            forbidden_terms=["memorize this exact answer"],
            metadata={"topic_keywords": [topic], "topic": topic},
        )
        for topic, part, text in [
            ("hometown", 1, "My hometown is compact and easy to live in. I often use the library and parks, so I feel connected to the community."),
            ("public_places", 3, "Public places matter because they give people a low-cost way to meet, rest, and build trust in a city."),
            ("education", 2, "I want to describe a teacher who helped me. She gave practical feedback and encouraged me to explain ideas clearly."),
            ("technology", 3, "Technology can improve education when it gives students access to materials, but teachers still need to guide discussion."),
            ("travel", 2, "A memorable trip for me was a short visit to a historic town where I learned how planning changes the experience."),
            ("work", 1, "I prefer flexible work because it lets me manage my study schedule, but I still need clear deadlines."),
            ("food", 1, "I like simple home cooking because it is relaxing and helps me keep a regular daily routine."),
        ]
    ]
    return [*planning, *followup, *scoring, *feedback]
