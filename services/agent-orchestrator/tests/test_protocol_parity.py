import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
EVENT_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "packages" / "protocol" / "schemas" / "agent-stream-event.schema.json"


def test_plan_response_has_harness_compatible_fields() -> None:
    orchestrator = client.post(
        "/agent/sessions/sess_parity_orch/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    ).json()

    required_top_level = {"run_id", "events", "state", "next_action"}
    assert required_top_level <= set(orchestrator.keys())

    for event in orchestrator["events"]:
        assert {"type", "session_id", "run_id", "payload", "created_at"} <= set(event.keys())

    assert orchestrator["next_action"] in {
        "wait_for_user_answer",
        "ask_next_question",
        "score_session",
        "finish_session",
        "retry_current_node",
    }


def test_stream_event_kinds_are_schema_compatible() -> None:
    if not EVENT_SCHEMA_PATH.exists():
        pytest.skip("agent-stream-event.schema.json not found")
    schema = json.loads(EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    allowed_kinds = set(schema["properties"]["kind"]["enum"])

    plan = client.post(
        "/agent/sessions/sess_parity_stream/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    ).json()
    events = client.get(f"/agent/runs/{plan['run_id']}/events").json()
    assert events
    for event in events:
        assert event["kind"] in allowed_kinds
