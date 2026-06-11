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


class AgentReasoningBlock(StrictModel):
    block_id: str
    type: str = "reasoning"
    text: str | None = None
    provider: str | None = None
    raw: Any = None
    created_at: datetime


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


class TranscribeAudioRequest(StrictModel):
    audio_asset_id: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    duration_ms: int | None = Field(default=None, gt=0)
    language_hint: str | None = Field(default=None, min_length=2)
    audio_url: str | None = Field(default=None, min_length=1)
    audio_base64: str | None = Field(default=None, min_length=1)


class TranscribeAudioResponse(StrictModel):
    audio_asset_id: str
    asr_text: str = Field(min_length=1)
    language: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    provider: str
    model: str
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SynthesizeSpeechRequest(StrictModel):
    text: str = Field(min_length=1, max_length=1200)
    voice_id: str = Field(default="ielts_examiner_default", min_length=1, max_length=120)
    speaking_rate: float = Field(default=1.0, ge=0.5, le=1.5)
    emotion: str | None = Field(default="neutral", max_length=60)
    style: str | None = Field(default="examiner", max_length=80)


class SynthesizeSpeechResponse(StrictModel):
    text: str
    audio_base64: str = Field(min_length=1)
    mime_type: str
    provider: str
    model: str
    voice_id: str
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(StrictModel):
    run_id: str
    events: list[SessionEvent]
    state: dict[str, Any]
    next_action: NextAction


class RunSummary(StrictModel):
    run_id: str
    status: Literal["running", "completed", "failed", "cancelled"]
    runtime: dict[str, str]
