from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


ContentStatus = Literal["draft", "reviewing", "active", "archived"]
KnowledgeDocType = Literal["question_bank", "rubric", "user_profile", "topic_knowledge", "review_history"]
QuestionSourceType = Literal["original", "authorized", "user_recall", "internal"]
SpeakingPart = Literal["1", "2", "3"]
ScoringCriterion = Literal[
    "fluency_coherence",
    "lexical_resource",
    "grammatical_range_accuracy",
    "pronunciation",
]
PrivacyLevel = Literal["normal", "sensitive", "private"]
AllowedUsage = Literal["question_personalization", "feedback_personalization", "scoring_context"]
TopicKnowledgeType = Literal["idea", "example", "vocabulary", "expression", "structure", "background"]
ReviewHistoryItemType = Literal["answer_excerpt", "score_evidence", "feedback_item", "weakness"]
RubricPolicyType = Literal["official_descriptor", "internal_policy", "anchor_example"]


class KnowledgeMetadataError(ValueError):
    pass


class _MetadataBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    doc_type: KnowledgeDocType
    title: str
    status: ContentStatus

    @field_validator("title", mode="before")
    @classmethod
    def _normalize_title(cls, value: Any) -> str:
        return _required_str(value)


class QuestionBankChunkMetadata(_MetadataBase):
    doc_type: Literal["question_bank"]
    season_id: str
    part: SpeakingPart
    topic: str
    source_type: QuestionSourceType
    question_id: str | None = None
    topic_id: str | None = None
    review_status: ContentStatus | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    license: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _backfill_season_id(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and "season_id" not in data and "season" in data:
            normalized = dict(data)
            normalized["season_id"] = normalized["season"]
            return normalized
        return data

    @field_validator("season_id", "topic", "source_type", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: Any) -> str:
        return _required_str(value)

    @field_validator("part", mode="before")
    @classmethod
    def _normalize_part(cls, value: Any) -> str:
        return _normalize_part(value)


class RubricChunkMetadata(_MetadataBase):
    doc_type: Literal["rubric"]
    criterion: ScoringCriterion
    band: str
    descriptor: str
    rubric_id: str | None = None
    rubric_version: str | None = None
    policy_type: RubricPolicyType | None = None
    anchor_sample_id: str | None = None
    has_guidance: bool | None = None

    @field_validator("criterion", "descriptor", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: Any) -> str:
        return _required_str(value)

    @field_validator("band", mode="before")
    @classmethod
    def _normalize_band(cls, value: Any) -> str:
        return _normalize_band(value)


class UserProfileChunkMetadata(_MetadataBase):
    doc_type: Literal["user_profile"]
    privacy_level: PrivacyLevel
    allowed_usage: list[AllowedUsage] = Field(min_length=1)
    owner_user_id: str | None = None
    fact_id: str | None = None
    topic: str | None = None
    fact_key: str | None = None
    questionnaire_id: str | None = None
    fact_value_hash: str | None = None

    @field_validator("privacy_level", mode="before")
    @classmethod
    def _normalize_privacy_level(cls, value: Any) -> str:
        return _required_str(value)

    @field_validator("allowed_usage", mode="before")
    @classmethod
    def _normalize_allowed_usage(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, list | tuple | set):
            values = list(value)
        else:
            return value

        normalized: list[str] = []
        for item in values:
            text = _required_str(item)
            if text not in normalized:
                normalized.append(text)
        return normalized


class TopicKnowledgeChunkMetadata(_MetadataBase):
    doc_type: Literal["topic_knowledge"]
    topic: str
    knowledge_type: TopicKnowledgeType | None = None
    source_type: QuestionSourceType | None = None

    @field_validator("topic", mode="before")
    @classmethod
    def _normalize_topic(cls, value: Any) -> str:
        return _required_str(value)


class ReviewHistoryChunkMetadata(_MetadataBase):
    doc_type: Literal["review_history"]
    session_id: str
    part: SpeakingPart
    review_item_type: ReviewHistoryItemType
    criterion: ScoringCriterion | None = None

    @field_validator("session_id", "review_item_type", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: Any) -> str:
        return _required_str(value)

    @field_validator("part", mode="before")
    @classmethod
    def _normalize_part(cls, value: Any) -> str:
        return _normalize_part(value)


METADATA_MODELS: dict[str, type[_MetadataBase]] = {
    "question_bank": QuestionBankChunkMetadata,
    "rubric": RubricChunkMetadata,
    "user_profile": UserProfileChunkMetadata,
    "topic_knowledge": TopicKnowledgeChunkMetadata,
    "review_history": ReviewHistoryChunkMetadata,
}


def normalize_chunk_metadata(doc_type: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
    model_cls = METADATA_MODELS.get(doc_type)
    if model_cls is None:
        raise KnowledgeMetadataError(f"unsupported knowledge doc_type: {doc_type}")

    try:
        model = model_cls.model_validate(dict(metadata))
    except ValidationError as exc:
        raise KnowledgeMetadataError(f"{doc_type} metadata invalid: {exc}") from exc
    return model.model_dump(mode="json", exclude_none=True)


def _required_str(value: Any) -> str:
    if value is None:
        raise ValueError("required string is missing")
    text = str(value).strip()
    if not text:
        raise ValueError("required string is empty")
    return text


def _normalize_part(value: Any) -> str:
    text = _required_str(value)
    if text not in {"1", "2", "3"}:
        raise ValueError("part must be 1, 2, or 3")
    return text


def _normalize_band(value: Any) -> str:
    text = _required_str(value)
    try:
        numeric = float(text)
    except ValueError as exc:
        raise ValueError("band must be numeric") from exc
    if numeric < 0 or numeric > 9 or numeric * 2 != int(numeric * 2):
        raise ValueError("band must be between 0 and 9 in 0.5 increments")
    if numeric.is_integer():
        return str(int(numeric))
    return str(numeric)
