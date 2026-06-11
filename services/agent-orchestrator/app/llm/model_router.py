from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.llm.mimo_client import ChatMessage, ChatResponse, MiMoChatClient, MiMoClientConfig, MiMoError


DEFAULT_TASK_PARAMS: dict[str, dict[str, float | int | None]] = {
    "default": {"temperature": 0.2, "max_tokens": 1024},
    "question_planning": {"temperature": 0.3, "max_tokens": 900},
    "examiner": {"temperature": 0.5, "max_tokens": 700},
    "followup_planning": {"temperature": 0.4, "max_tokens": 700},
    "scoring": {"temperature": 0.0, "max_tokens": 1800},
    "feedback": {"temperature": 0.4, "max_tokens": 1800},
    "cheap": {"temperature": 0.2, "max_tokens": 512},
}


class ModelRouterConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ModelRoute:
    task: str
    model: str
    fallback_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None

    @classmethod
    def default_for(cls, task: str, *, model: str) -> "ModelRoute":
        params = DEFAULT_TASK_PARAMS.get(task, DEFAULT_TASK_PARAMS["default"])
        return cls(
            task=task,
            model=model,
            temperature=_optional_float(params.get("temperature"), f"{task}.temperature"),
            max_tokens=_optional_int(params.get("max_tokens"), f"{task}.max_tokens"),
        )

    def with_override(self, raw: Any) -> "ModelRoute":
        if isinstance(raw, str):
            raw = {"model": raw}
        if not isinstance(raw, Mapping):
            raise ModelRouterConfigError(f"{self.task} route config must be an object or model name")

        return ModelRoute(
            task=self.task,
            model=_string_value(raw.get("model", self.model), f"{self.task}.model"),
            fallback_model=_optional_string(raw.get("fallback_model", self.fallback_model), f"{self.task}.fallback_model"),
            temperature=_optional_float(raw.get("temperature", self.temperature), f"{self.task}.temperature"),
            max_tokens=_optional_int(raw.get("max_tokens", self.max_tokens), f"{self.task}.max_tokens"),
        )


class ModelRouter:
    def __init__(self, client: MiMoChatClient, routes: Mapping[str, ModelRoute]) -> None:
        self._client = client
        self._routes = dict(routes)

    @classmethod
    def from_settings(cls, settings: Settings, client: MiMoChatClient | None = None) -> "ModelRouter":
        client_config = MiMoClientConfig.from_settings(settings)
        chat_client = client or MiMoChatClient(client_config)
        routes = build_routes(default_model=client_config.default_model, routes_json=settings.mimo_model_routes_json)
        return cls(chat_client, routes)

    async def aclose(self) -> None:
        await self._client.aclose()

    def resolve(self, task: str | None = None) -> ModelRoute:
        task_name = normalize_task(task or "default")
        return self._routes.get(task_name) or self._routes["default"]

    async def complete(
        self,
        task: str,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
        allow_fallback: bool = True,
    ) -> ChatResponse:
        route = self.resolve(task)
        request_temperature = temperature if temperature is not None else route.temperature
        request_max_tokens = max_tokens if max_tokens is not None else route.max_tokens

        try:
            return await self._client.complete(
                messages,
                model=route.model,
                temperature=request_temperature,
                max_tokens=request_max_tokens,
                tools=tools,
                response_format=response_format,
            )
        except MiMoError as exc:
            if not should_use_fallback(
                exc,
                request_model=route.model,
                fallback_model=route.fallback_model,
                allow_fallback=allow_fallback,
            ):
                raise

        return await self._client.complete(
            messages,
            model=route.fallback_model,
            temperature=request_temperature,
            max_tokens=request_max_tokens,
            tools=tools,
            response_format=response_format,
        )


def build_routes(*, default_model: str, routes_json: str | None) -> dict[str, ModelRoute]:
    base_routes = {task: ModelRoute.default_for(task, model=default_model) for task in DEFAULT_TASK_PARAMS}
    overrides = parse_routes_json(routes_json)
    for raw_task, raw_route in overrides.items():
        task = normalize_task(raw_task)
        route = base_routes.get(task) or ModelRoute.default_for(task, model=default_model)
        base_routes[task] = route.with_override(raw_route)
    return base_routes


def parse_routes_json(routes_json: str | None) -> dict[str, Any]:
    if routes_json is None or not routes_json.strip():
        return {}
    try:
        parsed = json.loads(routes_json)
    except json.JSONDecodeError as exc:
        raise ModelRouterConfigError(f"MIMO_MODEL_ROUTES_JSON is invalid JSON: {exc.msg}") from exc
    if isinstance(parsed, Mapping) and "routes" in parsed:
        parsed = parsed["routes"]
    if not isinstance(parsed, Mapping):
        raise ModelRouterConfigError("MIMO_MODEL_ROUTES_JSON must be an object or contain routes")
    return dict(parsed)


def normalize_task(task: str) -> str:
    return task.strip().lower().replace("-", "_")


def should_use_fallback(
    error: MiMoError,
    *,
    request_model: str,
    fallback_model: str | None,
    allow_fallback: bool,
) -> bool:
    return bool(allow_fallback and error.retryable and fallback_model and fallback_model != request_model)


def _string_value(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelRouterConfigError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _string_value(value, field_name)


def _optional_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelRouterConfigError(f"{field_name} must be numeric")
    return float(value)


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelRouterConfigError(f"{field_name} must be an integer")
    if value <= 0:
        raise ModelRouterConfigError(f"{field_name} must be positive")
    return value
