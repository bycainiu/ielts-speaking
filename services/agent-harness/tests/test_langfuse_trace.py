from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.observability.langfuse_client import (
    AgentRunTrace,
    TraceStep,
    build_langfuse_ingestion_payload,
    hash_user_id,
    sanitize_text,
)


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
                prompt_version="mock.exam_workflow.v1",
                model_name="mock-model",
                status="completed",
                input_summary="plan mode=full_exam",
                output_summary="next_action=wait_for_user_answer",
                latency_ms=12,
                started_at=now,
                finished_at=now,
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


def test_langfuse_enabled_requires_keys() -> None:
    settings = Settings(LANGFUSE_ENABLED=True, LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY="")

    with pytest.raises(RuntimeError):
        settings.validate_runtime()
