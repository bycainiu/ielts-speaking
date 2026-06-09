from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.mcp.report_mcp import CriterionScoreInput, ReportEvidence
from app.mcp.speech_metrics_mcp import TurnAudioMetrics


WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
COHERENCE_MARKER_RE = re.compile(
    r"\b(firstly|secondly|finally|because|so|therefore|however|for example|for instance|as a result|on the other hand)\b",
    re.IGNORECASE,
)
REPETITION_RE = re.compile(r"\b([A-Za-z]+)(?:\s+\1\b){1,}", re.IGNORECASE)
SELF_CORRECTION_RE = re.compile(r"\b(I mean|sorry|rather|actually|what I mean is|let me rephrase)\b", re.IGNORECASE)


class FluencyScoringTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1)
    transcript: str = Field(min_length=1)
    question_text: str | None = None
    part: Literal[1, 2, 3] | None = None
    metrics: TurnAudioMetrics | None = None

    @field_validator("transcript", "turn_id", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("text is required")
        return text


class FluencyCoherenceScorerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    turns: list[FluencyScoringTurn] = Field(min_length=1)
    rubric_descriptors: list[str] = Field(default_factory=list)
    anchor_sample_ids: list[str] = Field(default_factory=list)


class FluencyCoherenceScorerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: Literal["fluency_coherence"] = "fluency_coherence"
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


class FluencyCoherenceScorerAgent:
    scorer_version = "fluency_coherence_scorer.v1"

    def score(self, scorer_input: FluencyCoherenceScorerInput) -> FluencyCoherenceScorerOutput:
        features = extract_features(scorer_input.turns)
        band = estimate_band(features)
        confidence = estimate_confidence(features, scorer_input)
        evidence = build_evidence(scorer_input.turns, features)
        suggestions = build_suggestions(features)

        return FluencyCoherenceScorerOutput(
            band=band,
            confidence=confidence,
            evidence=evidence,
            suggestions=suggestions,
            raw_output={
                "scorer_version": self.scorer_version,
                "feature_summary": features,
                "rubric_descriptor_count": len(scorer_input.rubric_descriptors),
                "anchor_sample_ids": scorer_input.anchor_sample_ids,
                "dimension_boundary": "fluency_coherence_only_no_grammar_penalty",
            },
        )


def extract_features(turns: list[FluencyScoringTurn]) -> dict[str, Any]:
    word_counts: list[int] = []
    wpms: list[float] = []
    long_pauses: list[int] = []
    filler_ratios: list[float] = []
    asr_confidences: list[float] = []
    marker_count = 0
    repetition_count = 0
    self_correction_count = 0

    for turn in turns:
        words = turn.metrics.words_count if turn.metrics and turn.metrics.words_count is not None else count_words(turn.transcript)
        word_counts.append(words)
        marker_count += len(COHERENCE_MARKER_RE.findall(turn.transcript))
        repetition_count += len(REPETITION_RE.findall(turn.transcript))
        self_correction_count += len(SELF_CORRECTION_RE.findall(turn.transcript))

        if turn.metrics:
            if turn.metrics.wpm is not None:
                wpms.append(turn.metrics.wpm)
            if turn.metrics.long_pause_count is not None:
                long_pauses.append(turn.metrics.long_pause_count)
            if turn.metrics.filler_ratio is not None:
                filler_ratios.append(turn.metrics.filler_ratio)
            if turn.metrics.asr_confidence is not None:
                asr_confidences.append(turn.metrics.asr_confidence)

    total_words = sum(word_counts)
    return {
        "turn_count": len(turns),
        "total_words": total_words,
        "average_words_per_turn": round(total_words / len(turns), 2),
        "average_wpm": average(wpms),
        "total_long_pause_count": sum(long_pauses) if long_pauses else None,
        "average_filler_ratio": average(filler_ratios),
        "average_asr_confidence": average(asr_confidences),
        "coherence_marker_count": marker_count,
        "repetition_count": repetition_count,
        "self_correction_count": self_correction_count,
        "has_speech_metrics": bool(wpms or long_pauses or filler_ratios),
    }


def estimate_band(features: dict[str, Any]) -> float:
    score = 6.0
    average_wpm = features.get("average_wpm")
    long_pause_count = features.get("total_long_pause_count")
    filler_ratio = features.get("average_filler_ratio")
    total_words = features["total_words"]
    markers = features["coherence_marker_count"]
    repetitions = features["repetition_count"]
    self_corrections = features["self_correction_count"]

    if average_wpm is not None:
        if 100 <= average_wpm <= 160:
            score += 0.5
        elif average_wpm < 60 or average_wpm > 210:
            score -= 1.0
        elif average_wpm < 85 or average_wpm > 185:
            score -= 0.5

    if long_pause_count is not None:
        if long_pause_count <= 1:
            score += 0.5
        elif long_pause_count >= 5:
            score -= 1.0
        elif long_pause_count >= 3:
            score -= 0.5

    if filler_ratio is not None:
        if filler_ratio <= 0.03:
            score += 0.5
        elif filler_ratio > 0.15:
            score -= 1.0
        elif filler_ratio > 0.08:
            score -= 0.5

    if total_words < 20:
        score -= 1.0
    elif total_words < 45:
        score -= 0.5
    elif total_words >= 90:
        score += 0.5

    if markers >= 3:
        score += 0.5
    elif markers == 0 and total_words >= 45:
        score -= 0.5

    if repetitions >= 4:
        score -= 0.5
    if self_corrections >= 4:
        score -= 0.5

    return clamp_half_band(score)


def estimate_confidence(features: dict[str, Any], scorer_input: FluencyCoherenceScorerInput) -> float:
    confidence = 0.55
    if features["has_speech_metrics"]:
        confidence += 0.18
    if features["total_words"] >= 45:
        confidence += 0.1
    if scorer_input.rubric_descriptors:
        confidence += 0.07
    if scorer_input.anchor_sample_ids:
        confidence += 0.05
    asr_confidence = features.get("average_asr_confidence")
    if asr_confidence is not None:
        confidence = (confidence + asr_confidence) / 2
    return round(max(0.35, min(0.92, confidence)), 3)


def build_evidence(turns: list[FluencyScoringTurn], features: dict[str, Any]) -> list[ReportEvidence]:
    primary_turn = max(turns, key=lambda item: count_words(item.transcript))
    evidence = [
        ReportEvidence(
            turn_id=primary_turn.turn_id,
            quote=short_quote(primary_turn.transcript),
            reason=f"回答共 {features['total_words']} 词，平均每轮 {features['average_words_per_turn']} 词，可用于判断展开程度和连贯性。",
        )
    ]

    if features.get("average_wpm") is not None:
        evidence.append(
            ReportEvidence(
                turn_id=primary_turn.turn_id,
                quote=f"WPM {features['average_wpm']}",
                reason="语速证据用于判断流利度，不用于评价语法准确性。",
            )
        )
    if features.get("total_long_pause_count") is not None:
        evidence.append(
            ReportEvidence(
                turn_id=primary_turn.turn_id,
                quote=f"Long pauses {features['total_long_pause_count']}",
                reason="长停顿数量反映回答是否经常中断或需要重新组织思路。",
            )
        )
    if features["coherence_marker_count"] > 0:
        evidence.append(
            ReportEvidence(
                turn_id=primary_turn.turn_id,
                quote=f"Coherence markers {features['coherence_marker_count']}",
                reason="连接词和因果/举例标记可支持连贯性判断。",
            )
        )
    return evidence[:4]


def build_suggestions(features: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    average_wpm = features.get("average_wpm")
    if average_wpm is not None and average_wpm < 85:
        suggestions.append("先用 3 个关键词规划答案，再连续说完整句，减少边想边停顿。")
    if features.get("total_long_pause_count") is not None and features["total_long_pause_count"] >= 3:
        suggestions.append("练习用 because、for example、so 连接下一句，避免长时间空白。")
    if features.get("average_filler_ratio") is not None and features["average_filler_ratio"] > 0.08:
        suggestions.append("把 um、you know、I mean 替换成短暂停顿或自然连接词。")
    if features["coherence_marker_count"] == 0 and features["total_words"] >= 45:
        suggestions.append("每个回答至少加入一个原因和一个例子，让信息推进更清楚。")
    if not suggestions:
        suggestions.append("继续保持稳定语速，并用更明确的开头、原因和例子增强整体连贯性。")
    return suggestions[:4]


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


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
