from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.llm.model_router import ModelRouter
from app.llm.mimo_client import MiMoError
from app.llm.types import LlmToolCall, LlmToolResponse
from app.protocols.schemas import AgentUsageDetail


logger = logging.getLogger("agent_orchestrator.llm_gateway")

INVALID_API_KEYS = {"", "change-me"}


class LlmGateway:
    """LLM gateway with tool-calling support."""

    def __init__(self, settings: Settings, *, router: ModelRouter | None = None) -> None:
        self.settings = settings
        self.enabled = (not settings.mock_model_enabled) and settings.mimo_api_key not in INVALID_API_KEYS
        self._router = router
        if self.enabled and self._router is None:
            self._router = ModelRouter.from_settings(settings)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "LlmGateway":
        resolved = settings or get_settings()
        return cls(resolved)

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": "mimo",
            "default_model": self.settings.mimo_default_model,
            "mock_model_enabled": self.settings.mock_model_enabled,
        }

    async def aclose(self) -> None:
        if self._router is not None:
            await self._router.aclose()

    async def complete_with_tools(
        self,
        *,
        task: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LlmToolResponse | None:
        if not self.enabled or self._router is None:
            return None
        try:
            chat = await self._router.complete(
                task,
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools or None,
                response_format={"type": "json_object"},
            )
        except MiMoError as exc:
            logger.warning(
                "llm_complete_with_tools_failed",
                extra={"task": task, "error_code": exc.code, "retryable": exc.retryable},
            )
            return None
        except Exception:
            logger.exception("llm_complete_with_tools_unexpected", extra={"task": task})
            return None
        return _chat_response_to_tool_response(chat)

    def mock_tool_then_answer(
        self,
        *,
        tool_name: str,
        tool_arguments: dict[str, Any],
        final_json: dict[str, Any],
    ) -> list[LlmToolResponse]:
        return [
            LlmToolResponse(
                content=None,
                tool_calls=[LlmToolCall(id="call_1", name=tool_name, arguments=tool_arguments)],
                model_name="mock-orchestrator",
            ),
            LlmToolResponse(
                content=json.dumps(final_json, ensure_ascii=False),
                model_name="mock-orchestrator",
                usage=AgentUsageDetail(input_tokens=100, output_tokens=50, total_tokens=150),
            ),
        ]


def _chat_response_to_tool_response(chat: Any) -> LlmToolResponse:
    usage = chat.usage
    usage_detail = AgentUsageDetail(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens,
        cache_creation_input_tokens=usage.cache_creation_input_tokens,
    )
    reasoning_text = None
    raw_message = (chat.raw.get("choices") or [{}])[0].get("message") if isinstance(chat.raw, dict) else None
    if isinstance(raw_message, dict):
        reasoning_text = raw_message.get("reasoning_content") or raw_message.get("reasoning")
        if not isinstance(reasoning_text, str):
            reasoning_text = None

    return LlmToolResponse(
        content=chat.content or None,
        reasoning_text=reasoning_text,
        tool_calls=_parse_tool_calls(chat.tool_calls),
        model_name=chat.model,
        usage=usage_detail,
    )


def _parse_tool_calls(raw_calls: list[dict[str, Any]]) -> list[LlmToolCall]:
    parsed: list[LlmToolCall] = []
    for item in raw_calls:
        function = item.get("function") if isinstance(item, dict) else None
        if not isinstance(function, dict):
            continue
        arguments = function.get("arguments") or "{}"
        if isinstance(arguments, str):
            try:
                argument_dict = json.loads(arguments)
            except json.JSONDecodeError:
                argument_dict = {"raw": arguments}
        elif isinstance(arguments, dict):
            argument_dict = arguments
        else:
            argument_dict = {}
        parsed.append(
            LlmToolCall(
                id=str(item.get("id") or f"call_{uuid4().hex[:8]}"),
                name=str(function.get("name") or ""),
                arguments=argument_dict,
            )
        )
    return parsed
