from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.llm.tool_loop import AgentToolLoop
from app.observability.trace import OrchestratorTraceRecorder
from app.protocols.agent_message import AgentMessage
from app.protocols.message_bus import InMemoryMessageBus


class BaseSpecialistAgent(ABC):
    agent_name: str

    def __init__(
        self,
        message_bus: InMemoryMessageBus,
        tool_loop: AgentToolLoop,
        trace_recorder: OrchestratorTraceRecorder,
    ) -> None:
        self._bus = message_bus
        self._tool_loop = tool_loop
        self._trace = trace_recorder
        message_bus.subscribe(self.agent_name, self.handle_message)

    async def handle_message(self, message: AgentMessage) -> None:
        self._trace.stream_broker.publish(
            run_id=message.run_id,
            session_id=message.session_id,
            kind="agent.activated",
            phase=self.agent_name,
            payload={"agent_name": self.agent_name, "message_type": message.message_type},
        )
        try:
            await self._handle(message)
        finally:
            self._trace.stream_broker.publish(
                run_id=message.run_id,
                session_id=message.session_id,
                kind="agent.deactivated",
                phase=self.agent_name,
                payload={"agent_name": self.agent_name},
            )

    @abstractmethod
    async def _handle(self, message: AgentMessage) -> None: ...

    async def _reply(self, request: AgentMessage, payload: dict[str, Any], *, message_type: str) -> None:
        await self._bus.reply(request, payload, message_type=message_type)
