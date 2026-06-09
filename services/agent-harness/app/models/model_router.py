import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import Settings
from app.models.mimo_client import (
    ChatMessage,
    ChatResponse,
    ChatStreamChunk,
    MiMoChatClient,
    MiMoClientConfig,
    MiMoError,
)
from app.models.structured_output import OutputModelT, response_format_for_model, validate_chat_response_with_retries


ModelTask = Literal[
    "default",
    "question_planning",
    "examiner",
    "followup_planning",
    "scoring",
    "feedback",
    "cheap",
]

DEFAULT_TASKS: tuple[ModelTask, ...] = (
    "default",
    "question_planning",
    "examiner",
    "followup_planning",
    "scoring",
    "feedback",
    "cheap",
)

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
            raise ModelRouterConfigError(f"{self.task} 路由配置必须是对象或模型名字符串")

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
        routes = build_routes(
            default_model=client_config.default_model,
            routes_json=settings.mimo_model_routes_json,
        )
        return cls(chat_client, routes)

    async def __aenter__(self) -> "ModelRouter":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def resolve(self, task: str | ModelTask | None = None) -> ModelRoute:
        task_name = normalize_task(task or "default")
        return self._routes.get(task_name) or self._routes["default"]

    async def complete(
        self,
        task: str | ModelTask,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        *,
        model: str | None = None,
        fallback_model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
        allow_fallback: bool = True,
    ) -> ChatResponse:
        route = self.resolve(task)
        request_model = model or route.model
        request_temperature = temperature if temperature is not None else route.temperature
        request_max_tokens = max_tokens if max_tokens is not None else route.max_tokens
        fallback = fallback_model if fallback_model is not None else route.fallback_model

        try:
            return await self._client.complete(
                messages,
                model=request_model,
                temperature=request_temperature,
                max_tokens=request_max_tokens,
                tools=tools,
                response_format=response_format,
            )
        except MiMoError as exc:
            if not should_use_fallback(exc, request_model=request_model, fallback_model=fallback, allow_fallback=allow_fallback):
                raise

        return await self._client.complete(
            messages,
            model=fallback,
            temperature=request_temperature,
            max_tokens=request_max_tokens,
            tools=tools,
            response_format=response_format,
        )

    async def complete_structured(
        self,
        task: str | ModelTask,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        *,
        output_model: type[OutputModelT],
        model: str | None = None,
        fallback_model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
        allow_fallback: bool = True,
        max_validation_retries: int = 1,
    ) -> OutputModelT:
        structured_response_format = response_format or response_format_for_model(output_model)

        async def generate(
            current_messages: Sequence[ChatMessage | Mapping[str, Any]],
            current_response_format: Mapping[str, Any],
        ) -> ChatResponse:
            return await self.complete(
                task,
                current_messages,
                model=model,
                fallback_model=fallback_model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                response_format=current_response_format,
                allow_fallback=allow_fallback,
            )

        return await validate_chat_response_with_retries(
            generate=generate,
            messages=messages,
            model_type=output_model,
            response_format=structured_response_format,
            max_validation_retries=max_validation_retries,
        )

    async def stream(
        self,
        task: str | ModelTask,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        *,
        model: str | None = None,
        fallback_model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
        allow_fallback: bool = True,
    ) -> AsyncIterator[ChatStreamChunk]:
        route = self.resolve(task)
        request_model = model or route.model
        request_temperature = temperature if temperature is not None else route.temperature
        request_max_tokens = max_tokens if max_tokens is not None else route.max_tokens
        fallback = fallback_model if fallback_model is not None else route.fallback_model

        try:
            async for chunk in self._client.stream(
                messages,
                model=request_model,
                temperature=request_temperature,
                max_tokens=request_max_tokens,
                tools=tools,
                response_format=response_format,
            ):
                yield chunk
            return
        except MiMoError as exc:
            if not should_use_fallback(exc, request_model=request_model, fallback_model=fallback, allow_fallback=allow_fallback):
                raise

        async for chunk in self._client.stream(
            messages,
            model=fallback,
            temperature=request_temperature,
            max_tokens=request_max_tokens,
            tools=tools,
            response_format=response_format,
        ):
            yield chunk


def build_routes(*, default_model: str, routes_json: str | None) -> dict[str, ModelRoute]:
    base_routes = {task: ModelRoute.default_for(task, model=default_model) for task in DEFAULT_TASKS}
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
        raise ModelRouterConfigError(f"MIMO_MODEL_ROUTES_JSON 不是合法 JSON：{exc.msg}") from exc

    if isinstance(parsed, Mapping) and "routes" in parsed:
        parsed = parsed["routes"]
    if not isinstance(parsed, Mapping):
        raise ModelRouterConfigError("MIMO_MODEL_ROUTES_JSON 必须是对象，或包含 routes 对象")
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
    return bool(
        allow_fallback
        and error.retryable
        and fallback_model
        and fallback_model != request_model
    )


def _string_value(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelRouterConfigError(f"{field_name} 必须是非空字符串")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _string_value(value, field_name)


def _optional_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelRouterConfigError(f"{field_name} 必须是数字")
    if value < 0 or value > 2:
        raise ModelRouterConfigError(f"{field_name} 必须在 0 到 2 之间")
    return float(value)


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelRouterConfigError(f"{field_name} 必须是整数")
    if value <= 0:
        raise ModelRouterConfigError(f"{field_name} 必须大于 0")
    return value
