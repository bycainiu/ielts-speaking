from datetime import UTC, datetime
from typing import Any

from app.protocols.schemas import SessionEvent, SessionEventType


def build_session_event(
    *,
    event_type: SessionEventType,
    session_id: str,
    run_id: str,
    payload: dict[str, Any],
    created_at: datetime | None = None,
) -> SessionEvent:
    return SessionEvent(
        type=event_type,
        session_id=session_id,
        run_id=run_id,
        payload=payload,
        created_at=created_at or datetime.now(UTC),
    )
