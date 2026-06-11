from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.content.question_text import is_placeholder_question_text
from app.mcp.security import McpToolContext, authorize_tool_call, record_tool_execution
from app.rag.ingestion.question_bank_indexer import QuestionBankIndexer
from app.rag.llamaindex_service import KnowledgeSearchResult


QUESTION_BANK_READ_SCOPE = "question_bank:read"


class McpSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    chunk_id: str
    source: str = "knowledge_chunks"


class QuestionSearchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    part: int = Field(ge=1, le=3)
    topic: str
    season_id: str
    title: str
    content: str
    score: float = Field(ge=0, le=1)
    has_cue_card: bool = False
    source_ref: McpSourceRef


class SearchQuestionsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "search_questions"
    user_id: str
    session_id: str
    results: list[QuestionSearchItem]


class CueCardResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "get_cue_card"
    user_id: str
    session_id: str
    question_id: str
    cue_card_id: str | None = None
    prompt: str
    bullet_points: list[str] = Field(default_factory=list)
    preparation_seconds: int = Field(ge=0, le=120)
    speaking_seconds: int = Field(ge=60, le=240)
    source_ref: McpSourceRef


class FollowupTemplateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    followup_id: str | None = None
    part: int = Field(ge=1, le=3)
    text: str
    trigger_hint: str | None = None
    sort_order: int = Field(ge=0)
    source_ref: McpSourceRef


class FollowupTemplatesResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "get_followup_templates"
    user_id: str
    session_id: str
    question_id: str
    followups: list[FollowupTemplateItem]


class QuestionBankMcpTools:
    def __init__(self, indexer: QuestionBankIndexer) -> None:
        self.indexer = indexer

    def search_questions(
        self,
        context: McpToolContext,
        *,
        query: str,
        active_season_id: str | None = None,
        season_id: str | None = None,
        part: int | None = None,
        topic: str | None = None,
        topic_id: str | None = None,
        top_k: int = 5,
    ) -> SearchQuestionsResult:
        authorize_tool_call(context, tool_name="search_questions", required_scopes=[QUESTION_BANK_READ_SCOPE])
        query = _required_text(query, field_name="query")
        if top_k <= 0 or top_k > 20:
            raise ValueError("top_k must be between 1 and 20")

        arguments = {
            "query": query,
            "active_season_id": active_season_id,
            "season_id": season_id,
            "part": part,
            "topic": topic,
            "topic_id": topic_id,
            "top_k": top_k,
        }
        started = perf_counter()
        try:
            filters = {"topic_id": topic_id.strip()} if topic_id and topic_id.strip() else None
            matches = self.indexer.search_questions(
                query,
                active_season_id=active_season_id,
                season_id=season_id,
                part=part,
                topic=topic,
                filters=filters,
                top_k=top_k,
            )
            result = SearchQuestionsResult(
                user_id=context.user_id,
                session_id=context.session_id,
                results=[item for match in matches if (item := _search_item_from_match(match)) is not None],
            )
        except Exception as exc:
            record_tool_execution(
                context,
                tool_name="search_questions",
                required_scopes=[QUESTION_BANK_READ_SCOPE],
                status="failed",
                arguments=arguments,
                output_payload={"error": str(exc)},
                reason=str(getattr(exc, "code", exc.__class__.__name__)),
                latency_ms=max(0, int((perf_counter() - started) * 1000)),
            )
            raise
        record_tool_execution(
            context,
            tool_name="search_questions",
            required_scopes=[QUESTION_BANK_READ_SCOPE],
            status="completed",
            arguments=arguments,
            output_payload=result.model_dump(mode="json", exclude_none=True),
            latency_ms=max(0, int((perf_counter() - started) * 1000)),
        )
        return result

    def get_cue_card(self, context: McpToolContext, *, question_id: str) -> CueCardResult | None:
        authorize_tool_call(context, tool_name="get_cue_card", required_scopes=[QUESTION_BANK_READ_SCOPE])
        question_id = _required_text(question_id, field_name="question_id")
        arguments = {"question_id": question_id}
        started = perf_counter()
        try:
            match = self._get_question_match(question_id)
            if match is None or not match.metadata.get("has_cue_card"):
                result = None
            else:
                result = CueCardResult(
                    user_id=context.user_id,
                    session_id=context.session_id,
                    question_id=question_id,
                    cue_card_id=_optional_text(match.metadata.get("cue_card_id")),
                    prompt=_required_text(match.metadata.get("cue_card_prompt"), field_name="cue_card_prompt"),
                    bullet_points=_string_list(match.metadata.get("cue_card_bullet_points")),
                    preparation_seconds=int(match.metadata.get("cue_card_preparation_seconds") or 60),
                    speaking_seconds=int(match.metadata.get("cue_card_speaking_seconds") or 120),
                    source_ref=_source_ref(match),
                )
        except Exception as exc:
            record_tool_execution(
                context,
                tool_name="get_cue_card",
                required_scopes=[QUESTION_BANK_READ_SCOPE],
                status="failed",
                arguments=arguments,
                output_payload={"error": str(exc)},
                reason=str(getattr(exc, "code", exc.__class__.__name__)),
                latency_ms=max(0, int((perf_counter() - started) * 1000)),
            )
            raise
        record_tool_execution(
            context,
            tool_name="get_cue_card",
            required_scopes=[QUESTION_BANK_READ_SCOPE],
            status="completed",
            arguments=arguments,
            output_payload=result.model_dump(mode="json", exclude_none=True) if result is not None else None,
            latency_ms=max(0, int((perf_counter() - started) * 1000)),
        )
        return result

    def get_followup_templates(
        self,
        context: McpToolContext,
        *,
        question_id: str,
        part: int | None = None,
    ) -> FollowupTemplatesResult:
        authorize_tool_call(context, tool_name="get_followup_templates", required_scopes=[QUESTION_BANK_READ_SCOPE])
        question_id = _required_text(question_id, field_name="question_id")
        if part is not None and part not in {1, 2, 3}:
            raise ValueError("part must be 1, 2, or 3")
        arguments = {"question_id": question_id, "part": part}
        started = perf_counter()
        try:
            match = self._get_question_match(question_id)

            followups: list[FollowupTemplateItem] = []
            if match is not None:
                for raw in _mapping_list(match.metadata.get("followup_templates")):
                    followup_part = int(raw.get("part") or 3)
                    if part is not None and followup_part != part:
                        continue
                    followup_text = _required_text(raw.get("text"), field_name="followup.text")
                    if is_placeholder_question_text(followup_text):
                        continue
                    followups.append(
                        FollowupTemplateItem(
                            followup_id=_optional_text(raw.get("followup_id")),
                            part=followup_part,
                            text=followup_text,
                            trigger_hint=_optional_text(raw.get("trigger_hint")),
                            sort_order=int(raw.get("sort_order") or 0),
                            source_ref=_source_ref(match),
                        )
                    )

            result = FollowupTemplatesResult(
                user_id=context.user_id,
                session_id=context.session_id,
                question_id=question_id,
                followups=followups,
            )
        except Exception as exc:
            record_tool_execution(
                context,
                tool_name="get_followup_templates",
                required_scopes=[QUESTION_BANK_READ_SCOPE],
                status="failed",
                arguments=arguments,
                output_payload={"error": str(exc)},
                reason=str(getattr(exc, "code", exc.__class__.__name__)),
                latency_ms=max(0, int((perf_counter() - started) * 1000)),
            )
            raise
        record_tool_execution(
            context,
            tool_name="get_followup_templates",
            required_scopes=[QUESTION_BANK_READ_SCOPE],
            status="completed",
            arguments=arguments,
            output_payload=result.model_dump(mode="json", exclude_none=True),
            latency_ms=max(0, int((perf_counter() - started) * 1000)),
        )
        return result

    def _get_question_match(self, question_id: str) -> KnowledgeSearchResult | None:
        matches = self.indexer.search_questions(
            question_id,
            top_k=1,
            filters={"question_id": question_id},
        )
        return matches[0] if matches else None


def _search_item_from_match(match: KnowledgeSearchResult) -> QuestionSearchItem | None:
    metadata = match.metadata
    item = QuestionSearchItem(
        question_id=_required_text(metadata.get("question_id"), field_name="question_id"),
        part=int(metadata.get("part") or 0),
        topic=_required_text(metadata.get("topic"), field_name="topic"),
        season_id=_required_text(metadata.get("season_id"), field_name="season_id"),
        title=match.title,
        content=match.content,
        score=match.score,
        has_cue_card=bool(metadata.get("has_cue_card")),
        source_ref=_source_ref(match),
    )
    if is_placeholder_question_text(_extract_primary_question_text(item.content)):
        return None
    return item


def _source_ref(match: KnowledgeSearchResult) -> McpSourceRef:
    return McpSourceRef(doc_id=match.doc_id, chunk_id=match.chunk_id, source=match.source)


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(item).strip() for item in value if str(item).strip()]


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


def _extract_primary_question_text(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("question:"):
            return stripped.split(":", 1)[1].strip()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return content.strip()
