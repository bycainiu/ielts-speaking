from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    name: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    latency_ms: int = 0
