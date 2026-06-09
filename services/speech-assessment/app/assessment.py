from __future__ import annotations

import hashlib
import re

from app.fluency_metrics import compute_fluency_metrics
from app.gopt_scorer import build_pronunciation_evidence
from app.schemas import (
    AssessmentPolicy,
    AudioQualityEvidence,
    SpeechAssessmentRequest,
    SpeechAssessmentResponse,
)


def assess_speech(request: SpeechAssessmentRequest) -> SpeechAssessmentResponse:
    fluency = compute_fluency_metrics(request)
    pronunciation = build_pronunciation_evidence(request, fluency)
    confidence = round((fluency.confidence + pronunciation.confidence) / 2, 2)
    duration_ms = round(fluency.duration_sec * 1000)

    response = SpeechAssessmentResponse(
        evidence_id=stable_evidence_id(request),
        audio_asset_id=request.audio_asset_id,
        mode=request.mode,
        audio_quality=AudioQualityEvidence(
            duration_ms=duration_ms,
            quality_label="usable" if confidence >= 0.65 else "low_quality",
            clipping_detected=False,
            estimated_snr_db=28.0 if confidence >= 0.65 else None,
            confidence=confidence,
        ),
        fluency=fluency,
        pronunciation=pronunciation,
        confidence=confidence,
        policy=AssessmentPolicy(
            consumer_instruction=(
                "Use this payload as speech evidence only. ScoringWorkflow must combine it with "
                "transcript, rubric, anchors, and confidence; it must not map evidence directly to an IELTS band."
            ),
            separated_paths=["mock_exam", "pronunciation_drill"],
        ),
        warnings=[],
    )
    if not request.word_timestamps:
        response.warnings.append("word_timestamps_missing: using transcript-only deterministic estimates")
    if not request.vad_segments:
        response.warnings.append("vad_segments_missing: deriving speech duration from word timings or transcript")
    if request.mode == "mock_exam" and request.target_text:
        response.warnings.append("target_text_ignored_for_mock_exam")
    return response


def normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def stable_evidence_id(request: SpeechAssessmentRequest) -> str:
    raw = "|".join([request.audio_asset_id, request.mode, request.turn_id or "", request.transcript or ""])
    return f"speech_ev_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def clamp(value: float, floor: float = 0.0, ceiling: float = 1.0) -> float:
    return min(max(value, floor), ceiling)
