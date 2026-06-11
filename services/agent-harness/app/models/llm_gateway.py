"""同步 LLM 网关：供确定性工作流中的 Agent 调用真实模型。

设计要点：
- 工作流与 Agent 全部是同步代码，而 MiMoChatClient 基于 httpx.AsyncClient；
  网关维护一个常驻后台事件循环线程，通过 run_coroutine_threadsafe 提交协程，
  既能复用连接池，又不阻塞 FastAPI 的其他请求线程。
- 每次调用都会写入 LlmCaptureSink（payload_origin=captured 的数据源），
  并在存在 LiveStreamContext 时实时发布 message.delta / reasoning.delta / usage.updated。
- 任何模型错误（超时、限流、结构化校验失败）都只记录 failed capture 并返回 None，
  由调用方退回确定性规则路径，保证考试流程永不因模型故障中断。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Coroutine, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import httpx

from app.core.config import Settings
from app.models.mimo_client import ChatMessage, ChatUsage, MiMoError, normalize_message
from app.models.model_router import ModelRouter
from app.models.structured_output import (
    OutputModelT,
    RecoverableStructuredOutputError,
    StructuredOutputError,
    append_repair_instruction,
    parse_structured_output,
    response_format_for_model,
)
from app.observability.llm_capture import (
    CapturedLlmCall,
    LiveStreamContext,
    current_live_stream_context,
    get_llm_capture_sink,
)
from app.protocols.schemas import AgentUsageDetail


logger = logging.getLogger("agent_harness.llm_gateway")

CONTENT_FLUSH_CHARS = 48
REASONING_FLUSH_CHARS = 96
INVALID_API_KEYS = {"", "change-me"}


@dataclass(frozen=True)
class LlmTextResult:
    text: str
    reasoning_text: str | None
    model_name: str | None
    usage: AgentUsageDetail | None


@dataclass
class _StreamOutcome:
    content: str = ""
    reasoning: str = ""
    model_name: str | None = None
    usage: AgentUsageDetail | None = None
    stream_event_count: int = 0
    content_streamed: bool = False
    reasoning_streamed: bool = False


class _BackgroundEventLoop:
    """常驻事件循环线程，承载所有对模型供应商的异步调用。"""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def get_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                loop = asyncio.new_event_loop()
                thread = threading.Thread(target=loop.run_forever, name="llm-gateway-loop", daemon=True)
                thread.start()
                self._loop = loop
            return self._loop

    def run(self, coro: Coroutine[Any, Any, Any], *, timeout: float) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self.get_loop())
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            raise


_BACKGROUND_LOOP = _BackgroundEventLoop()


class LlmGateway:
    def __init__(
        self,
        settings: Settings,
        *,
        router: ModelRouter | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.settings = settings
        self._router = router
        self._router_lock = threading.Lock()
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = (not settings.mock_model_enabled) and settings.mimo_api_key not in INVALID_API_KEYS
        # 单次调用预算：覆盖供应商内部重试 + 结构化校验重试。
        self._call_timeout = max(10.0, settings.mimo_timeout_seconds * (settings.mimo_max_retries + 2) + 10.0)

    @classmethod
    def from_settings(cls, settings: Settings) -> "LlmGateway":
        return cls(settings)

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": "mimo",
            "default_model": self.settings.mimo_default_model,
            "mock_model_enabled": self.settings.mock_model_enabled,
        }

    def generate_text(
        self,
        *,
        task: str,
        call_name: str,
        agent_name: str,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        prompt_version: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LlmTextResult | None:
        """自由文本生成：内容增量实时发布为 message.delta。"""
        outcome = self._execute(
            task=task,
            call_name=call_name,
            agent_name=agent_name,
            prompt_version=prompt_version,
            messages=messages,
            response_format=None,
            publish_content=True,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if outcome is None or not outcome.content.strip():
            return None
        return LlmTextResult(
            text=outcome.content,
            reasoning_text=outcome.reasoning_text,
            model_name=outcome.model_name,
            usage=outcome.usage,
        )

    def generate_structured(
        self,
        *,
        task: str,
        call_name: str,
        agent_name: str,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        output_model: type[OutputModelT],
        prompt_version: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_validation_retries: int = 1,
    ) -> OutputModelT | None:
        """结构化生成：内容是 JSON，不作为 message.delta 发布，仅实时发布 thinking 增量。"""
        response_format = response_format_for_model(output_model)
        current_messages: list[ChatMessage | Mapping[str, Any]] = list(messages)
        for attempt in range(max_validation_retries + 1):
            outcome = self._execute(
                task=task,
                call_name=call_name,
                agent_name=agent_name,
                prompt_version=prompt_version,
                messages=current_messages,
                response_format=response_format,
                publish_content=False,
                temperature=temperature,
                max_tokens=max_tokens,
                output_model=output_model,
            )
            if outcome is None:
                return None
            if outcome.parsed is not None:
                return outcome.parsed
            if outcome.validation_error is None or attempt >= max_validation_retries:
                return None
            current_messages = append_repair_instruction(
                current_messages,
                outcome.content,
                outcome.validation_error,
                output_model,
            )
        return None

    # ------------------------------------------------------------------ #

    def _execute(
        self,
        *,
        task: str,
        call_name: str,
        agent_name: str,
        prompt_version: str | None,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        response_format: Mapping[str, Any] | None,
        publish_content: bool,
        temperature: float | None,
        max_tokens: int | None,
        output_model: type[OutputModelT] | None = None,
    ) -> "_ExecutionResult | None":
        if not self.enabled:
            return None
        context = current_live_stream_context()
        normalized_messages = [normalize_message(message) for message in messages]
        started_at = datetime.now(UTC)
        started_perf = perf_counter()
        record = CapturedLlmCall(
            call_name=call_name,
            agent_name=agent_name,
            task=task,
            provider="mimo",
            status="completed",
            prompt_version=prompt_version,
            request_messages=normalized_messages,
            started_at=started_at,
        )
        try:
            outcome: _StreamOutcome = _BACKGROUND_LOOP.run(
                self._stream_call(
                    task=task,
                    call_name=call_name,
                    agent_name=agent_name,
                    messages=normalized_messages,
                    response_format=response_format,
                    publish_content=publish_content,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    context=context,
                ),
                timeout=self._call_timeout,
            )
        except (MiMoError, TimeoutError, OSError, RuntimeError, httpx.HTTPError) as exc:
            record.status = "failed"
            record.error_code = str(getattr(exc, "code", exc.__class__.__name__))
            record.latency_ms = _elapsed_ms(started_perf)
            record.finished_at = datetime.now(UTC)
            get_llm_capture_sink().record(record)
            logger.warning(
                "llm_call_failed",
                extra={"call_name": call_name, "task": task, "error": record.error_code},
            )
            return None

        record.model_name = outcome.model_name
        record.response_content = outcome.content
        record.reasoning_text = outcome.reasoning.strip() or None
        record.usage = outcome.usage
        record.stream_event_count = outcome.stream_event_count
        record.content_streamed = outcome.content_streamed
        record.reasoning_streamed = outcome.reasoning_streamed
        record.latency_ms = _elapsed_ms(started_perf)
        record.finished_at = datetime.now(UTC)

        result = _ExecutionResult(
            content=outcome.content,
            reasoning_text=record.reasoning_text,
            model_name=record.model_name,
            usage=record.usage,
        )
        if output_model is not None:
            try:
                result.parsed = parse_structured_output(outcome.content, output_model)
                record.parsed_output = result.parsed.model_dump(mode="json", exclude_none=True)
            except RecoverableStructuredOutputError as exc:
                result.validation_error = exc
                record.status = "failed"
                record.error_code = exc.code
                logger.warning(
                    "llm_structured_output_invalid",
                    extra={"call_name": call_name, "task": task, "error": exc.code},
                )
            except StructuredOutputError as exc:
                record.status = "failed"
                record.error_code = exc.code

        get_llm_capture_sink().record(record)
        logger.info(
            "llm_call_completed",
            extra={
                "call_name": call_name,
                "task": task,
                "model": record.model_name,
                "status": record.status,
                "latency_ms": record.latency_ms,
                "stream_event_count": record.stream_event_count,
            },
        )
        if record.status == "failed" and result.validation_error is None:
            return None
        return result

    async def _stream_call(
        self,
        *,
        task: str,
        call_name: str,
        agent_name: str,
        messages: list[dict[str, Any]],
        response_format: Mapping[str, Any] | None,
        publish_content: bool,
        temperature: float | None,
        max_tokens: int | None,
        context: LiveStreamContext | None,
    ) -> _StreamOutcome:
        router = await self._ensure_router()
        route = router.resolve(task)
        outcome = _StreamOutcome(model_name=route.model)
        content_buffer = ""
        reasoning_buffer = ""

        def publish(kind: str, text: str) -> None:
            if context is None or not text:
                return
            payload = {"source": "live", "llm_call_name": call_name, "agent_name": agent_name, "task": task}
            if kind == "message.delta":
                context.broker.publish(
                    run_id=context.run_id,
                    session_id=context.session_id,
                    kind="message.delta",
                    phase=call_name,
                    role="assistant",
                    content_delta=text,
                    payload=payload,
                    visibility="default",
                )
                outcome.content_streamed = True
            else:
                context.broker.publish(
                    run_id=context.run_id,
                    session_id=context.session_id,
                    kind="reasoning.delta",
                    phase=call_name,
                    role="assistant",
                    reasoning_delta=text,
                    payload=payload,
                    visibility="reasoning",
                )
                outcome.reasoning_streamed = True
            outcome.stream_event_count += 1

        async for chunk in router.stream(
            task,
            messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if chunk.delta:
                outcome.content += chunk.delta
                if publish_content:
                    content_buffer += chunk.delta
                    if len(content_buffer) >= CONTENT_FLUSH_CHARS:
                        publish("message.delta", content_buffer)
                        content_buffer = ""
            if chunk.reasoning_delta:
                outcome.reasoning += chunk.reasoning_delta
                reasoning_buffer += chunk.reasoning_delta
                if len(reasoning_buffer) >= REASONING_FLUSH_CHARS:
                    publish("reasoning.delta", reasoning_buffer)
                    reasoning_buffer = ""
            if _usage_has_tokens(chunk.usage):
                outcome.usage = _usage_detail(chunk.usage, self.settings)
            chunk_model = chunk.raw.get("model") if isinstance(chunk.raw, dict) else None
            if isinstance(chunk_model, str) and chunk_model.strip():
                outcome.model_name = chunk_model.strip()

        if publish_content and content_buffer:
            publish("message.delta", content_buffer)
        if reasoning_buffer:
            publish("reasoning.delta", reasoning_buffer)
        if context is not None and outcome.usage is not None:
            context.broker.publish(
                run_id=context.run_id,
                session_id=context.session_id,
                kind="usage.updated",
                phase=call_name,
                usage=outcome.usage,
                payload={"source": "live", "llm_call_name": call_name, "model_name": outcome.model_name},
                visibility="admin",
            )
            outcome.stream_event_count += 1
        return outcome

    async def _ensure_router(self) -> ModelRouter:
        # router 在后台事件循环中惰性创建，保证 httpx.AsyncClient 绑定正确的 loop。
        with self._router_lock:
            if self._router is None:
                self._router = ModelRouter.from_settings(self.settings)
            return self._router


@dataclass
class _ExecutionResult:
    content: str
    reasoning_text: str | None = None
    model_name: str | None = None
    usage: AgentUsageDetail | None = None
    parsed: Any = None
    validation_error: RecoverableStructuredOutputError | None = None


def _usage_has_tokens(usage: ChatUsage) -> bool:
    return any(
        value is not None
        for value in (usage.input_tokens, usage.output_tokens, usage.total_tokens)
    )


def _usage_detail(usage: ChatUsage, settings: Settings) -> AgentUsageDetail:
    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens
    estimated_cost = None
    if input_tokens is not None or output_tokens is not None:
        estimated_cost = round(
            ((input_tokens or 0) / 1000) * settings.mimo_input_cost_usd_per_1k_tokens
            + ((output_tokens or 0) / 1000) * settings.mimo_output_cost_usd_per_1k_tokens,
            6,
        )
    return AgentUsageDetail(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=usage.total_tokens if usage.total_tokens is not None else _sum_tokens(input_tokens, output_tokens),
        cache_creation_input_tokens=usage.cache_creation_input_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens,
        estimated_cost_usd=estimated_cost,
    )


def _sum_tokens(input_tokens: int | None, output_tokens: int | None) -> int | None:
    if input_tokens is None and output_tokens is None:
        return None
    return (input_tokens or 0) + (output_tokens or 0)


def _elapsed_ms(started_perf: float) -> int:
    return max(0, int((perf_counter() - started_perf) * 1000))
