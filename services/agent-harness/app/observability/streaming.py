from __future__ import annotations

import asyncio
import queue
import threading
from collections import OrderedDict
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.protocols.schemas import AgentStreamEvent, AgentStreamEventKind, AgentUsageDetail, AgentStreamVisibility


TERMINAL_EVENT_KINDS = {"run.completed", "run.failed", "run.cancelled"}


class AgentRunStreamBroker:
    def __init__(
        self,
        *,
        buffer_limit: int = 1000,
        heartbeat_seconds: float = 15.0,
        max_clients_per_run: int = 8,
    ) -> None:
        self.buffer_limit = max(20, buffer_limit)
        self.heartbeat_seconds = max(1.0, heartbeat_seconds)
        self.max_clients_per_run = max(1, max_clients_per_run)
        self._events: OrderedDict[str, list[AgentStreamEvent]] = OrderedDict()
        self._subscribers: dict[str, set[queue.Queue[AgentStreamEvent]]] = {}
        self._last_seq: dict[str, int] = {}
        self._run_sessions: dict[str, str] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.RLock()

    def publish(
        self,
        *,
        run_id: str,
        session_id: str,
        kind: AgentStreamEventKind,
        step_id: str | None = None,
        parent_id: str | None = None,
        phase: str | None = None,
        role: str | None = None,
        content_delta: str | None = None,
        reasoning_delta: str | None = None,
        payload: dict[str, Any] | None = None,
        usage: AgentUsageDetail | dict[str, Any] | None = None,
        visibility: AgentStreamVisibility = "default",
        created_at: datetime | None = None,
    ) -> AgentStreamEvent:
        with self._lock:
            seq = self._last_seq.get(run_id, 0) + 1
            self._last_seq[run_id] = seq
            self._run_sessions[run_id] = session_id
            event = AgentStreamEvent(
                seq=seq,
                event_id=f"stream_{uuid4().hex}",
                run_id=run_id,
                session_id=session_id,
                step_id=step_id,
                parent_id=parent_id,
                kind=kind,
                phase=phase,
                role=role,
                content_delta=content_delta,
                reasoning_delta=reasoning_delta,
                payload=payload or {},
                usage=AgentUsageDetail.model_validate(usage) if isinstance(usage, dict) else usage,
                visibility=visibility,
                created_at=created_at or datetime.now(UTC),
            )
            self._append_locked(event)
            subscribers = list(self._subscribers.get(run_id, set()))

        for subscriber in subscribers:
            try:
                subscriber.put_nowait(event)
            except queue.Full:
                self.unsubscribe(run_id, subscriber)
        return event

    def add_many(self, events: Sequence[AgentStreamEvent]) -> None:
        for event in events:
            self.add(event)

    def add(self, event: AgentStreamEvent) -> None:
        with self._lock:
            self._last_seq[event.run_id] = max(self._last_seq.get(event.run_id, 0), event.seq)
            self._run_sessions[event.run_id] = event.session_id
            existing = self._events.get(event.run_id, [])
            if any(item.event_id == event.event_id or item.seq == event.seq for item in existing):
                return
            self._append_locked(event)
            subscribers = list(self._subscribers.get(event.run_id, set()))

        for subscriber in subscribers:
            try:
                subscriber.put_nowait(event)
            except queue.Full:
                self.unsubscribe(event.run_id, subscriber)

    def history(self, run_id: str, *, after_seq: int = 0) -> list[AgentStreamEvent]:
        with self._lock:
            events = list(self._events.get(run_id, []))
        return [event for event in events if event.seq > after_seq]

    def subscribe(self, run_id: str) -> queue.Queue[AgentStreamEvent]:
        subscriber: queue.Queue[AgentStreamEvent] = queue.Queue(maxsize=128)
        with self._lock:
            subscribers = self._subscribers.setdefault(run_id, set())
            if len(subscribers) >= self.max_clients_per_run:
                raise RuntimeError("run stream subscriber limit exceeded")
            subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, run_id: str, subscriber: queue.Queue[AgentStreamEvent]) -> None:
        with self._lock:
            subscribers = self._subscribers.get(run_id)
            if not subscribers:
                return
            subscribers.discard(subscriber)
            if not subscribers:
                self._subscribers.pop(run_id, None)

    def cancel(self, run_id: str) -> AgentStreamEvent | None:
        with self._lock:
            self._cancelled.add(run_id)
            session_id = self._run_sessions.get(run_id)
        if not session_id:
            return None
        return self.publish(
            run_id=run_id,
            session_id=session_id,
            kind="run.cancelled",
            phase="cancelled",
            payload={"status": "cancelled"},
            visibility="admin",
        )

    def is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._cancelled

    async def sse_stream(self, run_id: str, *, after_seq: int = 0) -> AsyncIterator[str]:
        replay = self.history(run_id, after_seq=after_seq)
        for event in replay:
            yield encode_sse_event(event)
            if event.kind in TERMINAL_EVENT_KINDS:
                return

        subscriber = self.subscribe(run_id)
        try:
            while True:
                try:
                    event = await asyncio.to_thread(subscriber.get, True, self.heartbeat_seconds)
                except queue.Empty:
                    yield encode_sse_event(self._heartbeat(run_id))
                    continue
                yield encode_sse_event(event)
                if event.kind in TERMINAL_EVENT_KINDS:
                    return
        finally:
            self.unsubscribe(run_id, subscriber)

    def _append_locked(self, event: AgentStreamEvent) -> None:
        events = self._events.setdefault(event.run_id, [])
        events.append(event)
        if len(events) > self.buffer_limit:
            del events[: len(events) - self.buffer_limit]
        self._events.move_to_end(event.run_id)
        while len(self._events) > self.buffer_limit:
            run_id, _ = self._events.popitem(last=False)
            self._last_seq.pop(run_id, None)
            self._run_sessions.pop(run_id, None)
            self._cancelled.discard(run_id)

    def _heartbeat(self, run_id: str) -> AgentStreamEvent:
        with self._lock:
            seq = self._last_seq.get(run_id, 0)
            session_id = self._run_sessions.get(run_id, "")
        return AgentStreamEvent(
            seq=seq,
            event_id=f"heartbeat_{uuid4().hex}",
            run_id=run_id,
            session_id=session_id or "unknown",
            kind="heartbeat",
            phase="alive",
            payload={"heartbeat": True},
            visibility="default",
            created_at=datetime.now(UTC),
        )


def encode_sse_event(event: AgentStreamEvent) -> str:
    data = event.model_dump_json(exclude_none=True)
    return f"id: {event.seq}\nevent: {event.kind}\ndata: {data}\n\n"


def terminal_event_seen(events: Sequence[AgentStreamEvent]) -> bool:
    return any(event.kind in TERMINAL_EVENT_KINDS for event in events)
