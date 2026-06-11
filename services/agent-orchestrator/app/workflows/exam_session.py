from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import uuid4

from app.agents.exam_director import ExamDirector
from app.agents.live_examiner import LiveExaminerAgent
from app.agents.question_strategist import QuestionStrategistAgent
from app.agents.response_analyzer import ResponseAnalyzerAgent
from app.clients.harness_fallback import AgentHarnessFallbackClient
from app.core.config import Settings, get_settings
from app.llm.gateway import LlmGateway
from app.llm.tool_loop import AgentToolLoop
from app.observability.trace import OrchestratorTraceRecorder
from app.protocols.message_bus import InMemoryMessageBus
from app.protocols.schemas import (
    AgentResponse,
    ConsumeAsrRequest,
    NextTurnRequest,
    PlanRequest,
    ScoreSessionRequest,
)
from app.safety.guardrail import GuardrailAgent
from app.tools.registry import ToolRegistry


logger = logging.getLogger("agent_orchestrator.exam_session")


class ExamSessionWorkflow:
    def __init__(self, settings: Settings, trace_recorder: OrchestratorTraceRecorder) -> None:
        self._trace = trace_recorder
        self._fallback = AgentHarnessFallbackClient.from_settings(settings)
        self._bus = InMemoryMessageBus(trace_recorder)
        gateway = LlmGateway.from_settings(settings)
        tool_registry = ToolRegistry()
        guardrail = GuardrailAgent()
        tool_loop = AgentToolLoop(
            gateway,
            tool_registry,
            guardrail,
            trace_recorder,
            max_iterations=settings.orchestrator_tool_loop_max_iterations,
        )
        self._question_strategist = QuestionStrategistAgent(self._bus, tool_loop, trace_recorder)
        self._live_examiner = LiveExaminerAgent(self._bus, tool_loop, trace_recorder)
        self._response_analyzer = ResponseAnalyzerAgent(self._bus, tool_loop, trace_recorder)
        self._director = ExamDirector(self._bus, agent_timeout=settings.orchestrator_agent_timeout_seconds, trace_recorder=trace_recorder)
        self._specialists = (self._question_strategist, self._live_examiner, self._response_analyzer)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ExamSessionWorkflow":
        resolved = settings or get_settings()
        trace = OrchestratorTraceRecorder(resolved)
        return cls(resolved, trace)

    async def plan(self, session_id: str, request: PlanRequest) -> AgentResponse:
        run_id = request.run_id_override or f"run_{uuid4().hex}"
        return await self._invoke(
            "plan",
            lambda: self._director.handle_plan(session_id, request, run_id=run_id),
            lambda: self._fallback.plan(session_id, request) if self._fallback else None,
        )

    async def consume_asr(self, session_id: str, request: ConsumeAsrRequest) -> AgentResponse:
        run_id = request.run_id_override or f"run_{uuid4().hex}"
        return await self._invoke(
            "consume_asr",
            lambda: self._director.handle_consume_asr(session_id, request, run_id=run_id),
            lambda: self._fallback.consume_asr(session_id, request) if self._fallback else None,
        )

    async def next_turn(self, session_id: str, request: NextTurnRequest) -> AgentResponse:
        run_id = request.run_id_override or f"run_{uuid4().hex}"
        return await self._invoke(
            "next_turn",
            lambda: self._director.handle_next_turn(session_id, request, run_id=run_id),
            lambda: self._fallback.next_turn(session_id, request) if self._fallback else None,
        )

    async def score_session(self, session_id: str, request: ScoreSessionRequest) -> AgentResponse:
        run_id = request.run_id_override or f"run_{uuid4().hex}"
        return await self._invoke(
            "score_session",
            lambda: self._director.handle_score(session_id, request, run_id=run_id),
            lambda: self._fallback.score_session(session_id, request) if self._fallback else None,
        )

    async def _invoke(
        self,
        workflow_node: str,
        primary: Callable[[], Awaitable[AgentResponse]],
        fallback: Callable[[], Awaitable[AgentResponse] | None],
    ) -> AgentResponse:
        try:
            return await primary()
        except Exception:
            logger.exception("orchestrator_workflow_failed", extra={"workflow_node": workflow_node})
            if self._fallback is None:
                raise
            logger.warning("orchestrator_using_harness_fallback", extra={"workflow_node": workflow_node})
            result = await fallback()
            if result is None:
                raise
            return result
