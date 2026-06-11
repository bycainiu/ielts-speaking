from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.observability.trace import OrchestratorTraceRecorder
from app.protocols.agent_message import AgentMessage


MessageHandler = Callable[[AgentMessage], Awaitable[None] | None]


class MessageBusTimeoutError(TimeoutError):
    pass


class InMemoryMessageBus:
    def __init__(self, trace_recorder: OrchestratorTraceRecorder) -> None:
        self._trace = trace_recorder
        self._handlers: dict[str, list[MessageHandler]] = defaultdict(list)
        self._history: dict[str, list[AgentMessage]] = defaultdict(list)
        self._pending: dict[str, asyncio.Future[AgentMessage]] = {}
        self._lock = asyncio.Lock()

    async def send(self, message: AgentMessage) -> None:
        self._trace.record_agent_message(message)
        self._history[message.session_id].append(message)
        self._trace.stream_broker.publish(
            run_id=message.run_id,
            session_id=message.session_id,
            kind="agent.message_sent",
            phase=message.source_agent,
            payload={
                "agent": message.source_agent,
                "target": message.target_agent,
                "type": message.message_type,
                "message_id": message.message_id,
                "payload": message.payload,
            },
            visibility="admin",
        )
        handlers = list(self._handlers.get(message.target_agent, []))
        for handler in handlers:
            result = handler(message)
            if asyncio.iscoroutine(result):
                await result

    async def request(self, message: AgentMessage, timeout: float = 30.0) -> AgentMessage:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[AgentMessage] = loop.create_future()
        self._pending[message.message_id] = future

        async def _reply_handler(inbound: AgentMessage) -> None:
            if inbound.reply_to != message.message_id:
                return
            if not future.done():
                future.set_result(inbound)
            self._trace.stream_broker.publish(
                run_id=inbound.run_id,
                session_id=inbound.session_id,
                kind="agent.message_received",
                phase=inbound.target_agent,
                payload={
                    "agent": inbound.target_agent,
                    "source": inbound.source_agent,
                    "type": inbound.message_type,
                    "message_id": inbound.message_id,
                    "reply_to": inbound.reply_to,
                    "payload": inbound.payload,
                },
                visibility="admin",
            )

        self.subscribe(message.source_agent, _reply_handler)
        try:
            await self.send(message)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise MessageBusTimeoutError(
                f"timeout waiting for reply to {message.message_id} from {message.target_agent}"
            ) from exc
        finally:
            self._pending.pop(message.message_id, None)
            self.unsubscribe(message.source_agent, _reply_handler)

    def subscribe(self, agent_name: str, handler: MessageHandler) -> None:
        self._handlers[agent_name].append(handler)

    def unsubscribe(self, agent_name: str, handler: MessageHandler) -> None:
        handlers = self._handlers.get(agent_name)
        if not handlers:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            return
        if not handlers:
            self._handlers.pop(agent_name, None)

    def history(self, session_id: str) -> list[AgentMessage]:
        return list(self._history.get(session_id, []))

    async def reply(self, request: AgentMessage, payload: dict[str, Any], *, message_type: str) -> AgentMessage:
        response = AgentMessage(
            message_id=f"msg_{uuid4().hex}",
            run_id=request.run_id,
            session_id=request.session_id,
            source_agent=request.target_agent,
            target_agent=request.source_agent,
            message_type=message_type,  # type: ignore[arg-type]
            payload=payload,
            reply_to=request.message_id,
            context=request.context,
            created_at=datetime.now(UTC),
        )
        await self.send(response)
        return response
