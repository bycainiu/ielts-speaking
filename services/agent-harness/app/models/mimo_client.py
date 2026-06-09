import asyncio
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from app.core.config import Settings


MimoAPIFormat = Literal["openai", "anthropic"]


@dataclass(frozen=True)
class MiMoClientConfig:
    api_key: str
    base_url: str
    default_model: str = "mimo-v2.5-pro"
    api_format: MimoAPIFormat = "openai"
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_base_seconds: float = 0.2

    @classmethod
    def from_settings(cls, settings: Settings) -> "MiMoClientConfig":
        return cls(
            api_key=settings.mimo_api_key,
            base_url=settings.mimo_base_url,
            default_model=settings.mimo_default_model,
            api_format=settings.mimo_api_format,  # type: ignore[arg-type]
            timeout_seconds=settings.mimo_timeout_seconds,
            max_retries=settings.mimo_max_retries,
        )


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None

    def to_openai(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            payload["name"] = self.name
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        return payload


@dataclass(frozen=True)
class ChatUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ChatResponse:
    model: str
    content: str
    finish_reason: str | None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: ChatUsage = field(default_factory=ChatUsage)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatStreamChunk:
    delta: str = ""
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class MiMoError(Exception):
    def __init__(self, message: str, *, code: str, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code


class MiMoTimeoutError(MiMoError):
    def __init__(self, message: str = "MiMo request timed out") -> None:
        super().__init__(message, code="timeout", retryable=True)


class MiMoAuthError(MiMoError):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message, code="auth_error", retryable=False, status_code=status_code)


class MiMoRateLimitError(MiMoError):
    def __init__(self, message: str, status_code: int = 429) -> None:
        super().__init__(message, code="rate_limit", retryable=True, status_code=status_code)


class MiMoAPIError(MiMoError):
    pass


class MiMoInvalidResponseError(MiMoError):
    def __init__(self, message: str = "MiMo response shape is invalid") -> None:
        super().__init__(message, code="invalid_response", retryable=False)


class MiMoChatClient:
    def __init__(self, config: MiMoClientConfig, http_client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=config.timeout_seconds)

    async def __aenter__(self) -> "MiMoChatClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def complete(
        self,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
    ) -> ChatResponse:
        request_model = model or self.config.default_model
        payload = self._build_payload(
            messages,
            model=request_model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            response_format=response_format,
            stream=False,
        )
        data = await self._post_json(self._endpoint(), payload)
        return self._parse_response(data, request_model)

    async def stream(
        self,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[ChatStreamChunk]:
        request_model = model or self.config.default_model
        payload = self._build_payload(
            messages,
            model=request_model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            response_format=response_format,
            stream=True,
        )
        async for chunk in self._stream_json(self._endpoint(), payload):
            yield self._parse_stream_chunk(chunk)

    def _endpoint(self) -> str:
        base_url = self.config.base_url.rstrip("/")
        if self.config.api_format == "anthropic":
            return f"{base_url}/messages"
        return f"{base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        if self.config.api_format == "anthropic":
            headers["x-api-key"] = self.config.api_key
            headers["anthropic-version"] = "2023-06-01"
        return headers

    def _build_payload(
        self,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        *,
        model: str,
        temperature: float | None,
        max_tokens: int | None,
        tools: Sequence[Mapping[str, Any]] | None,
        response_format: Mapping[str, Any] | None,
        stream: bool,
    ) -> dict[str, Any]:
        normalized = [normalize_message(message) for message in messages]
        if self.config.api_format == "anthropic":
            return build_anthropic_payload(
                normalized,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                response_format=response_format,
                stream=stream,
            )
        return build_openai_payload(
            normalized,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            response_format=response_format,
            stream=stream,
        )

    async def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        async def do_request() -> dict[str, Any]:
            response = await self._client.post(url, headers=self._headers(), json=payload)
            if response.status_code >= 400:
                raise error_from_response(response)
            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise MiMoInvalidResponseError(str(exc)) from exc

        return await self._with_retries(do_request)

    async def _stream_json(self, url: str, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        async def open_stream() -> httpx.Response:
            response = await self._client.stream("POST", url, headers=self._headers(), json=payload).__aenter__()
            if response.status_code >= 400:
                await response.aread()
                try:
                    raise error_from_response(response)
                finally:
                    await response.aclose()
            return response

        response = await self._with_retries(open_stream)
        try:
            async for line in response.aiter_lines():
                item = parse_sse_line(line)
                if item is None:
                    continue
                yield item
        finally:
            await response.aclose()

    async def _with_retries(self, operation: Any) -> Any:
        attempts = self.config.max_retries + 1
        last_error: MiMoError | None = None
        for attempt in range(attempts):
            try:
                return await operation()
            except httpx.TimeoutException as exc:
                last_error = MiMoTimeoutError(str(exc) or "MiMo request timed out")
            except httpx.TransportError as exc:
                last_error = MiMoAPIError(str(exc), code="network_error", retryable=True)
            except MiMoError as exc:
                last_error = exc

            if last_error is None or not last_error.retryable or attempt == attempts - 1:
                raise last_error
            await asyncio.sleep(self.config.retry_base_seconds * (2**attempt))

        raise last_error or MiMoAPIError("MiMo request failed", code="unknown", retryable=False)

    def _parse_response(self, data: dict[str, Any], fallback_model: str) -> ChatResponse:
        if self.config.api_format == "anthropic":
            return parse_anthropic_response(data, fallback_model)
        return parse_openai_response(data, fallback_model)

    def _parse_stream_chunk(self, data: dict[str, Any]) -> ChatStreamChunk:
        if self.config.api_format == "anthropic":
            return parse_anthropic_stream_chunk(data)
        return parse_openai_stream_chunk(data)


def normalize_message(message: ChatMessage | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(message, ChatMessage):
        return message.to_openai()
    role = str(message.get("role", "")).strip()
    content = message.get("content", "")
    if role not in {"system", "user", "assistant", "tool"} or not isinstance(content, str):
        raise MiMoInvalidResponseError("chat message must include role and string content")
    normalized: dict[str, Any] = {"role": role, "content": content}
    for key in ("name", "tool_call_id"):
        if key in message and message[key] is not None:
            normalized[key] = message[key]
    return normalized


def build_openai_payload(
    messages: list[dict[str, Any]],
    *,
    model: str,
    temperature: float | None,
    max_tokens: int | None,
    tools: Sequence[Mapping[str, Any]] | None,
    response_format: Mapping[str, Any] | None,
    stream: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if tools:
        payload["tools"] = list(tools)
    if response_format:
        payload["response_format"] = dict(response_format)
    return payload


def build_anthropic_payload(
    messages: list[dict[str, Any]],
    *,
    model: str,
    temperature: float | None,
    max_tokens: int | None,
    tools: Sequence[Mapping[str, Any]] | None,
    response_format: Mapping[str, Any] | None,
    stream: bool,
) -> dict[str, Any]:
    system_messages = [message["content"] for message in messages if message["role"] == "system"]
    anthropic_messages = [
        {"role": message["role"], "content": message["content"]}
        for message in messages
        if message["role"] in {"user", "assistant"}
    ]
    payload: dict[str, Any] = {
        "model": model,
        "messages": anthropic_messages,
        "max_tokens": max_tokens or 1024,
        "stream": stream,
    }
    if system_messages:
        payload["system"] = "\n\n".join(system_messages)
    if temperature is not None:
        payload["temperature"] = temperature
    if tools:
        payload["tools"] = list(tools)
    if response_format:
        payload["metadata"] = {"response_format": dict(response_format)}
    return payload


def parse_openai_response(data: dict[str, Any], fallback_model: str) -> ChatResponse:
    try:
        choice = data["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise MiMoInvalidResponseError() from exc

    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    if not isinstance(content, str):
        raise MiMoInvalidResponseError("OpenAI-compatible content must be text")

    usage = data.get("usage") or {}
    return ChatResponse(
        model=str(data.get("model") or fallback_model),
        content=content,
        finish_reason=choice.get("finish_reason"),
        tool_calls=list(message.get("tool_calls") or []),
        usage=ChatUsage(
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        ),
        raw=data,
    )


def parse_anthropic_response(data: dict[str, Any], fallback_model: str) -> ChatResponse:
    content_blocks = data.get("content")
    if not isinstance(content_blocks, list):
        raise MiMoInvalidResponseError("Anthropic-compatible content must be a list")

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text_parts.append(str(block.get("text") or ""))
        if block.get("type") == "tool_use":
            tool_calls.append(
                {
                    "id": block.get("id"),
                    "type": "function",
                    "function": {
                        "name": block.get("name"),
                        "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                    },
                }
            )

    usage = data.get("usage") or {}
    return ChatResponse(
        model=str(data.get("model") or fallback_model),
        content="".join(text_parts),
        finish_reason=data.get("stop_reason"),
        tool_calls=tool_calls,
        usage=ChatUsage(
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=sum_tokens(usage.get("input_tokens"), usage.get("output_tokens")),
        ),
        raw=data,
    )


def parse_sse_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line or line == "data: [DONE]":
        return None
    if line.startswith("data:"):
        line = line[len("data:") :].strip()
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise MiMoInvalidResponseError(str(exc)) from exc


def parse_openai_stream_chunk(data: dict[str, Any]) -> ChatStreamChunk:
    choices = data.get("choices") or []
    if not choices:
        return ChatStreamChunk(raw=data)
    choice = choices[0]
    delta = choice.get("delta") or {}
    return ChatStreamChunk(
        delta=str(delta.get("content") or ""),
        finish_reason=choice.get("finish_reason"),
        tool_calls=list(delta.get("tool_calls") or []),
        raw=data,
    )


def parse_anthropic_stream_chunk(data: dict[str, Any]) -> ChatStreamChunk:
    event_type = data.get("type")
    if event_type == "content_block_delta":
        delta = data.get("delta") or {}
        if delta.get("type") == "text_delta":
            return ChatStreamChunk(delta=str(delta.get("text") or ""), raw=data)
        if delta.get("type") == "input_json_delta":
            return ChatStreamChunk(delta=str(delta.get("partial_json") or ""), raw=data)
    if event_type == "message_stop":
        return ChatStreamChunk(finish_reason="stop", raw=data)
    return ChatStreamChunk(raw=data)


def error_from_response(response: httpx.Response) -> MiMoError:
    message = response.text
    error_code = "api_error"
    try:
        body = response.json()
        error = body.get("error", body)
        if isinstance(error, dict):
            message = str(error.get("message") or message)
            error_code = str(error.get("code") or error.get("type") or error_code)
    except json.JSONDecodeError:
        pass

    if response.status_code in {401, 403}:
        return MiMoAuthError(message or "MiMo authentication failed", response.status_code)
    if response.status_code == 429:
        return MiMoRateLimitError(message or "MiMo rate limit exceeded", response.status_code)
    if response.status_code >= 500:
        return MiMoAPIError(
            message or "MiMo upstream error",
            code=error_code,
            retryable=True,
            status_code=response.status_code,
        )
    return MiMoAPIError(message or "MiMo request failed", code=error_code, retryable=False, status_code=response.status_code)


def sum_tokens(input_tokens: Any, output_tokens: Any) -> int | None:
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        return input_tokens + output_tokens
    return None
