from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.config import Settings
from app.observability.langfuse_client import (
    AgentRunTrace,
    TraceLlmCall,
    TraceRecorder,
    TraceStep,
    TraceStore,
    build_langfuse_ingestion_payload,
    hash_user_id,
    request_payload,
    sanitize_text,
)
from app.protocols.schemas import AgentResponse, PlanRequest, SessionEvent


def test_sanitize_text_redacts_common_sensitive_patterns() -> None:
    sanitized = sanitize_text(
        "Bearer abc.def token=secret learner@example.com api_key=hidden",
        limit=200,
    )

    assert sanitized is not None
    assert "abc.def" not in sanitized
    assert "learner@example.com" not in sanitized
    assert "secret" not in sanitized
    assert "hidden" not in sanitized
    assert sanitized.count("[REDACTED]") >= 3


def test_user_hash_is_stable_and_salted() -> None:
    first = hash_user_id("user_001", "salt-a")
    second = hash_user_id("user_001", "salt-a")
    other_salt = hash_user_id("user_001", "salt-b")

    assert first == second
    assert first != other_salt
    assert "user_001" not in first


def test_build_langfuse_ingestion_payload_contains_trace_and_span() -> None:
    now = datetime.now(UTC)
    trace = AgentRunTrace(
        run_id="run_001",
        session_id="sess_001",
        user_id_hash="sha256:test",
        mode="full_exam",
        part=1,
        question_id="planner_fallback_p1_q1",
        status="completed",
        started_at=now,
        finished_at=now,
        steps=[
            TraceStep(
                step_id="step_001",
                workflow_node="plan_session",
                part=1,
                question_id="planner_fallback_p1_q1",
                agent_name="ExamWorkflow",
                execution_kind="deterministic",
                prompt_version="mock.exam_workflow.v1",
                model_name="mock-model",
                status="completed",
                input_summary="plan mode=full_exam",
                output_summary="next_action=wait_for_user_answer",
                latency_ms=12,
                started_at=now,
                finished_at=now,
                llm_calls=[
                    TraceLlmCall(
                        llm_call_id="llm_001",
                        call_name="plan_session",
                        agent_name="ExamWorkflow",
                        execution_kind="deterministic",
                        payload_origin="derived",
                        provider="deterministic",
                        model_name="mock-model",
                        prompt_version="mock.exam_workflow.v1",
                        status="completed",
                        request_payload={"mode": "full_exam"},
                        response_payload={"next_action": "wait_for_user_answer"},
                        input_tokens=6,
                        output_tokens=5,
                        latency_ms=12,
                        started_at=now,
                        finished_at=now,
                    )
                ],
                tool_calls=[],
            )
        ],
    )

    payload = build_langfuse_ingestion_payload(trace)

    assert payload["batch"][0]["type"] == "trace-create"
    assert payload["batch"][0]["body"]["id"] == "run_001"
    assert payload["batch"][0]["body"]["sessionId"] == "sess_001"
    assert payload["batch"][0]["body"]["metadata"]["part"] == 1
    assert payload["batch"][0]["body"]["metadata"]["question_id"] == "planner_fallback_p1_q1"
    assert payload["batch"][1]["type"] == "span-create"
    assert payload["batch"][1]["body"]["traceId"] == "run_001"
    assert payload["batch"][1]["body"]["metadata"]["part"] == 1
    assert payload["batch"][1]["body"]["metadata"]["question_id"] == "planner_fallback_p1_q1"
    assert payload["batch"][1]["body"]["metadata"]["prompt_version"] == "mock.exam_workflow.v1"
    assert payload["batch"][1]["body"]["metadata"]["execution_kind"] == "deterministic"
    assert payload["batch"][1]["body"]["metadata"]["llm_calls"][0]["call_name"] == "plan_session"


def test_request_payload_keeps_full_redacted_body_for_raw_debugging() -> None:
    long_prefix = "A" * 320
    long_suffix = "B" * 320

    payload = request_payload({"prompt": f"{long_prefix} token=secret {long_suffix}"})

    assert payload is not None
    assert payload["prompt"].startswith(long_prefix)
    assert payload["prompt"].endswith(long_suffix)
    assert payload["prompt"].count("...") == 0
    assert "[REDACTED]" in payload["prompt"]
    assert "secret" not in payload["prompt"]


def test_langfuse_enabled_requires_keys() -> None:
    settings = Settings(LANGFUSE_ENABLED=True, LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY="")

    with pytest.raises(RuntimeError):
        settings.validate_runtime()


def test_trace_persistence_requires_database_url_when_enabled() -> None:
    settings = Settings(
        TRACE_PERSISTENCE_ENABLED=True,
        TRACE_DATABASE_URL="",
        KNOWLEDGE_DATABASE_URL="",
    )

    with pytest.raises(RuntimeError, match="TRACE_PERSISTENCE_ENABLED"):
        settings.validate_runtime()


def test_trace_recorder_persists_completed_trace_and_events() -> None:
    repo = FakeTraceRepository()
    recorder = TraceRecorder(
        Settings(),
        store=TraceStore(max_runs=10),
        trace_repository=repo,
    )
    now = datetime.now(UTC)
    event = SessionEvent(
        type="session.started",
        session_id="sess_persist",
        run_id="run_persist",
        payload={"mode": "full_exam"},
        created_at=now,
    )

    response = recorder.record_agent_call(
        session_id="sess_persist",
        workflow_node="plan_session",
        request=PlanRequest(mode="full_exam", user_id="user_001"),
        call=lambda: AgentResponse(
            run_id="run_persist",
            events=[event],
            state={"mode": "full_exam"},
            next_action="wait_for_user_answer",
        ),
    )

    assert response.run_id == "run_persist"
    assert repo.saved_traces[0].run_id == "run_persist"
    assert repo.saved_events[0][0] == event
    assert recorder.get_trace("run_persist") is not None


def test_trace_recorder_reads_persisted_trace_after_memory_miss() -> None:
    persisted = make_trace("run_db", "sess_db")
    repo = FakeTraceRepository([persisted])
    recorder = TraceRecorder(
        Settings(),
        store=TraceStore(max_runs=1),
        trace_repository=repo,
    )

    trace = recorder.get_trace("run_db")

    assert trace == persisted
    assert recorder.store.get("run_db") == persisted


def test_trace_recorder_summary_merges_memory_and_persisted_runs() -> None:
    now = datetime.now(UTC)
    memory_trace = make_trace("run_shared", "sess_merge", started_at=now)
    persisted_duplicate = make_trace("run_shared", "sess_merge", started_at=now)
    persisted_only = make_trace("run_persisted_only", "sess_merge", started_at=now)
    repo = FakeTraceRepository([persisted_duplicate, persisted_only])
    store = TraceStore(max_runs=10)
    store.save(memory_trace)
    recorder = TraceRecorder(Settings(), store=store, trace_repository=repo)

    summary = recorder.query_summary(session_id="sess_merge", limit=10)

    assert summary.run_count == 2
    assert {run.run_id for run in summary.recent_runs} == {"run_shared", "run_persisted_only"}


def test_trace_recorder_cancel_updates_persisted_trace() -> None:
    repo = FakeTraceRepository([make_trace("run_cancel", "sess_cancel")])
    recorder = TraceRecorder(
        Settings(),
        store=TraceStore(max_runs=1),
        trace_repository=repo,
    )

    trace = recorder.cancel_run("run_cancel")

    assert trace is not None
    assert trace.status == "cancelled"
    assert repo.cancelled_run_ids == ["run_cancel"]


def test_postgres_trace_repository_writes_full_trace_and_only_captured_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.observability import trace_persistence

    fake_psycopg = FakePsycopg()
    monkeypatch.setattr(trace_persistence, "load_psycopg", lambda: (fake_psycopg, FakeJsonb))
    repo = trace_persistence.PostgresTraceRepository("postgres://trace-test")
    trace = make_trace(
        "run_postgres",
        "11111111-1111-1111-1111-111111111111",
        llm_calls=[
            make_llm_call("llm_derived", execution_kind="deterministic", payload_origin="derived"),
            make_llm_call("llm_captured_1", execution_kind="llm", payload_origin="captured"),
            make_llm_call("llm_captured_2", execution_kind="llm", payload_origin="captured"),
        ],
    )

    repo.save_trace(trace)

    model_call_statements = [item for item in fake_psycopg.connection.statements if "insert into model_calls" in item[0]]
    agent_run_statement = next(item for item in fake_psycopg.connection.statements if "insert into agent_runs" in item[0])
    metadata = agent_run_statement[1][4].value
    payload_origins = [statement[1][16] for statement in model_call_statements]

    assert metadata["trace_schema_version"] == "agent_run_trace.v2"
    assert metadata["trace_payload"]["run_id"] == "run_postgres"
    assert metadata["llm_call_count"] == 3
    assert metadata["captured_llm_call_count"] == 2
    assert "stream_event_count" in metadata
    assert "reasoning_block_count" in metadata
    assert len(model_call_statements) == 2
    assert payload_origins == ["captured", "captured"]


class FakeTraceRepository:
    def __init__(self, traces: list[AgentRunTrace] | None = None) -> None:
        self.traces = {trace.run_id: trace for trace in traces or []}
        self.saved_traces: list[AgentRunTrace] = []
        self.saved_events: list[list[SessionEvent]] = []
        self.cancelled_run_ids: list[str] = []

    def save_trace(self, trace: AgentRunTrace, *, events: list[SessionEvent] | None = None) -> None:
        self.saved_traces.append(trace)
        self.saved_events.append(list(events or []))
        self.traces[trace.run_id] = trace

    def get_trace(self, run_id: str) -> AgentRunTrace | None:
        return self.traces.get(run_id)

    def list_runs(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
        limit: int = 100,
    ) -> list[AgentRunTrace]:
        traces = list(self.traces.values())
        if session_id:
            traces = [trace for trace in traces if trace.session_id == session_id]
        if run_id:
            traces = [trace for trace in traces if trace.run_id == run_id]
        if mode:
            traces = [trace for trace in traces if trace.mode == mode]
        return sorted(traces, key=lambda trace: trace.started_at, reverse=True)[:limit]

    def session_ids(self, *, limit: int = 100) -> list[str]:
        ids = []
        for trace in self.list_runs(limit=limit):
            if trace.session_id not in ids:
                ids.append(trace.session_id)
        return ids[:limit]

    def list_events(self, session_id: str, *, limit: int = 500) -> list[SessionEvent]:
        return []

    def mark_cancelled(self, run_id: str) -> AgentRunTrace | None:
        self.cancelled_run_ids.append(run_id)
        trace = self.traces.get(run_id)
        if trace is None:
            return None
        updated = trace.model_copy(update={"status": "cancelled", "finished_at": datetime.now(UTC)})
        self.traces[run_id] = updated
        return updated


class FakeJsonb:
    def __init__(self, value: Any) -> None:
        self.value = value


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None, rows: list[dict[str, Any]] | None = None) -> None:
        self.row = row
        self.rows = rows or []

    def fetchone(self) -> dict[str, Any] | None:
        return self.row

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.step_index = 0

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def transaction(self) -> "FakeConnection":
        return self

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeResult:
        normalized_sql = " ".join(sql.split())
        self.statements.append((normalized_sql, params))
        if "returning id::text" in normalized_sql:
            self.step_index += 1
            return FakeResult({"id": f"00000000-0000-0000-0000-{self.step_index:012d}"})
        return FakeResult()


class FakeRows:
    dict_row = object()


class FakePsycopg:
    def __init__(self) -> None:
        self.rows = FakeRows()
        self.connection = FakeConnection()

    def connect(self, database_url: str, row_factory: object) -> FakeConnection:
        assert database_url == "postgres://trace-test"
        assert row_factory is self.rows.dict_row
        return self.connection


def make_trace(
    run_id: str,
    session_id: str,
    *,
    started_at: datetime | None = None,
    llm_calls: list[TraceLlmCall] | None = None,
) -> AgentRunTrace:
    now = started_at or datetime.now(UTC)
    return AgentRunTrace(
        run_id=run_id,
        session_id=session_id,
        mode="full_exam",
        status="completed",
        started_at=now,
        finished_at=now,
        steps=[
            TraceStep(
                step_id=f"step_{run_id}",
                workflow_node="examiner_turn",
                agent_name="ExaminerAgent",
                execution_kind="llm" if llm_calls else "deterministic",
                status="completed",
                input_payload={"messages": [{"role": "user", "content": "Next question"}]},
                output_payload={"content": "What do you do?"},
                latency_ms=20,
                started_at=now,
                finished_at=now,
                llm_calls=llm_calls or [],
            )
        ],
    )


def make_llm_call(
    llm_call_id: str,
    *,
    execution_kind: str,
    payload_origin: str,
) -> TraceLlmCall:
    now = datetime.now(UTC)
    return TraceLlmCall(
        llm_call_id=llm_call_id,
        call_name="examiner_turn",
        agent_name="ExaminerAgent",
        execution_kind=execution_kind,  # type: ignore[arg-type]
        payload_origin=payload_origin,  # type: ignore[arg-type]
        provider="mimo",
        model_name="mimo-v2.5-pro",
        prompt_version="examiner_turn.v1",
        status="completed",
        request_payload={"messages": [{"role": "user", "content": "Next question"}]},
        response_payload={"content": "What do you do?"},
        input_tokens=9,
        output_tokens=6,
        latency_ms=20,
        started_at=now,
        finished_at=now,
    )
