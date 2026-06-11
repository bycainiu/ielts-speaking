from __future__ import annotations

import inspect
import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

import logging

from app.core.config import Settings
from app.observability.models import OrchestratorRunRecord, OrchestratorTraceSnapshot, ToolLoopIterationRecord
from app.observability.persistence import PostgresOrchestratorRepository
from app.observability.streaming import OrchestratorStreamBroker
from app.protocols.agent_message import AgentMessage
from app.protocols.schemas import AgentResponse, AgentStreamEvent


logger = logging.getLogger("agent_orchestrator.trace")


class OrchestratorTraceRecorder:
    def __init__(
        self,
        settings: Settings,
        *,
        repository: PostgresOrchestratorRepository | None = None,
    ) -> None:
        self.settings = settings
        self.stream_broker = OrchestratorStreamBroker(
            buffer_limit=settings.agent_stream_buffer_limit,
            heartbeat_seconds=settings.agent_stream_heartbeat_seconds,
            max_clients_per_run=settings.agent_stream_max_clients_per_run,
        )
        self._repository = repository
        if self._repository is None and settings.trace_persistence_enabled and settings.trace_database_url:
            self._repository = PostgresOrchestratorRepository(
                settings.trace_database_url,
                reasoning_retention=settings.trace_reasoning_retention,
            )
        self._lock = threading.RLock()
        self._runs: OrderedDict[str, OrchestratorRunRecord] = OrderedDict()
        self._traces: OrderedDict[str, OrchestratorTraceSnapshot] = OrderedDict()
        self._messages: list[AgentMessage] = []
        self._tool_iterations: list[ToolLoopIterationRecord] = []

    def record_agent_message(self, message: AgentMessage) -> None:
        with self._lock:
            self._messages.append(message)
            trace = self._traces.get(message.run_id)
            if trace is not None:
                trace.message_count += 1

    def list_agent_messages(self, run_id: str) -> list[AgentMessage]:
        with self._lock:
            return [item for item in self._messages if item.run_id == run_id]

    def record_tool_loop_iteration(
        self,
        *,
        session_id: str,
        run_id: str,
        agent_name: str,
        iteration: int,
        phase: str,
        **details: Any,
    ) -> ToolLoopIterationRecord:
        record = ToolLoopIterationRecord(
            session_id=session_id,
            run_id=run_id,
            agent_name=agent_name,
            iteration=iteration,
            phase=phase,
            llm_request_messages=details.get("llm_request_messages"),
            llm_response_content=details.get("llm_response_content"),
            llm_reasoning_text=details.get("llm_reasoning_text"),
            llm_tool_calls=details.get("llm_tool_calls"),
            tool_name=details.get("tool_name"),
            tool_arguments=details.get("tool_arguments"),
            tool_result=details.get("tool_result"),
            tool_status=details.get("tool_status"),
            model_name=details.get("model_name"),
            input_tokens=details.get("input_tokens"),
            output_tokens=details.get("output_tokens"),
            latency_ms=int(details.get("latency_ms") or 0),
            error_code=details.get("error_code"),
        )
        with self._lock:
            self._tool_iterations.append(record)
            trace = self._traces.get(run_id)
            if trace is not None:
                trace.tool_iterations.append(record)
        return record

    def list_tool_iterations(self, run_id: str) -> list[ToolLoopIterationRecord]:
        with self._lock:
            return [item for item in self._tool_iterations if item.run_id == run_id]

    async def record_agent_call(
        self,
        *,
        session_id: str,
        workflow_node: str,
        request: Any,
        call: Callable[[], AgentResponse | Any],
    ) -> AgentResponse:
        run_id = getattr(request, "run_id_override", None) or f"run_{uuid4().hex}"
        started = perf_counter()
        started_at = datetime.now(UTC)
        self.stream_broker.publish(
            run_id=run_id,
            session_id=session_id,
            kind="run.started",
            phase=workflow_node,
            payload={"workflow_node": workflow_node},
        )
        with self._lock:
            self._runs[run_id] = OrchestratorRunRecord(
                run_id=run_id,
                session_id=session_id,
                workflow_node=workflow_node,
                status="running",
                started_at=started_at,
            )
            self._traces[run_id] = OrchestratorTraceSnapshot(
                run_id=run_id,
                session_id=session_id,
                status="running",
                workflow_node=workflow_node,
                started_at=started_at,
            )
            self._trim_locked()

        try:
            result = call()
            response = await result if inspect.isawaitable(result) else result
            if response.run_id != run_id:
                response = response.model_copy(update={"run_id": run_id})
            finished_at = datetime.now(UTC)
            latency_ms = int((perf_counter() - started) * 1000)
            self.stream_broker.publish(
                run_id=run_id,
                session_id=session_id,
                kind="run.completed",
                phase=workflow_node,
                payload={"status": "completed", "latency_ms": latency_ms},
            )
            with self._lock:
                run = self._runs[run_id]
                self._runs[run_id] = run.model_copy(
                    update={
                        "status": "completed",
                        "finished_at": finished_at,
                        "latency_ms": latency_ms,
                        "stream_event_count": len(self.stream_broker.history(run_id)),
                    }
                )
                trace = self._traces[run_id]
                self._traces[run_id] = trace.model_copy(
                    update={
                        "status": "completed",
                        "finished_at": finished_at,
                        "latency_ms": latency_ms,
                        "stream_events": self.stream_broker.history(run_id),
                    }
                )
            self._maybe_persist(run_id)
            return response
        except Exception as exc:
            finished_at = datetime.now(UTC)
            latency_ms = int((perf_counter() - started) * 1000)
            error_code = type(exc).__name__
            self.stream_broker.publish(
                run_id=run_id,
                session_id=session_id,
                kind="run.failed",
                phase=workflow_node,
                payload={"status": "failed", "error_code": error_code},
                visibility="admin",
            )
            with self._lock:
                run = self._runs[run_id]
                self._runs[run_id] = run.model_copy(
                    update={
                        "status": "failed",
                        "finished_at": finished_at,
                        "latency_ms": latency_ms,
                        "error_code": error_code,
                    }
                )
                trace = self._traces[run_id]
                self._traces[run_id] = trace.model_copy(
                    update={
                        "status": "failed",
                        "finished_at": finished_at,
                        "latency_ms": latency_ms,
                        "stream_events": self.stream_broker.history(run_id),
                    }
                )
            self._maybe_persist(run_id)
            raise

    def get_trace(self, run_id: str) -> OrchestratorTraceSnapshot | None:
        with self._lock:
            return self._traces.get(run_id)

    def list_stream_events(self, run_id: str, *, after_seq: int = 0) -> list[AgentStreamEvent]:
        return self.stream_broker.history(run_id, after_seq=after_seq)

    def list_runs(self, *, session_id: str | None = None, limit: int = 100) -> list[OrchestratorRunRecord]:
        with self._lock:
            runs = list(self._runs.values())
        if session_id:
            runs = [run for run in runs if run.session_id == session_id]
        runs.sort(key=lambda item: item.started_at, reverse=True)
        return runs[: max(1, limit)]

    def hash_user_id(self, user_id: str) -> str:
        digest = hashlib.sha256(f"{self.settings.trace_user_hash_salt}:{user_id}".encode()).hexdigest()
        return f"sha256:{digest}"

    def _maybe_persist(self, run_id: str) -> None:
        if self._repository is None:
            return
        with self._lock:
            trace = self._traces.get(run_id)
            if trace is None:
                return
            messages = [item for item in self._messages if item.run_id == run_id]
            tool_iterations = [item for item in self._tool_iterations if item.run_id == run_id]
            stream_events = self.stream_broker.history(run_id)
        try:
            self._repository.save_run_observability(
                trace=trace,
                messages=messages,
                tool_iterations=tool_iterations,
                stream_events=stream_events,
            )
        except Exception:
            logger.exception("orchestrator_trace_persistence_failed", extra={"run_id": run_id})

    def _trim_locked(self) -> None:
        while len(self._runs) > self.settings.trace_store_limit:
            run_id, _ = self._runs.popitem(last=False)
            self._traces.pop(run_id, None)
