from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.rag.chunk_schema import ContentStatus, ScoringCriterion
from app.rag.llamaindex_service import (
    KnowledgeDocument,
    KnowledgeIngestResult,
    KnowledgeSearchResult,
    LlamaIndexKnowledgeService,
    MetadataValue,
)


RubricPolicyType = Literal["official_descriptor", "internal_policy", "anchor_example"]


class RubricRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_id: str | None = None
    criterion: ScoringCriterion
    band: str
    descriptor: str = Field(min_length=1)
    rubric_version: str = "ielts-speaking-rubric-v1"
    policy_type: RubricPolicyType = "official_descriptor"
    status: ContentStatus = "active"
    guidance: str | None = None
    anchor_sample_id: str | None = None
    anchor_answer_excerpt: str | None = None
    anchor_score_rationale: str | None = None
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        normalized = dict(data)
        if "rubric_id" not in normalized and "id" in normalized:
            normalized["rubric_id"] = normalized["id"]
        if normalized.get("anchor_sample_id") and "policy_type" not in normalized:
            normalized["policy_type"] = "anchor_example"
        return normalized

    @model_validator(mode="after")
    def fill_rubric_id(self) -> "RubricRecord":
        if self.rubric_id:
            self.rubric_id = self.rubric_id.strip()
            return self

        descriptor_hash = hashlib.sha256(self.descriptor.encode("utf-8")).hexdigest()[:10]
        parts = [
            "rubric",
            self.rubric_version,
            self.criterion,
            f"band-{self.band}",
            self.policy_type,
            self.anchor_sample_id or descriptor_hash,
        ]
        self.rubric_id = ":".join(parts)
        return self

    @field_validator("band", mode="before")
    @classmethod
    def normalize_band_field(cls, value: Any) -> str:
        return normalize_band(value)

    @field_validator("descriptor", "rubric_version", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Any) -> str:
        return _required_text(value)

    @field_validator("guidance", "anchor_sample_id", "anchor_answer_excerpt", "anchor_score_rationale", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("evidence", mode="before")
    @classmethod
    def normalize_evidence(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [_required_text(item) for item in value if str(item).strip()]


class SkippedRubricRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_id: str
    reason: str


class RubricIndexResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_count: int = Field(ge=0)
    indexed_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    doc_ids: list[str] = Field(default_factory=list)
    skipped_records: list[SkippedRubricRecord] = Field(default_factory=list)


class RubricIndexer:
    def __init__(self, knowledge_service: LlamaIndexKnowledgeService) -> None:
        self.knowledge_service = knowledge_service

    def index_records(
        self,
        records: Sequence[RubricRecord | Mapping[str, Any]],
        *,
        only_active: bool = True,
    ) -> RubricIndexResult:
        documents: list[KnowledgeDocument] = []
        skipped: list[SkippedRubricRecord] = []
        normalized_records = [self._normalize_record(record) for record in records]

        for record in normalized_records:
            if only_active and record.status != "active":
                skipped.append(SkippedRubricRecord(rubric_id=record.rubric_id or "", reason="rubric_not_active"))
                continue
            documents.append(build_rubric_document(record))

        ingest_results: list[KnowledgeIngestResult] = []
        if documents:
            ingest_results = self.knowledge_service.ingest_documents(documents)

        return RubricIndexResult(
            requested_count=len(records),
            indexed_count=len(ingest_results),
            skipped_count=len(skipped),
            chunk_count=sum(result.chunk_count for result in ingest_results),
            doc_ids=[result.doc_id for result in ingest_results],
            skipped_records=skipped,
        )

    def search_rubric(
        self,
        query: str,
        *,
        criterion: ScoringCriterion | None = None,
        min_band: str | int | float | None = None,
        max_band: str | int | float | None = None,
        bands: Sequence[str | int | float] | None = None,
        policy_types: Sequence[RubricPolicyType] | None = None,
        anchor_sample_id: str | None = None,
        top_k: int = 5,
        filters: Mapping[str, MetadataValue] | None = None,
    ) -> list[KnowledgeSearchResult]:
        merged_filters: dict[str, MetadataValue] = {"doc_type": "rubric"}
        if criterion:
            merged_filters["criterion"] = criterion
        band_filter = build_band_filter(min_band=min_band, max_band=max_band, bands=bands)
        if band_filter:
            merged_filters["band"] = band_filter
        if policy_types:
            merged_filters["policy_type"] = [str(item) for item in policy_types]
        if anchor_sample_id:
            merged_filters["anchor_sample_id"] = anchor_sample_id.strip()
        merged_filters.update(dict(filters or {}))
        return self.knowledge_service.retrieve(query, top_k=top_k, filters=merged_filters)

    @staticmethod
    def _normalize_record(record: RubricRecord | Mapping[str, Any]) -> RubricRecord:
        if isinstance(record, RubricRecord):
            return record
        return RubricRecord.model_validate(dict(record))


def build_rubric_document(record: RubricRecord) -> KnowledgeDocument:
    doc_id = stable_uuid(record.rubric_id or "")
    metadata: dict[str, Any] = {
        **record.metadata,
        "rubric_id": record.rubric_id,
        "criterion": record.criterion,
        "band": record.band,
        "descriptor": record.descriptor,
        "rubric_version": record.rubric_version,
        "policy_type": record.policy_type,
    }
    if record.guidance:
        metadata["has_guidance"] = True
    if record.anchor_sample_id:
        metadata["anchor_sample_id"] = record.anchor_sample_id

    return KnowledgeDocument(
        doc_id=doc_id,
        doc_type="rubric",
        title=build_rubric_title(record),
        content=build_rubric_content(record),
        metadata=metadata,
        source_id=doc_id,
        status=record.status,
    )


def build_rubric_title(record: RubricRecord) -> str:
    return f"{humanize_criterion(record.criterion)} Band {record.band} {humanize_policy_type(record.policy_type)}"


def build_rubric_content(record: RubricRecord) -> str:
    sections = [
        f"Criterion: {humanize_criterion(record.criterion)}",
        f"Band: {record.band}",
        f"Descriptor: {record.descriptor}",
        f"Policy type: {humanize_policy_type(record.policy_type)}",
    ]
    if record.guidance:
        sections.append(f"Internal guidance: {record.guidance}")
    if record.anchor_sample_id:
        sections.append(f"Anchor sample ID: {record.anchor_sample_id}")
    if record.anchor_answer_excerpt:
        sections.append(f"Anchor answer excerpt: {record.anchor_answer_excerpt}")
    if record.anchor_score_rationale:
        sections.append(f"Anchor score rationale: {record.anchor_score_rationale}")
    if record.evidence:
        evidence_text = "\n".join(f"- {item}" for item in record.evidence)
        sections.append(f"Evidence signals:\n{evidence_text}")
    return "\n\n".join(sections)


def build_band_filter(
    *,
    min_band: str | int | float | None = None,
    max_band: str | int | float | None = None,
    bands: Sequence[str | int | float] | None = None,
) -> list[str]:
    if bands is not None:
        return unique_preserving_order(normalize_band(item) for item in bands)
    if min_band is None and max_band is None:
        return []

    min_value = band_to_half_step(min_band if min_band is not None else 0)
    max_value = band_to_half_step(max_band if max_band is not None else 9)
    if min_value > max_value:
        raise ValueError("min_band must be <= max_band")
    return [format_half_step_band(value) for value in range(min_value, max_value + 1)]


def normalize_band(value: Any) -> str:
    half_step = band_to_half_step(value)
    return format_half_step_band(half_step)


def band_to_half_step(value: Any) -> int:
    text = _required_text(value)
    try:
        numeric = float(text)
    except ValueError as exc:
        raise ValueError("band must be numeric") from exc
    doubled = numeric * 2
    if numeric < 0 or numeric > 9 or doubled != int(doubled):
        raise ValueError("band must be between 0 and 9 in 0.5 increments")
    return int(doubled)


def format_half_step_band(value: int) -> str:
    numeric = value / 2
    if numeric.is_integer():
        return str(int(numeric))
    return str(numeric)


def stable_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, f"ielts-speaking:{value}"))


def unique_preserving_order(values: Sequence[str] | Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def humanize_criterion(criterion: str) -> str:
    return criterion.replace("_", " ").title()


def humanize_policy_type(policy_type: str) -> str:
    return policy_type.replace("_", " ")


def _required_text(value: Any) -> str:
    if value is None:
        raise ValueError("required text is missing")
    text = str(value).strip()
    if not text:
        raise ValueError("required text is empty")
    return text
