from __future__ import annotations

import base64
import math
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.assessment import clamp, normalized_words
from app.schemas import (
    TimestampSegment,
    TimestampTranscriptionRequest,
    TimestampTranscriptionResponse,
    WordTimestamp,
)


class TimestampAdapterError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def transcribe_with_timestamps(request: TimestampTranscriptionRequest) -> TimestampTranscriptionResponse:
    if request.provider == "faster_whisper":
        return transcribe_with_faster_whisper(request)
    return deterministic_timestamps(request)


def deterministic_timestamps(request: TimestampTranscriptionRequest) -> TimestampTranscriptionResponse:
    transcript = (request.expected_transcript or "").strip()
    words = normalized_words(transcript)
    duration_ms = request.duration_ms or max(1000, len(words) * 620)
    word_timestamps = evenly_spaced_word_timestamps(words, duration_ms)
    segment = TimestampSegment(
        segment_id=0,
        start_ms=0,
        end_ms=duration_ms,
        text=transcript,
        confidence=0.78 if words else 0.42,
        words=word_timestamps,
    )
    alignment_confidence = 0.8 if words else 0.35
    asr_confidence = 0.82 if words else 0.4
    downstream_confidence = downstream_confidence_for(asr_confidence, alignment_confidence, duration_ms)
    return TimestampTranscriptionResponse(
        audio_asset_id=request.audio_asset_id,
        provider="deterministic",
        model="deterministic-word-timestamp-v0",
        transcript=transcript,
        language=request.language_hint,
        duration_ms=duration_ms,
        word_timestamps=word_timestamps,
        segments=[segment],
        asr_confidence=asr_confidence,
        alignment_confidence=alignment_confidence,
        downstream_confidence=downstream_confidence,
        audio_quality_label=quality_label_for(downstream_confidence),
        warnings=["deterministic_timestamp_provider: replace with faster_whisper for production audio alignment"],
        metadata={"source": "expected_transcript", "word_count": len(words)},
    )


def transcribe_with_faster_whisper(request: TimestampTranscriptionRequest) -> TimestampTranscriptionResponse:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TimestampAdapterError("faster-whisper is not installed in this runtime", retryable=False) from exc

    audio_path, cleanup_path = audio_source_path(request)
    try:
        model_size = os.getenv("FASTER_WHISPER_MODEL_SIZE", "tiny")
        device = os.getenv("FASTER_WHISPER_DEVICE", "cpu")
        compute_type = os.getenv("FASTER_WHISPER_COMPUTE_TYPE", "int8")
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments_iter, info = model.transcribe(
            audio_path,
            language=request.language_hint or None,
            word_timestamps=True,
            vad_filter=True,
        )
        segments = collect_segments(segments_iter)
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        words = [word for segment in segments for word in segment.words]
        duration_ms = request.duration_ms or max((segment.end_ms for segment in segments), default=0) or 1000
        asr_confidence = confidence_from_segments(segments)
        alignment_confidence = confidence_from_words(words)
        downstream_confidence = downstream_confidence_for(asr_confidence, alignment_confidence, duration_ms)
        return TimestampTranscriptionResponse(
            audio_asset_id=request.audio_asset_id,
            provider="faster_whisper",
            model=f"faster-whisper-{model_size}",
            transcript=transcript,
            language=getattr(info, "language", None) or request.language_hint,
            duration_ms=duration_ms,
            word_timestamps=words,
            segments=segments,
            asr_confidence=asr_confidence,
            alignment_confidence=alignment_confidence,
            downstream_confidence=downstream_confidence,
            audio_quality_label=quality_label_for(downstream_confidence),
            warnings=[] if downstream_confidence >= 0.55 else ["low_confidence_alignment: downstream scoring should reduce confidence"],
            metadata={
                "duration": getattr(info, "duration", None),
                "language_probability": getattr(info, "language_probability", None),
                "device": device,
                "compute_type": compute_type,
            },
        )
    except TimestampAdapterError:
        raise
    except Exception as exc:
        raise TimestampAdapterError(f"faster-whisper timestamp transcription failed: {exc}", retryable=True) from exc
    finally:
        if cleanup_path:
            cleanup_path.unlink(missing_ok=True)


def evenly_spaced_word_timestamps(words: list[str], duration_ms: int) -> list[WordTimestamp]:
    if not words:
        return []
    slot = max(120, duration_ms // max(len(words), 1))
    speech_width = max(80, round(slot * 0.72))
    timestamps: list[WordTimestamp] = []
    cursor = 0
    for word in words:
        start = cursor
        end = min(duration_ms, start + speech_width)
        timestamps.append(WordTimestamp(word=word, start_ms=start, end_ms=end, confidence=0.8))
        cursor = min(duration_ms, cursor + slot)
    return timestamps


def audio_source_path(request: TimestampTranscriptionRequest) -> tuple[str, Path | None]:
    if request.audio_path:
        return request.audio_path, None
    if request.audio_base64:
        suffix = suffix_for_mime_type(request.mime_type)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(base64.b64decode(request.audio_base64))
            return handle.name, Path(handle.name)
    raise TimestampAdapterError("faster_whisper requires audio_path or audio_base64", retryable=False)


def suffix_for_mime_type(mime_type: str | None) -> str:
    normalized = (mime_type or "").split(";", 1)[0].lower()
    if normalized in {"audio/wav", "audio/x-wav"}:
        return ".wav"
    if normalized in {"audio/mpeg", "audio/mp3"}:
        return ".mp3"
    if normalized == "audio/webm":
        return ".webm"
    return ".audio"


def collect_segments(raw_segments: Iterable[Any]) -> list[TimestampSegment]:
    segments: list[TimestampSegment] = []
    for index, raw in enumerate(raw_segments):
        words = [
            WordTimestamp(
                word=getattr(item, "word", "").strip(),
                start_ms=seconds_to_ms(getattr(item, "start", 0.0)),
                end_ms=seconds_to_ms(getattr(item, "end", 0.0)),
                confidence=probability_or_none(getattr(item, "probability", None)),
            )
            for item in (getattr(raw, "words", None) or [])
            if getattr(item, "word", "").strip()
        ]
        confidence = segment_confidence(raw)
        segments.append(
            TimestampSegment(
                segment_id=index,
                start_ms=seconds_to_ms(getattr(raw, "start", 0.0)),
                end_ms=seconds_to_ms(getattr(raw, "end", 0.0)),
                text=getattr(raw, "text", "").strip(),
                confidence=confidence,
                words=words,
            )
        )
    return segments


def segment_confidence(segment: Any) -> float | None:
    avg_logprob = getattr(segment, "avg_logprob", None)
    if avg_logprob is None:
        return None
    return round(clamp(math.exp(float(avg_logprob))), 3)


def probability_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(clamp(float(value)), 3)
    except (TypeError, ValueError):
        return None


def seconds_to_ms(value: Any) -> int:
    try:
        return max(0, round(float(value) * 1000))
    except (TypeError, ValueError):
        return 0


def confidence_from_segments(segments: list[TimestampSegment]) -> float:
    confidences = [segment.confidence for segment in segments if segment.confidence is not None]
    if not confidences:
        return 0.62 if segments else 0.35
    return round(clamp(sum(confidences) / len(confidences)), 2)


def confidence_from_words(words: list[WordTimestamp]) -> float:
    confidences = [word.confidence for word in words if word.confidence is not None]
    if not confidences:
        return 0.58 if words else 0.35
    return round(clamp(sum(confidences) / len(confidences)), 2)


def downstream_confidence_for(asr_confidence: float, alignment_confidence: float, duration_ms: int) -> float:
    duration_penalty = 0.12 if duration_ms < 3000 else 0
    return round(clamp((asr_confidence * 0.55) + (alignment_confidence * 0.45) - duration_penalty, 0.2, 0.92), 2)


def quality_label_for(confidence: float) -> str:
    if confidence >= 0.62:
        return "usable"
    if confidence >= 0.42:
        return "unknown"
    return "low_quality"
