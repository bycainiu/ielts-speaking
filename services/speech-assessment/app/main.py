import os
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.assessment import assess_speech
from app.pronunciation_drill import PronunciationDrillAdapterError, run_pronunciation_drill
from app.schemas import (
    PronunciationDrillRequest,
    PronunciationDrillResponse,
    SpeechAssessmentRequest,
    SpeechAssessmentResponse,
    TimestampTranscriptionRequest,
    TimestampTranscriptionResponse,
)
from app.timestamps import TimestampAdapterError, transcribe_with_timestamps


SERVICE_NAME = "speech-assessment-service"
MODEL_NAME = "speech-evidence-v0"

app = FastAPI(title="IELTS Speech Assessment Service", version="0.1.0")
request_count = 0
total_latency_ms = 0


@app.middleware("http")
async def request_metrics_middleware(request: Request, call_next):
    global request_count, total_latency_ms
    started = perf_counter()
    response = await call_next(request)
    request_count += 1
    total_latency_ms += int((perf_counter() - started) * 1000)
    response.headers["x-request-id"] = request.headers.get("x-request-id") or f"req_{uuid4().hex}"
    return response


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "env": os.getenv("APP_ENV", "local"),
        "model": MODEL_NAME,
        "mode": os.getenv("SPEECH_ASSESSMENT_MODE", "deterministic"),
        "timestamp_provider": os.getenv("SPEECH_ASR_TIMESTAMP_PROVIDER", "deterministic"),
        "features": {
            "audio_quality": True,
            "fluency_metrics": True,
            "pronunciation_evidence": True,
            "word_timestamps": True,
            "alignment": "optional",
            "faster_whisper": "optional",
            "gopt": "deterministic_gopt",
            "pronunciation_drill": True,
            "mfa_kaldi_gop_drill": "deterministic_adapter_boundary",
        },
        "policy": {
            "ielts_band_output_allowed": False,
            "mock_exam_and_pronunciation_drill_separated": True,
        },
    }


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> PlainTextResponse:
    average_latency = 0 if request_count == 0 else round(total_latency_ms / request_count, 2)
    body = "\n".join(
        [
            "# HELP speech_assessment_requests_total Total HTTP requests handled by speech assessment service.",
            "# TYPE speech_assessment_requests_total counter",
            f"speech_assessment_requests_total {request_count}",
            "# HELP speech_assessment_average_latency_ms Average in-process HTTP latency in milliseconds.",
            "# TYPE speech_assessment_average_latency_ms gauge",
            f"speech_assessment_average_latency_ms {average_latency}",
            "",
        ]
    )
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4")


@app.post("/speech/assess", response_model=SpeechAssessmentResponse)
def assess(request: SpeechAssessmentRequest) -> SpeechAssessmentResponse:
    return assess_speech(request)


@app.post("/speech/pronunciation-drill", response_model=PronunciationDrillResponse)
def pronunciation_drill(request: PronunciationDrillRequest) -> PronunciationDrillResponse:
    try:
        return run_pronunciation_drill(request)
    except PronunciationDrillAdapterError as exc:
        status_code = 503 if exc.retryable else 422
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": "pronunciation_drill_adapter_error",
                "message": str(exc),
                "retryable": exc.retryable,
            },
        ) from exc


@app.post("/speech/transcribe-timestamps", response_model=TimestampTranscriptionResponse)
def transcribe_timestamps(request: TimestampTranscriptionRequest) -> TimestampTranscriptionResponse:
    try:
        return transcribe_with_timestamps(request)
    except TimestampAdapterError as exc:
        status_code = 503 if exc.retryable else 422
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": "timestamp_adapter_error",
                "message": str(exc),
                "retryable": exc.retryable,
            },
        ) from exc
