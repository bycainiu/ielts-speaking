import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.runtime import OrchestratorRuntime
from app.observability.models import OrchestratorRunRecord
from app.observability.trace import OrchestratorTraceRecorder
from app.protocols.agent_message import AgentMessage
from app.protocols.schemas import (
    AgentResponse,
    AgentStreamEvent,
    ConsumeAsrRequest,
    NextTurnRequest,
    PlanRequest,
    ScoreSessionRequest,
)
from app.workflows.exam_session import ExamSessionWorkflow

settings = get_settings()
configure_logging(settings.log_level)
runtime = OrchestratorRuntime()
trace_recorder = OrchestratorTraceRecorder(settings)
exam_workflow = ExamSessionWorkflow(settings, trace_recorder)
logger = logging.getLogger("agent_orchestrator.request")

app = FastAPI(
    title="IELTS Speaking Agent Orchestrator",
    version="0.1.0",
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or f"req_{uuid4().hex}"
    started = perf_counter()
    session_id = session_id_from_path(request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed",
            extra={
                "request_id": request_id,
                "session_id": session_id,
                "method": request.method,
                "path": request.url.path,
                "latency_ms": int((perf_counter() - started) * 1000),
            },
        )
        raise
    response.headers["x-request-id"] = request_id
    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "session_id": session_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": int((perf_counter() - started) * 1000),
        },
    )
    return response


@app.get("/healthz")
def healthz() -> dict[str, object]:
    from app.llm.gateway import LlmGateway

    gateway = LlmGateway.from_settings(settings)
    return {
        "status": "ok",
        "service": "agent-orchestrator",
        "env": settings.app_env,
        "mock_model_enabled": settings.mock_model_enabled,
        "model_provider": {
            "api_format": settings.mimo_api_format,
            "default_model": settings.mimo_default_model,
            "available_models": settings.mimo_available_models(),
            "llm_enabled": gateway.enabled,
        },
        "runtime": runtime.describe(),
    }


def _resolve_run_id(request: object) -> str:
    override = getattr(request, "run_id_override", None)
    return override or f"run_{uuid4().hex}"


@app.post("/agent/sessions/{session_id}/plan", response_model=AgentResponse)
async def plan_session(session_id: str, request: PlanRequest) -> AgentResponse:
    run_id = _resolve_run_id(request)
    planned_request = request.model_copy(
        update={"session_seed": request.session_seed or session_id, "run_id_override": run_id}
    )
    return await trace_recorder.record_agent_call(
        session_id=session_id,
        workflow_node="plan_session",
        request=planned_request,
        call=lambda: exam_workflow.plan(session_id, planned_request),
    )


@app.post("/agent/sessions/{session_id}/consume-asr", response_model=AgentResponse)
async def consume_asr(session_id: str, request: ConsumeAsrRequest) -> AgentResponse:
    bound = request.model_copy(update={"run_id_override": _resolve_run_id(request)})
    return await trace_recorder.record_agent_call(
        session_id=session_id,
        workflow_node="consume_asr",
        request=bound,
        call=lambda: exam_workflow.consume_asr(session_id, bound),
    )


@app.post("/agent/sessions/{session_id}/next-turn", response_model=AgentResponse)
async def next_turn(session_id: str, request: NextTurnRequest) -> AgentResponse:
    bound = request.model_copy(update={"run_id_override": _resolve_run_id(request)})
    return await trace_recorder.record_agent_call(
        session_id=session_id,
        workflow_node="next_turn",
        request=bound,
        call=lambda: exam_workflow.next_turn(session_id, bound),
    )


@app.post("/agent/sessions/{session_id}/score", response_model=AgentResponse)
async def score_session(session_id: str, request: ScoreSessionRequest) -> AgentResponse:
    bound = request.model_copy(update={"run_id_override": _resolve_run_id(request)})
    return await trace_recorder.record_agent_call(
        session_id=session_id,
        workflow_node="score_session",
        request=bound,
        call=lambda: exam_workflow.score_session(session_id, bound),
    )


@app.get("/agent/runs", response_model=list[OrchestratorRunRecord])
def list_agent_runs(
    session_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[OrchestratorRunRecord]:
    return trace_recorder.list_runs(session_id=session_id, limit=limit)


@app.get("/agent/runs/{run_id}/events", response_model=list[AgentStreamEvent])
def list_run_stream_events(run_id: str, after_seq: int = Query(default=0, ge=0)) -> list[AgentStreamEvent]:
    events = trace_recorder.list_stream_events(run_id, after_seq=after_seq)
    if not events and trace_recorder.get_trace(run_id) is None:
        raise HTTPException(status_code=404, detail="agent run stream not found")
    return events


@app.get("/agent/runs/{run_id}/stream")
async def stream_run_events(run_id: str, after_seq: int = Query(default=0, ge=0)) -> StreamingResponse:
    existing_events = trace_recorder.list_stream_events(run_id, after_seq=0)
    if not existing_events and trace_recorder.get_trace(run_id) is None:
        raise HTTPException(status_code=404, detail="agent run stream not found")
    trace_recorder.stream_broker.add_many(existing_events)
    return StreamingResponse(
        trace_recorder.stream_broker.sse_stream(run_id, after_seq=after_seq),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/agent/runs/{run_id}/trace")
def get_run_trace(run_id: str) -> dict[str, object]:
    trace = trace_recorder.get_trace(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="agent run trace not found")
    return trace.model_dump(mode="json")


@app.get("/agent/runs/{run_id}/messages", response_model=list[AgentMessage])
def list_run_messages(run_id: str) -> list[AgentMessage]:
    messages = trace_recorder.list_agent_messages(run_id)
    if not messages and trace_recorder.get_trace(run_id) is None:
        raise HTTPException(status_code=404, detail="agent run messages not found")
    return messages


@app.get("/agent/runs/{run_id}/tool-iterations")
def list_run_tool_iterations(run_id: str) -> list[dict[str, object]]:
    iterations = trace_recorder.list_tool_iterations(run_id)
    if not iterations and trace_recorder.get_trace(run_id) is None:
        raise HTTPException(status_code=404, detail="agent run tool iterations not found")
    return [item.model_dump(mode="json") for item in iterations]


@app.get("/agent/sessions/{session_id}/timeline")
def get_session_timeline(session_id: str) -> dict[str, object]:
    runs = trace_recorder.list_runs(session_id=session_id, limit=100)
    if not runs:
        raise HTTPException(status_code=404, detail="session timeline not found")
    return {
        "session_id": session_id,
        "runs": [run.model_dump(mode="json") for run in runs],
    }


def session_id_from_path(path: str) -> str | None:
    marker = "/agent/sessions/"
    if marker not in path:
        return None
    remainder = path.split(marker, 1)[1]
    return remainder.split("/", 1)[0] or None
