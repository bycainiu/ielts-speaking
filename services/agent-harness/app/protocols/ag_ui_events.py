from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.protocols.schemas import SessionEvent, SessionEventType


AG_UI_EVENT_TYPES: tuple[str, ...] = (
    "session.started",
    "part.started",
    "examiner.thinking",
    "examiner.message",
    "examiner.audio_ready",
    "timer.started",
    "timer.tick",
    "timer.warning",
    "user.recording_started",
    "user.silence_detected",
    "user.answer_committed",
    "asr.processing",
    "asr.final",
    "agent.followup_planned",
    "part.completed",
    "scoring.started",
    "scoring.dimension_completed",
    "scoring.review_completed",
    "report.ready",
    "session.completed",
    "error.recoverable",
    "error.fatal",
)
AG_UI_EVENT_TYPE_SET = set(AG_UI_EVENT_TYPES)


class AGUIEventValidationError(ValueError):
    pass


class PayloadModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class TimerPolicyPayload(PayloadModel):
    suggested_seconds: int = Field(gt=0)


class SessionStartedPayload(PayloadModel):
    mode: str = Field(min_length=1)


class PartStartedPayload(PayloadModel):
    part: int = Field(ge=1, le=3)
    title: str = Field(min_length=1)


class ExaminerMessagePayload(PayloadModel):
    part: int = Field(ge=1, le=3)
    question_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    timer_policy: TimerPolicyPayload


class TimerStartedPayload(PayloadModel):
    part: int = Field(ge=1, le=3)
    suggested_seconds: int = Field(gt=0)


class AsrFinalPayload(PayloadModel):
    turn_id: str = Field(min_length=1)
    text: str
    audio_asset_id: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class FollowupPlannedPayload(PayloadModel):
    decision: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class PartCompletedPayload(PayloadModel):
    part: int = Field(ge=1, le=3)


class SessionCompletedPayload(PayloadModel):
    completed_parts: list[int]


class ScoringStartedPayload(PayloadModel):
    run_reason: str | None = None


PAYLOAD_MODELS: dict[str, type[PayloadModel]] = {
    "session.started": SessionStartedPayload,
    "part.started": PartStartedPayload,
    "examiner.message": ExaminerMessagePayload,
    "timer.started": TimerStartedPayload,
    "asr.final": AsrFinalPayload,
    "agent.followup_planned": FollowupPlannedPayload,
    "part.completed": PartCompletedPayload,
    "session.completed": SessionCompletedPayload,
    "scoring.started": ScoringStartedPayload,
}


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{uuid4().hex}"


def build_event(event_type: str, session_id: str, run_id: str, payload: dict[str, Any]) -> SessionEvent:
    event_type = validate_event_type(event_type)
    payload = validate_payload(event_type, payload)
    return SessionEvent(
        type=event_type,
        session_id=session_id,
        run_id=run_id,
        payload=payload,
        created_at=datetime.now(UTC),
    )


def build_scoring_started_event(
    session_id: str,
    run_id: str,
    *,
    run_reason: str | None = None,
    **payload: Any,
) -> SessionEvent:
    if run_reason is not None:
        payload["run_reason"] = run_reason
    return build_event("scoring.started", session_id, run_id, payload)


def validate_event_type(event_type: str) -> SessionEventType:
    if event_type not in AG_UI_EVENT_TYPE_SET:
        raise AGUIEventValidationError(f"不支持的 AG-UI 事件类型：{event_type}")
    return event_type  # type: ignore[return-value]


def validate_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AGUIEventValidationError("AG-UI 事件 payload 必须是对象")

    payload_model = PAYLOAD_MODELS.get(event_type)
    if payload_model is None:
        return dict(payload)

    try:
        validated = payload_model.model_validate(payload)
    except ValidationError as exc:
        raise AGUIEventValidationError(f"{event_type} payload 不合法：{exc}") from exc
    return validated.model_dump(mode="json", exclude_none=True)
