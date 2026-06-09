import asyncio
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import pytest

from app.core.config import Settings
from app.models.mimo_client import ChatMessage, ChatResponse, ChatStreamChunk, MiMoAPIError, MiMoAuthError
from app.models.model_router import ModelRouter, ModelRouterConfigError, build_routes


def run(coro):
    return asyncio.run(coro)


class RecordingClient:
    def __init__(self, errors: list[Exception] | None = None) -> None:
        self.errors = list(errors or [])
        self.calls: list[dict[str, Any]] = []
        self.closed = False

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
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": tools,
                "response_format": response_format,
            }
        )
        if self.errors:
            raise self.errors.pop(0)
        return ChatResponse(model=model or "missing-model", content="ok", finish_reason="stop")

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
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": tools,
                "response_format": response_format,
            }
        )
        yield ChatStreamChunk(delta="ok")

    async def aclose(self) -> None:
        self.closed = True


def test_default_routes_use_default_model_and_task_params() -> None:
    fake_client = RecordingClient()
    router = ModelRouter.from_settings(make_settings(), client=fake_client)  # type: ignore[arg-type]

    route = router.resolve("scoring")

    assert route.model == "mimo-v2.5-pro"
    assert route.temperature == 0.0
    assert route.max_tokens == 1800

    async def scenario() -> None:
        await router.complete("scoring", [{"role": "user", "content": "Score this answer."}])

    run(scenario())

    assert fake_client.calls[0]["model"] == "mimo-v2.5-pro"
    assert fake_client.calls[0]["temperature"] == 0.0
    assert fake_client.calls[0]["max_tokens"] == 1800


def test_json_routes_override_model_fallback_and_generation_params() -> None:
    settings = make_settings(
        MIMO_MODEL_ROUTES_JSON=json.dumps(
            {
                "scoring": {
                    "model": "mimo-score",
                    "fallback_model": "mimo-score-fallback",
                    "temperature": 0.1,
                    "max_tokens": 2048,
                },
                "cheap": "mimo-lite",
            }
        )
    )
    router = ModelRouter.from_settings(settings, client=RecordingClient())  # type: ignore[arg-type]

    scoring = router.resolve("scoring")
    cheap = router.resolve("cheap")

    assert scoring.model == "mimo-score"
    assert scoring.fallback_model == "mimo-score-fallback"
    assert scoring.temperature == 0.1
    assert scoring.max_tokens == 2048
    assert cheap.model == "mimo-lite"


def test_complete_uses_fallback_model_for_retryable_errors() -> None:
    error = MiMoAPIError("temporary", code="upstream_error", retryable=True, status_code=500)
    fake_client = RecordingClient(errors=[error])
    settings = make_settings(
        MIMO_MODEL_ROUTES_JSON=json.dumps(
            {
                "feedback": {
                    "model": "mimo-feedback",
                    "fallback_model": "mimo-feedback-backup",
                    "temperature": 0.4,
                    "max_tokens": 1600,
                }
            }
        )
    )
    router = ModelRouter.from_settings(settings, client=fake_client)  # type: ignore[arg-type]

    async def scenario() -> ChatResponse:
        return await router.complete("feedback", [{"role": "user", "content": "Give feedback."}])

    response = run(scenario())

    assert response.model == "mimo-feedback-backup"
    assert [call["model"] for call in fake_client.calls] == ["mimo-feedback", "mimo-feedback-backup"]
    assert fake_client.calls[1]["temperature"] == 0.4
    assert fake_client.calls[1]["max_tokens"] == 1600


def test_complete_does_not_fallback_for_non_retryable_errors() -> None:
    fake_client = RecordingClient(errors=[MiMoAuthError("blocked", 401)])
    settings = make_settings(
        MIMO_MODEL_ROUTES_JSON=json.dumps({"examiner": {"model": "mimo-main", "fallback_model": "mimo-backup"}})
    )
    router = ModelRouter.from_settings(settings, client=fake_client)  # type: ignore[arg-type]

    async def scenario() -> None:
        with pytest.raises(MiMoAuthError):
            await router.complete("examiner", [{"role": "user", "content": "Next question."}])

    run(scenario())

    assert [call["model"] for call in fake_client.calls] == ["mimo-main"]


def test_call_overrides_take_precedence_over_route_defaults() -> None:
    fake_client = RecordingClient()
    router = ModelRouter.from_settings(make_settings(), client=fake_client)  # type: ignore[arg-type]

    async def scenario() -> None:
        await router.complete(
            "question_planning",
            [{"role": "user", "content": "Plan questions."}],
            model="mimo-custom",
            temperature=0.75,
            max_tokens=333,
            response_format={"type": "json_object"},
        )

    run(scenario())

    assert fake_client.calls[0]["model"] == "mimo-custom"
    assert fake_client.calls[0]["temperature"] == 0.75
    assert fake_client.calls[0]["max_tokens"] == 333
    assert fake_client.calls[0]["response_format"] == {"type": "json_object"}


def test_invalid_route_json_reports_configuration_error() -> None:
    with pytest.raises(ModelRouterConfigError):
        build_routes(default_model="mimo-v2.5-pro", routes_json='{"scoring": {"temperature": 9}}')


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "APP_ENV": "local",
        "MIMO_API_KEY": "test-key",
        "MIMO_BASE_URL": "https://mimo.local/v1",
        "MIMO_DEFAULT_MODEL": "mimo-v2.5-pro",
        "MIMO_API_FORMAT": "openai",
        "MIMO_TIMEOUT_SECONDS": 3.0,
        "MIMO_MAX_RETRIES": 0,
        "MIMO_MODEL_ROUTES_JSON": "{}",
    }
    values.update(overrides)
    return Settings(**values)
