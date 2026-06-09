from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.mcp.report_mcp import CriterionScoreInput, ReportEvidence


SENTENCE_RE = re.compile(r"[^.!?]+[.!?]?")
WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
COMPLEX_MARKER_RE = re.compile(
    r"\b(because|although|even though|which|who|when|while|if|that|so that|where|after|before)\b",
    re.IGNORECASE,
)
SUBJECT_VERB_ERRORS = [
    (
        re.compile(r"\b(he|she|it)\s+(go|have|do|make|like|need|want|study|work|play|live)\b", re.IGNORECASE),
        "subject_verb_agreement",
        "third-person singular verb needs -s",
        "He goes / she has / it makes",
        "major",
    ),
    (
        re.compile(r"\b(people|students|children|friends|parents)\s+(is|was)\b", re.IGNORECASE),
        "plural_subject_be_verb",
        "plural subject should use are/were",
        "people are / students were",
        "major",
    ),
]
PAST_TIME_PRESENT_RE = re.compile(
    r"\b(yesterday|last week|last month|last year|in 2020|two years ago)\b[^.!?]{0,90}(?<!to\s)\b(go|have|do|make|meet|see|buy|take)\b",
    re.IGNORECASE,
)
ARTICLE_GAP_RE = re.compile(r"\b(go|went|travelled|traveled)\s+to\s+(park|museum|library|cinema|university)\b", re.IGNORECASE)


class GrammarScoringTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1)
    transcript: str = Field(min_length=1)
    question_text: str | None = None
    part: Literal[1, 2, 3] | None = None

    @field_validator("turn_id", "transcript", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("text is required")
        return text


class GrammarScorerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    turns: list[GrammarScoringTurn] = Field(min_length=1)
    rubric_descriptors: list[str] = Field(default_factory=list)
    anchor_sample_ids: list[str] = Field(default_factory=list)


class GrammarScorerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: Literal["grammatical_range_accuracy"] = "grammatical_range_accuracy"
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


class GrammarScorerAgent:
    scorer_version = "grammar_scorer.v1"

    def score(self, scorer_input: GrammarScorerInput) -> GrammarScorerOutput:
        features = extract_features(scorer_input.turns)
        band = estimate_band(features)
        confidence = estimate_confidence(features, scorer_input)
        evidence = build_evidence(scorer_input.turns, features)
        suggestions = build_suggestions(features)

        return GrammarScorerOutput(
            band=band,
            confidence=confidence,
            evidence=evidence,
            suggestions=suggestions,
            raw_output={
                "scorer_version": self.scorer_version,
                "feature_summary": features,
                "rubric_descriptor_count": len(scorer_input.rubric_descriptors),
                "anchor_sample_ids": scorer_input.anchor_sample_ids,
                "dimension_boundary": "grammar_range_accuracy_only_natural_spoken_rewrites",
            },
        )


def extract_features(turns: list[GrammarScoringTurn]) -> dict[str, Any]:
    transcripts = " ".join(turn.transcript for turn in turns)
    sentences = [sentence.strip() for sentence in SENTENCE_RE.findall(transcripts) if sentence.strip()]
    words = WORD_RE.findall(transcripts)
    complex_markers = COMPLEX_MARKER_RE.findall(transcripts)
    errors = detect_errors(turns)
    major_error_count = sum(1 for error in errors if error["severity"] == "major")
    minor_error_count = sum(1 for error in errors if error["severity"] == "minor")
    sentence_lengths = [len(WORD_RE.findall(sentence)) for sentence in sentences]
    average_sentence_length = round(sum(sentence_lengths) / len(sentence_lengths), 2) if sentence_lengths else 0.0
    sentence_length_range = max(sentence_lengths) - min(sentence_lengths) if sentence_lengths else 0

    return {
        "turn_count": len(turns),
        "total_words": len(words),
        "sentence_count": len(sentences),
        "average_sentence_length": average_sentence_length,
        "sentence_length_range": sentence_length_range,
        "complex_marker_count": len(complex_markers),
        "errors": errors[:10],
        "major_error_count": major_error_count,
        "minor_error_count": minor_error_count,
        "error_count": len(errors),
    }


def detect_errors(turns: list[GrammarScoringTurn]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for turn in turns:
        for pattern, kind, reason, rewrite_hint, severity in SUBJECT_VERB_ERRORS:
            for match in pattern.finditer(turn.transcript):
                errors.append(
                    {
                        "turn_id": turn.turn_id,
                        "kind": kind,
                        "quote": match.group(0),
                        "reason": reason,
                        "rewrite_hint": rewrite_hint,
                        "severity": severity,
                    }
                )
        for match in PAST_TIME_PRESENT_RE.finditer(turn.transcript):
            errors.append(
                {
                    "turn_id": turn.turn_id,
                    "kind": "past_time_tense_control",
                    "quote": short_quote(match.group(0), max_chars=90),
                    "reason": "past-time context needs a past-tense verb",
                    "rewrite_hint": "yesterday I went / last year I had",
                    "severity": "major",
                }
            )
        for match in ARTICLE_GAP_RE.finditer(turn.transcript):
            errors.append(
                {
                    "turn_id": turn.turn_id,
                    "kind": "article_gap",
                    "quote": match.group(0),
                    "reason": "common countable place nouns usually need an article",
                    "rewrite_hint": "went to the park / visited a museum",
                    "severity": "minor",
                }
            )
    return dedupe_errors(errors)


def estimate_band(features: dict[str, Any]) -> float:
    score = 6.0
    total_words = features["total_words"]
    major_errors = features["major_error_count"]
    minor_errors = features["minor_error_count"]
    complex_markers = features["complex_marker_count"]
    sentence_count = features["sentence_count"]
    sentence_length_range = features["sentence_length_range"]

    if total_words < 20:
        score -= 1.0
    elif total_words < 45:
        score -= 0.5
    elif total_words >= 90:
        score += 0.5

    if major_errors >= 4:
        score -= 1.5
    elif major_errors >= 2:
        score -= 1.0
    elif major_errors == 1:
        score -= 0.5

    if minor_errors >= 4:
        score -= 0.5

    if complex_markers >= 4 and sentence_length_range >= 6:
        score += 1.0
    elif complex_markers >= 2 and sentence_length_range >= 6:
        score += 0.5
    elif complex_markers == 0 and sentence_count >= 3 and total_words >= 45:
        score -= 0.5

    return clamp_half_band(score)


def estimate_confidence(features: dict[str, Any], scorer_input: GrammarScorerInput) -> float:
    confidence = 0.55
    if features["total_words"] >= 45:
        confidence += 0.12
    if features["sentence_count"] >= 2:
        confidence += 0.06
    if features["complex_marker_count"] >= 2:
        confidence += 0.05
    if scorer_input.rubric_descriptors:
        confidence += 0.06
    if scorer_input.anchor_sample_ids:
        confidence += 0.04
    return round(max(0.35, min(0.9, confidence)), 3)


def build_evidence(turns: list[GrammarScoringTurn], features: dict[str, Any]) -> list[ReportEvidence]:
    primary_turn = max(turns, key=lambda item: len(WORD_RE.findall(item.transcript)))
    evidence = [
        ReportEvidence(
            turn_id=primary_turn.turn_id,
            quote=short_quote(primary_turn.transcript),
            reason=(
                f"回答包含 {features['sentence_count']} 个句子、{features['complex_marker_count']} 个复杂结构标记，"
                "可用于判断语法范围。"
            ),
        )
    ]
    for error in diverse_errors(features["errors"])[:3]:
        evidence.append(
            ReportEvidence(
                turn_id=error["turn_id"],
                quote=error["quote"],
                reason=f"{error['kind']}: {error['reason']}；建议自然改为 {error['rewrite_hint']}。",
            )
        )
    return evidence[:4]


def build_suggestions(features: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    for error in diverse_errors(features["errors"])[:3]:
        suggestions.append(f"把 “{error['quote']}” 自然改成类似 “{error['rewrite_hint']}”，优先保证口语清楚。")
    if features["complex_marker_count"] == 0 and features["total_words"] >= 45:
        suggestions.append("每个较长回答加入一个 because / when / which 从句，展示句型范围。")
    if not suggestions:
        suggestions.append("继续保持清楚的基本句，并适量加入原因、时间或对比从句来展示语法范围。")
    return suggestions[:4]


def dedupe_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for error in errors:
        key = (error["turn_id"], error["kind"], error["quote"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(error)
    return unique


def diverse_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_kinds: set[str] = set()
    for error in errors:
        if error["kind"] in selected_kinds:
            continue
        selected.append(error)
        selected_kinds.add(error["kind"])
    if len(selected) < len(errors):
        selected.extend(error for error in errors if error["kind"] in selected_kinds)
    return selected


def clamp_half_band(value: float) -> float:
    rounded = round(value * 2) / 2
    return max(0.0, min(9.0, rounded))


def short_quote(text: str, max_chars: int = 160) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
