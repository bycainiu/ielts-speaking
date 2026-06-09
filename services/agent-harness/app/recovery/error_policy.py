from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


RecoverySeverity = Literal["recoverable", "degraded", "fatal"]
RecoveryNextAction = Literal[
    "retry_current_node",
    "manual_text_input",
    "text_only_examiner_message",
    "reconnect_and_restore_session",
    "safe_fallback_response",
    "finish_with_partial_report",
    "stop_session",
]


class RecoveryPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_type: str = Field(min_length=1)
    workflow_node: str | None = None
    retry_count: int = Field(default=0, ge=0)
    session_state: dict[str, Any] = Field(default_factory=dict)

    @field_validator("error_type", "workflow_node", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class RecoveryDirective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_type: str
    workflow_node: str | None = None
    severity: RecoverySeverity
    retryable: bool
    next_action: RecoveryNextAction
    user_message: str
    max_retries: int = Field(ge=0)
    preserve_session_state: bool = True
    manual_input_allowed: bool = False
    telemetry_tags: list[str] = Field(default_factory=list)


def recovery_directive_for(request: RecoveryPolicyRequest) -> RecoveryDirective:
    normalized_error = request.error_type.lower().strip()
    node = request.workflow_node

    if normalized_error in {"asr_failed", "asr_provider_error", "missing_audio_source", "unsupported_audio_format"}:
        if request.retry_count >= 2:
            return RecoveryDirective(
                error_type=normalized_error,
                workflow_node=node,
                severity="degraded",
                retryable=False,
                next_action="manual_text_input",
                user_message="语音识别连续失败，请保留当前会话并允许用户手动输入本轮回答。",
                max_retries=2,
                manual_input_allowed=True,
                telemetry_tags=["asr", "manual_input_fallback"],
            )
        return RecoveryDirective(
            error_type=normalized_error,
            workflow_node=node,
            severity="recoverable",
            retryable=True,
            next_action="retry_current_node",
            user_message="语音识别暂时失败，可以重试当前音频处理节点。",
            max_retries=2,
            manual_input_allowed=True,
            telemetry_tags=["asr", "retry"],
        )

    if normalized_error in {"tts_failed", "tts_provider_error", "tts_timeout"}:
        if request.retry_count >= 1:
            return RecoveryDirective(
                error_type=normalized_error,
                workflow_node=node,
                severity="degraded",
                retryable=False,
                next_action="text_only_examiner_message",
                user_message="考官语音暂时不可用，请展示文本问题并继续考试流程。",
                max_retries=1,
                telemetry_tags=["tts", "text_only_fallback"],
            )
        return RecoveryDirective(
            error_type=normalized_error,
            workflow_node=node,
            severity="recoverable",
            retryable=True,
            next_action="retry_current_node",
            user_message="语音合成暂时失败，可以先重试 TTS 节点。",
            max_retries=1,
            telemetry_tags=["tts", "retry"],
        )

    if normalized_error in {"structured_output_invalid", "schema_validation_failed", "agent_output_invalid"}:
        if request.retry_count >= 2:
            return RecoveryDirective(
                error_type=normalized_error,
                workflow_node=node,
                severity="degraded",
                retryable=False,
                next_action="safe_fallback_response",
                user_message="Agent 输出多次不合法，请使用受控兜底事件，避免中断整场会话。",
                max_retries=2,
                telemetry_tags=["agent", "schema", "safe_fallback"],
            )
        return RecoveryDirective(
            error_type=normalized_error,
            workflow_node=node,
            severity="recoverable",
            retryable=True,
            next_action="retry_current_node",
            user_message="Agent 输出未通过结构化校验，请带修复提示重试当前节点。",
            max_retries=2,
            telemetry_tags=["agent", "schema", "retry"],
        )

    if normalized_error in {"websocket_disconnected", "ws_disconnected", "network_lost"}:
        return RecoveryDirective(
            error_type=normalized_error,
            workflow_node=node,
            severity="recoverable",
            retryable=True,
            next_action="reconnect_and_restore_session",
            user_message="实时连接断开，请自动重连并用 session_id 恢复当前会话状态。",
            max_retries=5,
            telemetry_tags=["websocket", "reconnect"],
        )

    if normalized_error in {"no_scorable_answers", "review_requested_rescore"}:
        return RecoveryDirective(
            error_type=normalized_error,
            workflow_node=node,
            severity="recoverable",
            retryable=True,
            next_action="retry_current_node",
            user_message="评分节点需要更多可用证据或重新评分，请保留回答并重试评分。",
            max_retries=2,
            telemetry_tags=["scoring", "retry"],
        )

    return RecoveryDirective(
        error_type=normalized_error,
        workflow_node=node,
        severity="fatal",
        retryable=False,
        next_action="stop_session",
        user_message="出现未知错误，请停止当前自动流程并保留 session 状态供排查。",
        max_retries=0,
        preserve_session_state=True,
        telemetry_tags=["unknown_error"],
    )
