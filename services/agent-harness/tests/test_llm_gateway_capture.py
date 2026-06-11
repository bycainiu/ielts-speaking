"""LLM 网关捕获 + 实时流 + trace 集成测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.agents.examiner_agent import ExaminerAgent, ExaminerTurnInput
from app.agents.followup_planner_agent import FollowupPlannerAgent, FollowupPlannerInput
from app.core.config import Settings
from app.models.llm_gateway import LlmGateway, LlmTextResult
from app.models.mimo_client import ChatStreamChunk, ChatUsage, MiMoAPIError
from app.observability.langfuse_client import (
    build_trace_steps,
    live_streamed_texts,
    publish_trace_stream_events,
    run_summary,
    trace_llm_calls_from_capture,
    AgentRunTrace,
)
from app.observability.llm_capture import (
    CapturedLlmCall,
    LiveStreamContext,
    get_llm_capture_sink,
    reset_live_stream_context,
    reset_llm_capture_sink,
    set_live_stream_context,
)
from app.observability.streaming import AgentRunStreamBroker
from app.protocols.schemas import AgentResponse, PlanRequest, SessionEvent


@pytest.fixture(autouse=True)
def clean_capture_sink():
    reset_llm_capture_sink()
    yield
    reset_llm_capture_sink()


class FakeRoute:
    model = "mimo-v2.5-pro"


class FakeRouter:
    def __init__(self, chunks=None, error=None):
        self.chunks = chunks or []
        self.error = error
        self.calls: list[dict] = []

    def resolve(self, task):
        return FakeRoute()

    async def stream(self, task, messages, **kwargs):
        self.calls.append({"task": task, "messages": messages, **kwargs})
        if self.error is not None:
            raise self.error
        for chunk in self.chunks:
            yield chunk


def make_gateway(chunks=None, error=None) -> tuple[LlmGateway, FakeRouter]:
    router = FakeRouter(chunks=chunks, error=error)
    gateway = LlmGateway(Settings(), router=router, enabled=True)
    return gateway, router


def text_chunks():
    return [
        ChatStreamChunk(reasoning_delta="Candidate asked about hometown. Keep it neutral and short. " * 3),
        ChatStreamChunk(delta="Let's talk about your hometown. "),
        ChatStreamChunk(delta="Where is your hometown?", raw={"model": "mimo-v2.5-pro"}),
        ChatStreamChunk(finish_reason="stop", usage=ChatUsage(input_tokens=120, output_tokens=18, total_tokens=138)),
    ]


def test_generate_text_records_capture_and_streams_live_events():
    gateway, _ = make_gateway(chunks=text_chunks())
    broker = AgentRunStreamBroker()
    token = set_live_stream_context(LiveStreamContext(broker=broker, run_id="run_live", session_id="sess_live"))
    try:
        result = gateway.generate_text(
            task="examiner",
            call_name="examiner_turn",
            agent_name="ExaminerAgent",
            prompt_version="examiner_turn.llm.v1",
            messages=[{"role": "user", "content": "ask the hometown question"}],
        )
    finally:
        reset_live_stream_context(token)

    assert result is not None
    assert "Where is your hometown?" in result.text
    assert result.reasoning_text and "neutral" in result.reasoning_text
    assert result.usage is not None and result.usage.input_tokens == 120

    records = get_llm_capture_sink().records
    assert len(records) == 1
    record = records[0]
    assert record.status == "completed"
    assert record.call_name == "examiner_turn"
    assert record.model_name == "mimo-v2.5-pro"
    assert record.content_streamed is True
    assert record.reasoning_streamed is True
    assert record.stream_event_count >= 3

    events = broker.history("run_live")
    kinds = [event.kind for event in events]
    assert "message.delta" in kinds
    assert "reasoning.delta" in kinds
    assert "usage.updated" in kinds
    live_message = next(event for event in events if event.kind == "message.delta")
    assert live_message.payload.get("source") == "live"
    assert live_message.payload.get("llm_call_name") == "examiner_turn"


def test_generate_structured_parses_output_without_message_delta():
    json_payload = '{"decision": "ask_followup", "reason": "回答太短", "confidence": 0.82, "suggested_question": "Why is that?"}'
    chunks = [
        ChatStreamChunk(reasoning_delta="Answer is only five words, below the Part 1 benchmark." * 2),
        ChatStreamChunk(delta=json_payload),
        ChatStreamChunk(finish_reason="stop"),
    ]
    gateway, _ = make_gateway(chunks=chunks)
    broker = AgentRunStreamBroker()
    token = set_live_stream_context(LiveStreamContext(broker=broker, run_id="run_struct", session_id="sess_struct"))
    try:
        from app.models.output_schemas import FollowupDecisionOutput

        decision = gateway.generate_structured(
            task="followup_planning",
            call_name="followup_plan",
            agent_name="FollowupPlannerAgent",
            messages=[{"role": "user", "content": "decide"}],
            output_model=FollowupDecisionOutput,
        )
    finally:
        reset_live_stream_context(token)

    assert decision is not None
    assert decision.decision == "ask_followup"
    assert decision.suggested_question == "Why is that?"

    record = get_llm_capture_sink().records[0]
    assert record.parsed_output["decision"] == "ask_followup"
    # 结构化 JSON 不应作为 message.delta 进入用户可见时间线
    kinds = [event.kind for event in broker.history("run_struct")]
    assert "message.delta" not in kinds
    assert "reasoning.delta" in kinds


def test_generate_text_failure_records_failed_capture_and_returns_none():
    gateway, _ = make_gateway(error=MiMoAPIError("upstream down", code="api_error", retryable=False))
    result = gateway.generate_text(
        task="examiner",
        call_name="examiner_turn",
        agent_name="ExaminerAgent",
        messages=[{"role": "user", "content": "ask"}],
    )
    assert result is None
    records = get_llm_capture_sink().records
    assert len(records) == 1
    assert records[0].status == "failed"
    assert records[0].error_code == "api_error"


def test_examiner_agent_falls_back_to_rules_when_gateway_fails():
    gateway, _ = make_gateway(error=MiMoAPIError("boom", code="api_error", retryable=False))
    agent = ExaminerAgent(llm_gateway=gateway)
    utterance = agent.build_turn(
        ExaminerTurnInput(
            mode="full_exam",
            part=1,
            question_id="q1",
            question_text="Where is your hometown?",
            question_index=0,
            total_questions=2,
        )
    )
    assert utterance.generated_by == "rules"
    assert "hometown" in utterance.text.lower()


def test_examiner_agent_uses_llm_output_and_reasoning():
    gateway, _ = make_gateway(chunks=text_chunks())
    agent = ExaminerAgent(llm_gateway=gateway)
    utterance = agent.build_turn(
        ExaminerTurnInput(
            mode="full_exam",
            part=1,
            question_id="q1",
            question_text="Where is your hometown?",
            question_index=0,
            total_questions=2,
        )
    )
    assert utterance.generated_by == "llm"
    assert "llm_generated" in utterance.style_tags
    assert utterance.reasoning_text


def test_followup_planner_caps_llm_followup_decision():
    json_payload = '{"decision": "ask_followup", "reason": "想继续追问", "confidence": 0.9, "suggested_question": "More?"}'
    gateway, _ = make_gateway(chunks=[ChatStreamChunk(delta=json_payload), ChatStreamChunk(finish_reason="stop")])
    planner = FollowupPlannerAgent(llm_gateway=gateway)
    plan = planner.plan(
        FollowupPlannerInput(
            mode="full_exam",
            part=1,
            asr_text="short answer",
            question_text="Where is your hometown?",
            followup_count=1,
        )
    )
    # 已达单题追问上限，LLM 的 ask_followup 决策必须被钳制
    assert plan.decision.decision == "next_question"
    assert plan.next_action == "ask_next_question"


def make_examiner_capture(**overrides) -> CapturedLlmCall:
    defaults = dict(
        call_name="examiner_turn",
        agent_name="ExaminerAgent",
        task="examiner",
        provider="mimo",
        status="completed",
        model_name="mimo-v2.5-pro",
        prompt_version="examiner_turn.llm.v1",
        request_messages=[{"role": "user", "content": "ask"}],
        response_content="Let's talk about your hometown. Where is your hometown?",
        reasoning_text="Pick a neutral opener for Part 1.",
        stream_event_count=3,
        content_streamed=True,
        reasoning_streamed=True,
        latency_ms=420,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return CapturedLlmCall(**defaults)


def build_plan_response(run_id: str = "run_trace") -> tuple[PlanRequest, AgentResponse]:
    request = PlanRequest(mode="full_exam", user_id="user-1")
    examiner_event = SessionEvent(
        type="examiner.message",
        session_id="sess-1",
        run_id=run_id,
        payload={"part": 1, "question_id": "q1", "text": "Let's talk about your hometown. Where is your hometown?"},
        created_at=datetime.now(UTC),
    )
    thinking_event = SessionEvent(
        type="examiner.thinking",
        session_id="sess-1",
        run_id=run_id,
        payload={"part": 1, "question_id": "q1", "text": "Pick a neutral opener for Part 1.", "generated_by": "llm"},
        created_at=datetime.now(UTC),
    )
    response = AgentResponse(
        run_id=run_id,
        events=[thinking_event, examiner_event],
        state={"mode": "full_exam", "current_part": 1, "question_index": 0},
        next_action="wait_for_user_answer",
    )
    return request, response


def test_build_trace_steps_prefers_captured_llm_calls():
    settings = Settings()
    record = make_examiner_capture()
    captured = trace_llm_calls_from_capture(settings, [record])
    request, response = build_plan_response()

    now = datetime.now(UTC)
    steps = build_trace_steps(
        settings=settings,
        workflow_node="plan_session",
        request=request,
        response=response,
        trace_part=1,
        trace_question_id="q1",
        status="completed",
        latency_ms=900,
        error_code=None,
        started_at=now,
        finished_at=now,
        tool_calls=[],
        captured_llm_calls=captured,
    )

    examiner_steps = [step for step in steps if step.workflow_node == "examiner_turn"]
    assert len(examiner_steps) == 1
    examiner_step = examiner_steps[0]
    assert examiner_step.execution_kind == "llm"
    assert examiner_step.model_name == "mimo-v2.5-pro"
    assert len(examiner_step.llm_calls) == 1
    call = examiner_step.llm_calls[0]
    assert call.payload_origin == "captured"
    assert call.execution_kind == "llm"
    assert call.reasoning_blocks and "neutral opener" in (call.reasoning_blocks[0].text or "")

    trace = AgentRunTrace(
        run_id="run_trace",
        session_id="sess-1",
        status="completed",
        started_at=now,
        finished_at=now,
        steps=steps,
    )
    assert run_summary(trace).llm_call_count == 1


def test_publish_trace_stream_events_deduplicates_live_streamed_texts():
    settings = Settings()
    record = make_examiner_capture()
    captured = trace_llm_calls_from_capture(settings, [record])
    live_texts = live_streamed_texts([record])
    request, response = build_plan_response()

    now = datetime.now(UTC)
    steps = build_trace_steps(
        settings=settings,
        workflow_node="plan_session",
        request=request,
        response=response,
        trace_part=1,
        trace_question_id="q1",
        status="completed",
        latency_ms=900,
        error_code=None,
        started_at=now,
        finished_at=now,
        tool_calls=[],
        captured_llm_calls=captured,
    )
    trace = AgentRunTrace(
        run_id="run_trace",
        session_id="sess-1",
        status="completed",
        started_at=now,
        finished_at=now,
        steps=steps,
    )

    broker = AgentRunStreamBroker()
    publish_trace_stream_events(
        broker,
        trace,
        response.events,
        terminal_status="completed",
        terminal_error_code=None,
        live_streamed_texts=live_texts,
    )
    events = broker.history("run_trace")
    kinds = [event.kind for event in events]
    assert "question.requested" in kinds
    assert "run.completed" in kinds
    # 实时阶段已经流过的考官台词与 thinking 文本不会重复补发
    duplicated_messages = [
        event for event in events
        if event.kind == "message.delta" and (event.content_delta or "").startswith("Let's talk about your hometown")
    ]
    assert not duplicated_messages
    duplicated_reasoning = [
        event for event in events
        if event.kind == "reasoning.delta" and "neutral opener" in (event.reasoning_delta or "")
    ]
    assert not duplicated_reasoning


def test_publish_trace_stream_events_replays_when_not_streamed_live():
    settings = Settings()
    record = make_examiner_capture(stream_event_count=0, content_streamed=False, reasoning_streamed=False)
    captured = trace_llm_calls_from_capture(settings, [record])
    request, response = build_plan_response()

    now = datetime.now(UTC)
    steps = build_trace_steps(
        settings=settings,
        workflow_node="plan_session",
        request=request,
        response=response,
        trace_part=1,
        trace_question_id="q1",
        status="completed",
        latency_ms=900,
        error_code=None,
        started_at=now,
        finished_at=now,
        tool_calls=[],
        captured_llm_calls=captured,
    )
    trace = AgentRunTrace(
        run_id="run_trace2",
        session_id="sess-1",
        status="completed",
        started_at=now,
        finished_at=now,
        steps=steps,
    )

    broker = AgentRunStreamBroker()
    publish_trace_stream_events(
        broker,
        trace,
        response.events,
        terminal_status="completed",
        terminal_error_code=None,
        live_streamed_texts=set(),
    )
    events = broker.history("run_trace2")
    assert any(
        event.kind == "message.delta" and (event.content_delta or "").startswith("Let's talk about your hometown")
        for event in events
    )
    assert any(
        event.kind == "reasoning.delta" and "neutral opener" in (event.reasoning_delta or "")
        for event in events
    )


def test_examiner_agent_with_fake_gateway_result_passthrough():
    class StubGateway:
        enabled = True

        def generate_text(self, **kwargs):
            return LlmTextResult(
                text="Now, let's move on to your hometown. Where is your hometown?",
                reasoning_text="keep neutral",
                model_name="mimo-v2.5-pro",
                usage=None,
            )

    agent = ExaminerAgent(llm_gateway=StubGateway())
    utterance = agent.build_turn(
        ExaminerTurnInput(
            mode="full_exam",
            part=1,
            question_id="q1",
            question_text="Where is your hometown?",
            question_index=0,
            total_questions=2,
        )
    )
    assert utterance.generated_by == "llm"
    assert utterance.reasoning_text == "keep neutral"
