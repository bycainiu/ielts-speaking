from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Literal, Protocol, TypeAlias
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.mcp.security import get_mcp_audit_sink
from app.observability.llm_capture import (
    CapturedLlmCall,
    LiveStreamContext,
    get_llm_capture_sink,
    reset_live_stream_context,
    set_live_stream_context,
)
from app.observability.streaming import AgentRunStreamBroker
from app.protocols.schemas import (
    AgentReasoningBlock,
    AgentResponse,
    AgentStreamEvent,
    AgentUsageDetail,
    ConsumeAsrRequest,
    NextTurnRequest,
    PlanRequest,
    SessionEvent,
)


logger = logging.getLogger("agent_harness.trace")

TraceStatus = Literal["running", "completed", "failed", "cancelled"]
StepStatus = Literal["running", "completed", "failed"]
ToolStatus = Literal["completed", "failed"]
TraceExecutionKind = Literal["llm", "deterministic", "tool"]

DEFAULT_TRACE_STORE_LIMIT = 500
SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(api[_-]?key|secret|token|password)\s*[:=]\s*[^,\s]+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
)


class ScoreSessionTraceRequest(Protocol):
    session_state: dict[str, Any]
    rubric_descriptors: Mapping[str, Any]
    anchor_samples: Sequence[Any]


TraceableRequest: TypeAlias = PlanRequest | ConsumeAsrRequest | NextTurnRequest | ScoreSessionTraceRequest


class TraceToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    scope: str | None = None
    status: ToolStatus
    latency_ms: int = Field(ge=0)
    error_code: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    result_summary: str | None = None
    input_payload: Any = None
    output_payload: Any = None
    arguments: Any = None
    parameters: Any = None
    request: Any = None
    response: Any = None
    metadata: dict[str, Any] | None = None


class TraceMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str | None = None
    content: str | None = None
    type: str | None = None


class TraceLlmCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_call_id: str
    call_name: str
    agent_name: str | None = None
    execution_kind: TraceExecutionKind = "deterministic"
    payload_origin: Literal["captured", "derived"] = "derived"
    provider: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    provider_request_id: str | None = None
    status: StepStatus
    input_summary: str | None = None
    output_summary: str | None = None
    request_payload: Any = None
    response_payload: Any = None
    reasoning_blocks: list[AgentReasoningBlock] = Field(default_factory=list)
    usage_detail: AgentUsageDetail | None = None
    stream_event_count: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    workflow_node: str
    part: int | None = Field(default=None, ge=1, le=3)
    question_id: str | None = None
    agent_name: str | None = None
    execution_kind: TraceExecutionKind = "deterministic"
    prompt_version: str | None = None
    model_name: str | None = None
    status: StepStatus
    input_summary: str | None = None
    output_summary: str | None = None
    input_payload: Any = None
    input_detail: Any = None
    output_payload: Any = None
    messages: list[TraceMessage] | None = None
    reasoning_blocks: list[AgentReasoningBlock] = Field(default_factory=list)
    usage_detail: AgentUsageDetail | None = None
    stream_event_count: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    structured_output_validity: bool | None = None
    scoring_result: dict[str, Any] | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    error_type: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    llm_calls: list[TraceLlmCall] = Field(default_factory=list)
    tool_calls: list[TraceToolCall] = Field(default_factory=list)


class AgentRunTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    session_id: str
    user_id_hash: str | None = None
    mode: str | None = None
    part: int | None = Field(default=None, ge=1, le=3)
    question_id: str | None = None
    status: TraceStatus
    started_at: datetime
    finished_at: datetime | None = None
    steps: list[TraceStep] = Field(default_factory=list)
    stream_events: list[AgentStreamEvent] = Field(default_factory=list)


class LatencyStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    avg_ms: float = Field(ge=0)
    p50_ms: int = Field(ge=0)
    p95_ms: int = Field(ge=0)
    min_ms: int = Field(ge=0)
    max_ms: int = Field(ge=0)


class WorkflowNodeStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_node: str
    run_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    latency: LatencyStats


class ToolCallStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    call_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    avg_latency_ms: float = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)


class ObservabilityRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    session_id: str
    user_id_hash: str | None = None
    mode: str | None = None
    part: int | None = Field(default=None, ge=1, le=3)
    question_id: str | None = None
    status: TraceStatus
    latency_ms: int | None = Field(default=None, ge=0)
    step_count: int = Field(ge=0)
    llm_call_count: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    error_code: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class ObservabilitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    filters: dict[str, str] = Field(default_factory=dict)
    run_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    cancelled_count: int = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)
    latency: LatencyStats
    workflow_nodes: list[WorkflowNodeStats] = Field(default_factory=list)
    tool_call_count: int = Field(ge=0)
    tool_success_rate: float = Field(ge=0, le=1)
    tool_calls_by_name: list[ToolCallStats] = Field(default_factory=list)
    structured_output_total: int = Field(ge=0)
    structured_output_valid_count: int = Field(ge=0)
    structured_output_validity_rate: float = Field(ge=0, le=1)
    input_token_count: int = Field(ge=0)
    output_token_count: int = Field(ge=0)
    estimated_model_cost_usd: float = Field(ge=0)
    errors_by_code: dict[str, int] = Field(default_factory=dict)
    recent_runs: list[ObservabilityRunSummary] = Field(default_factory=list)


AlertSeverity = Literal["warning", "critical"]


class ObservabilityAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: str
    severity: AlertSeverity
    metric: str
    message: str
    threshold: float
    actual: float
    runbook: str


class SessionAuditSessionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    user_id_hash: str | None = None
    mode: str | None = None
    status: str
    started_at: datetime
    last_event_at: datetime
    run_count: int = Field(ge=0)
    event_count: int = Field(ge=0)
    completed_run_count: int = Field(ge=0)
    failed_run_count: int = Field(ge=0)
    current_part: int | None = Field(default=None, ge=1, le=3)
    latest_question_id: str | None = None
    completed_parts: list[int] = Field(default_factory=list)
    recent_event_types: list[str] = Field(default_factory=list)
    agent_names: list[str] = Field(default_factory=list)


class SessionAuditDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    user_id_hash: str | None = None
    mode: str | None = None
    status: str
    started_at: datetime
    last_event_at: datetime
    run_count: int = Field(ge=0)
    event_count: int = Field(ge=0)
    completed_run_count: int = Field(ge=0)
    failed_run_count: int = Field(ge=0)
    current_part: int | None = Field(default=None, ge=1, le=3)
    latest_question_id: str | None = None
    completed_parts: list[int] = Field(default_factory=list)
    recent_event_types: list[str] = Field(default_factory=list)
    agent_names: list[str] = Field(default_factory=list)
    event_type_counts: dict[str, int] = Field(default_factory=dict)
    events: list[SessionEvent] = Field(default_factory=list)
    runs: list[ObservabilityRunSummary] = Field(default_factory=list)
    traces: list[AgentRunTrace] = Field(default_factory=list)


class TraceStore:
    def __init__(self, max_runs: int = DEFAULT_TRACE_STORE_LIMIT) -> None:
        self.max_runs = max_runs
        self._runs: OrderedDict[str, AgentRunTrace] = OrderedDict()

    def save(self, trace: AgentRunTrace) -> None:
        self._runs[trace.run_id] = trace
        self._runs.move_to_end(trace.run_id)
        while len(self._runs) > self.max_runs:
            self._runs.popitem(last=False)

    def get(self, run_id: str) -> AgentRunTrace | None:
        trace = self._runs.get(run_id)
        if trace is not None:
            self._runs.move_to_end(run_id)
        return trace

    def list_runs(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
        limit: int = 100,
    ) -> list[AgentRunTrace]:
        traces = list(self._runs.values())
        if run_id:
            traces = [trace for trace in traces if trace.run_id == run_id]
        if session_id:
            traces = [trace for trace in traces if trace.session_id == session_id]
        if mode:
            traces = [trace for trace in traces if trace.mode == mode]
        traces.sort(key=lambda trace: trace.started_at, reverse=True)
        return traces[: max(1, limit)]

    def session_ids(self) -> list[str]:
        session_ids: list[str] = []
        seen: set[str] = set()
        for trace in reversed(self._runs.values()):
            if trace.session_id in seen:
                continue
            seen.add(trace.session_id)
            session_ids.append(trace.session_id)
        return session_ids

    def summary(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
        limit: int = 100,
    ) -> ObservabilitySummary:
        traces = self.list_runs(session_id=session_id, run_id=run_id, mode=mode, limit=limit)
        return build_observability_summary(
            traces,
            filters={
                **({"session_id": session_id} if session_id else {}),
                **({"run_id": run_id} if run_id else {}),
                **({"mode": mode} if mode else {}),
            },
        )

    def alerts(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
        limit: int = 100,
        error_rate_threshold: float = 0.1,
        latency_p95_threshold_ms: int = 5000,
    ) -> list[ObservabilityAlert]:
        summary = self.summary(session_id=session_id, run_id=run_id, mode=mode, limit=limit)
        return evaluate_observability_alerts(
            summary,
            error_rate_threshold=error_rate_threshold,
            latency_p95_threshold_ms=latency_p95_threshold_ms,
        )

    def mark_cancelled(self, run_id: str) -> AgentRunTrace | None:
        trace = self.get(run_id)
        if trace is None:
            return None
        updated = trace.model_copy(update={"status": "cancelled", "finished_at": datetime.now(UTC)})
        self.save(updated)
        return updated


class SessionEventStore:
    def __init__(self, max_sessions: int = DEFAULT_TRACE_STORE_LIMIT, max_events_per_session: int = 500) -> None:
        self.max_sessions = max(1, max_sessions)
        self.max_events_per_session = max(20, max_events_per_session)
        self._events: OrderedDict[str, list[SessionEvent]] = OrderedDict()

    def record(self, session_id: str, events: Sequence[SessionEvent]) -> None:
        if not events:
            return
        saved = list(self._events.get(session_id, []))
        saved.extend(_sanitize_session_event(event) for event in events)
        if len(saved) > self.max_events_per_session:
            saved = saved[-self.max_events_per_session :]
        self._events[session_id] = saved
        self._events.move_to_end(session_id)
        while len(self._events) > self.max_sessions:
            self._events.popitem(last=False)

    def list_events(self, session_id: str, *, limit: int = 500) -> list[SessionEvent]:
        events = list(self._events.get(session_id, []))
        if not events:
            return []
        events.sort(key=lambda event: event.created_at)
        return events[-max(1, limit) :]

    def session_ids(self) -> list[str]:
        return list(reversed(self._events.keys()))


class TracePersistenceRepository(Protocol):
    def save_trace(self, trace: AgentRunTrace, *, events: Sequence[SessionEvent] | None = None) -> None: ...
    def get_trace(self, run_id: str) -> AgentRunTrace | None: ...
    def list_runs(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
        limit: int = 100,
    ) -> list[AgentRunTrace]: ...
    def session_ids(self, *, limit: int = 100) -> list[str]: ...
    def list_events(self, session_id: str, *, limit: int = 500) -> list[SessionEvent]: ...
    def mark_cancelled(self, run_id: str) -> AgentRunTrace | None: ...


class LangfuseExporter:
    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.langfuse_enabled
        self.host = settings.langfuse_host.rstrip("/")
        self.public_key = settings.langfuse_public_key
        self.secret_key = settings.langfuse_secret_key
        self.timeout_seconds = settings.langfuse_timeout_seconds

    def export(self, trace: AgentRunTrace) -> tuple[bool, str | None]:
        if not self.enabled:
            return False, None
        payload = build_langfuse_ingestion_payload(trace)
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.host}/api/public/ingestion",
                    auth=(self.public_key, self.secret_key),
                    json=payload,
                )
                response.raise_for_status()
        except Exception as exc:  # pragma: no cover - 外部服务失败不能影响本地工作流
            return False, sanitize_text(str(exc))
        return True, None


class TraceRecorder:
    def __init__(
        self,
        settings: Settings,
        store: TraceStore | None = None,
        exporter: LangfuseExporter | None = None,
        event_store: SessionEventStore | None = None,
        trace_repository: TracePersistenceRepository | None = None,
        stream_broker: AgentRunStreamBroker | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or TraceStore(settings.trace_store_limit)
        self.exporter = exporter or LangfuseExporter(settings)
        self.event_store = event_store or SessionEventStore(settings.trace_store_limit, settings.trace_store_limit * 6)
        self.trace_repository = trace_repository if trace_repository is not None else build_trace_repository(settings)
        self.stream_broker = stream_broker or AgentRunStreamBroker(
            buffer_limit=settings.agent_stream_buffer_limit,
            heartbeat_seconds=settings.agent_stream_heartbeat_seconds,
            max_clients_per_run=settings.agent_stream_max_clients_per_run,
        )

    def record_agent_call(
        self,
        *,
        session_id: str,
        workflow_node: str,
        request: TraceableRequest,
        call: Any,
    ) -> AgentResponse:
        started_at = datetime.now(UTC)
        started_perf = perf_counter()
        mode = mode_from_request(request)
        user_id = user_id_from_request(request)
        run_id = run_id_from_request(request) or f"run_{uuid4().hex}"
        inject_run_id_override(request, run_id)
        status: TraceStatus = "completed"
        error_code: str | None = None
        audit_start_index = len(get_mcp_audit_sink().records)
        llm_capture_start_index = len(get_llm_capture_sink().records)
        running_trace = AgentRunTrace(
            run_id=run_id,
            session_id=session_id,
            user_id_hash=hash_user_id(user_id, self.settings.trace_user_hash_salt) if user_id else None,
            mode=mode,
            status="running",
            started_at=started_at,
        )
        started_event = self.stream_broker.publish(
            run_id=run_id,
            session_id=session_id,
            kind="run.started",
            phase=workflow_node,
            payload={"workflow_node": workflow_node, "mode": mode, "status": "running"},
            visibility="admin",
            created_at=started_at,
        )
        self.store.save(running_trace.model_copy(update={"stream_events": [started_event]}))
        live_context_token = set_live_stream_context(
            LiveStreamContext(broker=self.stream_broker, run_id=run_id, session_id=session_id)
        )

        try:
            response = call()
            run_id = response.run_id
            return response
        except Exception as exc:
            status = "failed"
            error_code = str(getattr(exc, "code", exc.__class__.__name__))
            raise
        finally:
            reset_live_stream_context(live_context_token)
            finished_at = datetime.now(UTC)
            latency_ms = elapsed_ms(started_perf)
            events = response.events if "response" in locals() else []
            if "response" in locals():
                self.event_store.record(session_id, events)
            tool_calls = tool_calls_from_mcp_audit(audit_start_index)
            captured_records = get_llm_capture_sink().records_since(llm_capture_start_index)
            captured_llm_calls = trace_llm_calls_from_capture(self.settings, captured_records)
            live_texts = live_streamed_texts(captured_records)
            trace_part, trace_question_id = trace_context_from_request(
                request,
                response if "response" in locals() else None,
            )
            steps = build_trace_steps(
                settings=self.settings,
                workflow_node=workflow_node,
                request=request,
                response=response if "response" in locals() else None,
                trace_part=trace_part,
                trace_question_id=trace_question_id,
                status=status,
                latency_ms=latency_ms,
                error_code=error_code,
                started_at=started_at,
                finished_at=finished_at,
                tool_calls=tool_calls,
                captured_llm_calls=captured_llm_calls,
            )

            trace = AgentRunTrace(
                run_id=run_id,
                session_id=session_id,
                user_id_hash=hash_user_id(user_id, self.settings.trace_user_hash_salt) if user_id else None,
                mode=mode,
                part=trace_part,
                question_id=trace_question_id,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
                steps=steps,
            )
            publish_trace_stream_events(
                self.stream_broker,
                trace,
                events,
                terminal_status=status,
                terminal_error_code=error_code,
                live_streamed_texts=live_texts,
            )
            stream_events = self.stream_broker.history(run_id)
            trace = trace.model_copy(
                update={
                    "steps": steps_with_stream_counts(steps, stream_events),
                    "stream_events": stream_events,
                }
            )
            self.exporter.export(trace)
            self.store.save(trace)
            self.persist_trace(trace, events=events)

    def get_trace(self, run_id: str) -> AgentRunTrace | None:
        trace = self.store.get(run_id)
        if trace is not None:
            return trace
        if self.trace_repository is None:
            return None
        try:
            trace = self.trace_repository.get_trace(run_id)
        except Exception as exc:
            logger.warning("trace_repository_get_failed", extra={"run_id": run_id, "error": str(exc)})
            return None
        if trace is not None:
            self.store.save(trace)
        return trace

    def cancel_run(self, run_id: str) -> AgentRunTrace | None:
        cancel_event = self.stream_broker.cancel(run_id)
        trace = self.store.mark_cancelled(run_id)
        if trace is not None and cancel_event is not None:
            trace = trace.model_copy(update={"stream_events": self.stream_broker.history(run_id)})
            self.store.save(trace)
        persisted_trace = None
        if self.trace_repository is not None:
            try:
                persisted_trace = self.trace_repository.mark_cancelled(run_id)
            except Exception as exc:
                logger.warning("trace_repository_cancel_failed", extra={"run_id": run_id, "error": str(exc)})
        return trace or persisted_trace

    def list_stream_events(self, run_id: str, *, after_seq: int = 0) -> list[AgentStreamEvent]:
        events = self.stream_broker.history(run_id, after_seq=after_seq)
        if events:
            return events
        trace = self.get_trace(run_id)
        if trace is None:
            return []
        return [event for event in trace.stream_events if event.seq > after_seq]

    def query_summary(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
        limit: int = 100,
    ) -> ObservabilitySummary:
        traces = self.list_traces(session_id=session_id, run_id=run_id, mode=mode, limit=limit)
        return build_observability_summary(
            traces,
            filters={
                **({"session_id": session_id} if session_id else {}),
                **({"run_id": run_id} if run_id else {}),
                **({"mode": mode} if mode else {}),
            },
        )

    def query_alerts(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
        limit: int = 100,
    ) -> list[ObservabilityAlert]:
        summary = self.query_summary(session_id=session_id, run_id=run_id, mode=mode, limit=limit)
        return evaluate_observability_alerts(
            summary,
            error_rate_threshold=self.settings.observability_error_rate_alert_threshold,
            latency_p95_threshold_ms=self.settings.observability_latency_p95_alert_ms,
        )

    def query_audit_sessions(
        self,
        *,
        session_id: str | None = None,
        mode: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SessionAuditSessionSummary]:
        session_ids = list(dict.fromkeys([*self.event_store.session_ids(), *self.store.session_ids(), *self.persisted_session_ids(limit=limit)]))
        summaries: list[SessionAuditSessionSummary] = []
        for candidate in session_ids:
            if session_id and candidate != session_id:
                continue
            detail = self.get_session_audit(candidate, limit=max(limit, self.settings.trace_store_limit))
            if detail is None:
                continue
            if mode and detail.mode != mode:
                continue
            if status and detail.status != status:
                continue
            summaries.append(
                SessionAuditSessionSummary(
                    session_id=detail.session_id,
                    user_id_hash=detail.user_id_hash,
                    mode=detail.mode,
                    status=detail.status,
                    started_at=detail.started_at,
                    last_event_at=detail.last_event_at,
                    run_count=detail.run_count,
                    event_count=detail.event_count,
                    completed_run_count=detail.completed_run_count,
                    failed_run_count=detail.failed_run_count,
                    current_part=detail.current_part,
                    latest_question_id=detail.latest_question_id,
                    completed_parts=detail.completed_parts,
                    recent_event_types=detail.recent_event_types,
                    agent_names=detail.agent_names,
                )
            )
        summaries.sort(key=lambda item: item.last_event_at, reverse=True)
        return summaries[: max(1, limit)]

    def get_session_audit(self, session_id: str, *, limit: int = 500) -> SessionAuditDetail | None:
        events = merge_events(
            self.event_store.list_events(session_id, limit=limit),
            self.persisted_events(session_id, limit=limit),
        )
        traces = self.list_traces(session_id=session_id, limit=limit)
        if not events and not traces:
            return None
        traces = sorted(traces, key=lambda trace: trace.started_at)
        return build_session_audit_detail(session_id=session_id, events=events, traces=traces)

    def prometheus_metrics(self) -> str:
        return build_prometheus_metrics(self.query_summary(limit=self.settings.trace_store_limit))

    def persist_trace(self, trace: AgentRunTrace, *, events: Sequence[SessionEvent]) -> None:
        if self.trace_repository is None:
            return
        try:
            self.trace_repository.save_trace(trace, events=events)
        except Exception as exc:
            logger.warning("trace_repository_save_failed", extra={"run_id": trace.run_id, "error": str(exc)})

    def list_traces(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
        limit: int = 100,
    ) -> list[AgentRunTrace]:
        memory_traces = self.store.list_runs(session_id=session_id, run_id=run_id, mode=mode, limit=limit)
        persisted_traces: list[AgentRunTrace] = []
        if self.trace_repository is not None:
            try:
                persisted_traces = self.trace_repository.list_runs(session_id=session_id, run_id=run_id, mode=mode, limit=limit)
            except Exception as exc:
                logger.warning("trace_repository_list_failed", extra={"error": str(exc)})
        return merge_traces(memory_traces, persisted_traces)[: max(1, limit)]

    def persisted_session_ids(self, *, limit: int) -> list[str]:
        if self.trace_repository is None:
            return []
        try:
            return self.trace_repository.session_ids(limit=limit)
        except Exception as exc:
            logger.warning("trace_repository_session_ids_failed", extra={"error": str(exc)})
            return []

    def persisted_events(self, session_id: str, *, limit: int) -> list[SessionEvent]:
        if self.trace_repository is None:
            return []
        try:
            return self.trace_repository.list_events(session_id, limit=limit)
        except Exception as exc:
            logger.warning("trace_repository_events_failed", extra={"session_id": session_id, "error": str(exc)})
            return []


def build_trace_repository(settings: Settings) -> TracePersistenceRepository | None:
    if not settings.trace_persistence_enabled:
        return None
    database_url = settings.trace_database_url or settings.knowledge_database_url
    if not database_url:
        return None
    try:
        from app.observability.trace_persistence import PostgresTraceRepository

        return PostgresTraceRepository(database_url)
    except Exception as exc:
        logger.warning("trace_repository_init_failed", extra={"error": str(exc)})
        return None


def merge_traces(*groups: Sequence[AgentRunTrace]) -> list[AgentRunTrace]:
    by_run_id: dict[str, AgentRunTrace] = {}
    for group in groups:
        for trace in group:
            if trace.run_id not in by_run_id:
                by_run_id[trace.run_id] = trace
    return sorted(by_run_id.values(), key=lambda trace: trace.started_at, reverse=True)


def merge_events(*groups: Sequence[SessionEvent]) -> list[SessionEvent]:
    by_key: dict[tuple[str, str, str], SessionEvent] = {}
    for group in groups:
        for event in group:
            key = (event.run_id, event.type, event.created_at.isoformat())
            if key not in by_key:
                by_key[key] = event
    return sorted(by_key.values(), key=lambda event: event.created_at)


def run_id_from_request(request: TraceableRequest) -> str | None:
    value = getattr(request, "run_id_override", None)
    return value if isinstance(value, str) and value.strip() else None


def inject_run_id_override(request: TraceableRequest, run_id: str) -> None:
    if not hasattr(request, "run_id_override"):
        return
    try:
        if not getattr(request, "run_id_override", None):
            setattr(request, "run_id_override", run_id)
    except Exception:
        logger.debug("run_id_override_injection_skipped", extra={"run_id": run_id})


def publish_trace_stream_events(
    broker: AgentRunStreamBroker,
    trace: AgentRunTrace,
    session_events: Sequence[SessionEvent],
    *,
    terminal_status: TraceStatus,
    terminal_error_code: str | None,
    live_streamed_texts: set[str] | None = None,
) -> None:
    live_texts = live_streamed_texts or set()
    if not trace.steps:
        publish_terminal_stream_event(broker, trace, terminal_status, terminal_error_code)
        return

    session_events_emitted = False
    for step in trace.steps:
        broker.publish(
            run_id=trace.run_id,
            session_id=trace.session_id,
            step_id=step.step_id,
            kind="step.started",
            phase=step.workflow_node,
            payload={
                "workflow_node": step.workflow_node,
                "agent_name": step.agent_name,
                "execution_kind": step.execution_kind,
                "status": step.status,
                "part": step.part,
                "question_id": step.question_id,
            },
            visibility="admin",
            created_at=step.started_at,
        )

        if not session_events_emitted:
            publish_session_event_stream_events(broker, trace, step.step_id, session_events, live_streamed_texts=live_texts)
            session_events_emitted = True

        for block in reasoning_blocks_for_replay(step, live_texts):
            broker.publish(
                run_id=trace.run_id,
                session_id=trace.session_id,
                step_id=step.step_id,
                kind="reasoning.delta",
                phase=step.workflow_node,
                reasoning_delta=block.text,
                payload=block.model_dump(mode="json", exclude_none=True),
                visibility="reasoning",
                created_at=block.created_at,
            )

        usage_streamed_live = any(call.stream_event_count > 0 and call.usage_detail is not None for call in step.llm_calls)
        if step.usage_detail is not None and not usage_streamed_live:
            broker.publish(
                run_id=trace.run_id,
                session_id=trace.session_id,
                step_id=step.step_id,
                kind="usage.updated",
                phase=step.workflow_node,
                usage=step.usage_detail,
                payload={"workflow_node": step.workflow_node},
                visibility="admin",
                created_at=step.finished_at or datetime.now(UTC),
            )

        for tool in step.tool_calls:
            tool_payload = tool.model_dump(mode="json", exclude_none=True)
            broker.publish(
                run_id=trace.run_id,
                session_id=trace.session_id,
                step_id=step.step_id,
                kind="tool.started",
                phase=step.workflow_node,
                payload={"tool_name": tool.tool_name, "scope": tool.scope},
                visibility="admin",
                created_at=step.started_at,
            )
            broker.publish(
                run_id=trace.run_id,
                session_id=trace.session_id,
                step_id=step.step_id,
                kind="tool.completed",
                phase=step.workflow_node,
                payload=tool_payload,
                visibility="admin",
                created_at=step.finished_at or datetime.now(UTC),
            )

        broker.publish(
            run_id=trace.run_id,
            session_id=trace.session_id,
            step_id=step.step_id,
            kind="step.completed",
            phase=step.workflow_node,
            payload={
                "workflow_node": step.workflow_node,
                "status": step.status,
                "latency_ms": step.latency_ms,
                "error_code": step.error_code,
            },
            visibility="admin",
            created_at=step.finished_at or datetime.now(UTC),
        )

    publish_terminal_stream_event(broker, trace, terminal_status, terminal_error_code)


def reasoning_blocks_for_replay(step: TraceStep, live_texts: set[str]) -> list[AgentReasoningBlock]:
    """补发推理块：跳过实时流阶段已经发布过的 thinking 内容，避免时间线重复。"""
    if step.llm_calls:
        blocks: list[AgentReasoningBlock] = []
        for call in step.llm_calls:
            for block in call.reasoning_blocks:
                if call.stream_event_count > 0 and normalize_live_text(block.text) in live_texts:
                    continue
                blocks.append(block)
        return blocks
    return [block for block in step.reasoning_blocks if normalize_live_text(block.text) not in live_texts]


def publish_session_event_stream_events(
    broker: AgentRunStreamBroker,
    trace: AgentRunTrace,
    step_id: str,
    session_events: Sequence[SessionEvent],
    *,
    live_streamed_texts: set[str] | None = None,
) -> None:
    live_texts = live_streamed_texts or set()
    for event in session_events:
        payload = sanitize_raw_payload(event.payload)
        if event.type == "examiner.message":
            broker.publish(
                run_id=trace.run_id,
                session_id=trace.session_id,
                step_id=step_id,
                kind="question.requested",
                phase=event.type,
                payload=payload,
                visibility="default",
                created_at=event.created_at,
            )
            message_text = str(payload.get("text") or "")
            if normalize_live_text(message_text) not in live_texts:
                broker.publish(
                    run_id=trace.run_id,
                    session_id=trace.session_id,
                    step_id=step_id,
                    kind="message.delta",
                    phase=event.type,
                    role="assistant",
                    content_delta=message_text,
                    payload=payload,
                    visibility="default",
                    created_at=event.created_at,
                )
            continue
        if event.type == "examiner.thinking":
            thinking_text = str(payload.get("text") or "")
            if thinking_text and normalize_live_text(thinking_text) not in live_texts:
                broker.publish(
                    run_id=trace.run_id,
                    session_id=trace.session_id,
                    step_id=step_id,
                    kind="reasoning.delta",
                    phase=event.type,
                    role="assistant",
                    reasoning_delta=thinking_text,
                    payload=payload,
                    visibility="reasoning",
                    created_at=event.created_at,
                )
            continue
        if event.type == "asr.final":
            broker.publish(
                run_id=trace.run_id,
                session_id=trace.session_id,
                step_id=step_id,
                kind="message.delta",
                phase=event.type,
                role="user",
                content_delta=str(payload.get("text") or ""),
                payload=payload,
                visibility="default",
                created_at=event.created_at,
            )
            continue
        if event.type == "agent.followup_planned":
            broker.publish(
                run_id=trace.run_id,
                session_id=trace.session_id,
                step_id=step_id,
                kind="reasoning.delta",
                phase=event.type,
                role="assistant",
                reasoning_delta=str(payload.get("reason") or ""),
                payload=payload,
                visibility="reasoning",
                created_at=event.created_at,
            )
            continue
        kind = "markdown.delta" if event.type not in {"error.recoverable", "error.fatal"} else "message.delta"
        broker.publish(
            run_id=trace.run_id,
            session_id=trace.session_id,
            step_id=step_id,
            kind=kind,
            phase=event.type,
            role="system",
            content_delta=markdown_for_session_event(event.type, payload),
            payload=payload,
            visibility="admin" if event.type.startswith("error.") else "default",
            created_at=event.created_at,
        )


def publish_terminal_stream_event(
    broker: AgentRunStreamBroker,
    trace: AgentRunTrace,
    terminal_status: TraceStatus,
    error_code: str | None,
) -> None:
    kind = "run.completed"
    if terminal_status == "failed":
        kind = "run.failed"
    elif terminal_status == "cancelled":
        kind = "run.cancelled"
    broker.publish(
        run_id=trace.run_id,
        session_id=trace.session_id,
        kind=kind,  # type: ignore[arg-type]
        phase=terminal_status,
        payload={
            "status": terminal_status,
            "error_code": error_code,
            "step_count": len(trace.steps),
        },
        visibility="admin",
        created_at=trace.finished_at or datetime.now(UTC),
    )


def markdown_for_session_event(event_type: str, payload: Mapping[str, Any]) -> str:
    if event_type == "report.ready":
        overall = payload.get("overall_band")
        confidence = payload.get("confidence")
        return f"**Report ready**\n\nOverall band: `{overall}`  \nConfidence: `{confidence}`"
    if event_type == "scoring.dimension_completed":
        return f"**Scoring dimension completed** `{payload.get('criterion')}` -> band `{payload.get('band')}`"
    if event_type == "scoring.review_completed":
        return f"**Scoring review** `{payload.get('status')}`"
    if event_type == "part.started":
        return f"**Part started** `{payload.get('title') or payload.get('part')}`"
    if event_type == "part.completed":
        return f"**Part completed** `{payload.get('part')}`"
    if event_type == "session.completed":
        return "**Session completed**"
    if event_type == "timer.started":
        return f"**Timer started** `{payload.get('suggested_seconds')}` seconds"
    if event_type == "error.recoverable" or event_type == "error.fatal":
        return str(payload.get("message") or payload.get("error") or event_type)
    return f"**{event_type}**"


def steps_with_stream_counts(steps: Sequence[TraceStep], events: Sequence[AgentStreamEvent]) -> list[TraceStep]:
    counts: dict[str, int] = {}
    for event in events:
        if event.step_id:
            counts[event.step_id] = counts.get(event.step_id, 0) + 1
    return [step.model_copy(update={"stream_event_count": counts.get(step.step_id, 0)}) for step in steps]


def build_trace_steps(
    *,
    settings: Settings,
    workflow_node: str,
    request: TraceableRequest,
    response: AgentResponse | None,
    trace_part: int | None,
    trace_question_id: str | None,
    status: TraceStatus,
    latency_ms: int,
    error_code: str | None,
    started_at: datetime,
    finished_at: datetime,
    tool_calls: list[TraceToolCall],
    captured_llm_calls: list[TraceLlmCall] | None = None,
) -> list[TraceStep]:
    step_status: StepStatus = "completed" if status == "completed" else "failed"
    remaining_captured = list(captured_llm_calls or [])

    child_steps: list[TraceStep] = []
    if response is not None and status == "completed":
        builders = {
            "plan_session": build_plan_session_trace_steps,
            "consume_asr": build_consume_asr_trace_steps,
            "next_turn": build_next_turn_trace_steps,
            "score_session": build_score_session_trace_steps,
        }
        builder = builders.get(workflow_node)
        if builder is not None:
            child_steps = builder(
                settings=settings,
                request=request,
                response=response,
                trace_part=trace_part,
                trace_question_id=trace_question_id,
                status=step_status,
                latency_ms=latency_ms,
                started_at=started_at,
                finished_at=finished_at,
                tool_calls=[],
                captured_llm_calls=remaining_captured,
            )

    # 未被任何子 step 认领的真实 LLM 调用（例如失败的运行）挂到 workflow 根节点，保证不丢观测数据。
    root_llm_calls = list(remaining_captured)
    root_step = build_trace_step(
        settings=settings,
        workflow_node=workflow_node,
        agent_name=agent_name_for_node(workflow_node, mode_from_request(request)),
        execution_kind="llm" if any(is_real_llm_call(call) for call in root_llm_calls) else "deterministic",
        prompt_version=prompt_version_for_node(workflow_node, mode_from_request(request)),
        model_name=next((call.model_name for call in root_llm_calls if call.model_name), step_model_name("deterministic")),
        status=step_status,
        part=trace_part,
        question_id=trace_question_id,
        input_payload=request_payload(request),
        output_payload=response_payload(response),
        messages=trace_messages_from_response(response),
        llm_calls=root_llm_calls,
        tool_calls=tool_calls,
        retrieved_chunks=retrieved_chunks_from_response(response) if response is not None else [],
        structured_output_validity=status == "completed" if response is not None else None,
        scoring_result=scoring_result_from_response(response) if response is not None else None,
        latency_ms=0,
        error_code=error_code,
        error_type=error_code,
        input_summary_override=summarize_request(request),
        output_summary_override=summarize_response(response) if response is not None else None,
        started_at=started_at,
        finished_at=finished_at,
        estimate_payload_tokens=False,
    )
    return [root_step, *child_steps]


def take_captured_llm_calls(captured_llm_calls: list[TraceLlmCall], call_name: str) -> list[TraceLlmCall]:
    """从未认领的真实 LLM 调用池里取走指定 call_name 的记录（按发生顺序）。"""
    taken = [call for call in captured_llm_calls if call.call_name == call_name]
    for call in taken:
        captured_llm_calls.remove(call)
    return taken


def resolve_step_llm_calls(
    captured_llm_calls: list[TraceLlmCall],
    call_name: str,
    derived_call_factory: Any,
) -> tuple[list[TraceLlmCall], TraceExecutionKind, str | None, str | None]:
    """优先使用真实捕获的 LLM 调用；没有时回退到派生记录。

    返回 (llm_calls, execution_kind, model_name, prompt_version)。
    """
    captured = take_captured_llm_calls(captured_llm_calls, call_name)
    if captured:
        model_name = next((call.model_name for call in captured if call.model_name), "model-call")
        prompt_version = next((call.prompt_version for call in captured if call.prompt_version), None)
        return captured, "llm", model_name, prompt_version
    return [derived_call_factory()], "deterministic", step_model_name("deterministic"), None


def build_plan_session_trace_steps(
    *,
    settings: Settings,
    request: TraceableRequest,
    response: AgentResponse,
    trace_part: int | None,
    trace_question_id: str | None,
    status: StepStatus,
    latency_ms: int,
    started_at: datetime,
    finished_at: datetime,
    tool_calls: list[TraceToolCall],
    captured_llm_calls: list[TraceLlmCall],
) -> list[TraceStep]:
    step_latency = per_step_latency(latency_ms, 2)
    steps: list[TraceStep] = []
    question_plan = sanitize_raw_payload(response.state.get("question_plan"))
    planner_calls, planner_kind, planner_model, planner_prompt = resolve_step_llm_calls(
        captured_llm_calls,
        "question_set_plan",
        lambda: build_trace_llm_call(
            settings=settings,
            call_name="question_set_plan",
            agent_name="QuestionSetPlannerAgent",
            execution_kind="deterministic",
            prompt_version="question_set_planner.v1",
            model_name=step_model_name("deterministic"),
            status=status,
            request_payload=request_payload(request),
            response_payload=question_plan,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=step_latency,
        ),
    )
    steps.append(
        build_trace_step(
            settings=settings,
            workflow_node="question_planner",
            agent_name="QuestionSetPlannerAgent",
            execution_kind=planner_kind,
            prompt_version=planner_prompt or "question_set_planner.v1",
            model_name=planner_model,
            status=status,
            part=trace_part,
            question_id=trace_question_id,
            input_payload=request_payload(request),
            output_payload=question_plan,
            llm_calls=planner_calls,
            tool_calls=tool_calls,
            retrieved_chunks=retrieved_chunks_from_response(response),
            structured_output_validity=True,
            latency_ms=step_latency,
            started_at=started_at,
            finished_at=finished_at,
        )
    )
    examiner_event = first_event_by_type(response, "examiner.message")
    if examiner_event is not None:
        examiner_output = sanitize_raw_payload(examiner_event.payload)
        examiner_calls, examiner_kind, examiner_model, examiner_prompt = resolve_step_llm_calls(
            captured_llm_calls,
            "examiner_turn",
            lambda: build_trace_llm_call(
                settings=settings,
                call_name="examiner_turn",
                agent_name="ExaminerAgent",
                execution_kind="deterministic",
                prompt_version="examiner_turn.v1",
                model_name=step_model_name("deterministic"),
                status=status,
                request_payload=build_examiner_input_payload(response, examiner_event),
                response_payload=examiner_output,
                started_at=started_at,
                finished_at=finished_at,
                latency_ms=step_latency,
            ),
        )
        steps.append(
            build_trace_step(
                settings=settings,
                workflow_node="examiner_turn",
                agent_name="ExaminerAgent",
                execution_kind=examiner_kind,
                prompt_version=examiner_prompt or "examiner_turn.v1",
                model_name=examiner_model,
                status=status,
                part=normalize_part(examiner_event.payload.get("part")) or trace_part,
                question_id=sanitize_trace_id(examiner_event.payload.get("question_id")) or trace_question_id,
                input_payload=build_examiner_input_payload(response, examiner_event),
                output_payload=examiner_output,
                messages=[TraceMessage(role="assistant", content=event_message_content(examiner_event), type=examiner_event.type)],
                llm_calls=examiner_calls,
                structured_output_validity=True,
                latency_ms=step_latency,
                started_at=started_at,
                finished_at=finished_at,
            )
        )
    return steps


def build_consume_asr_trace_steps(
    *,
    settings: Settings,
    request: TraceableRequest,
    response: AgentResponse,
    trace_part: int | None,
    trace_question_id: str | None,
    status: StepStatus,
    latency_ms: int,
    started_at: datetime,
    finished_at: datetime,
    tool_calls: list[TraceToolCall],
    captured_llm_calls: list[TraceLlmCall],
) -> list[TraceStep]:
    if not isinstance(request, ConsumeAsrRequest):
        return []
    step_latency = per_step_latency(latency_ms, 2)
    steps: list[TraceStep] = []
    followup_event = first_event_by_type(response, "agent.followup_planned")
    followup_input = {
        "mode": mode_from_request(request),
        "part": trace_part,
        "question_id": trace_question_id,
        "turn_id": request.turn_id,
        "asr_text": request.asr_text,
        "followup_count": request.session_state.get("followup_count"),
        "current_question_text": latest_question_text(request.session_state),
    }
    followup_output = sanitize_raw_payload(followup_event.payload) if followup_event is not None else {"next_action": response.next_action}
    followup_calls, followup_kind, followup_model, followup_prompt = resolve_step_llm_calls(
        captured_llm_calls,
        "followup_plan",
        lambda: build_trace_llm_call(
            settings=settings,
            call_name="followup_plan",
            agent_name="FollowupPlannerAgent",
            execution_kind="deterministic",
            prompt_version="followup_planner.v1",
            model_name=step_model_name("deterministic"),
            status=status,
            request_payload=followup_input,
            response_payload=followup_output,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=step_latency,
        ),
    )
    steps.append(
        build_trace_step(
            settings=settings,
            workflow_node="followup_planner",
            agent_name="FollowupPlannerAgent",
            execution_kind=followup_kind,
            prompt_version=followup_prompt or "followup_planner.v1",
            model_name=followup_model,
            status=status,
            part=trace_part,
            question_id=trace_question_id,
            input_payload=followup_input,
            output_payload=followup_output,
            llm_calls=followup_calls,
            tool_calls=tool_calls,
            structured_output_validity=True,
            latency_ms=step_latency,
            started_at=started_at,
            finished_at=finished_at,
        )
    )
    examiner_event = first_event_by_type(response, "examiner.message")
    if examiner_event is not None:
        examiner_output = sanitize_raw_payload(examiner_event.payload)
        examiner_input = {
            "mode": mode_from_request(request),
            "part": normalize_part(examiner_event.payload.get("part")) or trace_part,
            "question_id": sanitize_trace_id(examiner_event.payload.get("question_id")) or trace_question_id,
            "followup_decision": sanitize_raw_payload(followup_output),
            "question_text": examiner_event.payload.get("text"),
        }
        examiner_calls, examiner_kind, examiner_model, examiner_prompt = resolve_step_llm_calls(
            captured_llm_calls,
            "examiner_turn",
            lambda: build_trace_llm_call(
                settings=settings,
                call_name="examiner_turn",
                agent_name="ExaminerAgent",
                execution_kind="deterministic",
                prompt_version="examiner_turn.v1",
                model_name=step_model_name("deterministic"),
                status=status,
                request_payload=examiner_input,
                response_payload=examiner_output,
                started_at=started_at,
                finished_at=finished_at,
                latency_ms=step_latency,
            ),
        )
        steps.append(
            build_trace_step(
                settings=settings,
                workflow_node="examiner_turn",
                agent_name="ExaminerAgent",
                execution_kind=examiner_kind,
                prompt_version=examiner_prompt or "examiner_turn.v1",
                model_name=examiner_model,
                status=status,
                part=normalize_part(examiner_event.payload.get("part")) or trace_part,
                question_id=sanitize_trace_id(examiner_event.payload.get("question_id")) or trace_question_id,
                input_payload=examiner_input,
                output_payload=examiner_output,
                messages=[TraceMessage(role="assistant", content=event_message_content(examiner_event), type=examiner_event.type)],
                llm_calls=examiner_calls,
                structured_output_validity=True,
                latency_ms=step_latency,
                started_at=started_at,
                finished_at=finished_at,
            )
        )
    return steps


def build_next_turn_trace_steps(
    *,
    settings: Settings,
    request: TraceableRequest,
    response: AgentResponse,
    trace_part: int | None,
    trace_question_id: str | None,
    status: StepStatus,
    latency_ms: int,
    started_at: datetime,
    finished_at: datetime,
    tool_calls: list[TraceToolCall],
    captured_llm_calls: list[TraceLlmCall],
) -> list[TraceStep]:
    step_latency = per_step_latency(latency_ms, 1)
    examiner_event = first_event_by_type(response, "examiner.message")
    if examiner_event is not None:
        examiner_output = sanitize_raw_payload(examiner_event.payload)
        examiner_input = build_examiner_input_payload(response, examiner_event)
        examiner_calls, examiner_kind, examiner_model, examiner_prompt = resolve_step_llm_calls(
            captured_llm_calls,
            "examiner_turn",
            lambda: build_trace_llm_call(
                settings=settings,
                call_name="examiner_turn",
                agent_name="ExaminerAgent",
                execution_kind="deterministic",
                prompt_version="examiner_turn.v1",
                model_name=step_model_name("deterministic"),
                status=status,
                request_payload=examiner_input,
                response_payload=examiner_output,
                started_at=started_at,
                finished_at=finished_at,
                latency_ms=step_latency,
            ),
        )
        return [
            build_trace_step(
                settings=settings,
                workflow_node="examiner_turn",
                agent_name="ExaminerAgent",
                execution_kind=examiner_kind,
                prompt_version=examiner_prompt or "examiner_turn.v1",
                model_name=examiner_model,
                status=status,
                part=normalize_part(examiner_event.payload.get("part")) or trace_part,
                question_id=sanitize_trace_id(examiner_event.payload.get("question_id")) or trace_question_id,
                input_payload=examiner_input,
                output_payload=examiner_output,
                messages=[TraceMessage(role="assistant", content=event_message_content(examiner_event), type=examiner_event.type)],
                llm_calls=examiner_calls,
                tool_calls=tool_calls,
                structured_output_validity=True,
                latency_ms=step_latency,
                started_at=started_at,
                finished_at=finished_at,
            )
        ]
    transition_payload = {
        "next_action": response.next_action,
        "events": [event.model_dump(mode="json") for event in response.events],
        "state": sanitize_raw_payload(response.state),
    }
    return [
        build_trace_step(
            settings=settings,
            workflow_node="session_progression",
            agent_name=agent_name_for_node("next_turn", mode_from_request(request)),
            execution_kind="deterministic",
            prompt_version=prompt_version_for_node("next_turn", mode_from_request(request)),
            model_name=step_model_name("deterministic"),
            status=status,
            part=trace_part,
            question_id=trace_question_id,
            input_payload=request_payload(request),
            output_payload=transition_payload,
            messages=trace_messages_from_response(response),
            llm_calls=[
                build_trace_llm_call(
                    settings=settings,
                    call_name="session_progression",
                    agent_name=agent_name_for_node("next_turn", mode_from_request(request)),
                    execution_kind="deterministic",
                    prompt_version=prompt_version_for_node("next_turn", mode_from_request(request)),
                    model_name=step_model_name("deterministic"),
                    status=status,
                    request_payload=request_payload(request),
                    response_payload=transition_payload,
                    started_at=started_at,
                    finished_at=finished_at,
                    latency_ms=step_latency,
                )
            ],
            tool_calls=tool_calls,
            structured_output_validity=True,
            latency_ms=step_latency,
            started_at=started_at,
            finished_at=finished_at,
        )
    ]


def build_score_session_trace_steps(
    *,
    settings: Settings,
    request: TraceableRequest,
    response: AgentResponse,
    trace_part: int | None,
    trace_question_id: str | None,
    status: StepStatus,
    latency_ms: int,
    started_at: datetime,
    finished_at: datetime,
    tool_calls: list[TraceToolCall],
    captured_llm_calls: list[TraceLlmCall],
) -> list[TraceStep]:
    state = response.state if isinstance(response.state, Mapping) else {}
    report = state.get("score_report") if isinstance(state.get("score_report"), Mapping) else {}
    criteria = report.get("criteria") if isinstance(report.get("criteria"), Mapping) else {}
    review = state.get("score_review") if isinstance(state.get("score_review"), Mapping) else {}
    calibration = state.get("score_calibration") if isinstance(state.get("score_calibration"), Mapping) else {}
    answers = normalize_trace_answers(state)
    step_latency = per_step_latency(latency_ms, 7)
    steps: list[TraceStep] = []

    for criterion, workflow_name, agent_name, default_version in [
        ("fluency_coherence", "fluency_scorer", "FluencyCoherenceScorerAgent", "fluency_coherence_scorer.v1"),
        ("lexical_resource", "lexical_scorer", "LexicalResourceScorerAgent", "lexical_resource_scorer.v1"),
        ("grammatical_range_accuracy", "grammar_scorer", "GrammarScorerAgent", "grammar_scorer.v1"),
        ("pronunciation", "pronunciation_scorer", "PronunciationScorerAgent", "pronunciation_scorer.v1"),
    ]:
        criterion_output = criteria.get(criterion)
        if not isinstance(criterion_output, Mapping):
            continue
        input_payload = build_scoring_dimension_input(request, answers, criterion)
        output_payload = sanitize_raw_payload({"criterion": criterion, **dict(criterion_output)})
        prompt_version = raw_output_version(criterion_output, "scorer_version") or default_version
        steps.append(
            build_trace_step(
                settings=settings,
                workflow_node=workflow_name,
                agent_name=agent_name,
                execution_kind="deterministic",
                prompt_version=prompt_version,
                model_name=step_model_name("deterministic"),
                status=status,
                part=trace_part,
                question_id=trace_question_id,
                input_payload=input_payload,
                output_payload=output_payload,
                llm_calls=[
                    build_trace_llm_call(
                        settings=settings,
                        call_name=f"{criterion}_scoring",
                        agent_name=agent_name,
                        execution_kind="deterministic",
                        prompt_version=prompt_version,
                        model_name=step_model_name("deterministic"),
                        status=status,
                        request_payload=input_payload,
                        response_payload=output_payload,
                        started_at=started_at,
                        finished_at=finished_at,
                        latency_ms=step_latency,
                    )
                ],
                structured_output_validity=True,
                latency_ms=step_latency,
                started_at=started_at,
                finished_at=finished_at,
            )
        )

    if review:
        review_output = sanitize_raw_payload(review)
        review_input = {"session_id": state.get("session_id"), "criteria": sanitize_raw_payload(criteria)}
        prompt_version = raw_output_version(review, "reviewer_version") or "score_reviewer.v1"
        steps.append(
            build_trace_step(
                settings=settings,
                workflow_node="score_review",
                agent_name="ScoreReviewerAgent",
                execution_kind="deterministic",
                prompt_version=prompt_version,
                model_name=step_model_name("deterministic"),
                status=status,
                part=trace_part,
                question_id=trace_question_id,
                input_payload=review_input,
                output_payload=review_output,
                llm_calls=[
                    build_trace_llm_call(
                        settings=settings,
                        call_name="score_review",
                        agent_name="ScoreReviewerAgent",
                        execution_kind="deterministic",
                        prompt_version=prompt_version,
                        model_name=step_model_name("deterministic"),
                        status=status,
                        request_payload=review_input,
                        response_payload=review_output,
                        started_at=started_at,
                        finished_at=finished_at,
                        latency_ms=step_latency,
                    )
                ],
                structured_output_validity=True,
                latency_ms=step_latency,
                started_at=started_at,
                finished_at=finished_at,
            )
        )

    if calibration:
        calibration_output = sanitize_raw_payload(calibration)
        calibration_input = {
            "session_id": state.get("session_id"),
            "criteria": sanitize_raw_payload(review.get("reviewed_criteria") if isinstance(review.get("reviewed_criteria"), Mapping) else criteria),
            "anchor_samples": sanitize_raw_payload(list(getattr(request, "anchor_samples", []) or [])),
        }
        prompt_version = raw_output_version(calibration, "calibrator_version") or "score_calibrator.v1"
        steps.append(
            build_trace_step(
                settings=settings,
                workflow_node="score_calibration",
                agent_name="ScoreCalibrator",
                execution_kind="deterministic",
                prompt_version=prompt_version,
                model_name=step_model_name("deterministic"),
                status=status,
                part=trace_part,
                question_id=trace_question_id,
                input_payload=calibration_input,
                output_payload=calibration_output,
                llm_calls=[
                    build_trace_llm_call(
                        settings=settings,
                        call_name="score_calibration",
                        agent_name="ScoreCalibrator",
                        execution_kind="deterministic",
                        prompt_version=prompt_version,
                        model_name=step_model_name("deterministic"),
                        status=status,
                        request_payload=calibration_input,
                        response_payload=calibration_output,
                        started_at=started_at,
                        finished_at=finished_at,
                        latency_ms=step_latency,
                    )
                ],
                structured_output_validity=True,
                latency_ms=step_latency,
                started_at=started_at,
                finished_at=finished_at,
            )
        )

    feedback_output = build_feedback_trace_output(state, report)
    if feedback_output is not None:
        feedback_input = {
            "session_id": state.get("session_id"),
            "score_report": sanitize_raw_payload(report),
            "answers": answers,
            "user_background": sanitize_raw_payload(user_background_from_trace_state(state)),
        }
        prompt_version = raw_output_version(feedback_output, "coach_version") or "feedback_coach.v1"
        steps.append(
            build_trace_step(
                settings=settings,
                workflow_node="feedback_coaching",
                agent_name="FeedbackCoachAgent",
                execution_kind="deterministic",
                prompt_version=prompt_version,
                model_name=step_model_name("deterministic"),
                status=status,
                part=trace_part,
                question_id=trace_question_id,
                input_payload=feedback_input,
                output_payload=feedback_output,
                llm_calls=[
                    build_trace_llm_call(
                        settings=settings,
                        call_name="feedback_coaching",
                        agent_name="FeedbackCoachAgent",
                        execution_kind="deterministic",
                        prompt_version=prompt_version,
                        model_name=step_model_name("deterministic"),
                        status=status,
                        request_payload=feedback_input,
                        response_payload=feedback_output,
                        started_at=started_at,
                        finished_at=finished_at,
                        latency_ms=step_latency,
                    )
                ],
                tool_calls=tool_calls,
                structured_output_validity=True,
                scoring_result=scoring_result_from_response(response),
                latency_ms=step_latency,
                started_at=started_at,
                finished_at=finished_at,
            )
        )

    return steps


def build_trace_step(
    *,
    settings: Settings,
    workflow_node: str,
    agent_name: str,
    execution_kind: TraceExecutionKind,
    prompt_version: str | None,
    model_name: str | None,
    status: StepStatus,
    part: int | None,
    question_id: str | None,
    input_payload: Any,
    output_payload: Any,
    started_at: datetime,
    finished_at: datetime,
    latency_ms: int | None,
    llm_calls: list[TraceLlmCall] | None = None,
    tool_calls: list[TraceToolCall] | None = None,
    messages: list[TraceMessage] | None = None,
    retrieved_chunks: list[dict[str, Any]] | None = None,
    structured_output_validity: bool | None = None,
    scoring_result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_type: str | None = None,
    input_summary_override: str | None = None,
    output_summary_override: str | None = None,
    estimate_payload_tokens: bool = True,
) -> TraceStep:
    normalized_input = sanitize_raw_payload(input_payload)
    normalized_output = sanitize_raw_payload(output_payload)
    normalized_llm_calls = list(llm_calls or [])
    real_llm_calls = [item for item in normalized_llm_calls if is_real_llm_call(item)]
    input_tokens = sum(item.input_tokens or 0 for item in real_llm_calls)
    output_tokens = sum(item.output_tokens or 0 for item in real_llm_calls)
    reasoning_blocks = [block for call in normalized_llm_calls for block in call.reasoning_blocks]
    usage_detail = aggregate_usage_detail(real_llm_calls)
    if estimate_payload_tokens and execution_kind == "llm" and real_llm_calls:
        input_tokens = input_tokens or estimate_tokens(payload_to_text(normalized_input))
        output_tokens = output_tokens or estimate_tokens(payload_to_text(normalized_output))
    return TraceStep(
        step_id=f"step_{uuid4().hex}",
        workflow_node=workflow_node,
        part=part,
        question_id=question_id,
        agent_name=agent_name,
        execution_kind=execution_kind,
        prompt_version=prompt_version,
        model_name=model_name,
        status=status,
        input_summary=input_summary_override if input_summary_override is not None else summarize_payload_text(normalized_input),
        output_summary=output_summary_override if output_summary_override is not None else summarize_payload_text(normalized_output),
        input_payload=normalized_input,
        input_detail=normalized_input,
        output_payload=normalized_output,
        messages=messages,
        reasoning_blocks=reasoning_blocks,
        usage_detail=usage_detail,
        stream_event_count=sum(call.stream_event_count for call in normalized_llm_calls),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimate_model_cost_usd(input_tokens, output_tokens, settings) if real_llm_calls else 0.0,
        retrieved_chunks=retrieved_chunks or [],
        structured_output_validity=structured_output_validity,
        scoring_result=scoring_result,
        latency_ms=latency_ms,
        error_code=error_code,
        error_type=error_type,
        started_at=started_at,
        finished_at=finished_at,
        llm_calls=normalized_llm_calls,
        tool_calls=list(tool_calls or []),
    )


def aggregate_usage_detail(calls: Sequence[TraceLlmCall]) -> AgentUsageDetail | None:
    if not calls:
        return None
    usage_items = [call.usage_detail for call in calls if call.usage_detail is not None]
    if usage_items:
        return AgentUsageDetail(
            input_tokens=sum(item.input_tokens or 0 for item in usage_items) or None,
            output_tokens=sum(item.output_tokens or 0 for item in usage_items) or None,
            total_tokens=sum(item.total_tokens or 0 for item in usage_items) or None,
            cache_creation_input_tokens=sum(item.cache_creation_input_tokens or 0 for item in usage_items) or None,
            cache_read_input_tokens=sum(item.cache_read_input_tokens or 0 for item in usage_items) or None,
            estimated_cost_usd=round(sum(item.estimated_cost_usd or 0 for item in usage_items), 6) or None,
        )
    input_tokens = sum(call.input_tokens or 0 for call in calls)
    output_tokens = sum(call.output_tokens or 0 for call in calls)
    if input_tokens == 0 and output_tokens == 0:
        return None
    return AgentUsageDetail(
        input_tokens=input_tokens or None,
        output_tokens=output_tokens or None,
        total_tokens=(input_tokens + output_tokens) or None,
    )


def build_trace_llm_call(
    *,
    settings: Settings,
    call_name: str,
    agent_name: str,
    execution_kind: TraceExecutionKind,
    prompt_version: str | None,
    model_name: str | None,
    status: StepStatus,
    request_payload: Any,
    response_payload: Any,
    started_at: datetime,
    finished_at: datetime,
    latency_ms: int | None,
    provider_request_id: str | None = None,
    reasoning_blocks: list[AgentReasoningBlock] | None = None,
    usage_detail: AgentUsageDetail | None = None,
    stream_event_count: int = 0,
    error_code: str | None = None,
) -> TraceLlmCall:
    normalized_request = sanitize_raw_payload(request_payload)
    normalized_response = sanitize_raw_payload(response_payload)
    is_llm = execution_kind == "llm"
    input_text = payload_to_text(normalized_request) if is_llm else ""
    output_text = payload_to_text(normalized_response) if is_llm else ""
    return TraceLlmCall(
        llm_call_id=f"llm_{uuid4().hex}",
        call_name=call_name,
        agent_name=agent_name,
        execution_kind=execution_kind,
        payload_origin="derived",
        provider="deterministic" if execution_kind != "llm" else ("mock" if settings.mock_model_enabled else "mimo"),
        model_name=model_name,
        prompt_version=prompt_version,
        provider_request_id=provider_request_id,
        status=status,
        input_summary=summarize_payload_text(normalized_request),
        output_summary=summarize_payload_text(normalized_response),
        request_payload=normalized_request,
        response_payload=normalized_response,
        reasoning_blocks=reasoning_blocks or [],
        usage_detail=usage_detail,
        stream_event_count=stream_event_count,
        input_tokens=estimate_tokens(input_text) if is_llm else None,
        output_tokens=estimate_tokens(output_text) if is_llm else None,
        latency_ms=latency_ms,
        error_code=error_code,
        started_at=started_at,
        finished_at=finished_at,
    )


def trace_llm_calls_from_capture(settings: Settings, records: Sequence[CapturedLlmCall]) -> list[TraceLlmCall]:
    """把 LlmCaptureSink 捕获的真实模型调用转换为 payload_origin=captured 的 TraceLlmCall。"""
    calls: list[TraceLlmCall] = []
    for record in records:
        request_payload_value = sanitize_raw_payload({"task": record.task, "messages": record.request_messages})
        response_payload_value = sanitize_raw_payload(
            {
                "content": record.response_content,
                **({"parsed_output": record.parsed_output} if record.parsed_output is not None else {}),
            }
        )
        usage_detail = record.usage
        input_tokens = usage_detail.input_tokens if usage_detail else None
        output_tokens = usage_detail.output_tokens if usage_detail else None
        calls.append(
            TraceLlmCall(
                llm_call_id=f"llm_{uuid4().hex}",
                call_name=record.call_name,
                agent_name=record.agent_name,
                execution_kind="llm",
                payload_origin="captured",
                provider=record.provider,
                model_name=record.model_name,
                prompt_version=record.prompt_version,
                provider_request_id=record.provider_request_id,
                status="completed" if record.status == "completed" else "failed",
                input_summary=summarize_payload_text(request_payload_value),
                output_summary=summarize_payload_text(response_payload_value),
                request_payload=request_payload_value,
                response_payload=response_payload_value,
                reasoning_blocks=reasoning_blocks_for_capture(settings, record),
                usage_detail=usage_detail,
                stream_event_count=record.stream_event_count,
                input_tokens=input_tokens if input_tokens is not None else estimate_tokens(payload_to_text(request_payload_value)),
                output_tokens=output_tokens if output_tokens is not None else estimate_tokens(record.response_content or ""),
                latency_ms=record.latency_ms,
                error_code=record.error_code,
                started_at=record.started_at,
                finished_at=record.finished_at,
            )
        )
    return calls


def reasoning_blocks_for_capture(settings: Settings, record: CapturedLlmCall) -> list[AgentReasoningBlock]:
    if not record.reasoning_text:
        return []
    retention = settings.trace_reasoning_retention
    if retention == "none":
        return []
    limit = None if retention == "full" else 300
    text = sanitize_text(record.reasoning_text, limit=limit)
    if not text:
        return []
    return [
        AgentReasoningBlock(
            block_id=f"reasoning_{uuid4().hex}",
            type="reasoning",
            text=text,
            provider=record.provider,
            created_at=record.finished_at,
        )
    ]


def live_streamed_texts(records: Sequence[CapturedLlmCall]) -> set[str]:
    """实时流阶段已经发布过的文本（归一化后），用于批量补发去重。"""
    texts: set[str] = set()
    for record in records:
        if record.content_streamed and record.response_content:
            texts.add(normalize_live_text(record.response_content))
        if record.reasoning_streamed and record.reasoning_text:
            texts.add(normalize_live_text(record.reasoning_text))
    return {text for text in texts if text}


def normalize_live_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def build_examiner_input_payload(response: AgentResponse, event: SessionEvent) -> dict[str, Any]:
    payload = event.payload
    question = question_from_state(response.state, normalize_part(payload.get("part")), sanitize_trace_id(payload.get("question_id")))
    return sanitize_raw_payload(
        {
            "mode": response.state.get("mode"),
            "part": payload.get("part"),
            "question_id": payload.get("question_id"),
            "question_text": question.get("text") if isinstance(question, Mapping) else payload.get("text"),
            "question_index": response.state.get("question_index"),
            "practice_mode": payload.get("practice_mode"),
            "style_tags": payload.get("style_tags"),
        }
    )


def build_scoring_dimension_input(request: TraceableRequest, answers: list[dict[str, Any]], criterion: str) -> dict[str, Any]:
    rubric = getattr(request, "rubric_descriptors", {}) or {}
    payload = {
        "session_id": getattr(request, "session_state", {}).get("session_id") if hasattr(request, "session_state") else None,
        "turns": trace_turn_payloads(answers, criterion),
        "rubric_descriptors": sanitize_raw_payload((rubric.get(criterion) if isinstance(rubric, Mapping) else []) or []),
        "anchor_sample_ids": trace_anchor_ids(getattr(request, "anchor_samples", []) or [], criterion),
    }
    if criterion == "lexical_resource":
        payload["topic_keywords"] = trace_topic_keywords(request, answers)
    return sanitize_raw_payload(payload)


def build_feedback_trace_output(state: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any] | None:
    raw_report = report.get("raw_report") if isinstance(report.get("raw_report"), Mapping) else {}
    feedback_raw = raw_report.get("feedback") if isinstance(raw_report.get("feedback"), Mapping) else {}
    if not feedback_raw and not state.get("feedback_items") and not state.get("reference_answers"):
        return None
    return sanitize_raw_payload(
        {
            **dict(feedback_raw),
            "summary": state.get("feedback_summary"),
            "feedback_items": state.get("feedback_items"),
            "reference_answers": state.get("reference_answers"),
            "next_practice_plan": report.get("next_practice_plan"),
        }
    )


def raw_output_version(payload: Any, version_key: str) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    raw_output = payload.get("raw_output")
    if not isinstance(raw_output, Mapping):
        return None
    version = raw_output.get(version_key)
    return sanitize_text(str(version), limit=120) if version else None


def payload_to_text(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(payload)


def summarize_payload_text(payload: Any, *, limit: int = 220) -> str | None:
    text = payload_to_text(payload)
    return sanitize_text(text, limit=limit)


def per_step_latency(total_latency: int, step_count: int) -> int:
    if step_count <= 0:
        return total_latency
    if total_latency <= 0:
        return 0
    return max(1, int(total_latency / step_count))


def step_model_name(execution_kind: TraceExecutionKind) -> str | None:
    if execution_kind == "llm":
        return "model-call"
    return None


def is_real_llm_call(call: TraceLlmCall) -> bool:
    return call.execution_kind == "llm" and call.payload_origin == "captured"


def first_event_by_type(response: AgentResponse, event_type: str) -> SessionEvent | None:
    for event in response.events:
        if event.type == event_type:
            return event
    return None


def question_from_state(state: Mapping[str, Any], part: int | None, question_id: str | None) -> Mapping[str, Any] | None:
    question_plan = state.get("question_plan")
    if not isinstance(question_plan, Mapping):
        return None
    for part_plan in question_plan.get("parts") or []:
        if not isinstance(part_plan, Mapping):
            continue
        if part is not None and normalize_part(part_plan.get("part")) != part:
            continue
        for question in part_plan.get("questions") or []:
            if not isinstance(question, Mapping):
                continue
            candidate_id = sanitize_trace_id(question.get("question_id"))
            if question_id is None or candidate_id == question_id:
                return question
    return None


def latest_question_text(state: Mapping[str, Any]) -> str | None:
    question = question_from_state(state, part_from_state(state), question_id_from_state(state))
    if isinstance(question, Mapping):
        text = question.get("text")
        if isinstance(text, str):
            return sanitize_text(text, limit=240)
    for answer in reversed(state.get("answers") or []):
        if isinstance(answer, Mapping):
            question_text = answer.get("question_text")
            if isinstance(question_text, str) and question_text.strip():
                return sanitize_text(question_text, limit=240)
    return None


def normalize_trace_answers(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    for index, item in enumerate(state.get("answers") or []):
        if not isinstance(item, Mapping):
            continue
        transcript = first_text(item, "transcript", "asr_text", "answer_text", "text", limit=None)
        if not transcript:
            continue
        normalized = dict(item)
        normalized["turn_id"] = first_text(item, "turn_id", limit=None) or f"answer_{index + 1}"
        normalized["transcript"] = transcript
        answers.append(sanitize_raw_payload(normalized))
    return answers


def trace_turn_payloads(answers: list[dict[str, Any]], criterion: str) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for answer in answers:
        turn = {
            "turn_id": answer.get("turn_id"),
            "transcript": answer.get("transcript"),
            "question_text": first_text(answer, "question_text", limit=None),
            "part": normalize_part(answer.get("part")),
        }
        if criterion == "lexical_resource":
            turn["topic"] = answer_topic(answer)
        if criterion in {"fluency_coherence", "pronunciation"}:
            turn["metrics"] = answer.get("speech_metrics") if isinstance(answer.get("speech_metrics"), Mapping) else answer.get("metrics")
        if criterion == "pronunciation":
            turn["pronunciation_evidence"] = answer.get("pronunciation_evidence")
        turns.append(sanitize_raw_payload(turn))
    return turns


def trace_anchor_ids(anchors: Sequence[Any], criterion: str) -> list[str]:
    anchor_ids: list[str] = []
    for anchor in anchors:
        if isinstance(anchor, Mapping):
            if str(anchor.get("criterion") or "") != criterion:
                continue
            anchor_id = sanitize_trace_id(anchor.get("anchor_sample_id"))
        else:
            if str(getattr(anchor, "criterion", "") or "") != criterion:
                continue
            anchor_id = sanitize_trace_id(getattr(anchor, "anchor_sample_id", None))
        if anchor_id:
            anchor_ids.append(anchor_id)
    return anchor_ids


def trace_topic_keywords(request: TraceableRequest, answers: list[dict[str, Any]]) -> list[str]:
    keywords = list(getattr(request, "topic_keywords", []) or [])
    for answer in answers:
        topic = answer_topic(answer)
        if topic:
            keywords.append(topic)
        guidance = answer.get("topic_guidance")
        if isinstance(guidance, Mapping):
            keywords.extend(str(item) for item in guidance.get("vocabulary") or [])
    deduped: list[str] = []
    for item in keywords:
        text = str(item).strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped[:20]


def answer_topic(answer: Mapping[str, Any]) -> str | None:
    topic = first_text(answer, "topic")
    if topic:
        return topic
    topic_ids = answer.get("topic_ids")
    if isinstance(topic_ids, list) and topic_ids:
        return sanitize_text(str(topic_ids[0]), limit=120)
    return None


def user_background_from_trace_state(state: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("user_background", "background", "profile"):
        value = state.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def first_text(payload: Mapping[str, Any], *keys: str, limit: int | None = 300) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return sanitize_text(value.strip(), limit=limit)
    return None


def build_langfuse_ingestion_payload(trace: AgentRunTrace) -> dict[str, Any]:
    trace_body = {
        "id": trace.run_id,
        "name": "agent-harness-run",
        "sessionId": trace.session_id,
        "userId": trace.user_id_hash,
        "metadata": {
            "run_id": trace.run_id,
            "mode": trace.mode,
            "part": trace.part,
            "question_id": trace.question_id,
            "status": trace.status,
        },
    }
    batch: list[dict[str, Any]] = [
        {
            "id": f"event_{uuid4().hex}",
            "type": "trace-create",
            "timestamp": trace.started_at.isoformat(),
            "body": trace_body,
        }
    ]
    for step in trace.steps:
        batch.append(
            {
                "id": f"event_{uuid4().hex}",
                "type": "span-create",
                "timestamp": step.started_at.isoformat(),
                "body": {
                    "id": step.step_id,
                    "traceId": trace.run_id,
                    "name": step.workflow_node,
                    "startTime": step.started_at.isoformat(),
                    "endTime": step.finished_at.isoformat() if step.finished_at else None,
                    "metadata": {
                        "agent_name": step.agent_name,
                        "execution_kind": step.execution_kind,
                        "part": step.part,
                        "question_id": step.question_id,
                        "prompt_version": step.prompt_version,
                        "model_name": step.model_name,
                        "status": step.status,
                        "latency_ms": step.latency_ms,
                        "input_tokens": step.input_tokens,
                        "output_tokens": step.output_tokens,
                        "estimated_cost_usd": step.estimated_cost_usd,
                        "retrieved_chunks": step.retrieved_chunks,
                        "structured_output_validity": step.structured_output_validity,
                        "scoring_result": step.scoring_result,
                        "error_code": step.error_code,
                        "error_type": step.error_type,
                        "input_payload": step.input_payload,
                        "output_payload": step.output_payload,
                        "reasoning_block_count": len(step.reasoning_blocks),
                        "stream_event_count": step.stream_event_count,
                        "usage_detail": step.usage_detail.model_dump(mode="json", exclude_none=True) if step.usage_detail else None,
                        "llm_calls": [langfuse_safe_llm_call(call) for call in step.llm_calls],
                        "tool_calls": [tool.model_dump(mode="json", exclude_none=True) for tool in step.tool_calls],
                    },
                    "input": step.input_summary,
                    "output": step.output_summary,
                },
            }
        )
    return {"batch": batch}


def langfuse_safe_llm_call(call: TraceLlmCall) -> dict[str, Any]:
    payload = call.model_dump(
        mode="json",
        exclude_none=True,
        exclude={"request_payload", "response_payload", "reasoning_blocks"},
    )
    payload["reasoning_block_count"] = len(call.reasoning_blocks)
    payload["stream_event_count"] = call.stream_event_count
    return payload


def hash_user_id(user_id: str, salt: str) -> str:
    digest = hashlib.sha256(f"{salt}:{user_id}".encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def sanitize_text(value: str | None, *, limit: int | None = 300) -> str | None:
    if value is None:
        return None
    sanitized = value
    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    if limit is not None and len(sanitized) > limit:
        return f"{sanitized[:limit]}..."
    return sanitized


def sanitize_payload(value: Any, *, limit: int | None = 300) -> Any:
    if isinstance(value, str):
        return sanitize_text(value, limit=limit)
    if isinstance(value, Mapping):
        return {str(key): sanitize_payload(nested, limit=limit) for key, nested in value.items()}
    if isinstance(value, list):
        return [sanitize_payload(item, limit=limit) for item in value]
    if isinstance(value, tuple):
        return [sanitize_payload(item, limit=limit) for item in value]
    return value


def sanitize_raw_payload(value: Any) -> Any:
    return sanitize_payload(value, limit=None)


def _sanitize_session_event(event: SessionEvent) -> SessionEvent:
    return event.model_copy(update={"payload": sanitize_payload(event.payload)})


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, len(re.findall(r"\w+|[^\w\s]", text)))


def estimate_model_cost_usd(input_tokens: int | None, output_tokens: int | None, settings: Settings) -> float:
    input_cost = ((input_tokens or 0) / 1000) * settings.mimo_input_cost_usd_per_1k_tokens
    output_cost = ((output_tokens or 0) / 1000) * settings.mimo_output_cost_usd_per_1k_tokens
    return round(input_cost + output_cost, 6)


def request_payload(request: TraceableRequest) -> Any:
    if hasattr(request, "model_dump"):
        return sanitize_raw_payload(request.model_dump(mode="json", exclude_none=True))
    if isinstance(request, Mapping):
        return sanitize_raw_payload(dict(request))
    return None


def response_payload(response: AgentResponse | None) -> Any:
    if response is None:
        return None
    payload = {
        "next_action": response.next_action,
        "events": [event.model_dump(mode="json") for event in response.events],
        "state": response.state,
    }
    return sanitize_raw_payload(payload)


def trace_messages_from_response(response: AgentResponse | None) -> list[TraceMessage] | None:
    if response is None or not response.events:
        return None
    messages: list[TraceMessage] = []
    for event in response.events:
        content = event_message_content(event)
        messages.append(
            TraceMessage(
                role=event.type.split(".", 1)[0],
                content=content,
                type=event.type,
            )
        )
    return messages


def event_message_content(event: SessionEvent) -> str:
    sanitized = sanitize_payload(event.payload, limit=180)
    if isinstance(sanitized, Mapping):
        try:
            return json.dumps(sanitized, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return sanitize_text(str(sanitized), limit=220) or ""
    if isinstance(sanitized, list):
        return sanitize_text(json.dumps(sanitized, ensure_ascii=False), limit=220) or ""
    return sanitize_text(str(sanitized), limit=220) or ""


def summarize_request(request: TraceableRequest) -> str:
    if isinstance(request, PlanRequest):
        return sanitize_text(
            "plan "
            f"mode={request.mode} part={request.part or 'auto'} "
            f"season_present={bool(request.season_id)} topic_count={len(request.topic_ids)}"
        ) or ""
    if isinstance(request, ConsumeAsrRequest):
        return (
            "consume_asr "
            f"turn_id={sanitize_text(request.turn_id, limit=80)} "
            f"asr_text_chars={len(request.asr_text)} "
            f"audio_present={bool(request.audio_asset_id)} "
            f"confidence_present={request.asr_confidence is not None}"
        )

    if hasattr(request, "session_state"):
        state = request.session_state
    else:
        state = {}
    if hasattr(request, "rubric_descriptors"):
        return sanitize_text(
            "score_session "
            f"mode={state.get('mode', 'unknown')} "
            f"answer_count={len(state.get('answers') or [])} "
            f"rubric_criteria_count={len(getattr(request, 'rubric_descriptors', {}) or {})} "
            f"anchor_count={len(getattr(request, 'anchor_samples', []) or [])}"
        ) or ""

    return sanitize_text(
        "next_turn "
        f"mode={state.get('mode', 'unknown')} "
        f"current_part={state.get('current_part', 'unknown')} "
        f"question_index={state.get('question_index', 'unknown')} "
        f"completed_parts_count={len(state.get('completed_parts') or [])}"
    ) or ""


def summarize_response(response: AgentResponse) -> str:
    event_types = [event.type for event in response.events]
    return sanitize_text(
        f"next_action={response.next_action} events={','.join(event_types)} state_keys={','.join(sorted(response.state.keys()))}"
    ) or ""


def mode_from_request(request: TraceableRequest) -> str | None:
    if isinstance(request, PlanRequest):
        return request.mode
    if hasattr(request, "session_state"):
        mode = request.session_state.get("mode")
        return str(mode) if mode else None
    return None


def user_id_from_request(request: TraceableRequest) -> str | None:
    if isinstance(request, PlanRequest):
        return request.user_id
    if hasattr(request, "session_state"):
        user_id = request.session_state.get("user_id")
        return str(user_id) if user_id else None
    return None


def trace_context_from_request(
    request: TraceableRequest,
    response: AgentResponse | None,
) -> tuple[int | None, str | None]:
    request_state = request.session_state if hasattr(request, "session_state") else {}
    request_part = request.part if isinstance(request, PlanRequest) else part_from_state(request_state)
    request_question_id = question_id_from_state(request_state)

    response_part: int | None = None
    response_question_id: str | None = None
    if response is not None:
        response_part, response_question_id = trace_context_from_response(response)

    part = normalize_part(request_part) or response_part
    question_id = sanitize_trace_id(request_question_id) or response_question_id
    return part, question_id


def trace_context_from_response(response: AgentResponse) -> tuple[int | None, str | None]:
    part: int | None = None
    question_id: str | None = None
    for event in response.events:
        payload = event.payload
        if part is None:
            part = normalize_part(payload.get("part"))
        if question_id is None:
            question_id = sanitize_trace_id(payload.get("question_id"))
        if part is not None and question_id is not None:
            return part, question_id

    state_part = part_from_state(response.state)
    state_question_id = question_id_from_state(response.state)
    return part or state_part, question_id or sanitize_trace_id(state_question_id)


def part_from_state(state: Mapping[str, Any]) -> int | None:
    part = normalize_part(state.get("current_part") or state.get("part"))
    if part is not None:
        return part
    for answer in state.get("answers") or []:
        if isinstance(answer, Mapping):
            answer_part = normalize_part(answer.get("part"))
            if answer_part is not None:
                return answer_part
    return None


def question_id_from_state(state: Mapping[str, Any]) -> str | None:
    direct = sanitize_trace_id(state.get("question_id"))
    if direct:
        return direct

    current_part = part_from_state(state)
    question_index = normalize_question_index(state.get("question_index"))
    question_plan = state.get("question_plan")
    if isinstance(question_plan, Mapping):
        for part_plan in question_plan.get("parts") or []:
            if not isinstance(part_plan, Mapping):
                continue
            if current_part is not None and normalize_part(part_plan.get("part")) != current_part:
                continue
            questions = part_plan.get("questions") or []
            if 0 <= question_index < len(questions):
                question = questions[question_index]
                if isinstance(question, Mapping):
                    question_id = sanitize_trace_id(question.get("question_id"))
                    if question_id:
                        return question_id

    for answer in reversed(state.get("answers") or []):
        if isinstance(answer, Mapping):
            question_id = sanitize_trace_id(answer.get("question_id"))
            if question_id:
                return question_id
    return None


def normalize_part(value: Any) -> int | None:
    if value is None:
        return None
    try:
        part = int(value)
    except (TypeError, ValueError):
        return None
    return part if part in {1, 2, 3} else None


def normalize_question_index(value: Any) -> int:
    try:
        index = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, index)


def sanitize_trace_id(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return sanitize_text(value.strip(), limit=120)


def agent_name_for_node(workflow_node: str, mode: str | None) -> str:
    if workflow_node == "consume_asr":
        return "FollowupPlannerAgent"
    if mode in {"part_practice", "topic_practice"}:
        return "PracticeWorkflow"
    return "ExamWorkflow"


def prompt_version_for_node(workflow_node: str, mode: str | None) -> str:
    if workflow_node == "consume_asr":
        return "mock.followup_planner.v1"
    if mode in {"part_practice", "topic_practice"}:
        return "mock.practice_workflow.v1"
    return "mock.exam_workflow.v1"


def model_name_for_settings(settings: Settings) -> str:
    if settings.mock_model_enabled:
        return "mock-model"
    return settings.mimo_default_model


def elapsed_ms(started_perf: float) -> int:
    return max(0, int((perf_counter() - started_perf) * 1000))


def retrieved_chunks_from_response(response: AgentResponse) -> list[dict[str, Any]]:
    question_plan = response.state.get("question_plan")
    if not isinstance(question_plan, dict):
        return []
    chunks: list[dict[str, Any]] = []
    for part in question_plan.get("parts") or []:
        if not isinstance(part, dict):
            continue
        for question in part.get("questions") or []:
            if not isinstance(question, dict):
                continue
            evidence = question.get("evidence")
            if not isinstance(evidence, dict):
                continue
            source_ref = evidence.get("source_ref")
            chunks.append(
                {
                    "workflow_node": "question_planner",
                    "source": evidence.get("source"),
                    "question_id": question.get("question_id"),
                    "score": evidence.get("score"),
                    "source_ref": source_ref if isinstance(source_ref, dict) else None,
                }
            )
    return chunks[:20]


def scoring_result_from_response(response: AgentResponse) -> dict[str, Any] | None:
    report = response.state.get("score_report")
    if not isinstance(report, dict):
        return None
    criteria = report.get("criteria") if isinstance(report.get("criteria"), dict) else {}
    return {
        "overall_band": report.get("overall_band"),
        "confidence": report.get("confidence"),
        "criteria": {
            key: {
                "band": value.get("band"),
                "confidence": value.get("confidence"),
            }
            for key, value in criteria.items()
            if isinstance(value, dict)
        },
        "disclaimer_present": bool(report.get("disclaimer")),
    }


def tool_calls_from_mcp_audit(start_index: int) -> list[TraceToolCall]:
    records = list(get_mcp_audit_sink().records[start_index:])
    if not records:
        return []
    execution_records = [record for record in records if record.phase == "execution"]
    selected = execution_records or records
    calls: list[TraceToolCall] = []
    for record in selected:
        calls.append(
            TraceToolCall(
                tool_name=record.tool_name,
                scope=",".join(record.required_scopes) or None,
                status="completed" if record.status in {"allowed", "completed"} else "failed",
                latency_ms=record.latency_ms or 0,
                error_code=record.reason,
                input_summary=sanitize_text(json.dumps(record.arguments, ensure_ascii=False), limit=160) if record.arguments else None,
                output_summary=sanitize_text(json.dumps(record.output_payload, ensure_ascii=False), limit=160) if record.output_payload is not None else None,
                result_summary=sanitize_text(str(record.reason), limit=160) if record.reason else None,
                input_payload=sanitize_raw_payload(record.arguments) if record.arguments else None,
                output_payload=sanitize_raw_payload(record.output_payload) if record.output_payload is not None else None,
                arguments=sanitize_raw_payload(record.arguments) if record.arguments else None,
                parameters=sanitize_raw_payload(record.arguments) if record.arguments else None,
                request=sanitize_raw_payload(record.arguments) if record.arguments else None,
                response=sanitize_raw_payload(record.output_payload) if record.output_payload is not None else None,
                metadata={
                    "phase": record.phase,
                    "request_id": record.request_id,
                    "granted_scopes": record.granted_scopes,
                    "user_id_hash": record.user_id_hash,
                },
            )
        )
    return calls


def build_session_audit_detail(
    *,
    session_id: str,
    events: Sequence[SessionEvent],
    traces: Sequence[AgentRunTrace],
) -> SessionAuditDetail:
    started_candidates = [event.created_at for event in events] + [trace.started_at for trace in traces]
    ended_candidates = [event.created_at for event in events] + [trace.finished_at or trace.started_at for trace in traces]
    completed_parts = completed_parts_from_events(events)
    recent_events = list(sorted(events, key=lambda event: event.created_at))[-6:]
    mode = next((trace.mode for trace in reversed(traces) if trace.mode), mode_from_events(events))
    current_part = current_part_from_events(events) or next((trace.part for trace in reversed(traces) if trace.part), None)
    latest_question_id = latest_question_id_from_events(events) or next((trace.question_id for trace in reversed(traces) if trace.question_id), None)
    user_id_hash = next((trace.user_id_hash for trace in reversed(traces) if trace.user_id_hash), None)
    agent_names = sorted({step.agent_name for trace in traces for step in trace.steps if step.agent_name})
    event_type_counts: dict[str, int] = {}
    for event in events:
        event_type_counts[event.type] = event_type_counts.get(event.type, 0) + 1
    runs = [run_summary(trace) for trace in sorted(traces, key=lambda trace: trace.started_at, reverse=True)]
    completed_run_count = sum(1 for trace in traces if trace.status == "completed")
    failed_run_count = sum(1 for trace in traces if trace.status == "failed")
    status = session_status_from_audit(events, traces)
    return SessionAuditDetail(
        session_id=session_id,
        user_id_hash=user_id_hash,
        mode=mode,
        status=status,
        started_at=min(started_candidates) if started_candidates else datetime.now(UTC),
        last_event_at=max(ended_candidates) if ended_candidates else datetime.now(UTC),
        run_count=len(traces),
        event_count=len(events),
        completed_run_count=completed_run_count,
        failed_run_count=failed_run_count,
        current_part=current_part,
        latest_question_id=latest_question_id,
        completed_parts=completed_parts,
        recent_event_types=[event.type for event in recent_events],
        agent_names=agent_names,
        event_type_counts=dict(sorted(event_type_counts.items())),
        events=list(sorted(events, key=lambda event: event.created_at)),
        runs=runs,
        traces=list(traces),
    )


def session_status_from_audit(events: Sequence[SessionEvent], traces: Sequence[AgentRunTrace]) -> str:
    if any(event.type == "report.ready" for event in events):
        return "completed"
    if any(event.type == "error.fatal" for event in events):
        return "failed"
    if any(trace.status == "failed" for trace in traces):
        return "failed"
    if any(event.type == "scoring.started" for event in events):
        return "scoring"
    if any(event.type == "session.completed" for event in events):
        return "session_completed"
    if traces:
        return traces[-1].status
    return "in_progress"


def mode_from_events(events: Sequence[SessionEvent]) -> str | None:
    for event in events:
        mode = event.payload.get("mode")
        if isinstance(mode, str) and mode.strip():
            return mode
    return None


def current_part_from_events(events: Sequence[SessionEvent]) -> int | None:
    for event in reversed(events):
        part = normalize_part(event.payload.get("part"))
        if part is not None:
            return part
    return None


def latest_question_id_from_events(events: Sequence[SessionEvent]) -> str | None:
    for event in reversed(events):
        question_id = sanitize_trace_id(event.payload.get("question_id"))
        if question_id:
            return question_id
    return None


def completed_parts_from_events(events: Sequence[SessionEvent]) -> list[int]:
    completed: set[int] = set()
    for event in events:
        if event.type == "session.completed":
            for part in event.payload.get("completed_parts") or []:
                normalized = normalize_part(part)
                if normalized is not None:
                    completed.add(normalized)
        if event.type == "part.completed":
            normalized = normalize_part(event.payload.get("part"))
            if normalized is not None:
                completed.add(normalized)
    return sorted(completed)


def build_observability_summary(traces: Sequence[AgentRunTrace], *, filters: dict[str, str]) -> ObservabilitySummary:
    run_latencies = [run_latency_ms(trace) for trace in traces if run_latency_ms(trace) is not None]
    completed_count = sum(1 for trace in traces if trace.status == "completed")
    failed_count = sum(1 for trace in traces if trace.status == "failed")
    cancelled_count = sum(1 for trace in traces if trace.status == "cancelled")
    tool_calls = [tool for trace in traces for step in trace.steps for tool in step.tool_calls]
    tool_failed_count = sum(1 for tool in tool_calls if tool.status == "failed")
    steps = [step for trace in traces for step in trace.steps]
    structured_steps = [step for step in steps if step.structured_output_validity is not None]
    structured_valid_count = sum(1 for step in structured_steps if step.structured_output_validity is True)
    real_llm_calls = [call for step in steps for call in step.llm_calls if is_real_llm_call(call)]
    input_token_count = sum(call.input_tokens or 0 for call in real_llm_calls)
    output_token_count = sum(call.output_tokens or 0 for call in real_llm_calls)
    estimated_model_cost_usd = round(
        sum(step.estimated_cost_usd or 0 for step in steps if any(is_real_llm_call(call) for call in step.llm_calls)),
        6,
    )
    errors_by_code: dict[str, int] = {}
    for trace in traces:
        for step in trace.steps:
            if step.error_code:
                errors_by_code[step.error_code] = errors_by_code.get(step.error_code, 0) + 1

    return ObservabilitySummary(
        generated_at=datetime.now(UTC),
        filters=filters,
        run_count=len(traces),
        completed_count=completed_count,
        failed_count=failed_count,
        cancelled_count=cancelled_count,
        error_rate=round(failed_count / len(traces), 4) if traces else 0.0,
        latency=latency_stats(run_latencies),
        workflow_nodes=workflow_node_stats(traces),
        tool_call_count=len(tool_calls),
        tool_success_rate=round((len(tool_calls) - tool_failed_count) / len(tool_calls), 4) if tool_calls else 1.0,
        tool_calls_by_name=tool_call_stats(tool_calls),
        structured_output_total=len(structured_steps),
        structured_output_valid_count=structured_valid_count,
        structured_output_validity_rate=round(structured_valid_count / len(structured_steps), 4) if structured_steps else 1.0,
        input_token_count=input_token_count,
        output_token_count=output_token_count,
        estimated_model_cost_usd=estimated_model_cost_usd,
        errors_by_code=dict(sorted(errors_by_code.items())),
        recent_runs=[run_summary(trace) for trace in traces],
    )


def run_latency_ms(trace: AgentRunTrace) -> int | None:
    latencies = [step.latency_ms for step in trace.steps if step.latency_ms is not None]
    if latencies:
        return sum(latencies)
    if trace.finished_at:
        return max(0, int((trace.finished_at - trace.started_at).total_seconds() * 1000))
    return None


def latency_stats(latencies: Sequence[int]) -> LatencyStats:
    values = sorted(max(0, int(value)) for value in latencies)
    if not values:
        return LatencyStats(count=0, avg_ms=0.0, p50_ms=0, p95_ms=0, min_ms=0, max_ms=0)
    return LatencyStats(
        count=len(values),
        avg_ms=round(sum(values) / len(values), 2),
        p50_ms=percentile(values, 0.50),
        p95_ms=percentile(values, 0.95),
        min_ms=values[0],
        max_ms=values[-1],
    )


def percentile(sorted_values: Sequence[int], quantile: float) -> int:
    if not sorted_values:
        return 0
    index = max(0, min(len(sorted_values) - 1, int((len(sorted_values) - 1) * quantile + 0.999999)))
    return sorted_values[index]


def workflow_node_stats(traces: Sequence[AgentRunTrace]) -> list[WorkflowNodeStats]:
    grouped: dict[str, list[TraceStep]] = {}
    for trace in traces:
        for step in trace.steps:
            grouped.setdefault(step.workflow_node, []).append(step)
    stats: list[WorkflowNodeStats] = []
    for node, steps in sorted(grouped.items()):
        latencies = [step.latency_ms for step in steps if step.latency_ms is not None]
        stats.append(
            WorkflowNodeStats(
                workflow_node=node,
                run_count=len(steps),
                failed_count=sum(1 for step in steps if step.status == "failed"),
                latency=latency_stats(latencies),
            )
        )
    return stats


def tool_call_stats(tool_calls: Sequence[TraceToolCall]) -> list[ToolCallStats]:
    grouped: dict[str, list[TraceToolCall]] = {}
    for tool in tool_calls:
        grouped.setdefault(tool.tool_name, []).append(tool)
    stats: list[ToolCallStats] = []
    for tool_name, calls in sorted(grouped.items()):
        failed_count = sum(1 for call in calls if call.status == "failed")
        stats.append(
            ToolCallStats(
                tool_name=tool_name,
                call_count=len(calls),
                failed_count=failed_count,
                avg_latency_ms=round(sum(call.latency_ms for call in calls) / len(calls), 2),
                success_rate=round((len(calls) - failed_count) / len(calls), 4),
            )
        )
    return stats


def run_summary(trace: AgentRunTrace) -> ObservabilityRunSummary:
    return ObservabilityRunSummary(
        run_id=trace.run_id,
        session_id=trace.session_id,
        user_id_hash=trace.user_id_hash,
        mode=trace.mode,
        part=trace.part,
        question_id=trace.question_id,
        status=trace.status,
        latency_ms=run_latency_ms(trace),
        step_count=len(trace.steps),
        llm_call_count=sum(1 for step in trace.steps for call in step.llm_calls if is_real_llm_call(call)),
        tool_call_count=sum(len(step.tool_calls) for step in trace.steps),
        error_code=next((step.error_code for step in trace.steps if step.error_code), None),
        started_at=trace.started_at,
        finished_at=trace.finished_at,
    )


def evaluate_observability_alerts(
    summary: ObservabilitySummary,
    *,
    error_rate_threshold: float,
    latency_p95_threshold_ms: int,
) -> list[ObservabilityAlert]:
    alerts: list[ObservabilityAlert] = []
    if summary.run_count > 0 and summary.error_rate >= error_rate_threshold:
        alerts.append(
            ObservabilityAlert(
                alert_id="agent_error_rate_high",
                severity="critical" if summary.error_rate >= error_rate_threshold * 2 else "warning",
                metric="agent_error_rate",
                message="Agent Harness 错误率超过发布阈值，请优先查看 errors_by_code 与失败 trace。",
                threshold=error_rate_threshold,
                actual=summary.error_rate,
                runbook="docs/phase9_quality_gate.md#日志与告警",
            )
        )
    if summary.latency.count > 0 and summary.latency.p95_ms >= latency_p95_threshold_ms:
        alerts.append(
            ObservabilityAlert(
                alert_id="agent_latency_p95_high",
                severity="warning",
                metric="agent_latency_p95_ms",
                message="Agent Harness p95 延迟超过基线阈值，请拆分 ASR/TTS/评分/报告节点耗时。",
                threshold=float(latency_p95_threshold_ms),
                actual=float(summary.latency.p95_ms),
                runbook="docs/phase9_quality_gate.md#性能基线",
            )
        )
    if summary.tool_call_count > 0 and summary.tool_success_rate < 0.98:
        alerts.append(
            ObservabilityAlert(
                alert_id="agent_tool_success_rate_low",
                severity="critical",
                metric="agent_tool_success_rate",
                message="MCP 工具调用成功率低于阈值，高风险工具失败会阻塞发布。",
                threshold=0.98,
                actual=summary.tool_success_rate,
                runbook="docs/phase9_quality_gate.md#promptfoo-安全红队",
            )
        )
    return alerts


def build_prometheus_metrics(summary: ObservabilitySummary) -> str:
    lines = [
        "# HELP agent_harness_runs_total Number of recorded Agent Harness runs.",
        "# TYPE agent_harness_runs_total gauge",
        f"agent_harness_runs_total {summary.run_count}",
        "# HELP agent_harness_errors_total Number of failed Agent Harness runs.",
        "# TYPE agent_harness_errors_total gauge",
        f"agent_harness_errors_total {summary.failed_count}",
        "# HELP agent_harness_error_rate Current in-memory Agent Harness error rate.",
        "# TYPE agent_harness_error_rate gauge",
        f"agent_harness_error_rate {summary.error_rate}",
        "# HELP agent_harness_latency_p95_ms Current in-memory Agent Harness p95 latency in milliseconds.",
        "# TYPE agent_harness_latency_p95_ms gauge",
        f"agent_harness_latency_p95_ms {summary.latency.p95_ms}",
        "# HELP agent_harness_tool_success_rate Current MCP tool success rate.",
        "# TYPE agent_harness_tool_success_rate gauge",
        f"agent_harness_tool_success_rate {summary.tool_success_rate}",
        "# HELP agent_harness_structured_output_validity_rate Current structured output validity rate.",
        "# TYPE agent_harness_structured_output_validity_rate gauge",
        f"agent_harness_structured_output_validity_rate {summary.structured_output_validity_rate}",
        "# HELP agent_harness_input_tokens_total Estimated input tokens across recorded runs.",
        "# TYPE agent_harness_input_tokens_total gauge",
        f"agent_harness_input_tokens_total {summary.input_token_count}",
        "# HELP agent_harness_output_tokens_total Estimated output tokens across recorded runs.",
        "# TYPE agent_harness_output_tokens_total gauge",
        f"agent_harness_output_tokens_total {summary.output_token_count}",
        "# HELP agent_harness_estimated_model_cost_usd Estimated model cost in USD across recorded runs.",
        "# TYPE agent_harness_estimated_model_cost_usd gauge",
        f"agent_harness_estimated_model_cost_usd {summary.estimated_model_cost_usd}",
    ]
    for node in summary.workflow_nodes:
        label = sanitize_metric_label(node.workflow_node)
        lines.append(f'agent_harness_workflow_node_runs_total{{workflow_node="{label}"}} {node.run_count}')
        lines.append(f'agent_harness_workflow_node_failed_total{{workflow_node="{label}"}} {node.failed_count}')
        lines.append(f'agent_harness_workflow_node_latency_p95_ms{{workflow_node="{label}"}} {node.latency.p95_ms}')
    return "\n".join(lines) + "\n"


def sanitize_metric_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
