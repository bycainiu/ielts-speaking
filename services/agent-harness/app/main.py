import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.audio.asr_service import (
    ASR_MODEL,
    SUPPORTED_AUDIO_MIME_TYPES,
    AsrService,
    AsrServiceError,
    MissingAudioSourceError,
    UnsupportedAudioFormatError,
)
from app.audio.tts_service import TTS_MODEL, TTSService, TTSServiceError
from app.agents.score_calibrator import ScoreCalibratorInput, ScoreCalibratorOutput
from app.agents.question_planner_agent import QuestionSetPlannerAgent
from app.calibration_api import (
    AnchorSamplesResponse,
    CalibrationQualityGateRequest,
    CalibrationQualityGateResponse,
    MultiPAExperimentRunRequest,
    SpeechCalibrationRunRequest,
    build_anchor_samples_response,
    run_calibration_quality_gate,
    run_multipa_experiment,
    run_score_calibration,
    run_speech_calibration,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.runtime import AgentRuntime
from app.evals.multipa_open_response import MultiPAExperimentReport
from app.evals.speech_calibration import SpeechCalibrationRegressionReport
from app.observability.langfuse_client import AgentRunTrace, ObservabilityAlert, ObservabilitySummary, TraceRecorder
from app.protocols.schemas import (
    AgentResponse,
    ConsumeAsrRequest,
    NextTurnRequest,
    PlanRequest,
    RunSummary,
    SynthesizeSpeechRequest,
    SynthesizeSpeechResponse,
    TranscribeAudioRequest,
    TranscribeAudioResponse,
)
from app.mcp.question_bank_mcp import QuestionBankMcpTools
from app.rag.llamaindex_service import LlamaIndexKnowledgeService
from app.rag.ingestion.question_bank_indexer import QuestionBankIndexer
from app.recovery.error_policy import RecoveryDirective, RecoveryPolicyRequest, recovery_directive_for
from app.workflows.exam_workflow import ExamWorkflow
from app.workflows.practice_workflow import PracticeWorkflow
from app.workflows.scoring_workflow import ScoreSessionRequest, ScoringWorkflow

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="IELTS Speaking Agent Harness",
    version="0.1.0",
)
runtime = AgentRuntime()
scoring_workflow = ScoringWorkflow()
trace_recorder = TraceRecorder(settings)
knowledge_service = LlamaIndexKnowledgeService.from_settings(settings)
question_bank_tools = QuestionBankMcpTools(QuestionBankIndexer(knowledge_service))
exam_workflow = ExamWorkflow(question_planner=QuestionSetPlannerAgent(question_bank_tools=question_bank_tools))
practice_workflow = PracticeWorkflow(question_planner=QuestionSetPlannerAgent(question_bank_tools=question_bank_tools))
asr_service = AsrService(settings)
tts_service = TTSService(settings)
logger = logging.getLogger("agent_harness.request")


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
    return {
        "status": "ok",
        "service": "agent-harness",
        "env": settings.app_env,
        "mock_model_enabled": settings.mock_model_enabled,
        "model_provider": {
            "api_format": settings.mimo_api_format,
            "default_model": settings.mimo_default_model,
            "available_models": settings.mimo_available_models(),
        },
        "asr": {
            "model": ASR_MODEL,
            "mock_enabled": settings.mock_model_enabled,
            "supported_mime_types": sorted(SUPPORTED_AUDIO_MIME_TYPES),
        },
        "tts": {
            "model": TTS_MODEL,
            "mock_enabled": settings.mock_model_enabled,
            "default_mime_type": "audio/wav",
        },
        "runtime": runtime.describe(),
        "knowledge_service": knowledge_service.describe(),
    }


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics() -> PlainTextResponse:
    return PlainTextResponse(trace_recorder.prometheus_metrics(), media_type="text/plain; version=0.0.4")


@app.post("/agent/sessions/{session_id}/plan", response_model=AgentResponse)
def plan_session(session_id: str, request: PlanRequest) -> AgentResponse:
    planned_request = request.model_copy(update={"session_seed": request.session_seed or session_id})
    return trace_recorder.record_agent_call(
        session_id=session_id,
        workflow_node="plan_session",
        request=planned_request,
        call=lambda: workflow_for_mode(planned_request.mode).plan(session_id, planned_request),
    )


@app.post("/agent/sessions/{session_id}/consume-asr", response_model=AgentResponse)
def consume_asr(session_id: str, request: ConsumeAsrRequest) -> AgentResponse:
    mode = str(request.session_state.get("mode") or "full_exam")
    return trace_recorder.record_agent_call(
        session_id=session_id,
        workflow_node="consume_asr",
        request=request,
        call=lambda: workflow_for_mode(mode).consume_asr(session_id, request),
    )


@app.post("/agent/sessions/{session_id}/next-turn", response_model=AgentResponse)
def next_turn(session_id: str, request: NextTurnRequest) -> AgentResponse:
    mode = str(request.session_state.get("mode") or "full_exam")
    return trace_recorder.record_agent_call(
        session_id=session_id,
        workflow_node="next_turn",
        request=request,
        call=lambda: workflow_for_mode(mode).next_turn(session_id, request),
    )


@app.post("/agent/sessions/{session_id}/score", response_model=AgentResponse)
def score_session(session_id: str, request: ScoreSessionRequest) -> AgentResponse:
    return trace_recorder.record_agent_call(
        session_id=session_id,
        workflow_node="score_session",
        request=request,
        call=lambda: scoring_workflow.score_session(session_id, request),
    )


@app.post("/agent/audio/transcribe", response_model=TranscribeAudioResponse)
async def transcribe_audio(request: TranscribeAudioRequest) -> TranscribeAudioResponse:
    try:
        return await asr_service.transcribe(request)
    except UnsupportedAudioFormatError as exc:
        raise HTTPException(status_code=415, detail=error_detail(exc)) from exc
    except MissingAudioSourceError as exc:
        raise HTTPException(status_code=422, detail=error_detail(exc)) from exc
    except AsrServiceError as exc:
        status_code = 503 if exc.retryable else 502
        raise HTTPException(status_code=status_code, detail=error_detail(exc)) from exc


@app.post("/agent/audio/synthesize", response_model=SynthesizeSpeechResponse)
async def synthesize_speech(request: SynthesizeSpeechRequest) -> SynthesizeSpeechResponse:
    try:
        return await tts_service.synthesize(request)
    except TTSServiceError as exc:
        status_code = 503 if exc.retryable else 502
        raise HTTPException(status_code=status_code, detail=error_detail(exc)) from exc


@app.get("/agent/runs/{run_id}", response_model=RunSummary)
def get_run(run_id: str) -> RunSummary:
    trace = trace_recorder.get_trace(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="agent run not found")
    return RunSummary(run_id=run_id, status=trace.status, runtime=runtime.describe())


@app.get("/agent/runs/{run_id}/trace", response_model=AgentRunTrace)
def get_trace(run_id: str) -> AgentRunTrace:
    trace = trace_recorder.get_trace(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="agent run trace not found")
    return trace


@app.get("/agent/observability/summary", response_model=ObservabilitySummary)
def get_observability_summary(
    session_id: str | None = None,
    run_id: str | None = None,
    mode: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> ObservabilitySummary:
    return trace_recorder.query_summary(session_id=session_id, run_id=run_id, mode=mode, limit=limit)


@app.get("/agent/observability/alerts", response_model=list[ObservabilityAlert])
def get_observability_alerts(
    session_id: str | None = None,
    run_id: str | None = None,
    mode: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ObservabilityAlert]:
    return trace_recorder.query_alerts(session_id=session_id, run_id=run_id, mode=mode, limit=limit)


@app.get("/agent/calibration/anchor-samples", response_model=AnchorSamplesResponse)
def get_calibration_anchor_samples(include_samples: bool = True) -> AnchorSamplesResponse:
    return build_anchor_samples_response(include_samples=include_samples)


@app.post("/agent/calibration/score", response_model=ScoreCalibratorOutput)
def calibrate_score(request: ScoreCalibratorInput) -> ScoreCalibratorOutput:
    return run_score_calibration(request)


@app.post("/agent/calibration/speech-regression", response_model=SpeechCalibrationRegressionReport)
def run_speech_calibration_regression(request: SpeechCalibrationRunRequest) -> SpeechCalibrationRegressionReport:
    return run_speech_calibration(request)


@app.post("/agent/calibration/multipa-experiment", response_model=MultiPAExperimentReport)
def run_multipa_open_response_experiment(request: MultiPAExperimentRunRequest) -> MultiPAExperimentReport:
    return run_multipa_experiment(request)


@app.post("/agent/calibration/quality-gate", response_model=CalibrationQualityGateResponse)
def run_calibration_gate(request: CalibrationQualityGateRequest) -> CalibrationQualityGateResponse:
    return run_calibration_quality_gate(request)


@app.post("/agent/runs/{run_id}/cancel", response_model=RunSummary)
def cancel_run(run_id: str) -> RunSummary:
    trace = trace_recorder.cancel_run(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="agent run not found")
    return RunSummary(run_id=run_id, status="cancelled", runtime=runtime.describe())


@app.post("/agent/recovery/directive", response_model=RecoveryDirective)
def get_recovery_directive(request: RecoveryPolicyRequest) -> RecoveryDirective:
    return recovery_directive_for(request)


def workflow_for_mode(mode: str) -> ExamWorkflow | PracticeWorkflow:
    if mode in {"part_practice", "topic_practice"}:
        return practice_workflow
    return exam_workflow


def error_detail(error: AsrServiceError) -> dict[str, object]:
    detail: dict[str, object] = {
        "error": error.code,
        "message": str(error),
        "retryable": error.retryable,
    }
    if isinstance(error, UnsupportedAudioFormatError):
        detail["supported_mime_types"] = sorted(SUPPORTED_AUDIO_MIME_TYPES)
    return detail


def session_id_from_path(path: str) -> str | None:
    marker = "/sessions/"
    if marker not in path:
        return None
    tail = path.split(marker, 1)[1]
    session_id = tail.split("/", 1)[0].strip()
    return session_id or None
