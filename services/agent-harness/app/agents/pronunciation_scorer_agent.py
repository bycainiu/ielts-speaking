from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.mcp.report_mcp import CriterionScoreInput, ReportEvidence
from app.mcp.speech_metrics_mcp import TurnAudioMetrics


WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
UNCLEAR_SEGMENT_RE = re.compile(r"\[(?:unclear|inaudible|noise|unknown)\]|\b(?:xxx|<unk>)\b", re.IGNORECASE)


class PronunciationEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1)
    intelligibility_score: float | None = Field(default=None, ge=0, le=1)
    pronunciation_score: float | None = Field(default=None, ge=0, le=1)
    prosody_score: float | None = Field(default=None, ge=0, le=1)
    unclear_segment_count: int | None = Field(default=None, ge=0)
    audio_quality: Literal["good", "fair", "poor"] | None = None
    evidence_source: str | None = None

    @field_validator("turn_id", mode="before")
    @classmethod
    def normalize_turn_id(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("turn_id is required")
        return text


class PronunciationScoringTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1)
    transcript: str = Field(min_length=1)
    question_text: str | None = None
    part: Literal[1, 2, 3] | None = None
    metrics: TurnAudioMetrics | None = None
    pronunciation_evidence: PronunciationEvidenceInput | None = None

    @field_validator("turn_id", "transcript", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("text is required")
        return text


class PronunciationScorerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    turns: list[PronunciationScoringTurn] = Field(min_length=1)
    rubric_descriptors: list[str] = Field(default_factory=list)
    anchor_sample_ids: list[str] = Field(default_factory=list)


class PronunciationScorerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: Literal["pronunciation"] = "pronunciation"
    band: float = Field(ge=0, le=9)
    confidence: float = Field(ge=0, le=1)
    evidence: list[ReportEvidence] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    raw_output: dict[str, Any] = Field(default_factory=dict)

    def to_report_criterion(self) -> CriterionScoreInput:
        return CriterionScoreInput(
            band=self.band,
            confidence=self.confidence,
            evidence=self.evidence,
            suggestions=self.suggestions,
            raw_output=self.raw_output,
        )


class PronunciationScorerAgent:
    scorer_version = "pronunciation_scorer.v1"

    def score(self, scorer_input: PronunciationScorerInput) -> PronunciationScorerOutput:
        features = extract_features(scorer_input.turns)
        band = estimate_band(features)
        confidence = estimate_confidence(features, scorer_input)
        evidence = build_evidence(scorer_input.turns, features)
        suggestions = build_suggestions(features, confidence)

        return PronunciationScorerOutput(
            band=band,
            confidence=confidence,
            evidence=evidence,
            suggestions=suggestions,
            raw_output={
                "scorer_version": self.scorer_version,
                "feature_summary": features,
                "rubric_descriptor_count": len(scorer_input.rubric_descriptors),
                "anchor_sample_ids": scorer_input.anchor_sample_ids,
                "dimension_boundary": "pronunciation_only_intelligibility_rhythm_stress_no_accent_penalty",
            },
        )


def extract_features(turns: list[PronunciationScoringTurn]) -> dict[str, Any]:
    asr_confidences: list[float] = []
    wpms: list[float] = []
    long_pauses: list[int] = []
    mean_pauses: list[float] = []
    intelligibility_scores: list[float] = []
    pronunciation_scores: list[float] = []
    prosody_scores: list[float] = []
    audio_quality_counts = {"good": 0, "fair": 0, "poor": 0}
    evidence_sources: list[str] = []
    unclear_segments = 0
    total_words = 0

    for turn in turns:
        total_words += len(WORD_RE.findall(turn.transcript))
        unclear_segments += len(UNCLEAR_SEGMENT_RE.findall(turn.transcript))
        if turn.metrics:
            if turn.metrics.asr_confidence is not None:
                asr_confidences.append(turn.metrics.asr_confidence)
            if turn.metrics.wpm is not None:
                wpms.append(turn.metrics.wpm)
            if turn.metrics.long_pause_count is not None:
                long_pauses.append(turn.metrics.long_pause_count)
            if turn.metrics.mean_pause_ms is not None:
                mean_pauses.append(turn.metrics.mean_pause_ms)
        if turn.pronunciation_evidence:
            evidence = turn.pronunciation_evidence
            if evidence.intelligibility_score is not None:
                intelligibility_scores.append(evidence.intelligibility_score)
            if evidence.pronunciation_score is not None:
                pronunciation_scores.append(evidence.pronunciation_score)
            if evidence.prosody_score is not None:
                prosody_scores.append(evidence.prosody_score)
            if evidence.unclear_segment_count is not None:
                unclear_segments += evidence.unclear_segment_count
            if evidence.audio_quality is not None:
                audio_quality_counts[evidence.audio_quality] += 1
            if evidence.evidence_source:
                evidence_sources.append(evidence.evidence_source)

    average_wpm = average(wpms)
    total_long_pause_count = sum(long_pauses) if long_pauses else None
    rhythm_issue_count = estimate_rhythm_issues(average_wpm=average_wpm, total_long_pause_count=total_long_pause_count)
    return {
        "turn_count": len(turns),
        "total_words": total_words,
        "average_asr_confidence": average(asr_confidences),
        "average_wpm": average_wpm,
        "total_long_pause_count": total_long_pause_count,
        "average_mean_pause_ms": average(mean_pauses),
        "average_intelligibility_score": average(intelligibility_scores),
        "average_pronunciation_score": average(pronunciation_scores),
        "average_prosody_score": average(prosody_scores),
        "unclear_segment_count": unclear_segments,
        "rhythm_issue_count": rhythm_issue_count,
        "audio_quality_counts": audio_quality_counts,
        "evidence_sources": sorted(set(evidence_sources)),
        "has_pronunciation_evidence": bool(intelligibility_scores or pronunciation_scores or prosody_scores),
        "has_speech_metrics": bool(asr_confidences or wpms or long_pauses or mean_pauses),
    }


def estimate_band(features: dict[str, Any]) -> float:
    score = 6.0
    asr_confidence = features.get("average_asr_confidence")
    intelligibility = features.get("average_intelligibility_score")
    pronunciation = features.get("average_pronunciation_score")
    prosody = features.get("average_prosody_score")
    unclear_segments = features["unclear_segment_count"]
    rhythm_issues = features["rhythm_issue_count"]
    poor_audio_count = features["audio_quality_counts"]["poor"]

    if intelligibility is not None:
        if intelligibility >= 0.82:
            score += 0.5
        elif intelligibility < 0.55:
            score -= 1.0
        elif intelligibility < 0.68:
            score -= 0.5

    if pronunciation is not None:
        if pronunciation >= 0.82:
            score += 0.5
        elif pronunciation < 0.55:
            score -= 1.0
        elif pronunciation < 0.68:
            score -= 0.5

    if prosody is not None:
        if prosody >= 0.78:
            score += 0.5
        elif prosody < 0.5:
            score -= 0.5

    if asr_confidence is not None and asr_confidence < 0.62 and unclear_segments >= 2:
        score -= 0.5
    if unclear_segments >= 5:
        score -= 1.0
    elif unclear_segments >= 2:
        score -= 0.5
    if rhythm_issues >= 2:
        score -= 0.5
    if poor_audio_count and not features["has_pronunciation_evidence"]:
        score -= 0.5

    return clamp_half_band(score)


def estimate_confidence(features: dict[str, Any], scorer_input: PronunciationScorerInput) -> float:
    confidence = 0.45
    if features["has_speech_metrics"]:
        confidence += 0.12
    if features["has_pronunciation_evidence"]:
        confidence += 0.18
    if features["total_words"] >= 45:
        confidence += 0.08
    if scorer_input.rubric_descriptors:
        confidence += 0.05
    if scorer_input.anchor_sample_ids:
        confidence += 0.04

    asr_confidence = features.get("average_asr_confidence")
    if asr_confidence is not None:
        confidence = (confidence + asr_confidence) / 2
    if features["audio_quality_counts"]["poor"]:
        confidence -= 0.12
    if features["unclear_segment_count"] >= 4:
        confidence -= 0.08
    return round(max(0.25, min(0.9, confidence)), 3)


def build_evidence(turns: list[PronunciationScoringTurn], features: dict[str, Any]) -> list[ReportEvidence]:
    primary_turn = max(turns, key=lambda item: len(WORD_RE.findall(item.transcript)))
    evidence = [
        ReportEvidence(
            turn_id=primary_turn.turn_id,
            quote=short_quote(primary_turn.transcript),
            reason=(
                f"可懂度相关证据：ASR confidence={features['average_asr_confidence']}，"
                f"unclear segments={features['unclear_segment_count']}，用于保守判断 pronunciation。"
            ),
        )
    ]
    if features.get("average_pronunciation_score") is not None:
        evidence.append(
            ReportEvidence(
                turn_id=primary_turn.turn_id,
                quote=f"Pronunciation evidence {features['average_pronunciation_score']}",
                reason="开源或内部发音 evidence 只作为可懂度和发音清晰度参考，不直接等同 IELTS 官方分。",
            )
        )
    if features.get("average_prosody_score") is not None:
        evidence.append(
            ReportEvidence(
                turn_id=primary_turn.turn_id,
                quote=f"Prosody evidence {features['average_prosody_score']}",
                reason="韵律 evidence 用于判断重音、节奏和语调自然度。",
            )
        )
    if features["rhythm_issue_count"] > 0:
        evidence.append(
            ReportEvidence(
                turn_id=primary_turn.turn_id,
                quote=f"Rhythm issues {features['rhythm_issue_count']}",
                reason="语速过快/过慢或长停顿过多会影响听者理解，属于节奏和停顿分块证据。",
            )
        )
    return evidence[:4]


def build_suggestions(features: dict[str, Any], confidence: float) -> list[str]:
    suggestions: list[str] = []
    if confidence < 0.55:
        suggestions.append("本轮发音评分置信度较低，可能受录音质量、ASR 置信度或不可识别片段影响，建议重录或补充更清晰音频后复核。")
    if features["unclear_segment_count"] >= 2:
        suggestions.append("优先练习把关键词说完整，减少不可识别片段，让听者能稳定抓住核心名词和动词。")
    if features["rhythm_issue_count"] > 0:
        suggestions.append("按 meaning chunks 分组停顿，例如先说观点，再说原因和例子，避免一口气过快或长时间断开。")
    prosody = features.get("average_prosody_score")
    if prosody is not None and prosody < 0.65:
        suggestions.append("选择 1-2 个关键词做重音，句尾保持自然升降调，让答案更容易跟上。")
    if not suggestions:
        suggestions.append("继续保持清晰可懂的发音，重点练习关键词重音、自然节奏和停顿分块。")
    return suggestions[:4]


def estimate_rhythm_issues(*, average_wpm: float | None, total_long_pause_count: int | None) -> int:
    issues = 0
    if average_wpm is not None and (average_wpm < 65 or average_wpm > 190):
        issues += 1
    if total_long_pause_count is not None and total_long_pause_count >= 4:
        issues += 1
    return issues


def average(values: list[float] | list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def clamp_half_band(value: float) -> float:
    rounded = round(value * 2) / 2
    return max(0.0, min(9.0, rounded))


def short_quote(text: str, max_chars: int = 160) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
