from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.observability.trace import OrchestratorTraceRecorder
from app.protocols.agent_message import (
    RESULT_QUESTIONS_PLANNED,
    TASK_PLAN_QUESTIONS,
    SessionContext,
)
from app.protocols.message_bus import InMemoryMessageBus, MessageBusTimeoutError


def _context(session_id: str = "sess_bus") -> SessionContext:
    return SessionContext(session_id=session_id, mode="full_exam")


def _message(
    *,
    message_id: str,
    run_id: str,
    session_id: str,
    source_agent: str,
    target_agent: str,
    message_type: str,
    reply_to: str | None = None,
) -> object:
    from app.protocols.agent_message import AgentMessage

    return AgentMessage(
        message_id=message_id,
        run_id=run_id,
        session_id=session_id,
        source_agent=source_agent,
        target_agent=target_agent,
        message_type=message_type,  # type: ignore[arg-type]
        payload={},
        reply_to=reply_to,
        context=_context(session_id),
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def trace_recorder() -> OrchestratorTraceRecorder:
    get_settings.cache_clear()
    return OrchestratorTraceRecorder(get_settings())


@pytest.fixture
def message_bus(trace_recorder: OrchestratorTraceRecorder) -> InMemoryMessageBus:
    return InMemoryMessageBus(trace_recorder)


@pytest.mark.asyncio
async def test_send_records_history(message_bus: InMemoryMessageBus) -> None:
    message = _message(
        message_id="msg_1",
        run_id="run_1",
        session_id="sess_1",
        source_agent="exam_director",
        target_agent="question_strategist",
        message_type=TASK_PLAN_QUESTIONS,
    )
    await message_bus.send(message)
    history = message_bus.history("sess_1")
    assert len(history) == 1
    assert history[0].message_id == "msg_1"


@pytest.mark.asyncio
async def test_request_reply_round_trip(message_bus: InMemoryMessageBus) -> None:
    request_id = f"msg_{uuid4().hex}"
    run_id = "run_reply"
    session_id = "sess_reply"

    async def strategist_handler(message) -> None:
        if message.message_type != TASK_PLAN_QUESTIONS:
            return
        await message_bus.reply(
            message,
            {"question_plan": {"parts": []}},
            message_type=RESULT_QUESTIONS_PLANNED,
        )

    message_bus.subscribe("question_strategist", strategist_handler)
    request = _message(
        message_id=request_id,
        run_id=run_id,
        session_id=session_id,
        source_agent="exam_director",
        target_agent="question_strategist",
        message_type=TASK_PLAN_QUESTIONS,
    )
    response = await message_bus.request(request, timeout=1.0)
    assert response.reply_to == request_id
    assert response.message_type == RESULT_QUESTIONS_PLANNED
    assert response.payload["question_plan"]["parts"] == []


@pytest.mark.asyncio
async def test_request_timeout(message_bus: InMemoryMessageBus) -> None:
    request = _message(
        message_id=f"msg_{uuid4().hex}",
        run_id="run_timeout",
        session_id="sess_timeout",
        source_agent="exam_director",
        target_agent="question_strategist",
        message_type=TASK_PLAN_QUESTIONS,
    )
    with pytest.raises(MessageBusTimeoutError):
        await message_bus.request(request, timeout=0.05)
