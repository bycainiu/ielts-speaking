from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.mcp.security import McpToolContext, authorize_tool_call
from app.rag.chunk_schema import ScoringCriterion
from app.rag.ingestion.rubric_indexer import RubricIndexer, RubricPolicyType
from app.rag.llamaindex_service import KnowledgeSearchResult


RUBRIC_READ_SCOPE = "rubric:read"


class RubricSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    chunk_id: str
    source: str = "knowledge_chunks"


class SpeakingBandDescriptorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_id: str | None = None
    criterion: ScoringCriterion
    band: str
    descriptor: str
    policy_type: RubricPolicyType | None = None
    rubric_version: str | None = None
    content: str
    score: float = Field(ge=0, le=1)
    source_ref: RubricSourceRef


class SpeakingBandDescriptorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "retrieve_speaking_band_descriptor"
    session_id: str
    descriptors: list[SpeakingBandDescriptorItem]


class AnchorSampleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_sample_id: str
    rubric_id: str | None = None
    criterion: ScoringCriterion
    band: str
    content: str
    score: float = Field(ge=0, le=1)
    source_ref: RubricSourceRef


class AnchorSamplesResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "get_anchor_samples"
    session_id: str
    anchors: list[AnchorSampleItem]


class RubricMcpTools:
    def __init__(self, indexer: RubricIndexer) -> None:
        self.indexer = indexer

    def retrieve_speaking_band_descriptor(
        self,
        context: McpToolContext,
        *,
        query: str,
        criterion: ScoringCriterion | None = None,
        min_band: str | int | float | None = None,
        max_band: str | int | float | None = None,
        bands: Sequence[str | int | float] | None = None,
        policy_types: Sequence[RubricPolicyType] | None = None,
        top_k: int = 5,
    ) -> SpeakingBandDescriptorResult:
        authorize_tool_call(
            context,
            tool_name="retrieve_speaking_band_descriptor",
            required_scopes=[RUBRIC_READ_SCOPE],
        )
        query = _required_text(query, field_name="query")
        _validate_top_k(top_k)
        matches = self.indexer.search_rubric(
            query,
            criterion=criterion,
            min_band=min_band,
            max_band=max_band,
            bands=bands,
            policy_types=policy_types,
            top_k=top_k,
        )
        return SpeakingBandDescriptorResult(
            session_id=context.session_id,
            descriptors=[_descriptor_from_match(match) for match in matches],
        )

    def get_anchor_samples(
        self,
        context: McpToolContext,
        *,
        query: str = "anchor sample speaking evidence",
        criterion: ScoringCriterion | None = None,
        anchor_sample_id: str | None = None,
        bands: Sequence[str | int | float] | None = None,
        top_k: int = 5,
    ) -> AnchorSamplesResult:
        authorize_tool_call(context, tool_name="get_anchor_samples", required_scopes=[RUBRIC_READ_SCOPE])
        query = _required_text(query, field_name="query")
        _validate_top_k(top_k)
        matches = self.indexer.search_rubric(
            query,
            criterion=criterion,
            bands=bands,
            policy_types=["anchor_example"],
            anchor_sample_id=anchor_sample_id,
            top_k=top_k,
        )
        return AnchorSamplesResult(
            session_id=context.session_id,
            anchors=[_anchor_from_match(match) for match in matches],
        )


def _descriptor_from_match(match: KnowledgeSearchResult) -> SpeakingBandDescriptorItem:
    metadata = match.metadata
    return SpeakingBandDescriptorItem(
        rubric_id=_optional_text(metadata.get("rubric_id")),
        criterion=_required_text(metadata.get("criterion"), field_name="criterion"),  # type: ignore[arg-type]
        band=_required_text(metadata.get("band"), field_name="band"),
        descriptor=_required_text(metadata.get("descriptor"), field_name="descriptor"),
        policy_type=_optional_text(metadata.get("policy_type")),  # type: ignore[arg-type]
        rubric_version=_optional_text(metadata.get("rubric_version")),
        content=match.content,
        score=match.score,
        source_ref=_source_ref(match),
    )


def _anchor_from_match(match: KnowledgeSearchResult) -> AnchorSampleItem:
    metadata = match.metadata
    return AnchorSampleItem(
        anchor_sample_id=_required_text(metadata.get("anchor_sample_id"), field_name="anchor_sample_id"),
        rubric_id=_optional_text(metadata.get("rubric_id")),
        criterion=_required_text(metadata.get("criterion"), field_name="criterion"),  # type: ignore[arg-type]
        band=_required_text(metadata.get("band"), field_name="band"),
        content=match.content,
        score=match.score,
        source_ref=_source_ref(match),
    )


def _source_ref(match: KnowledgeSearchResult) -> RubricSourceRef:
    return RubricSourceRef(doc_id=match.doc_id, chunk_id=match.chunk_id, source=match.source)


def _validate_top_k(top_k: int) -> None:
    if top_k <= 0 or top_k > 20:
        raise ValueError("top_k must be between 1 and 20")


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: Any, *, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"{field_name} is required")
    return text
