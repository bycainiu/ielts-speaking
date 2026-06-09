import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.protocols.ag_ui_events import (
    AGUIEventValidationError,
    AG_UI_EVENT_TYPES,
    build_event,
    build_scoring_started_event,
)
from app.protocols.schemas import SessionEvent


def test_build_event_validates_examiner_message_payload() -> None:
    event = build_event(
        "examiner.message",
        "sess_001",
        "run_001",
        {
            "part": 1,
            "question_id": "q_001",
            "text": "Where is your hometown?",
            "timer_policy": {"suggested_seconds": 30},
            "practice_hints": ["Add one concrete detail."],
        },
    )

    assert event.type == "examiner.message"
    assert event.payload["timer_policy"] == {"suggested_seconds": 30}
    assert event.payload["practice_hints"] == ["Add one concrete detail."]


def test_build_event_rejects_unknown_event_type() -> None:
    with pytest.raises(AGUIEventValidationError):
        build_event("unknown.event", "sess_001", "run_001", {})


def test_build_event_rejects_invalid_payload_shape() -> None:
    with pytest.raises(AGUIEventValidationError):
        build_event(
            "timer.started",
            "sess_001",
            "run_001",
            {"part": 1, "suggested_seconds": 0},
        )


def test_scoring_started_event_is_supported() -> None:
    event = build_scoring_started_event("sess_001", "run_001", run_reason="session_completed")

    assert event.type == "scoring.started"
    assert event.payload == {"run_reason": "session_completed"}


def test_session_event_schema_rejects_types_outside_shared_protocol() -> None:
    with pytest.raises(ValidationError):
        SessionEvent.model_validate(
            {
                "type": "scoring.review.completed",
                "session_id": "sess_001",
                "run_id": "run_001",
                "payload": {},
                "created_at": "2026-06-07T00:00:00Z",
            }
        )


def test_python_event_types_match_core_protocol_count() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "packages" / "protocol" / "schemas" / "session-event.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert list(AG_UI_EVENT_TYPES) == schema["properties"]["type"]["enum"]
