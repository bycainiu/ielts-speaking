import asyncio
import json

import httpx
import pytest

from app.models.mimo_client import (
    ChatMessage,
    MiMoAuthError,
    MiMoChatClient,
    MiMoClientConfig,
    MiMoRateLimitError,
)


def run(coro):
    return asyncio.run(coro)


def test_openai_complete_supports_tools_and_response_format() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "mimo-v2.5-pro",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_001",
                                    "type": "function",
                                    "function": {"name": "search_questions", "arguments": "{\"part\":1}"},
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = MiMoChatClient(make_config(), http_client=http_client)
            response = await client.complete(
                [ChatMessage(role="user", content="Plan a Part 1 question.")],
                tools=[{"type": "function", "function": {"name": "search_questions", "parameters": {"type": "object"}}}],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=256,
            )

        assert response.model == "mimo-v2.5-pro"
        assert response.tool_calls[0]["function"]["name"] == "search_questions"
        assert response.usage.total_tokens == 15
        assert requests[0]["model"] == "mimo-v2.5-pro"
        assert requests[0]["response_format"] == {"type": "json_object"}
        assert requests[0]["tools"][0]["function"]["name"] == "search_questions"

    run(scenario())


def test_openai_stream_yields_text_chunks() -> None:
    stream = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=stream)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = MiMoChatClient(make_config(), http_client=http_client)
            chunks = [
                chunk
                async for chunk in client.stream([{"role": "user", "content": "Say hello."}])
            ]

        assert "".join(chunk.delta for chunk in chunks) == "Hello world"
        assert chunks[-1].finish_reason == "stop"

    run(scenario())


def test_anthropic_complete_parses_text_and_tool_use() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1/messages"
        assert body["system"] == "You are an examiner."
        assert body["messages"] == [{"role": "user", "content": "Next question?"}]
        return httpx.Response(
            200,
            json={
                "model": "mimo-v2.5-pro",
                "stop_reason": "tool_use",
                "content": [
                    {"type": "text", "text": "I will search first."},
                    {"type": "tool_use", "id": "tool_001", "name": "search_questions", "input": {"part": 1}},
                ],
                "usage": {"input_tokens": 7, "output_tokens": 4},
            },
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = MiMoChatClient(make_config(api_format="anthropic"), http_client=http_client)
            response = await client.complete(
                [
                    ChatMessage(role="system", content="You are an examiner."),
                    ChatMessage(role="user", content="Next question?"),
                ],
                tools=[{"name": "search_questions", "input_schema": {"type": "object"}}],
            )

        assert response.content == "I will search first."
        assert response.tool_calls[0]["function"]["name"] == "search_questions"
        assert json.loads(response.tool_calls[0]["function"]["arguments"]) == {"part": 1}
        assert response.usage.total_tokens == 11

    run(scenario())


def test_retries_retryable_errors_then_succeeds() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, json={"error": {"message": "temporary", "code": "upstream_error"}})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Recovered"}, "finish_reason": "stop"}]},
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = MiMoChatClient(make_config(max_retries=1), http_client=http_client)
            response = await client.complete([{"role": "user", "content": "Retry?"}])

        assert response.content == "Recovered"
        assert attempts == 2

    run(scenario())


def test_classifies_auth_and_rate_limit_errors() -> None:
    async def assert_error(status_code: int, expected_type: type[Exception]) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, json={"error": {"message": "blocked"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = MiMoChatClient(make_config(max_retries=0), http_client=http_client)
            with pytest.raises(expected_type):
                await client.complete([{"role": "user", "content": "Hello"}])

    run(assert_error(401, MiMoAuthError))
    run(assert_error(429, MiMoRateLimitError))


def test_config_from_settings_uses_mimo_v25_pro() -> None:
    config = make_config()

    assert config.default_model == "mimo-v2.5-pro"
    assert config.base_url == "https://mimo.local/v1"


def make_config(**overrides) -> MiMoClientConfig:
    values = {
        "api_key": "test-key",
        "base_url": "https://mimo.local/v1",
        "default_model": "mimo-v2.5-pro",
        "api_format": "openai",
        "timeout_seconds": 3.0,
        "max_retries": 0,
        "retry_base_seconds": 0.001,
    }
    values.update(overrides)
    return MiMoClientConfig(**values)
