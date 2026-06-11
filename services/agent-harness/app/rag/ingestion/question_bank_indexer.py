from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.content.question_text import is_placeholder_question_text
from app.rag.chunk_schema import ContentStatus, QuestionSourceType
from app.rag.llamaindex_service import (
    KnowledgeDocument,
    KnowledgeIngestResult,
    KnowledgeSearchResult,
    LlamaIndexKnowledgeService,
    MetadataValue,
    load_psycopg,
)


class QuestionCueCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cue_card_id: str | None = None
    prompt: str = Field(min_length=1)
    bullet_points: list[str] = Field(default_factory=list)
    preparation_seconds: int = Field(default=60, ge=0, le=120)
    speaking_seconds: int = Field(default=120, ge=60, le=240)

    @field_validator("prompt", mode="before")
    @classmethod
    def normalize_prompt(cls, value: Any) -> str:
        return _required_text(value)

    @field_validator("bullet_points", mode="before")
    @classmethod
    def normalize_bullet_points(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [_required_text(item) for item in value if str(item).strip()]


class QuestionFollowup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    followup_id: str | None = None
    part: int = Field(ge=1, le=3)
    text: str = Field(min_length=1)
    trigger_hint: str | None = None
    sort_order: int = Field(default=0, ge=0)
    review_status: ContentStatus = "active"

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return _required_text(value)


class QuestionBankRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    season_id: str = Field(min_length=1)
    part: int = Field(ge=1, le=3)
    text: str = Field(min_length=1)
    topic: str | None = None
    topic_id: str | None = None
    source_type: QuestionSourceType = "original"
    review_status: ContentStatus = "active"
    difficulty: int | None = Field(default=None, ge=1, le=5)
    license: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    cue_card: QuestionCueCard | None = None
    followup_templates: list[QuestionFollowup] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        normalized = dict(data)
        if "question_id" not in normalized and "id" in normalized:
            normalized["question_id"] = normalized["id"]
        if "followup_templates" not in normalized and "followups" in normalized:
            normalized["followup_templates"] = normalized["followups"]
        return normalized

    @model_validator(mode="after")
    def fill_topic_from_metadata(self) -> "QuestionBankRecord":
        if self.topic:
            self.topic = self.topic.strip()
            return self

        for key in ("topic", "topic_slug", "topic_name"):
            value = self.metadata.get(key)
            if value and str(value).strip():
                self.topic = str(value).strip()
                return self

        if self.topic_id:
            self.topic = self.topic_id
            return self

        raise ValueError("question_bank record requires topic, topic_id, or metadata.topic")

    @field_validator("question_id", "season_id", "text", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Any) -> str:
        return _required_text(value)

    @field_validator("topic", "topic_id", "license", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class SkippedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    reason: str


class QuestionBankIndexResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_count: int = Field(ge=0)
    indexed_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    doc_ids: list[str] = Field(default_factory=list)
    skipped_questions: list[SkippedQuestion] = Field(default_factory=list)


class QuestionBankSource(Protocol):
    def list_questions(
        self,
        *,
        active_season_only: bool = True,
        season_id: str | None = None,
        part: int | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> Sequence[QuestionBankRecord | Mapping[str, Any]]:
        ...


class QuestionBankIndexer:
    def __init__(self, knowledge_service: LlamaIndexKnowledgeService) -> None:
        self.knowledge_service = knowledge_service

    def index_records(
        self,
        records: Sequence[QuestionBankRecord | Mapping[str, Any]],
        *,
        active_season_id: str | None = None,
        season_id: str | None = None,
        part: int | None = None,
        only_active: bool = True,
    ) -> QuestionBankIndexResult:
        active_season_id = _normalize_optional_filter(active_season_id)
        season_id = _normalize_optional_filter(season_id)
        if active_season_id and season_id and active_season_id != season_id:
            raise ValueError("active_season_id and season_id cannot point to different seasons")
        target_season_id = season_id or active_season_id

        documents: list[KnowledgeDocument] = []
        skipped: list[SkippedQuestion] = []
        normalized_records = [self._normalize_record(record) for record in records]
        for record in normalized_records:
            reason = skip_reason(record, target_season_id=target_season_id, part=part, only_active=only_active)
            if reason:
                skipped.append(SkippedQuestion(question_id=record.question_id, reason=reason))
                continue
            documents.append(build_question_document(record, active_season_id=active_season_id))

        ingest_results: list[KnowledgeIngestResult] = []
        if documents:
            ingest_results = self.knowledge_service.ingest_documents(documents)

        return QuestionBankIndexResult(
            requested_count=len(records),
            indexed_count=len(ingest_results),
            skipped_count=len(skipped),
            chunk_count=sum(result.chunk_count for result in ingest_results),
            doc_ids=[result.doc_id for result in ingest_results],
            skipped_questions=skipped,
        )

    def sync_from_source(
        self,
        source: QuestionBankSource,
        *,
        active_season_id: str | None = None,
        season_id: str | None = None,
        part: int | None = None,
        only_active: bool = True,
        limit: int = 1000,
        offset: int = 0,
    ) -> QuestionBankIndexResult:
        records = source.list_questions(
            active_season_only=active_season_id is not None and season_id is None,
            season_id=season_id or active_season_id,
            part=part,
            limit=limit,
            offset=offset,
        )
        return self.index_records(
            records,
            active_season_id=active_season_id,
            season_id=season_id,
            part=part,
            only_active=only_active,
        )

    def search_questions(
        self,
        query: str,
        *,
        active_season_id: str | None = None,
        season_id: str | None = None,
        part: int | None = None,
        topic: str | None = None,
        top_k: int = 5,
        filters: Mapping[str, MetadataValue] | None = None,
    ) -> list[KnowledgeSearchResult]:
        active_season_id = _normalize_optional_filter(active_season_id)
        season_id = _normalize_optional_filter(season_id)
        if active_season_id and season_id and active_season_id != season_id:
            raise ValueError("active_season_id and season_id cannot point to different seasons")

        merged_filters: dict[str, MetadataValue] = {"doc_type": "question_bank"}
        if season_id or active_season_id:
            merged_filters["season_id"] = season_id or active_season_id
        if part is not None:
            if part not in {1, 2, 3}:
                raise ValueError("part must be 1, 2, or 3")
            merged_filters["part"] = str(part)
        if topic:
            merged_filters["topic"] = topic.strip()
        merged_filters.update(dict(filters or {}))
        return self.knowledge_service.retrieve(query, top_k=top_k, filters=merged_filters)

    @staticmethod
    def _normalize_record(record: QuestionBankRecord | Mapping[str, Any]) -> QuestionBankRecord:
        if isinstance(record, QuestionBankRecord):
            return record
        return QuestionBankRecord.model_validate(dict(record))


class PostgresQuestionBankSource:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self.database_url = database_url

    def list_questions(
        self,
        *,
        active_season_only: bool = True,
        season_id: str | None = None,
        part: int | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[QuestionBankRecord]:
        psycopg, _ = load_psycopg()
        sql, params = build_question_bank_select_sql(
            active_season_only=active_season_only,
            season_id=season_id,
            part=part,
            limit=limit,
            offset=offset,
        )
        with psycopg.connect(self.database_url) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [record_from_pg_row(row) for row in rows]


def build_question_document(record: QuestionBankRecord, *, active_season_id: str | None = None) -> KnowledgeDocument:
    metadata: dict[str, Any] = {
        **record.metadata,
        "season_id": record.season_id,
        "part": str(record.part),
        "topic": record.topic,
        "source_type": record.source_type,
        "question_id": record.question_id,
        "review_status": record.review_status,
    }
    if record.topic_id:
        metadata["topic_id"] = record.topic_id
    if record.difficulty is not None:
        metadata["difficulty"] = record.difficulty
    if record.license:
        metadata["license"] = record.license
    if record.cue_card:
        metadata["cue_card_id"] = record.cue_card.cue_card_id
        metadata["has_cue_card"] = True
        metadata["cue_card_prompt"] = record.cue_card.prompt
        metadata["cue_card_bullet_points"] = record.cue_card.bullet_points
        metadata["cue_card_preparation_seconds"] = record.cue_card.preparation_seconds
        metadata["cue_card_speaking_seconds"] = record.cue_card.speaking_seconds
    if record.followup_templates:
        active_followups = [
            followup
            for followup in record.followup_templates
            if followup.review_status == "active" and not is_placeholder_question_text(followup.text)
        ]
        metadata["followup_count"] = len(active_followups)
        if active_followups:
            metadata["followup_templates"] = [
                {
                    "followup_id": followup.followup_id,
                    "part": followup.part,
                    "text": followup.text,
                    "trigger_hint": followup.trigger_hint,
                    "sort_order": followup.sort_order,
                }
                for followup in sorted(active_followups, key=lambda item: item.sort_order)
            ]
    if active_season_id is not None:
        metadata["is_active_season"] = record.season_id == active_season_id

    return KnowledgeDocument(
        doc_id=record.question_id,
        doc_type="question_bank",
        title=build_question_title(record),
        content=build_question_content(record),
        metadata=metadata,
        source_id=record.question_id,
        status=record.review_status,
    )


def build_question_title(record: QuestionBankRecord) -> str:
    text = record.text.strip()
    if len(text) > 80:
        text = text[:77].rstrip() + "..."
    return f"Part {record.part} {record.topic}: {text}"


def build_question_content(record: QuestionBankRecord) -> str:
    sections = [f"Question: {record.text}"]
    if record.cue_card:
        sections.append(f"Cue card: {record.cue_card.prompt}")
        if record.cue_card.bullet_points:
            bullet_text = "\n".join(f"- {point}" for point in record.cue_card.bullet_points)
            sections.append(f"Cue card bullet points:\n{bullet_text}")
        sections.append(
            "Cue card timing: "
            f"{record.cue_card.preparation_seconds}s preparation, {record.cue_card.speaking_seconds}s speaking"
        )

    active_followups = [
        followup
        for followup in record.followup_templates
        if followup.review_status == "active" and not is_placeholder_question_text(followup.text)
    ]
    if active_followups:
        followup_text = "\n".join(
            f"- {followup.text}" + (f" ({followup.trigger_hint})" if followup.trigger_hint else "")
            for followup in sorted(active_followups, key=lambda item: item.sort_order)
        )
        sections.append(f"Follow-up questions:\n{followup_text}")
    return "\n\n".join(sections)


def skip_reason(
    record: QuestionBankRecord,
    *,
    target_season_id: str | None,
    part: int | None,
    only_active: bool,
) -> str | None:
    if only_active and record.review_status != "active":
        return "question_not_active"
    if target_season_id and record.season_id != target_season_id:
        return "season_not_selected"
    if part is not None and record.part != part:
        return "part_not_selected"
    if is_placeholder_question_text(record.text):
        return "placeholder_question_text"
    return None


def build_question_bank_select_sql(
    *,
    active_season_only: bool,
    season_id: str | None,
    part: int | None,
    limit: int,
    offset: int,
) -> tuple[str, list[Any]]:
    if limit <= 0 or limit > 5000:
        raise ValueError("limit must be between 1 and 5000")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if part is not None and part not in {1, 2, 3}:
        raise ValueError("part must be 1, 2, or 3")

    params: list[Any] = []
    conditions = [
        "q.deleted_at is null",
        "q.review_status = 'active'",
        "s.deleted_at is null",
        "s.status = 'active'",
    ]
    if active_season_only:
        conditions.append("s.is_active = true")
    if season_id:
        params.append(season_id)
        conditions.append(f"q.season_id = %s::uuid")
    if part is not None:
        params.append(part)
        conditions.append("q.part = %s")

    params.extend([limit, offset])
    sql = f"""
        select
            q.id::text as question_id,
            q.season_id::text as season_id,
            q.topic_id::text as topic_id,
            q.part,
            q.text,
            q.difficulty,
            q.source_type::text,
            q.license,
            q.review_status::text,
            q.metadata::text,
            coalesce(t.slug, t.name, q.topic_id::text) as topic,
            cc.id::text as cue_card_id,
            cc.prompt as cue_card_prompt,
            coalesce(to_json(cc.bullet_points), '[]'::json)::text as cue_card_bullets,
            cc.preparation_seconds,
            cc.speaking_seconds,
            coalesce((
                select json_agg(
                    json_build_object(
                        'followup_id', ft.id::text,
                        'part', ft.part,
                        'text', ft.text,
                        'trigger_hint', ft.trigger_hint,
                        'sort_order', ft.sort_order,
                        'review_status', ft.review_status::text
                    )
                    order by ft.sort_order asc, ft.created_at asc
                )
                from followup_templates ft
                where ft.question_id = q.id
                  and ft.review_status = 'active'
            ), '[]'::json)::text as followups_json
        from questions q
        join seasons s on s.id = q.season_id
        left join topics t on t.id = q.topic_id and t.deleted_at is null
        left join cue_cards cc on cc.question_id = q.id
        where {" and ".join(conditions)}
        order by q.part asc, q.created_at desc
        limit %s offset %s
    """
    return sql, params


def record_from_pg_row(row: Sequence[Any]) -> QuestionBankRecord:
    cue_card = None
    if row[12]:
        cue_card = QuestionCueCard(
            cue_card_id=row[11],
            prompt=row[12],
            bullet_points=json.loads(row[13] or "[]"),
            preparation_seconds=row[14] or 60,
            speaking_seconds=row[15] or 120,
        )

    return QuestionBankRecord(
        question_id=row[0],
        season_id=row[1],
        topic_id=row[2],
        part=row[3],
        text=row[4],
        difficulty=row[5],
        source_type=row[6],
        license=row[7],
        review_status=row[8],
        metadata=json.loads(row[9] or "{}"),
        topic=row[10],
        cue_card=cue_card,
        followup_templates=json.loads(row[16] or "[]"),
    )


def _required_text(value: Any) -> str:
    if value is None:
        raise ValueError("required text is missing")
    text = str(value).strip()
    if not text:
        raise ValueError("required text is empty")
    return text


def _normalize_optional_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
