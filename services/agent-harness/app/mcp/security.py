from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class McpAuthorizationError(PermissionError):
    """MCP 工具调用未通过 scope 或 allowlist 校验。"""


DEFAULT_MCP_AUDIT_HASH_SALT = "local-mcp-audit-salt-change-me"
DEFAULT_HIGH_RISK_TOOLS = [
    "save_score_report",
    "save_feedback",
    "save_reference_answer",
]


class McpToolContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    scopes: list[str] = Field(default_factory=list)
    allowed_tools: list[str] | None = None
    disabled_tools: list[str] = Field(default_factory=list)
    disable_high_risk_tools: bool = False
    high_risk_tools: list[str] = Field(default_factory=lambda: list(DEFAULT_HIGH_RISK_TOOLS))
    request_id: str | None = None
    audit_hash_salt: str = DEFAULT_MCP_AUDIT_HASH_SALT

    @field_validator("user_id", "session_id", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Any) -> str:
        if value is None:
            raise ValueError("required context field is missing")
        text = str(value).strip()
        if not text:
            raise ValueError("required context field is empty")
        return text

    @field_validator("scopes", "allowed_tools", "disabled_tools", "high_risk_tools", mode="before")
    @classmethod
    def normalize_string_list(cls, value: Any, info: Any) -> list[str] | None:
        if value is None:
            if info.field_name == "high_risk_tools":
                return list(DEFAULT_HIGH_RISK_TOOLS)
            if info.field_name in {"scopes", "disabled_tools", "high_risk_tools"}:
                return []
            return None
        if isinstance(value, str):
            values = [value]
        else:
            values = list(value)

        normalized: list[str] = []
        for item in values:
            text = str(item).strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized


class McpAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str | None = None
    phase: Literal["authorization", "execution"] = "authorization"
    tool_name: str
    user_id_hash: str
    session_id: str
    request_id: str | None = None
    status: Literal["allowed", "denied", "completed", "failed"]
    reason: str | None = None
    required_scopes: list[str] = Field(default_factory=list)
    granted_scopes: list[str] = Field(default_factory=list)
    arguments: dict[str, Any] = Field(default_factory=dict)
    output_payload: Any = None
    latency_ms: int | None = Field(default=None, ge=0)


class McpAuditSink(Protocol):
    def record(self, record: McpAuditRecord) -> McpAuditRecord:
        ...


class InMemoryMcpAuditSink:
    def __init__(self) -> None:
        self.records: list[McpAuditRecord] = []

    def record(self, record: McpAuditRecord) -> McpAuditRecord:
        saved = record.model_copy(update={"audit_id": record.audit_id or f"mcp_audit_{len(self.records) + 1:04d}"})
        self.records.append(saved)
        return saved

    def clear(self) -> None:
        self.records.clear()


_DEFAULT_AUDIT_SINK = InMemoryMcpAuditSink()


def get_mcp_audit_sink() -> InMemoryMcpAuditSink:
    return _DEFAULT_AUDIT_SINK


def reset_mcp_audit_sink() -> None:
    _DEFAULT_AUDIT_SINK.clear()


def hash_user_id(user_id: str, *, salt: str = DEFAULT_MCP_AUDIT_HASH_SALT) -> str:
    digest = hashlib.sha256(f"{salt}:{user_id}".encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def authorize_tool_call(
    context: McpToolContext,
    *,
    tool_name: str,
    required_scopes: Iterable[str],
    audit_sink: McpAuditSink | None = None,
) -> None:
    tool_name = _normalize_text(tool_name, field_name="tool_name")
    required = [_normalize_text(scope, field_name="required_scope") for scope in required_scopes]
    sink = audit_sink or _DEFAULT_AUDIT_SINK

    disabled_tools = set(context.disabled_tools)
    if context.disable_high_risk_tools:
        disabled_tools.update(context.high_risk_tools)
    if tool_name in disabled_tools:
        _record_audit(context, sink, tool_name=tool_name, required_scopes=required, status="denied", reason="tool_disabled")
        raise McpAuthorizationError(f"tool is disabled: {tool_name}")

    if context.allowed_tools is not None and tool_name not in context.allowed_tools:
        _record_audit(context, sink, tool_name=tool_name, required_scopes=required, status="denied", reason="tool_not_allowed")
        raise McpAuthorizationError(f"tool is not allowed: {tool_name}")

    granted_scopes = set(context.scopes)
    missing_scopes = [scope for scope in required if scope not in granted_scopes]
    if missing_scopes:
        _record_audit(
            context,
            sink,
            tool_name=tool_name,
            required_scopes=required,
            status="denied",
            reason=f"missing_scope:{','.join(missing_scopes)}",
        )
        raise McpAuthorizationError(f"missing required scope: {', '.join(missing_scopes)}")

    _record_audit(context, sink, tool_name=tool_name, required_scopes=required, status="allowed", reason=None)


def record_tool_execution(
    context: McpToolContext,
    *,
    tool_name: str,
    required_scopes: Iterable[str],
    status: Literal["completed", "failed"],
    arguments: dict[str, Any] | None = None,
    output_payload: Any = None,
    reason: str | None = None,
    latency_ms: int | None = None,
    audit_sink: McpAuditSink | None = None,
) -> McpAuditRecord:
    tool_name = _normalize_text(tool_name, field_name="tool_name")
    required = [_normalize_text(scope, field_name="required_scope") for scope in required_scopes]
    sink = audit_sink or _DEFAULT_AUDIT_SINK
    return sink.record(
        McpAuditRecord(
            phase="execution",
            tool_name=tool_name,
            user_id_hash=hash_user_id(context.user_id, salt=context.audit_hash_salt),
            session_id=context.session_id,
            request_id=context.request_id,
            status=status,
            reason=reason,
            required_scopes=required,
            granted_scopes=context.scopes,
            arguments=dict(arguments or {}),
            output_payload=output_payload,
            latency_ms=latency_ms,
        )
    )


def _record_audit(
    context: McpToolContext,
    sink: McpAuditSink,
    *,
    tool_name: str,
    required_scopes: list[str],
    status: Literal["allowed", "denied"],
    reason: str | None,
) -> McpAuditRecord:
    return sink.record(
        McpAuditRecord(
            phase="authorization",
            tool_name=tool_name,
            user_id_hash=hash_user_id(context.user_id, salt=context.audit_hash_salt),
            session_id=context.session_id,
            request_id=context.request_id,
            status=status,
            reason=reason,
            required_scopes=required_scopes,
            granted_scopes=context.scopes,
        )
    )


def _normalize_text(value: Any, *, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} is empty")
    return text
