from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.mcp.security import McpToolContext, authorize_tool_call
from app.rag.chunk_schema import AllowedUsage, PrivacyLevel
from app.rag.ingestion.user_profile_indexer import UserProfileIndexer
from app.rag.llamaindex_service import KnowledgeSearchResult, load_psycopg


PROFILE_READ_SCOPE = "profile:read"


class ProfilePrivacySource(Protocol):
    def get_privacy_exclusions(self, user_id: str) -> Sequence[str]:
        ...


class ProfileFactItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str | None = None
    fact_key: str | None = None
    topic: str | None = None
    privacy_level: PrivacyLevel
    allowed_usage: list[AllowedUsage]
    content: str
    source_ref: dict[str, str]


class UserBackgroundSummaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "get_user_background_summary"
    user_id: str
    session_id: str
    summary_text: str
    facts: list[ProfileFactItem]


class PrivacyExclusionsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "get_privacy_exclusions"
    user_id: str
    session_id: str
    privacy_exclusions: list[str] = Field(default_factory=list)


class ProfileMcpTools:
    def __init__(
        self,
        indexer: UserProfileIndexer,
        *,
        privacy_source: ProfilePrivacySource | None = None,
    ) -> None:
        self.indexer = indexer
        self.privacy_source = privacy_source

    def get_user_background_summary(
        self,
        context: McpToolContext,
        *,
        query: str = "user background facts",
        topic: str | None = None,
        allowed_usage: Sequence[AllowedUsage] | None = None,
        top_k: int = 8,
    ) -> UserBackgroundSummaryResult:
        authorize_tool_call(context, tool_name="get_user_background_summary", required_scopes=[PROFILE_READ_SCOPE])
        query = _required_text(query, field_name="query")
        if top_k <= 0 or top_k > 20:
            raise ValueError("top_k must be between 1 and 20")

        matches = self.indexer.search_user_facts(
            query,
            user_id=context.user_id,
            topic=topic,
            allowed_usage=allowed_usage,
            include_private=False,
            top_k=top_k,
        )
        facts = [_fact_item_from_match(match) for match in matches]
        return UserBackgroundSummaryResult(
            user_id=context.user_id,
            session_id=context.session_id,
            summary_text=build_summary_text(facts),
            facts=facts,
        )

    def get_privacy_exclusions(self, context: McpToolContext) -> PrivacyExclusionsResult:
        authorize_tool_call(context, tool_name="get_privacy_exclusions", required_scopes=[PROFILE_READ_SCOPE])
        exclusions = []
        if self.privacy_source is not None:
            exclusions = normalize_privacy_exclusions(self.privacy_source.get_privacy_exclusions(context.user_id))
        return PrivacyExclusionsResult(
            user_id=context.user_id,
            session_id=context.session_id,
            privacy_exclusions=exclusions,
        )


class PostgresProfilePrivacySource:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self.database_url = database_url

    def get_privacy_exclusions(self, user_id: str) -> list[str]:
        psycopg, _ = load_psycopg()
        sql, params = build_privacy_exclusions_select_sql(user_id=user_id)
        with psycopg.connect(self.database_url) as conn:
            row = conn.execute(sql, params).fetchone()
        if row is None:
            return []
        return normalize_privacy_exclusions(json.loads(row[0] or "[]"))


def build_privacy_exclusions_select_sql(*, user_id: str) -> tuple[str, list[Any]]:
    user_id = _required_text(user_id, field_name="user_id")
    return (
        """
        select privacy_exclusions::text
        from background_questionnaires
        where user_id = %s::uuid
        order by created_at desc
        limit 1
        """,
        [user_id],
    )


def build_summary_text(facts: Sequence[ProfileFactItem]) -> str:
    if not facts:
        return "No allowed user background facts found."
    lines: list[str] = []
    for fact in facts:
        label_parts = [part for part in [fact.topic, fact.fact_key] if part]
        label = " / ".join(label_parts) or "background"
        lines.append(f"- {label}: {extract_fact_value(fact.content)}")
    return "\n".join(lines)


def extract_fact_value(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("Fact value:"):
            value = line.removeprefix("Fact value:").strip()
            if value:
                return value
    return content.strip()


def normalize_privacy_exclusions(values: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for item in values:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _fact_item_from_match(match: KnowledgeSearchResult) -> ProfileFactItem:
    metadata = match.metadata
    return ProfileFactItem(
        fact_id=_optional_text(metadata.get("fact_id")),
        fact_key=_optional_text(metadata.get("fact_key")),
        topic=_optional_text(metadata.get("topic")),
        privacy_level=_required_text(metadata.get("privacy_level"), field_name="privacy_level"),  # type: ignore[arg-type]
        allowed_usage=_allowed_usage(metadata.get("allowed_usage")),
        content=match.content,
        source_ref={"doc_id": match.doc_id, "chunk_id": match.chunk_id, "source": match.source},
    )


def _allowed_usage(value: Any) -> list[AllowedUsage]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("allowed_usage is required")
    return [_required_text(item, field_name="allowed_usage") for item in value]  # type: ignore[list-item]


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
