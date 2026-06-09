from __future__ import annotations

import re
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.mcp.report_mcp import CriterionScoreInput, ReportEvidence


WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "because",
    "but",
    "can",
    "do",
    "for",
    "from",
    "have",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "so",
    "that",
    "the",
    "they",
    "this",
    "to",
    "was",
    "with",
}
LOW_VALUE_EXPRESSIONS: dict[str, str] = {
    "good": "useful / enjoyable / well-organized",
    "nice": "pleasant / supportive / memorable",
    "bad": "frustrating / inefficient / hard to follow",
    "thing": "activity / reason / habit / feature",
    "things": "details / examples / responsibilities",
    "stuff": "materials / tasks / examples",
    "interesting": "engaging / thought-provoking / worth discussing",
    "important": "meaningful / practical / influential",
    "very": "用更具体的形容词替代 very + adjective",
    "a lot": "many examples / frequently / a wide range",
}
LOW_VALUE_PATTERN = re.compile(
    r"\b(good|nice|bad|thing|things|stuff|interesting|important|very|a lot)\b",
    re.IGNORECASE,
)


class LexicalScoringTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1)
    transcript: str = Field(min_length=1)
    question_text: str | None = None
    topic: str | None = None
    part: Literal[1, 2, 3] | None = None

    @field_validator("turn_id", "transcript", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("text is required")
        return text


class LexicalResourceScorerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    turns: list[LexicalScoringTurn] = Field(min_length=1)
    rubric_descriptors: list[str] = Field(default_factory=list)
    anchor_sample_ids: list[str] = Field(default_factory=list)
    topic_keywords: list[str] = Field(default_factory=list)


class LexicalResourceScorerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: Literal["lexical_resource"] = "lexical_resource"
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


class LexicalResourceScorerAgent:
    scorer_version = "lexical_resource_scorer.v1"

    def score(self, scorer_input: LexicalResourceScorerInput) -> LexicalResourceScorerOutput:
        features = extract_features(scorer_input.turns, topic_keywords=scorer_input.topic_keywords)
        band = estimate_band(features)
        confidence = estimate_confidence(features, scorer_input)
        evidence = build_evidence(scorer_input.turns, features)
        suggestions = build_suggestions(features)

        return LexicalResourceScorerOutput(
            band=band,
            confidence=confidence,
            evidence=evidence,
            suggestions=suggestions,
            raw_output={
                "scorer_version": self.scorer_version,
                "feature_summary": features,
                "rubric_descriptor_count": len(scorer_input.rubric_descriptors),
                "anchor_sample_ids": scorer_input.anchor_sample_ids,
                "dimension_boundary": "lexical_resource_only_no_rare_word_stuffing",
            },
        )


def extract_features(turns: list[LexicalScoringTurn], *, topic_keywords: list[str]) -> dict[str, Any]:
    transcripts = " ".join(turn.transcript for turn in turns)
    words = normalize_words(transcripts)
    content_words = [word for word in words if word not in STOPWORDS and len(word) > 2]
    content_counts = Counter(content_words)
    repeated_words = [
        {"word": word, "count": count}
        for word, count in content_counts.most_common()
        if count >= 3
    ]
    low_value_counts = Counter(match.group(1).lower() for match in LOW_VALUE_PATTERN.finditer(transcripts))
    normalized_topic_keywords = sorted({keyword.lower().strip() for keyword in topic_keywords if keyword.strip()})
    topic_hits = [
        keyword
        for keyword in normalized_topic_keywords
        if re.search(rf"\b{re.escape(keyword)}\b", transcripts, flags=re.IGNORECASE)
    ]

    total_words = len(words)
    unique_content_words = len(set(content_words))
    lexical_diversity = round(unique_content_words / len(content_words), 3) if content_words else 0.0
    low_value_total = sum(low_value_counts.values())
    return {
        "turn_count": len(turns),
        "total_words": total_words,
        "content_word_count": len(content_words),
        "unique_content_word_count": unique_content_words,
        "lexical_diversity": lexical_diversity,
        "repeated_words": repeated_words[:8],
        "repeated_word_type_count": len(repeated_words),
        "low_value_expressions": [
            {
                "expression": expression,
                "count": count,
                "replacement": LOW_VALUE_EXPRESSIONS.get(expression, "choose a more precise expression"),
            }
            for expression, count in low_value_counts.most_common()
        ],
        "low_value_expression_count": low_value_total,
        "topic_keywords_provided": normalized_topic_keywords,
        "topic_keyword_hits": topic_hits,
        "topic_keyword_hit_count": len(topic_hits),
    }


def estimate_band(features: dict[str, Any]) -> float:
    score = 6.0
    total_words = features["total_words"]
    diversity = features["lexical_diversity"]
    repeated_word_type_count = features["repeated_word_type_count"]
    low_value_count = features["low_value_expression_count"]
    topic_keywords = features["topic_keywords_provided"]
    topic_hit_count = features["topic_keyword_hit_count"]

    if total_words < 20:
        score -= 1.0
    elif total_words < 45:
        score -= 0.5
    elif total_words >= 90:
        score += 0.5

    if diversity >= 0.68 and features["content_word_count"] >= 25:
        score += 0.5
    elif diversity < 0.38:
        score -= 1.0
    elif diversity < 0.48:
        score -= 0.5

    if repeated_word_type_count >= 6:
        score -= 1.0
    elif repeated_word_type_count >= 3:
        score -= 0.5

    if low_value_count == 0 and total_words >= 35:
        score += 0.5
    elif low_value_count >= 6:
        score -= 1.0
    elif low_value_count >= 3:
        score -= 0.5

    if topic_keywords:
        if topic_hit_count >= 3:
            score += 0.5
        elif topic_hit_count == 0 and total_words >= 35:
            score -= 0.5

    return clamp_half_band(score)


def estimate_confidence(features: dict[str, Any], scorer_input: LexicalResourceScorerInput) -> float:
    confidence = 0.55
    if features["total_words"] >= 45:
        confidence += 0.12
    if features["content_word_count"] >= 25:
        confidence += 0.06
    if scorer_input.topic_keywords:
        confidence += 0.05
    if scorer_input.rubric_descriptors:
        confidence += 0.06
    if scorer_input.anchor_sample_ids:
        confidence += 0.04
    return round(max(0.35, min(0.9, confidence)), 3)


def build_evidence(turns: list[LexicalScoringTurn], features: dict[str, Any]) -> list[ReportEvidence]:
    primary_turn = max(turns, key=lambda item: len(normalize_words(item.transcript)))
    evidence = [
        ReportEvidence(
            turn_id=primary_turn.turn_id,
            quote=short_quote(primary_turn.transcript),
            reason=(
                f"回答共 {features['total_words']} 词，内容词多样性为 {features['lexical_diversity']}，"
                "可用于判断词汇资源是否丰富且不重复。"
            ),
        )
    ]

    if features["repeated_words"]:
        repeated = ", ".join(f"{item['word']} x{item['count']}" for item in features["repeated_words"][:4])
        evidence.append(
            ReportEvidence(
                turn_id=primary_turn.turn_id,
                quote=f"Repeated words: {repeated}",
                reason="高频重复内容词说明表达可能依赖少数安全词，需要更准确的替代表达。",
            )
        )
    if features["low_value_expressions"]:
        low_value = ", ".join(
            f"{item['expression']} -> {item['replacement']}" for item in features["low_value_expressions"][:3]
        )
        evidence.append(
            ReportEvidence(
                turn_id=primary_turn.turn_id,
                quote=f"Low-value expressions: {low_value}",
                reason="空泛词会降低表达准确度，替换为具体、自然的词组更符合 Lexical Resource 维度。",
            )
        )
    if features["topic_keyword_hits"]:
        evidence.append(
            ReportEvidence(
                turn_id=primary_turn.turn_id,
                quote=f"Topic vocabulary: {', '.join(features['topic_keyword_hits'][:5])}",
                reason="适量话题词能支持回答的具体性，但不应为了显得高级而堆砌生僻词。",
            )
        )
    return evidence[:4]


def build_suggestions(features: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    if features["low_value_expressions"]:
        for item in features["low_value_expressions"][:3]:
            suggestions.append(f"把 {item['expression']} 替换为更具体的表达，例如 {item['replacement']}。")
    if features["repeated_words"]:
        repeated = ", ".join(item["word"] for item in features["repeated_words"][:3])
        suggestions.append(f"减少 {repeated} 这类高频重复词，按原因、例子、影响分别准备自然替换。")
    if features["topic_keywords_provided"] and features["topic_keyword_hit_count"] == 0:
        suggestions.append("补入 1-2 个贴近题目的话题词，但要服务于具体例子，不要堆砌生僻词。")
    if features["lexical_diversity"] < 0.48:
        suggestions.append("用同义改写和具体名词替换泛泛表达，让信息更精确。")
    if not suggestions:
        suggestions.append("继续保持自然准确的词汇选择，优先表达清楚，再逐步增加话题搭配。")
    return suggestions[:4]


def normalize_words(text: str) -> list[str]:
    return [match.group(0).lower() for match in WORD_RE.finditer(text)]


def clamp_half_band(value: float) -> float:
    rounded = round(value * 2) / 2
    return max(0.0, min(9.0, rounded))


def short_quote(text: str, max_chars: int = 160) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
