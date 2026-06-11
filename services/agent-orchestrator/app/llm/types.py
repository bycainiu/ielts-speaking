from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.protocols.schemas import AgentUsageDetail


@dataclass
class LlmToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LlmToolResponse:
    content: str | None = None
    reasoning_text: str | None = None
    tool_calls: list[LlmToolCall] = field(default_factory=list)
    model_name: str | None = None
    usage: AgentUsageDetail | None = None


@dataclass
class AgentToolLoopResult:
    output: dict[str, Any] | str | None
    iterations: int
    fallback_used: bool = False
    tool_calls_made: list[str] = field(default_factory=list)
    reasoning_text: str | None = None
