from __future__ import annotations

import hashlib
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
from app.protocols.schemas import AgentResponse, ConsumeAsrRequest, NextTurnRequest, PlanRequest


TraceStatus = Literal["running", "completed", "failed", "cancelled"]
StepStatus = Literal["running", "completed", "failed"]
ToolStatus = Literal["completed", "failed"]

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


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    workflow_node: str
    part: int | None = Field(default=None, ge=1, le=3)
    question_id: str | None = None
    agent_name: str | None = None
    prompt_version: str | None = None
    model_name: str | None = None
    status: StepStatus
    input_summary: str | None = None
    output_summary: str | None = None
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
    mode: str | None = None
    part: int | None = Field(default=None, ge=1, le=3)
    question_id: str | None = None
    status: TraceStatus
    latency_ms: int | None = Field(default=None, ge=0)
    step_count: int = Field(ge=0)
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
    def __init__(self, settings: Settings, store: TraceStore | None = None, exporter: LangfuseExporter | None = None) -> None:
        self.settings = settings
        self.store = store or TraceStore(settings.trace_store_limit)
        self.exporter = exporter or LangfuseExporter(settings)

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
        run_id = ""
        status: TraceStatus = "completed"
        error_code: str | None = None
        audit_start_index = len(get_mcp_audit_sink().records)

        try:
            response = call()
            run_id = response.run_id
            return response
        except Exception as exc:
            status = "failed"
            run_id = f"run_failed_{uuid4().hex}"
            error_code = str(getattr(exc, "code", exc.__class__.__name__))
            raise
        finally:
            finished_at = datetime.now(UTC)
            latency_ms = elapsed_ms(started_perf)
            output_summary = None
            if "response" in locals():
                output_summary = summarize_response(response)
            input_summary = summarize_request(request)
            input_tokens = estimate_tokens(input_summary)
            output_tokens = estimate_tokens(output_summary or "")
            tool_calls = tool_calls_from_mcp_audit(audit_start_index)
            trace_part, trace_question_id = trace_context_from_request(
                request,
                response if "response" in locals() else None,
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
                steps=[
                    TraceStep(
                        step_id=f"step_{uuid4().hex}",
                        workflow_node=workflow_node,
                        part=trace_part,
                        question_id=trace_question_id,
                        agent_name=agent_name_for_node(workflow_node, mode),
                        prompt_version=prompt_version_for_node(workflow_node, mode),
                        model_name=model_name_for_settings(self.settings),
                        status="completed" if status == "completed" else "failed",
                        input_summary=input_summary,
                        output_summary=output_summary,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        estimated_cost_usd=estimate_model_cost_usd(input_tokens, output_tokens, self.settings),
                        retrieved_chunks=retrieved_chunks_from_response(response) if "response" in locals() else [],
                        structured_output_validity=status == "completed",
                        scoring_result=scoring_result_from_response(response) if "response" in locals() else None,
                        latency_ms=latency_ms,
                        error_code=error_code,
                        error_type=error_code,
                        started_at=started_at,
                        finished_at=finished_at,
                        tool_calls=tool_calls,
                    )
                ],
            )
            self.exporter.export(trace)
            self.store.save(trace)

    def get_trace(self, run_id: str) -> AgentRunTrace | None:
        return self.store.get(run_id)

    def cancel_run(self, run_id: str) -> AgentRunTrace | None:
        return self.store.mark_cancelled(run_id)

    def query_summary(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
        limit: int = 100,
    ) -> ObservabilitySummary:
        return self.store.summary(session_id=session_id, run_id=run_id, mode=mode, limit=limit)

    def query_alerts(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
        limit: int = 100,
    ) -> list[ObservabilityAlert]:
        return self.store.alerts(
            session_id=session_id,
            run_id=run_id,
            mode=mode,
            limit=limit,
            error_rate_threshold=self.settings.observability_error_rate_alert_threshold,
            latency_p95_threshold_ms=self.settings.observability_latency_p95_alert_ms,
        )

    def prometheus_metrics(self) -> str:
        return build_prometheus_metrics(self.store.summary(limit=self.settings.trace_store_limit))


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
                        "tool_calls": [tool.model_dump(mode="json", exclude_none=True) for tool in step.tool_calls],
                    },
                    "input": step.input_summary,
                    "output": step.output_summary,
                },
            }
        )
    return {"batch": batch}


def hash_user_id(user_id: str, salt: str) -> str:
    digest = hashlib.sha256(f"{salt}:{user_id}".encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def sanitize_text(value: str | None, *, limit: int = 300) -> str | None:
    if value is None:
        return None
    sanitized = value
    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    if len(sanitized) > limit:
        return f"{sanitized[:limit]}..."
    return sanitized


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, len(re.findall(r"\w+|[^\w\s]", text)))


def estimate_model_cost_usd(input_tokens: int | None, output_tokens: int | None, settings: Settings) -> float:
    input_cost = ((input_tokens or 0) / 1000) * settings.mimo_input_cost_usd_per_1k_tokens
    output_cost = ((output_tokens or 0) / 1000) * settings.mimo_output_cost_usd_per_1k_tokens
    return round(input_cost + output_cost, 6)


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
    calls: list[TraceToolCall] = []
    for record in get_mcp_audit_sink().records[start_index:]:
        calls.append(
            TraceToolCall(
                tool_name=record.tool_name,
                scope=",".join(record.required_scopes) or None,
                status="completed" if record.status == "allowed" else "failed",
                latency_ms=0,
                error_code=record.reason,
            )
        )
    return calls


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
    input_token_count = sum(step.input_tokens or 0 for step in steps)
    output_token_count = sum(step.output_tokens or 0 for step in steps)
    estimated_model_cost_usd = round(sum(step.estimated_cost_usd or 0 for step in steps), 6)
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
        recent_runs=[run_summary(trace) for trace in traces[:20]],
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
        mode=trace.mode,
        part=trace.part,
        question_id=trace.question_id,
        status=trace.status,
        latency_ms=run_latency_ms(trace),
        step_count=len(trace.steps),
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
