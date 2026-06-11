"""真实 LLM 调用捕获与实时流上下文。

- `InMemoryLlmCaptureSink`：与 MCP 审计 sink 同构的进程内捕获器，记录每一次真实模型调用
  （请求 messages、响应内容、thinking 文本、token 用量、延迟、错误码）。
- `LiveStreamContext`：由 TraceRecorder 在工作流执行期间通过 contextvar 注入，
  使模型网关可以在调用过程中实时向 AgentRunStreamBroker 发布
  message.delta / reasoning.delta / usage.updated 事件。
"""

from __future__ import annotations

import threading
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from app.observability.streaming import AgentRunStreamBroker
from app.protocols.schemas import AgentUsageDetail


LlmCallStatus = Literal["completed", "failed"]


@dataclass
class CapturedLlmCall:
    call_name: str
    agent_name: str
    task: str
    provider: str
    status: LlmCallStatus
    model_name: str | None = None
    prompt_version: str | None = None
    request_messages: list[dict[str, Any]] = field(default_factory=list)
    response_content: str | None = None
    parsed_output: Any = None
    reasoning_text: str | None = None
    usage: AgentUsageDetail | None = None
    latency_ms: int = 0
    error_code: str | None = None
    provider_request_id: str | None = None
    stream_event_count: int = 0
    content_streamed: bool = False
    reasoning_streamed: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class InMemoryLlmCaptureSink:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.records: list[CapturedLlmCall] = []

    def record(self, record: CapturedLlmCall) -> CapturedLlmCall:
        with self._lock:
            self.records.append(record)
        return record

    def records_since(self, start_index: int) -> list[CapturedLlmCall]:
        with self._lock:
            return list(self.records[start_index:])

    def clear(self) -> None:
        with self._lock:
            self.records.clear()


_DEFAULT_LLM_CAPTURE_SINK = InMemoryLlmCaptureSink()


def get_llm_capture_sink() -> InMemoryLlmCaptureSink:
    return _DEFAULT_LLM_CAPTURE_SINK


def reset_llm_capture_sink() -> None:
    _DEFAULT_LLM_CAPTURE_SINK.clear()


@dataclass(frozen=True)
class LiveStreamContext:
    broker: AgentRunStreamBroker
    run_id: str
    session_id: str


_live_stream_context: ContextVar[LiveStreamContext | None] = ContextVar("agent_live_stream_context", default=None)


def set_live_stream_context(context: LiveStreamContext) -> Token[LiveStreamContext | None]:
    return _live_stream_context.set(context)


def reset_live_stream_context(token: Token[LiveStreamContext | None]) -> None:
    _live_stream_context.reset(token)


def current_live_stream_context() -> LiveStreamContext | None:
    return _live_stream_context.get()
