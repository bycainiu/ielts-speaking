import pytest

from app.mcp.report_mcp import (
    IELTS_DISCLAIMER,
    FeedbackInput,
    FeedbackSaved,
    InMemoryReportAuditSink,
    PostgresReportStore,
    ReferenceAnswerInput,
    ReferenceAnswerSaved,
    ReportMcpTools,
    ScoreReportInput,
    ScoreReportSaved,
    build_raw_report_payload,
    build_score_report_insert_sql,
    nullable_uuid,
)
from app.mcp.security import McpAuthorizationError, McpToolContext


USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SESSION_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
REPORT_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def test_save_score_report_persists_report_and_writes_audit() -> None:
    store = FakeReportStore()
    audit = InMemoryReportAuditSink()
    tools = ReportMcpTools(store, audit_sink=audit)
    context = read_context(allowed_tools=["save_score_report"])

    result = tools.save_score_report(context, report=make_score_report_payload())

    assert result.report_id == REPORT_ID
    assert result.criterion_count == 4
    assert result.study_plan_count == 1
    assert result.audit_id == "audit_0001"
    assert store.saved_reports[0].overall_band == 6.5
    assert store.saved_reports[0].version == 1
    assert store.saved_reports[0].disclaimer == IELTS_DISCLAIMER
    assert audit.records[0].tool_name == "save_score_report"
    assert audit.records[0].user_id == USER_ID
    assert audit.records[0].session_id == SESSION_ID
    assert audit.records[0].request_id == "req_1"
    assert audit.records[0].target_id == REPORT_ID


def test_save_score_report_rejects_session_mismatch() -> None:
    tools = ReportMcpTools(FakeReportStore())
    context = read_context(allowed_tools=["save_score_report"])
    payload = make_score_report_payload()
    payload["session_id"] = "other-session"

    with pytest.raises(ValueError, match="report.session_id"):
        tools.save_score_report(context, report=payload)


def test_score_report_input_requires_all_criteria_and_official_disclaimer() -> None:
    payload = make_score_report_payload()
    payload["criteria"].pop("pronunciation")

    with pytest.raises(ValueError, match="criteria missing"):
        ScoreReportInput.model_validate(payload)

    payload = make_score_report_payload()
    payload["disclaimer"] = "Official IELTS score."
    with pytest.raises(ValueError, match="disclaimer"):
        ScoreReportInput.model_validate(payload)


def test_save_feedback_persists_item_and_writes_audit() -> None:
    store = FakeReportStore()
    audit = InMemoryReportAuditSink()
    tools = ReportMcpTools(store, audit_sink=audit)
    context = read_context(allowed_tools=["save_feedback"])

    result = tools.save_feedback(
        context,
        feedback={
            "report_id": REPORT_ID,
            "category": "fluency",
            "priority": 2,
            "title": "Reduce long pauses",
            "body": "Practice grouping ideas before speaking.",
            "evidence_refs": [{"turn_id": "turn_1"}],
        },
    )

    assert result.feedback_id == "feedback_001"
    assert result.session_id == SESSION_ID
    assert store.saved_feedback[0].title == "Reduce long pauses"
    assert audit.records[0].tool_name == "save_feedback"
    assert audit.records[0].target_id == "feedback_001"


def test_save_reference_answer_persists_item_and_writes_audit() -> None:
    store = FakeReportStore()
    audit = InMemoryReportAuditSink()
    tools = ReportMcpTools(store, audit_sink=audit)
    context = read_context(allowed_tools=["save_reference_answer"])

    result = tools.save_reference_answer(
        context,
        reference_answer={
            "report_id": REPORT_ID,
            "turn_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            "band_target": 7.0,
            "skeleton": {"opening": "direct answer"},
            "answer_text": "I would start with a direct answer and then add one example.",
            "personalization_notes": "Use the learner's city example.",
        },
    )

    assert result.reference_answer_id == "reference_001"
    assert result.session_id == SESSION_ID
    assert store.saved_references[0].band_target == 7.0
    assert audit.records[0].tool_name == "save_reference_answer"


def test_report_mcp_rejects_missing_scope_and_disallowed_tool() -> None:
    tools = ReportMcpTools(FakeReportStore())

    with pytest.raises(McpAuthorizationError, match="missing required scope"):
        tools.save_score_report(
            McpToolContext(user_id=USER_ID, session_id=SESSION_ID, scopes=[]),
            report=make_score_report_payload(),
        )

    with pytest.raises(McpAuthorizationError, match="tool is not allowed"):
        tools.save_feedback(
            read_context(allowed_tools=["save_score_report"]),
            feedback={"report_id": REPORT_ID, "category": "x", "title": "x", "body": "x"},
        )


def test_postgres_store_sql_helpers_and_raw_report_payload() -> None:
    sql = build_score_report_insert_sql()
    report = ScoreReportInput.model_validate(make_score_report_payload())
    raw = build_raw_report_payload(report)

    assert "insert into score_reports" in sql
    assert "on conflict (session_id, version)" in sql
    assert "returning id::text" in sql
    assert raw["version"] == 1
    assert raw["status"] == "ready"
    assert raw["reviewer_notes"] == ["Use conservative scoring."]
    assert raw["next_practice_plan"][0]["focus"] == "fluency"
    assert raw["disclaimer"] == IELTS_DISCLAIMER


def test_postgres_report_store_rejects_missing_database_url() -> None:
    with pytest.raises(ValueError, match="database_url is required"):
        PostgresReportStore("")


def test_nullable_uuid_drops_non_database_turn_ids() -> None:
    assert nullable_uuid("dddddddd-dddd-dddd-dddd-dddddddddddd") == "dddddddd-dddd-dddd-dddd-dddddddddddd"
    assert nullable_uuid("turn_score_001") is None
    assert nullable_uuid(None) is None


class FakeReportStore:
    def __init__(self) -> None:
        self.saved_reports: list[ScoreReportInput] = []
        self.saved_feedback: list[FeedbackInput] = []
        self.saved_references: list[ReferenceAnswerInput] = []

    def save_score_report(self, *, user_id: str, report: ScoreReportInput) -> ScoreReportSaved:
        assert user_id == USER_ID
        self.saved_reports.append(report)
        return ScoreReportSaved(
            session_id=report.session_id,
            report_id=REPORT_ID,
            criterion_count=len(report.criteria),
            study_plan_count=len(report.next_practice_plan),
        )

    def save_feedback(self, *, user_id: str, feedback: FeedbackInput) -> FeedbackSaved:
        assert user_id == USER_ID
        self.saved_feedback.append(feedback)
        return FeedbackSaved(session_id=SESSION_ID, feedback_id="feedback_001", report_id=feedback.report_id)

    def save_reference_answer(self, *, user_id: str, reference_answer: ReferenceAnswerInput) -> ReferenceAnswerSaved:
        assert user_id == USER_ID
        self.saved_references.append(reference_answer)
        return ReferenceAnswerSaved(
            session_id=SESSION_ID,
            reference_answer_id="reference_001",
            report_id=reference_answer.report_id,
        )


def read_context(*, allowed_tools: list[str]) -> McpToolContext:
    return McpToolContext(
        user_id=USER_ID,
        session_id=SESSION_ID,
        scopes=["report:write"],
        allowed_tools=allowed_tools,
        request_id="req_1",
    )


def make_score_report_payload() -> dict:
    criterion = {
        "band": 6.5,
        "confidence": 0.82,
        "evidence": [{"turn_id": "turn_1", "quote": "I think it is useful", "reason": "clear answer"}],
        "suggestions": ["Add one more specific example."],
        "raw_output": {"source": "test"},
    }
    return {
        "session_id": SESSION_ID,
        "version": 1,
        "status": "ready",
        "overall_band": 6.5,
        "confidence": 0.8,
        "criteria": {
            "fluency_coherence": criterion,
            "lexical_resource": criterion,
            "grammatical_range_accuracy": criterion,
            "pronunciation": criterion,
        },
        "reviewer_notes": ["Use conservative scoring."],
        "next_practice_plan": [{"priority": 2, "focus": "fluency", "task": "Record a 90-second answer."}],
        "disclaimer": IELTS_DISCLAIMER,
        "model_run_id": "run_001",
        "raw_report": {"provider": "agent-harness-test"},
    }
