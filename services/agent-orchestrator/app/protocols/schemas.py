from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SessionMode = Literal["full_exam", "part_practice", "topic_practice"]
SessionEventType = Literal[
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
]
NextAction = Literal[
    "wait_for_user_answer",
    "ask_next_question",
    "score_session",
    "finish_session",
    "retry_current_node",
]
AgentStreamEventKind = Literal[
    "run.started",
    "step.started",
    "message.delta",
    "reasoning.delta",
    "tool.started",
    "tool.delta",
    "tool.completed",
    "markdown.delta",
    "question.requested",
    "usage.updated",
    "step.completed",
    "run.completed",
    "run.failed",
    "run.cancelled",
    "heartbeat",
    "agent.activated",
    "agent.thinking",
    "agent.action",
    "agent.tool_call",
    "agent.tool_result",
    "agent.message_sent",
    "agent.message_received",
    "agent.output",
    "agent.deactivated",
    "director.route_change",
    "director.constraint_check",
]
AgentStreamVisibility = Literal["default", "admin", "reasoning", "hidden"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionEvent(StrictModel):
    type: SessionEventType
    session_id: str
    run_id: str
    payload: dict[str, Any]
    created_at: datetime


class AgentUsageDetail(StrictModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cache_creation_input_tokens: int | None = Field(default=None, ge=0)
    cache_read_input_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)


class AgentStreamEvent(StrictModel):
    seq: int = Field(ge=0)
    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    step_id: str | None = None
    parent_id: str | None = None
    kind: AgentStreamEventKind
    phase: str | None = None
    role: str | None = None
    content_delta: str | None = None
    reasoning_delta: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    usage: AgentUsageDetail | None = None
    visibility: AgentStreamVisibility = "default"
    created_at: datetime


class PlanRequest(StrictModel):
    mode: SessionMode
    user_id: str = Field(min_length=1)
    season_id: str | None = None
    part: Literal[1, 2, 3] | None = None
    topic_ids: list[str] = Field(default_factory=list)
    topic_labels: list[str] = Field(default_factory=list)
    session_seed: str | None = Field(default=None, min_length=1)
    user_background: dict[str, Any] = Field(default_factory=dict)
    run_id_override: str | None = Field(default=None, min_length=1)


class NextTurnRequest(StrictModel):
    session_state: dict[str, Any]
    run_id_override: str | None = Field(default=None, min_length=1)


class ConsumeAsrRequest(StrictModel):
    turn_id: str = Field(min_length=1)
    asr_text: str
    audio_asset_id: str | None = None
    asr_confidence: float | None = Field(default=None, ge=0, le=1)
    session_state: dict[str, Any] = Field(default_factory=dict)
    run_id_override: str | None = Field(default=None, min_length=1)


class ScoreSessionRequest(StrictModel):
    session_state: dict[str, Any] = Field(default_factory=dict)
    rubric_descriptors: dict[str, list[str]] = Field(default_factory=dict)
    anchor_samples: list[dict[str, Any]] = Field(default_factory=list)
    topic_keywords: list[str] = Field(default_factory=list)
    model_run_id: str | None = None
    run_id_override: str | None = Field(default=None, min_length=1)


class AgentResponse(StrictModel):
    run_id: str
    events: list[SessionEvent]
    state: dict[str, Any]
    next_action: NextAction


class RunSummary(StrictModel):
    run_id: str
    status: Literal["running", "completed", "failed", "cancelled"]
    runtime: dict[str, str]
