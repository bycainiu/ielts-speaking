import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.models.mimo_client import ChatMessage, ChatResponse
from app.models.model_router import ModelRouter
from app.models.output_schemas import (
    CriterionScoreOutput,
    ExaminerMessageOutput,
    FeedbackPlanOutput,
    FollowupDecisionOutput,
)
from app.models.structured_output import (
    RecoverableStructuredOutputError,
    build_recoverable_error_event,
    parse_structured_output,
    response_format_for_model,
    validate_chat_response_with_retries,
)
from app.observability.langfuse_client import TraceRecorder, TraceStore
from app.protocols.schemas import PlanRequest


def run(coro):
    return asyncio.run(coro)


class FollowupDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class FakeStructuredClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

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
        content = self.responses.pop(0)
        return ChatResponse(model=model or "mock", content=content, finish_reason="stop")

    async def stream(self, *args: Any, **kwargs: Any):
        raise NotImplementedError

    async def aclose(self) -> None:
        pass


def test_parse_structured_output_accepts_markdown_json() -> None:
    parsed = parse_structured_output(
        '```json\n{"decision":"ask_next","reason":"The answer was short."}\n```',
        FollowupDecision,
    )

    assert parsed.decision == "ask_next"
    assert parsed.reason == "The answer was short."


def test_parse_structured_output_rejects_extra_fields() -> None:
    with pytest.raises(RecoverableStructuredOutputError) as exc:
        parse_structured_output(
            '{"decision":"ask_next","reason":"ok","unsafe_extra":"nope"}',
            FollowupDecision,
        )

    assert exc.value.code == "structured_output_invalid"
    assert exc.value.validation_errors


def test_response_format_uses_model_json_schema() -> None:
    response_format = response_format_for_model(FollowupDecision)

    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "FollowupDecision"
    assert response_format["json_schema"]["strict"] is True
    assert "decision" in response_format["json_schema"]["schema"]["properties"]


def test_validate_chat_response_retries_with_repair_instruction() -> None:
    calls: list[list[ChatMessage | Mapping[str, Any]]] = []
    responses = [
        ChatResponse(model="mock", content="not json", finish_reason="stop"),
        ChatResponse(model="mock", content='{"decision":"ask_next","reason":"valid after repair"}', finish_reason="stop"),
    ]

    async def generate(messages: Sequence[ChatMessage | Mapping[str, Any]], _: Mapping[str, Any]) -> ChatResponse:
        calls.append(list(messages))
        return responses.pop(0)

    parsed = run(
        validate_chat_response_with_retries(
            generate=generate,
            messages=[ChatMessage(role="user", content="Return a followup decision.")],
            model_type=FollowupDecision,
            max_validation_retries=1,
        )
    )

    assert parsed.reason == "valid after repair"
    assert len(calls) == 2
    assert len(calls[1]) == 2
    assert isinstance(calls[1][-1], ChatMessage)
    assert "failed the required JSON schema validation" in calls[1][-1].content


def test_validate_chat_response_returns_recoverable_error_after_retries() -> None:
    async def generate(_: Sequence[ChatMessage | Mapping[str, Any]], __: Mapping[str, Any]) -> ChatResponse:
        return ChatResponse(model="mock", content="still not json", finish_reason="stop")

    with pytest.raises(RecoverableStructuredOutputError):
        run(
            validate_chat_response_with_retries(
                generate=generate,
                messages=[ChatMessage(role="user", content="Return JSON.")],
                model_type=FollowupDecision,
                max_validation_retries=0,
            )
        )


def test_model_router_complete_structured_injects_response_format_and_validates() -> None:
    fake_client = FakeStructuredClient(['{"decision":"ask_next","reason":"schema passed"}'])
    router = ModelRouter.from_settings(make_settings(), client=fake_client)  # type: ignore[arg-type]

    parsed = run(
        router.complete_structured(
            "followup_planning",
            [ChatMessage(role="user", content="Decide next step.")],
            output_model=FollowupDecision,
        )
    )

    assert parsed.decision == "ask_next"
    assert fake_client.calls[0]["response_format"]["type"] == "json_schema"
    assert fake_client.calls[0]["model"] == "mimo-v2.5-pro"


def test_recoverable_error_event_can_be_forwarded_to_frontend() -> None:
    error = RecoverableStructuredOutputError("invalid model JSON")

    event = build_recoverable_error_event(
        session_id="sess_001",
        run_id="run_001",
        error=error,
        workflow_node="followup_planning",
    )

    assert event.type == "error.recoverable"
    assert event.payload["error_code"] == "structured_output_invalid"
    assert event.payload["workflow_node"] == "followup_planning"


def test_structured_output_error_code_is_recorded_to_trace() -> None:
    store = TraceStore()
    recorder = TraceRecorder(make_settings(), store=store)
    request = PlanRequest(mode="full_exam", user_id="user_001")

    with pytest.raises(RecoverableStructuredOutputError):
        recorder.record_agent_call(
            session_id="sess_001",
            workflow_node="structured_output_test",
            request=request,
            call=lambda: (_ for _ in ()).throw(RecoverableStructuredOutputError("bad json")),
        )

    trace = next(iter(store._runs.values()))
    assert trace.status == "failed"
    assert trace.steps[0].error_code == "structured_output_invalid"


def test_key_agent_output_schemas_are_strict_and_json_schema_ready() -> None:
    schema_models = [
        ExaminerMessageOutput,
        FollowupDecisionOutput,
        CriterionScoreOutput,
        FeedbackPlanOutput,
    ]

    for schema_model in schema_models:
        response_format = response_format_for_model(schema_model)
        assert response_format["json_schema"]["schema"]["additionalProperties"] is False
        assert response_format["json_schema"]["schema"]["properties"]

    with pytest.raises(RecoverableStructuredOutputError):
        parse_structured_output(
            '{"decision":"next_question","reason":"ok","confidence":0.8,"extra":"blocked"}',
            FollowupDecisionOutput,
        )


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
        "LANGFUSE_ENABLED": False,
    }
    values.update(overrides)
    return Settings(**values)
