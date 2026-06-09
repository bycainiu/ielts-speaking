from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.models.mimo_client import ChatMessage, ChatResponse
from app.protocols.ag_ui_events import build_event
from app.protocols.schemas import SessionEvent


OutputModelT = TypeVar("OutputModelT", bound=BaseModel)

JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


class StructuredOutputError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool = True,
        raw_content: str | None = None,
        validation_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.raw_content = raw_content
        self.validation_errors = validation_errors or []


class RecoverableStructuredOutputError(StructuredOutputError):
    def __init__(
        self,
        message: str,
        *,
        raw_content: str | None = None,
        validation_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="structured_output_invalid",
            retryable=True,
            raw_content=raw_content,
            validation_errors=validation_errors,
        )


def response_format_for_model(model_type: type[BaseModel], *, name: str | None = None, strict: bool = True) -> dict[str, Any]:
    schema_name = name or model_type.__name__
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": strict,
            "schema": model_type.model_json_schema(),
        },
    }


def parse_structured_output(content: str, model_type: type[OutputModelT]) -> OutputModelT:
    raw_json = extract_json_text(content)
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RecoverableStructuredOutputError(
            f"模型输出不是合法 JSON：{exc.msg}",
            raw_content=content,
            validation_errors=[{"type": "json_decode", "message": exc.msg, "pos": exc.pos}],
        ) from exc

    try:
        return model_type.model_validate(data)
    except ValidationError as exc:
        raise RecoverableStructuredOutputError(
            "模型输出未通过结构化 schema 校验",
            raw_content=content,
            validation_errors=exc.errors(),
        ) from exc


def extract_json_text(content: str) -> str:
    text = content.strip()
    if not text:
        raise RecoverableStructuredOutputError("模型输出为空", raw_content=content)

    fenced = JSON_FENCE_RE.search(text)
    if fenced:
        return fenced.group(1).strip()

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            _, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        return text[index : index + end].strip()

    raise RecoverableStructuredOutputError("模型输出中未找到 JSON 对象", raw_content=content)


async def validate_chat_response_with_retries(
    *,
    generate: Any,
    messages: Sequence[ChatMessage | Mapping[str, Any]],
    model_type: type[OutputModelT],
    response_format: Mapping[str, Any] | None = None,
    max_validation_retries: int = 1,
) -> OutputModelT:
    if max_validation_retries < 0:
        raise ValueError("max_validation_retries 不能小于 0")

    current_messages: list[ChatMessage | Mapping[str, Any]] = list(messages)
    format_hint = response_format or response_format_for_model(model_type)
    last_error: RecoverableStructuredOutputError | None = None

    for attempt in range(max_validation_retries + 1):
        response: ChatResponse = await generate(current_messages, format_hint)
        try:
            return parse_structured_output(response.content, model_type)
        except RecoverableStructuredOutputError as exc:
            last_error = exc
            if attempt >= max_validation_retries:
                break
            current_messages = append_repair_instruction(current_messages, response.content, exc, model_type)

    raise last_error or RecoverableStructuredOutputError("模型结构化输出校验失败")


def append_repair_instruction(
    messages: Sequence[ChatMessage | Mapping[str, Any]],
    raw_content: str,
    error: RecoverableStructuredOutputError,
    model_type: type[BaseModel],
) -> list[ChatMessage | Mapping[str, Any]]:
    repair_message = ChatMessage(
        role="user",
        content=(
            "Your previous response failed the required JSON schema validation. "
            f"Return only valid JSON for schema `{model_type.__name__}`. "
            f"Validation error code: {error.code}. "
            f"Invalid response excerpt: {safe_excerpt(raw_content)}"
        ),
    )
    return [*messages, repair_message]


def build_recoverable_error_event(
    *,
    session_id: str,
    run_id: str,
    error: StructuredOutputError,
    workflow_node: str,
) -> SessionEvent:
    return build_event(
        "error.recoverable",
        session_id,
        run_id,
        {
            "error_code": error.code,
            "message": str(error),
            "workflow_node": workflow_node,
            "retryable": error.retryable,
        },
    )


def safe_excerpt(content: str, limit: int = 240) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."
