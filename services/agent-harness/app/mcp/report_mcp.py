from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.mcp.security import McpToolContext, authorize_tool_call
from app.rag.chunk_schema import ScoringCriterion
from app.rag.llamaindex_service import load_psycopg


REPORT_WRITE_SCOPE = "report:write"
IELTS_DISCLAIMER = "AI 模拟评分仅用于练习参考，不代表 IELTS 官方成绩。"
CriterionStatus = Literal["generating", "ready", "failed"]


class ReportEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class CriterionScoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    band: float = Field(ge=0, le=9)
    confidence: float = Field(ge=0, le=1)
    evidence: list[ReportEvidence] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    raw_output: dict[str, Any] = Field(default_factory=dict)

    @field_validator("band")
    @classmethod
    def validate_band_half_step(cls, value: float) -> float:
        if value * 2 != int(value * 2):
            raise ValueError("band must be in 0.5 increments")
        return value


class PracticePlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int = Field(ge=1, le=5)
    focus: str = Field(min_length=1)
    task: str = Field(min_length=1)
    due_on: str | None = None


class ScoreReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    report_id: str | None = None
    version: int = Field(default=1, ge=1)
    status: CriterionStatus = "ready"
    overall_band: float = Field(ge=0, le=9)
    confidence: float = Field(ge=0, le=1)
    criteria: dict[ScoringCriterion, CriterionScoreInput]
    reviewer_notes: list[str] = Field(default_factory=list)
    next_practice_plan: list[PracticePlanInput] = Field(default_factory=list)
    disclaimer: str = IELTS_DISCLAIMER
    model_run_id: str | None = None
    raw_report: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_required_criteria(self) -> "ScoreReportInput":
        required = {
            "fluency_coherence",
            "lexical_resource",
            "grammatical_range_accuracy",
            "pronunciation",
        }
        missing = required.difference(self.criteria)
        if missing:
            raise ValueError(f"criteria missing required items: {', '.join(sorted(missing))}")
        return self

    @field_validator("overall_band")
    @classmethod
    def validate_overall_band_half_step(cls, value: float) -> float:
        if value * 2 != int(value * 2):
            raise ValueError("overall_band must be in 0.5 increments")
        return value

    @field_validator("disclaimer")
    @classmethod
    def validate_disclaimer(cls, value: str) -> str:
        if value != IELTS_DISCLAIMER:
            raise ValueError("disclaimer must match IELTS practice disclaimer")
        return value


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    priority: int = Field(default=3, ge=1, le=5)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ReferenceAnswerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    turn_id: str | None = None
    band_target: float | None = Field(default=None, ge=0, le=9)
    skeleton: dict[str, Any] = Field(default_factory=dict)
    answer_text: str = Field(min_length=1)
    personalization_notes: str | None = None

    @field_validator("band_target")
    @classmethod
    def validate_band_target(cls, value: float | None) -> float | None:
        if value is not None and value * 2 != int(value * 2):
            raise ValueError("band_target must be in 0.5 increments")
        return value


class ScoreReportSaved(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "save_score_report"
    session_id: str
    report_id: str
    criterion_count: int = Field(ge=0)
    study_plan_count: int = Field(ge=0)
    audit_id: str | None = None


class FeedbackSaved(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "save_feedback"
    session_id: str
    feedback_id: str
    report_id: str
    audit_id: str | None = None


class ReferenceAnswerSaved(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "save_reference_answer"
    session_id: str
    reference_answer_id: str
    report_id: str
    audit_id: str | None = None


class ReportAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str | None = None
    tool_name: str
    user_id: str
    session_id: str
    request_id: str | None = None
    status: Literal["success", "error"] = "success"
    target_id: str | None = None


class ReportStore(Protocol):
    def save_score_report(self, *, user_id: str, report: ScoreReportInput) -> ScoreReportSaved:
        ...

    def save_feedback(self, *, user_id: str, feedback: FeedbackInput) -> FeedbackSaved:
        ...

    def save_reference_answer(self, *, user_id: str, reference_answer: ReferenceAnswerInput) -> ReferenceAnswerSaved:
        ...


class ReportAuditSink(Protocol):
    def record(self, record: ReportAuditRecord) -> ReportAuditRecord:
        ...


class InMemoryReportAuditSink:
    def __init__(self) -> None:
        self.records: list[ReportAuditRecord] = []

    def record(self, record: ReportAuditRecord) -> ReportAuditRecord:
        saved = record.model_copy(update={"audit_id": record.audit_id or f"audit_{len(self.records) + 1:04d}"})
        self.records.append(saved)
        return saved


class ReportMcpTools:
    def __init__(self, store: ReportStore, *, audit_sink: ReportAuditSink | None = None) -> None:
        self.store = store
        self.audit_sink = audit_sink or InMemoryReportAuditSink()

    def save_score_report(self, context: McpToolContext, *, report: ScoreReportInput | Mapping[str, Any]) -> ScoreReportSaved:
        authorize_tool_call(context, tool_name="save_score_report", required_scopes=[REPORT_WRITE_SCOPE])
        normalized = report if isinstance(report, ScoreReportInput) else ScoreReportInput.model_validate(dict(report))
        if normalized.session_id != context.session_id:
            raise ValueError("report.session_id must match context.session_id")
        saved = self.store.save_score_report(user_id=context.user_id, report=normalized)
        audit = self._audit(context, tool_name="save_score_report", target_id=saved.report_id)
        return saved.model_copy(update={"audit_id": audit.audit_id})

    def save_feedback(self, context: McpToolContext, *, feedback: FeedbackInput | Mapping[str, Any]) -> FeedbackSaved:
        authorize_tool_call(context, tool_name="save_feedback", required_scopes=[REPORT_WRITE_SCOPE])
        normalized = feedback if isinstance(feedback, FeedbackInput) else FeedbackInput.model_validate(dict(feedback))
        saved = self.store.save_feedback(user_id=context.user_id, feedback=normalized)
        audit = self._audit(context, tool_name="save_feedback", target_id=saved.feedback_id)
        return saved.model_copy(update={"session_id": context.session_id, "audit_id": audit.audit_id})

    def save_reference_answer(
        self,
        context: McpToolContext,
        *,
        reference_answer: ReferenceAnswerInput | Mapping[str, Any],
    ) -> ReferenceAnswerSaved:
        authorize_tool_call(context, tool_name="save_reference_answer", required_scopes=[REPORT_WRITE_SCOPE])
        normalized = (
            reference_answer
            if isinstance(reference_answer, ReferenceAnswerInput)
            else ReferenceAnswerInput.model_validate(dict(reference_answer))
        )
        saved = self.store.save_reference_answer(user_id=context.user_id, reference_answer=normalized)
        audit = self._audit(context, tool_name="save_reference_answer", target_id=saved.reference_answer_id)
        return saved.model_copy(update={"session_id": context.session_id, "audit_id": audit.audit_id})

    def _audit(self, context: McpToolContext, *, tool_name: str, target_id: str | None) -> ReportAuditRecord:
        return self.audit_sink.record(
            ReportAuditRecord(
                tool_name=tool_name,
                user_id=context.user_id,
                session_id=context.session_id,
                request_id=context.request_id,
                status="success",
                target_id=target_id,
            )
        )


class PostgresReportStore:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self.database_url = database_url

    def save_score_report(self, *, user_id: str, report: ScoreReportInput) -> ScoreReportSaved:
        psycopg, Jsonb = load_psycopg()
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                ensure_session_ownership(conn, user_id=user_id, session_id=report.session_id)
                row = conn.execute(
                    """
                    insert into score_reports
                        (id, session_id, version, status, overall_band, confidence, disclaimer, model_run_id, raw_report)
                    values
                        (coalesce(%s::uuid, gen_random_uuid()), %s::uuid, %s, %s::report_status, %s, %s, %s, %s, %s::jsonb)
                    on conflict (session_id, version) do update set
                        status = excluded.status,
                        overall_band = excluded.overall_band,
                        confidence = excluded.confidence,
                        disclaimer = excluded.disclaimer,
                        model_run_id = excluded.model_run_id,
                        raw_report = excluded.raw_report,
                        updated_at = now()
                    returning id::text
                    """,
                    (
                        report.report_id,
                        report.session_id,
                        report.version,
                        report.status,
                        report.overall_band,
                        report.confidence,
                        report.disclaimer,
                        existing_model_run_id(conn, report.model_run_id),
                        Jsonb(build_raw_report_payload(report)),
                    ),
                ).fetchone()
                report_id = row[0]
                replace_criterion_scores(conn, Jsonb, report_id=report_id, criteria=report.criteria)
                replace_study_plan(conn, user_id=user_id, report_id=report_id, plan=report.next_practice_plan)
        return ScoreReportSaved(
            session_id=report.session_id,
            report_id=report_id,
            criterion_count=len(report.criteria),
            study_plan_count=len(report.next_practice_plan),
        )

    def save_feedback(self, *, user_id: str, feedback: FeedbackInput) -> FeedbackSaved:
        psycopg, Jsonb = load_psycopg()
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                session_id = get_report_session_id(conn, user_id=user_id, report_id=feedback.report_id)
                row = conn.execute(
                    """
                    insert into feedback_items (report_id, category, priority, title, body, evidence_refs)
                    values (%s::uuid, %s, %s, %s, %s, %s::jsonb)
                    returning id::text
                    """,
                    (
                        feedback.report_id,
                        feedback.category,
                        feedback.priority,
                        feedback.title,
                        feedback.body,
                        Jsonb(feedback.evidence_refs),
                    ),
                ).fetchone()
        return FeedbackSaved(session_id=session_id, feedback_id=row[0], report_id=feedback.report_id)

    def save_reference_answer(self, *, user_id: str, reference_answer: ReferenceAnswerInput) -> ReferenceAnswerSaved:
        psycopg, Jsonb = load_psycopg()
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                session_id = get_report_session_id(conn, user_id=user_id, report_id=reference_answer.report_id)
                row = conn.execute(
                    """
                    insert into reference_answers
                        (report_id, turn_id, band_target, skeleton, answer_text, personalization_notes)
                    values
                        (%s::uuid, %s::uuid, %s, %s::jsonb, %s, %s)
                    returning id::text
                    """,
                    (
                        reference_answer.report_id,
                        nullable_uuid(reference_answer.turn_id),
                        reference_answer.band_target,
                        Jsonb(reference_answer.skeleton),
                        reference_answer.answer_text,
                        reference_answer.personalization_notes,
                    ),
                ).fetchone()
        return ReferenceAnswerSaved(
            session_id=session_id,
            reference_answer_id=row[0],
            report_id=reference_answer.report_id,
        )


def ensure_session_ownership(conn: Any, *, user_id: str, session_id: str) -> None:
    row = conn.execute(
        """
        select exists(
            select 1
            from practice_sessions
            where id = %s::uuid and user_id = %s::uuid and deleted_at is null
        )
        """,
        (session_id, user_id),
    ).fetchone()
    if not row or not row[0]:
        raise PermissionError("session not found or not owned by user")


def existing_model_run_id(conn: Any, model_run_id: str | None) -> str | None:
    if not model_run_id:
        return None
    row = conn.execute("select exists(select 1 from agent_runs where id = %s)", (model_run_id,)).fetchone()
    if not row or not row[0]:
        return None
    return model_run_id


def get_report_session_id(conn: Any, *, user_id: str, report_id: str) -> str:
    row = conn.execute(
        """
        select sr.session_id::text
        from score_reports sr
        join practice_sessions ps on ps.id = sr.session_id
        where sr.id = %s::uuid and ps.user_id = %s::uuid and ps.deleted_at is null
        """,
        (report_id, user_id),
    ).fetchone()
    if not row:
        raise PermissionError("report not found or not owned by user")
    return row[0]


def nullable_uuid(value: str | None) -> str | None:
    if not value:
        return None
    try:
        UUID(value)
    except ValueError:
        return None
    return value


def replace_criterion_scores(conn: Any, Jsonb: Any, *, report_id: str, criteria: Mapping[str, CriterionScoreInput]) -> None:
    conn.execute("delete from criterion_scores where report_id = %s::uuid", (report_id,))
    for criterion, score in criteria.items():
        conn.execute(
            """
            insert into criterion_scores
                (report_id, criterion, band, confidence, evidence, suggestions, raw_output)
            values
                (%s::uuid, %s::scoring_criterion, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
            """,
            (
                report_id,
                criterion,
                score.band,
                score.confidence,
                Jsonb([item.model_dump(mode="json") for item in score.evidence]),
                Jsonb(score.suggestions),
                Jsonb(score.raw_output),
            ),
        )


def replace_study_plan(conn: Any, *, user_id: str, report_id: str, plan: Sequence[PracticePlanInput]) -> None:
    conn.execute("delete from study_plans where report_id = %s::uuid", (report_id,))
    for item in plan:
        conn.execute(
            """
            insert into study_plans (report_id, user_id, priority, focus, task, due_on)
            values (%s::uuid, %s::uuid, %s, %s, %s, %s::date)
            """,
            (report_id, user_id, item.priority, item.focus, item.task, item.due_on),
        )


def build_raw_report_payload(report: ScoreReportInput) -> dict[str, Any]:
    payload = dict(report.raw_report)
    payload.setdefault("version", report.version)
    payload.setdefault("status", report.status)
    payload.setdefault("reviewer_notes", report.reviewer_notes)
    payload.setdefault("next_practice_plan", [item.model_dump(mode="json", exclude_none=True) for item in report.next_practice_plan])
    payload.setdefault("disclaimer", report.disclaimer)
    return payload


def build_score_report_insert_sql() -> str:
    return """
        insert into score_reports
            (id, session_id, version, status, overall_band, confidence, disclaimer, model_run_id, raw_report)
        values
            (coalesce(%s::uuid, gen_random_uuid()), %s::uuid, %s, %s::report_status, %s, %s, %s, %s, %s::jsonb)
        on conflict (session_id, version) do update set
            status = excluded.status,
            overall_band = excluded.overall_band,
            confidence = excluded.confidence,
            disclaimer = excluded.disclaimer,
            model_run_id = excluded.model_run_id,
            raw_report = excluded.raw_report,
            updated_at = now()
        returning id::text
    """
