from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.rag.chunk_schema import AllowedUsage, PrivacyLevel
from app.rag.llamaindex_service import (
    KnowledgeDocument,
    KnowledgeIngestResult,
    KnowledgeSearchResult,
    LlamaIndexKnowledgeService,
    MetadataValue,
    load_psycopg,
)


DEFAULT_ALLOWED_USAGE: list[AllowedUsage] = ["question_personalization", "feedback_personalization"]


class UserProfileFactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str | None = None
    user_id: str = Field(min_length=1)
    questionnaire_id: str | None = None
    topic: str | None = None
    fact_key: str = Field(min_length=1)
    fact_value: str = Field(min_length=1)
    privacy_level: PrivacyLevel = "normal"
    allowed_usage: list[AllowedUsage] = Field(default_factory=lambda: list(DEFAULT_ALLOWED_USAGE))
    is_excluded: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        normalized = dict(data)
        if "fact_id" not in normalized and "id" in normalized:
            normalized["fact_id"] = normalized["id"]
        if "fact_key" not in normalized and "key" in normalized:
            normalized["fact_key"] = normalized["key"]
        if "fact_value" not in normalized and "value" in normalized:
            normalized["fact_value"] = normalized["value"]
        return normalized

    @field_validator("user_id", "fact_key", "fact_value", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Any) -> str:
        return _required_text(value)

    @field_validator("fact_id", "questionnaire_id", "topic", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("allowed_usage", mode="before")
    @classmethod
    def normalize_allowed_usage(cls, value: Any) -> list[str]:
        if value is None:
            value = DEFAULT_ALLOWED_USAGE
        if isinstance(value, str):
            value = [value]
        normalized: list[str] = []
        for item in value:
            text = _required_text(item)
            if text not in normalized:
                normalized.append(text)
        return normalized


class SkippedUserFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    reason: str


class UserProfileIndexResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_count: int = Field(ge=0)
    indexed_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    deleted_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    doc_ids: list[str] = Field(default_factory=list)
    skipped_facts: list[SkippedUserFact] = Field(default_factory=list)


class UserProfileSource(Protocol):
    def list_user_facts(
        self,
        user_id: str,
        *,
        include_excluded: bool = True,
        include_private: bool = True,
        topic: str | None = None,
        allowed_usage: Sequence[AllowedUsage] | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> Sequence[UserProfileFactRecord | Mapping[str, Any]]:
        ...


class UserProfileIndexer:
    def __init__(self, knowledge_service: LlamaIndexKnowledgeService) -> None:
        self.knowledge_service = knowledge_service

    def index_records(
        self,
        records: Sequence[UserProfileFactRecord | Mapping[str, Any]],
        *,
        user_id: str | None = None,
        topic: str | None = None,
        allowed_usage: Sequence[AllowedUsage] | None = None,
        include_private: bool = False,
        replace_user_index: bool = False,
    ) -> UserProfileIndexResult:
        normalized_records = [self._normalize_record(record) for record in records]
        target_user_id = normalize_optional_text(user_id) or infer_single_user_id(normalized_records)
        normalized_topic = normalize_optional_text(topic)
        normalized_usage = normalize_allowed_usage_filter(allowed_usage)

        if replace_user_index and not target_user_id:
            raise ValueError("replace_user_index requires user_id or records from one user")

        deleted_count = 0
        if replace_user_index and target_user_id:
            deleted_count = self.knowledge_service.delete_by_filters(
                {"doc_type": "user_profile", "owner_user_id": target_user_id}
            )

        documents: list[KnowledgeDocument] = []
        skipped: list[SkippedUserFact] = []
        skipped_doc_ids: list[str] = []
        for record in normalized_records:
            reason = skip_reason(
                record,
                target_user_id=target_user_id,
                topic=normalized_topic,
                allowed_usage=normalized_usage,
                include_private=include_private,
            )
            if reason:
                skipped.append(SkippedUserFact(fact_id=record.fact_id or stable_fact_key(record), reason=reason))
                if not replace_user_index:
                    skipped_doc_ids.append(stable_fact_doc_id(record))
                continue
            documents.append(build_user_fact_document(record))

        if skipped_doc_ids:
            deleted_count += self.knowledge_service.delete_documents(skipped_doc_ids)

        ingest_results: list[KnowledgeIngestResult] = []
        if documents:
            ingest_results = self.knowledge_service.ingest_documents(documents)

        return UserProfileIndexResult(
            requested_count=len(records),
            indexed_count=len(ingest_results),
            skipped_count=len(skipped),
            deleted_count=deleted_count,
            chunk_count=sum(result.chunk_count for result in ingest_results),
            doc_ids=[result.doc_id for result in ingest_results],
            skipped_facts=skipped,
        )

    def sync_from_source(
        self,
        source: UserProfileSource,
        *,
        user_id: str,
        topic: str | None = None,
        allowed_usage: Sequence[AllowedUsage] | None = None,
        include_private: bool = False,
        replace_user_index: bool = True,
        limit: int = 1000,
        offset: int = 0,
    ) -> UserProfileIndexResult:
        records = source.list_user_facts(
            user_id,
            include_excluded=True,
            include_private=True,
            topic=topic,
            allowed_usage=allowed_usage,
            limit=limit,
            offset=offset,
        )
        return self.index_records(
            records,
            user_id=user_id,
            topic=topic,
            allowed_usage=allowed_usage,
            include_private=include_private,
            replace_user_index=replace_user_index,
        )

    def search_user_facts(
        self,
        query: str,
        *,
        user_id: str,
        topic: str | None = None,
        allowed_usage: Sequence[AllowedUsage] | None = None,
        include_private: bool = False,
        top_k: int = 5,
        filters: Mapping[str, MetadataValue] | None = None,
    ) -> list[KnowledgeSearchResult]:
        merged_filters: dict[str, MetadataValue] = {
            "doc_type": "user_profile",
            "owner_user_id": _required_text(user_id),
        }
        if topic:
            merged_filters["topic"] = topic.strip()
        normalized_usage = normalize_allowed_usage_filter(allowed_usage)
        if normalized_usage:
            merged_filters["allowed_usage"] = normalized_usage
        if not include_private:
            merged_filters["privacy_level"] = ["normal", "sensitive"]
        merged_filters.update(dict(filters or {}))
        return self.knowledge_service.retrieve(query, top_k=top_k, filters=merged_filters)

    @staticmethod
    def _normalize_record(record: UserProfileFactRecord | Mapping[str, Any]) -> UserProfileFactRecord:
        if isinstance(record, UserProfileFactRecord):
            return record
        return UserProfileFactRecord.model_validate(dict(record))


class PostgresUserProfileSource:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self.database_url = database_url

    def list_user_facts(
        self,
        user_id: str,
        *,
        include_excluded: bool = True,
        include_private: bool = True,
        topic: str | None = None,
        allowed_usage: Sequence[AllowedUsage] | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[UserProfileFactRecord]:
        psycopg, _ = load_psycopg()
        sql, params = build_user_profile_select_sql(
            user_id=user_id,
            include_excluded=include_excluded,
            include_private=include_private,
            topic=topic,
            allowed_usage=allowed_usage,
            limit=limit,
            offset=offset,
        )
        with psycopg.connect(self.database_url) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [record_from_pg_row(row) for row in rows]


def build_user_fact_document(record: UserProfileFactRecord) -> KnowledgeDocument:
    doc_id = stable_fact_doc_id(record)
    metadata: dict[str, Any] = {
        **record.metadata,
        "fact_id": record.fact_id,
        "fact_key": record.fact_key,
        "privacy_level": record.privacy_level,
        "allowed_usage": record.allowed_usage,
        "fact_value_hash": hash_fact_value(record.fact_value),
    }
    if record.topic:
        metadata["topic"] = record.topic
    if record.questionnaire_id:
        metadata["questionnaire_id"] = record.questionnaire_id

    return KnowledgeDocument(
        doc_id=doc_id,
        doc_type="user_profile",
        title=build_user_fact_title(record),
        content=build_user_fact_content(record),
        metadata=metadata,
        source_id=doc_id,
        owner_user_id=record.user_id,
        status="active",
    )


def build_user_fact_title(record: UserProfileFactRecord) -> str:
    if record.topic:
        return f"User fact {record.topic}: {record.fact_key}"
    return f"User fact: {record.fact_key}"


def build_user_fact_content(record: UserProfileFactRecord) -> str:
    sections = ["User background fact"]
    if record.topic:
        sections.append(f"Topic: {record.topic}")
    sections.extend(
        [
            f"Fact key: {record.fact_key}",
            f"Fact value: {record.fact_value}",
            f"Allowed usage: {', '.join(record.allowed_usage)}",
            f"Privacy level: {record.privacy_level}",
        ]
    )
    return "\n".join(sections)


def skip_reason(
    record: UserProfileFactRecord,
    *,
    target_user_id: str | None,
    topic: str | None,
    allowed_usage: Sequence[AllowedUsage] | None,
    include_private: bool,
) -> str | None:
    if target_user_id and record.user_id != target_user_id:
        return "user_not_selected"
    if record.is_excluded:
        return "fact_excluded"
    if record.privacy_level == "private" and not include_private:
        return "fact_private"
    if topic and record.topic != topic:
        return "topic_not_selected"
    if allowed_usage and not set(record.allowed_usage).intersection(allowed_usage):
        return "usage_not_allowed"
    return None


def build_user_profile_select_sql(
    *,
    user_id: str,
    include_excluded: bool,
    include_private: bool,
    topic: str | None,
    allowed_usage: Sequence[AllowedUsage] | None,
    limit: int,
    offset: int,
) -> tuple[str, list[Any]]:
    if limit <= 0 or limit > 5000:
        raise ValueError("limit must be between 1 and 5000")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    params: list[Any] = [user_id, user_id]
    conditions = ["bf.user_id = %s::uuid"]
    if not include_excluded:
        conditions.append("bf.is_excluded = false")
    if not include_private:
        conditions.append("bf.privacy_level <> 'private'")
    normalized_topic = normalize_optional_text(topic)
    if normalized_topic:
        params.append(normalized_topic)
        conditions.append("bf.topic = %s")
    normalized_usage = normalize_allowed_usage_filter(allowed_usage)
    if normalized_usage:
        params.append(normalized_usage)
        conditions.append("bf.allowed_usage && %s::text[]")

    params.extend([limit, offset])
    sql = f"""
        with latest_questionnaire as (
            select id
            from background_questionnaires
            where user_id = %s::uuid
            order by created_at desc
            limit 1
        )
        select
            bf.id::text as fact_id,
            bf.user_id::text as user_id,
            bf.questionnaire_id::text as questionnaire_id,
            bf.topic,
            bf.fact_key,
            bf.fact_value,
            bf.privacy_level,
            to_json(bf.allowed_usage)::text as allowed_usage,
            bf.is_excluded
        from background_facts bf
        join latest_questionnaire lq on lq.id = bf.questionnaire_id
        where {" and ".join(conditions)}
        order by bf.created_at asc
        limit %s offset %s
    """
    return sql, params


def record_from_pg_row(row: Sequence[Any]) -> UserProfileFactRecord:
    return UserProfileFactRecord(
        fact_id=row[0],
        user_id=row[1],
        questionnaire_id=row[2],
        topic=row[3],
        fact_key=row[4],
        fact_value=row[5],
        privacy_level=row[6],
        allowed_usage=json.loads(row[7] or "[]"),
        is_excluded=row[8],
    )


def stable_fact_doc_id(record: UserProfileFactRecord) -> str:
    if record.fact_id:
        return stable_uuid(record.fact_id)
    return stable_uuid(stable_fact_key(record))


def stable_fact_key(record: UserProfileFactRecord) -> str:
    parts = [
        "user-profile",
        record.user_id,
        record.questionnaire_id or "latest",
        record.topic or "general",
        record.fact_key,
    ]
    return ":".join(parts)


def stable_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, f"ielts-speaking:{value}"))


def hash_fact_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def infer_single_user_id(records: Sequence[UserProfileFactRecord]) -> str | None:
    user_ids = {record.user_id for record in records}
    if len(user_ids) > 1:
        raise ValueError("records contain multiple users; pass user_id explicitly")
    return next(iter(user_ids), None)


def normalize_allowed_usage_filter(values: Sequence[AllowedUsage] | None) -> list[AllowedUsage]:
    if values is None:
        return []
    normalized: list[AllowedUsage] = []
    for item in values:
        text = _required_text(item)
        if text not in normalized:
            normalized.append(text)  # type: ignore[arg-type]
    return normalized


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: Any) -> str:
    if value is None:
        raise ValueError("required text is missing")
    text = str(value).strip()
    if not text:
        raise ValueError("required text is empty")
    return text
