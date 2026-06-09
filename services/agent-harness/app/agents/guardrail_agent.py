from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.observability.langfuse_client import sanitize_text


GuardrailRisk = Literal["low", "medium", "high"]
GuardrailStage = Literal["examiner", "scoring", "feedback", "tool"]

PROMPT_INJECTION_RE = re.compile(
    r"\b(ignore|override|forget|bypass)\b.{0,80}\b(system|developer|instruction|policy|rules?)\b",
    re.IGNORECASE,
)
SYSTEM_LEAK_RE = re.compile(
    r"\b(system prompt|developer message|hidden instruction|private tools?|rubric|band descriptor|scoring rule)\b",
    re.IGNORECASE,
)
PRIVACY_EXFILTRATION_RE = re.compile(
    r"\b(password|api key|secret|token|email address|phone number|private profile|full background)\b",
    re.IGNORECASE,
)
TOOL_OVERRIDE_RE = re.compile(
    r"\b(call|invoke|use|run)\b.{0,80}\b(tool|database|mcp|report|profile|admin)\b",
    re.IGNORECASE,
)


class GuardrailDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: GuardrailStage
    allowed: bool
    risk: GuardrailRisk
    reasons: list[str] = Field(default_factory=list)
    sanitized_text: str | None = None


class ToolGuardrailDecision(GuardrailDecision):
    tool_name: str
    allowed_tool_names: list[str]


class GuardrailAgent:
    def evaluate_user_text(self, text: str, *, stage: GuardrailStage) -> GuardrailDecision:
        reasons = detect_risk_reasons(text)
        risk: GuardrailRisk = "low"
        allowed = True
        if any(reason in reasons for reason in ("prompt_injection", "system_prompt_leak", "privacy_exfiltration")):
            risk = "high"
            allowed = False
        elif reasons:
            risk = "medium"
        return GuardrailDecision(
            stage=stage,
            allowed=allowed,
            risk=risk,
            reasons=reasons,
            sanitized_text=sanitize_guarded_text(text),
        )

    def evaluate_model_output(self, text: str, *, stage: GuardrailStage) -> GuardrailDecision:
        sanitized = sanitize_guarded_text(text)
        leaked = SYSTEM_LEAK_RE.search(text) is not None or PRIVACY_EXFILTRATION_RE.search(text) is not None
        return GuardrailDecision(
            stage=stage,
            allowed=not leaked,
            risk="high" if leaked else "low",
            reasons=["unsafe_model_output"] if leaked else [],
            sanitized_text=sanitized,
        )

    def evaluate_tool_request(
        self,
        *,
        tool_name: str,
        allowed_tool_names: Sequence[str],
        arguments: Mapping[str, Any],
        user_text: str,
    ) -> ToolGuardrailDecision:
        allowed_tools = list(allowed_tool_names)
        reasons = detect_risk_reasons(user_text)
        if tool_name not in allowed_tools:
            reasons.append("tool_not_allowed")
        if TOOL_OVERRIDE_RE.search(user_text):
            reasons.append("user_tool_override")
        direct_user_argument = any(
            isinstance(value, str) and value.strip() and value.strip() in user_text
            for value in arguments.values()
        )
        if direct_user_argument and "user_tool_override" in reasons:
            reasons.append("user_controlled_tool_argument")

        allowed = not any(
            reason in reasons
            for reason in ("tool_not_allowed", "user_tool_override", "user_controlled_tool_argument", "prompt_injection")
        )
        return ToolGuardrailDecision(
            stage="tool",
            tool_name=tool_name,
            allowed_tool_names=allowed_tools,
            allowed=allowed,
            risk="high" if not allowed else "low",
            reasons=sorted(set(reasons)),
            sanitized_text=sanitize_guarded_text(user_text),
        )


def detect_risk_reasons(text: str) -> list[str]:
    reasons: list[str] = []
    if PROMPT_INJECTION_RE.search(text):
        reasons.append("prompt_injection")
    if SYSTEM_LEAK_RE.search(text):
        reasons.append("system_prompt_leak")
    if PRIVACY_EXFILTRATION_RE.search(text):
        reasons.append("privacy_exfiltration")
    if TOOL_OVERRIDE_RE.search(text):
        reasons.append("tool_override_attempt")
    return reasons


def sanitize_guarded_text(text: str) -> str:
    sanitized = SYSTEM_LEAK_RE.sub("exam instruction", text)
    sanitized = PRIVACY_EXFILTRATION_RE.sub("private detail", sanitized)
    return sanitize_text(sanitized, limit=500) or ""
