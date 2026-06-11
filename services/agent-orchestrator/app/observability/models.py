from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.protocols.schemas import AgentStreamEvent


TraceStatus = Literal["running", "completed", "failed", "cancelled"]


class OrchestratorRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    session_id: str
    workflow_node: str
    status: TraceStatus
    started_at: datetime
    finished_at: datetime | None = None
    latency_ms: int = Field(default=0, ge=0)
    error_code: str | None = None
    message_count: int = 0
    stream_event_count: int = 0


class ToolLoopIterationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    run_id: str
    agent_name: str
    iteration: int
    phase: str
    llm_request_messages: list[dict[str, Any]] | None = None
    llm_response_content: str | None = None
    llm_reasoning_text: str | None = None
    llm_tool_calls: list[dict[str, Any]] | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None
    tool_status: str | None = None
    model_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0
    error_code: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrchestratorTraceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    session_id: str
    status: TraceStatus
    workflow_node: str
    started_at: datetime
    finished_at: datetime | None = None
    latency_ms: int = 0
    message_count: int = 0
    stream_events: list[AgentStreamEvent] = Field(default_factory=list)
    tool_iterations: list[ToolLoopIterationRecord] = Field(default_factory=list)
