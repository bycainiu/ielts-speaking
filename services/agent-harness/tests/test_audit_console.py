from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.mcp.security import McpToolContext, authorize_tool_call, record_tool_execution, reset_mcp_audit_sink
from app.observability.langfuse_client import (
    AgentRunTrace,
    SessionEventStore,
    TraceRecorder,
    TraceStep,
    TraceStore,
    build_session_audit_detail,
    tool_calls_from_mcp_audit,
    trace_messages_from_response,
)
from app.protocols.ag_ui_events import build_event
from app.protocols.schemas import AgentResponse


def test_session_event_store_redacts_sensitive_payload_and_keeps_order() -> None:
    store = SessionEventStore(max_sessions=4, max_events_per_session=4)
    events = [
        build_event("session.started", "sess_audit_store", "run_plan", {"mode": "full_exam"}),
        build_event(
            "asr.final",
            "sess_audit_store",
            "run_asr",
            {"turn_id": "turn_001", "text": "email learner@example.com token=secret-token"},
        ),
    ]

    store.record("sess_audit_store", events)
    recorded = store.list_events("sess_audit_store")

    assert [item.type for item in recorded] == ["session.started", "asr.final"]
    assert "learner@example.com" not in str(recorded[1].payload)
    assert "secret-token" not in str(recorded[1].payload)


def test_trace_recorder_can_query_audit_sessions_and_detail_from_in_memory_data() -> None:
    settings = Settings(MOCK_MODEL_ENABLED=True, KNOWLEDGE_STORE_BACKEND="memory", MIMO_API_KEY="test-key")
    recorder = TraceRecorder(
        settings,
        store=TraceStore(max_runs=10),
        event_store=SessionEventStore(max_sessions=10, max_events_per_session=20),
    )
    now = datetime.now(UTC)
    plan_trace = AgentRunTrace(
        run_id="run_plan_001",
        session_id="sess_audit_agg",
        user_id_hash="sha256:user",
        mode="full_exam",
        part=1,
        question_id="question_plan_001",
        status="completed",
        started_at=now,
        finished_at=now,
        steps=[
            TraceStep(
                step_id="step_plan",
                workflow_node="plan_session",
                agent_name="ExamWorkflow",
                status="completed",
                latency_ms=12,
                started_at=now,
                finished_at=now,
            )
        ],
    )
    asr_trace = AgentRunTrace(
        run_id="run_asr_001",
        session_id="sess_audit_agg",
        user_id_hash="sha256:user",
        mode="full_exam",
        part=1,
        question_id="question_plan_001",
        status="completed",
        started_at=now + timedelta(seconds=1),
        finished_at=now + timedelta(seconds=1),
        steps=[
            TraceStep(
                step_id="step_asr",
                workflow_node="consume_asr",
                agent_name="FollowupPlannerAgent",
                status="completed",
                latency_ms=18,
                started_at=now + timedelta(seconds=1),
                finished_at=now + timedelta(seconds=1),
            )
        ],
    )
    recorder.store.save(plan_trace)
    recorder.store.save(asr_trace)
    recorder.event_store.record(
        "sess_audit_agg",
        [
            build_event("session.started", "sess_audit_agg", "run_plan_001", {"mode": "full_exam"}),
            build_event("part.started", "sess_audit_agg", "run_plan_001", {"part": 1, "title": "Part 1"}),
            build_event(
                "examiner.message",
                "sess_audit_agg",
                "run_plan_001",
                {
                    "part": 1,
                    "question_id": "question_plan_001",
                    "text": "Where is your hometown?",
                    "timer_policy": {"suggested_seconds": 30},
                },
            ),
            build_event("asr.final", "sess_audit_agg", "run_asr_001", {"turn_id": "turn_001", "text": "My hometown is Hangzhou."}),
        ],
    )

    summaries = recorder.query_audit_sessions(session_id="sess_audit_agg")
    detail = recorder.get_session_audit("sess_audit_agg")

    assert len(summaries) == 1
    assert summaries[0].session_id == "sess_audit_agg"
    assert summaries[0].run_count == 2
    assert summaries[0].event_count == 4
    assert summaries[0].current_part == 1
    assert summaries[0].latest_question_id == "question_plan_001"
    assert detail is not None
    assert detail.status == "completed"
    assert detail.agent_names == ["ExamWorkflow", "FollowupPlannerAgent"]
    assert detail.event_type_counts["session.started"] == 1
    assert len(detail.traces) == 2
    assert detail.runs[0].run_id == "run_asr_001"


def test_build_session_audit_detail_summarizes_recent_signals() -> None:
    now = datetime.now(UTC)
    events = [
        build_event("session.started", "sess_summary", "run_001", {"mode": "full_exam"}),
        build_event("part.completed", "sess_summary", "run_002", {"part": 1}),
        build_event("scoring.started", "sess_summary", "run_003", {"run_reason": "session_completed"}),
    ]
    traces = [
        AgentRunTrace(
            run_id="run_001",
            session_id="sess_summary",
            mode="full_exam",
            status="completed",
            started_at=now,
            finished_at=now,
            steps=[TraceStep(step_id="step_001", workflow_node="plan_session", status="completed", started_at=now, finished_at=now)],
        )
    ]

    detail = build_session_audit_detail(session_id="sess_summary", events=events, traces=traces)

    assert detail.status == "scoring"
    assert detail.completed_parts == [1]
    assert detail.recent_event_types[-1] == "scoring.started"


def test_trace_recorder_filters_audit_sessions_by_mode_and_status() -> None:
    settings = Settings(MOCK_MODEL_ENABLED=True, KNOWLEDGE_STORE_BACKEND="memory", MIMO_API_KEY="test-key")
    recorder = TraceRecorder(
        settings,
        store=TraceStore(max_runs=10),
        event_store=SessionEventStore(max_sessions=10, max_events_per_session=20),
    )
    now = datetime.now(UTC)
    recorder.store.save(
        AgentRunTrace(
            run_id="run_full_exam",
            session_id="sess_full_exam",
            mode="full_exam",
            status="completed",
            started_at=now,
            finished_at=now,
            steps=[TraceStep(step_id="step_full_exam", workflow_node="plan_session", status="completed", started_at=now, finished_at=now)],
        )
    )
    recorder.store.save(
        AgentRunTrace(
            run_id="run_topic_practice",
            session_id="sess_topic_practice",
            mode="topic_practice",
            status="failed",
            started_at=now + timedelta(seconds=1),
            finished_at=now + timedelta(seconds=1),
            steps=[TraceStep(step_id="step_topic_practice", workflow_node="consume_asr", status="failed", started_at=now + timedelta(seconds=1), finished_at=now + timedelta(seconds=1))],
        )
    )
    recorder.event_store.record(
        "sess_full_exam",
        [build_event("session.started", "sess_full_exam", "run_full_exam", {"mode": "full_exam"})],
    )
    recorder.event_store.record(
        "sess_topic_practice",
        [
            build_event("session.started", "sess_topic_practice", "run_topic_practice", {"mode": "topic_practice"}),
            build_event("error.fatal", "sess_topic_practice", "run_topic_practice", {"message": "planner failed"}),
        ],
    )

    summaries = recorder.query_audit_sessions(mode="topic_practice", status="failed")

    assert [item.session_id for item in summaries] == ["sess_topic_practice"]
    assert summaries[0].mode == "topic_practice"
    assert summaries[0].status == "failed"


def test_tool_calls_from_mcp_audit_prefers_execution_records_and_exposes_payloads() -> None:
    reset_mcp_audit_sink()
    context = McpToolContext(
        user_id="user_001",
        session_id="sess_tools",
        scopes=["question_bank:read"],
        request_id="req_tools",
        audit_hash_salt="test-salt",
    )

    authorize_tool_call(context, tool_name="search_questions", required_scopes=["question_bank:read"])
    record_tool_execution(
        context,
        tool_name="search_questions",
        required_scopes=["question_bank:read"],
        status="completed",
        arguments={"query": "hometown"},
        output_payload={"count": 2},
        latency_ms=9,
    )

    calls = tool_calls_from_mcp_audit(0)

    assert len(calls) == 1
    assert calls[0].tool_name == "search_questions"
    assert calls[0].latency_ms == 9
    assert calls[0].arguments == {"query": "hometown"}
    assert calls[0].output_payload == {"count": 2}
    assert calls[0].metadata["phase"] == "execution"


def test_trace_messages_from_response_uses_event_sequence() -> None:
    response = AgentResponse(
        run_id="run_messages",
        events=[
            build_event("session.started", "sess_messages", "run_messages", {"mode": "full_exam"}),
            build_event(
                "examiner.message",
                "sess_messages",
                "run_messages",
                {
                    "part": 1,
                    "question_id": "q1",
                    "text": "Where is your hometown?",
                    "timer_policy": {"suggested_seconds": 30},
                },
            ),
        ],
        state={"mode": "full_exam"},
        next_action="wait_for_user_answer",
    )

    messages = trace_messages_from_response(response)

    assert messages is not None
    assert [item.type for item in messages] == ["session.started", "examiner.message"]
    assert "Where is your hometown?" in (messages[1].content or "")
