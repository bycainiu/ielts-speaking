from __future__ import annotations

import re

from app.schemas import FluencyEvidence, SpeechAssessmentRequest, VadSegment, WordTimestamp


FILLERS = {"um", "uh", "erm", "er", "like", "actually", "basically"}
SELF_CORRECTION_MARKERS = ("i mean", "sorry", "rather", "let me rephrase", "what i mean is")
LONG_PAUSE_THRESHOLD_MS = 700


def compute_fluency_metrics(request: SpeechAssessmentRequest) -> FluencyEvidence:
    text = request.transcript or request.target_text or ""
    words = normalized_words(text)
    duration_ms = infer_duration_ms(request, len(words))
    speech_duration_ms = infer_speech_duration_ms(request, duration_ms)
    pauses = pause_lengths(request)
    filler_count = count_fillers(words)
    repetition_count = count_repetitions(words)
    self_correction_count = count_self_corrections(text)
    confidence = fluency_confidence(request, words)

    duration_sec = round(duration_ms / 1000, 2)
    return FluencyEvidence(
        duration_sec=duration_sec,
        speech_duration_sec=round(speech_duration_ms / 1000, 2),
        silence_ratio=round(clamp((duration_ms - speech_duration_ms) / duration_ms), 3),
        wpm=round((len(words) / max(duration_sec, 1)) * 60, 2),
        long_pause_count=sum(1 for value in pauses if value >= LONG_PAUSE_THRESHOLD_MS),
        mean_pause_ms=round(sum(pauses) / len(pauses)) if pauses else 0,
        filler_count=filler_count,
        filler_ratio=round(filler_count / max(len(words), 1), 3),
        repetition_count=repetition_count,
        self_correction_count=self_correction_count,
        confidence=confidence,
    )


def normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def infer_duration_ms(request: SpeechAssessmentRequest, word_count: int) -> int:
    if request.duration_ms:
        return request.duration_ms
    if request.vad_segments:
        return max(item.end_ms for item in request.vad_segments) or 1000
    if request.word_timestamps:
        return max(item.end_ms for item in request.word_timestamps) or 1000
    return max(5000, int(max(word_count, 1) * 650))


def infer_speech_duration_ms(request: SpeechAssessmentRequest, duration_ms: int) -> int:
    if request.vad_segments:
        return min(duration_ms, sum(segment_duration(item) for item in request.vad_segments))
    if request.word_timestamps:
        return min(duration_ms, sum(word_duration(item) for item in request.word_timestamps))
    return round(duration_ms * 0.72)


def pause_lengths(request: SpeechAssessmentRequest) -> list[int]:
    if request.vad_segments:
        return segment_gaps(request.vad_segments)
    if request.word_timestamps:
        return word_gaps(request.word_timestamps)
    return []


def segment_gaps(segments: list[VadSegment]) -> list[int]:
    ordered = sorted(segments, key=lambda item: (item.start_ms, item.end_ms))
    return positive_gaps([(item.start_ms, item.end_ms) for item in ordered])


def word_gaps(timestamps: list[WordTimestamp]) -> list[int]:
    ordered = sorted(timestamps, key=lambda item: (item.start_ms, item.end_ms))
    return positive_gaps([(item.start_ms, item.end_ms) for item in ordered])


def positive_gaps(spans: list[tuple[int, int]]) -> list[int]:
    if len(spans) < 2:
        return []
    gaps: list[int] = []
    for previous, current in zip(spans, spans[1:]):
        gap = current[0] - previous[1]
        if gap > 0:
            gaps.append(gap)
    return gaps


def count_fillers(words: list[str]) -> int:
    count = 0
    for index, word in enumerate(words):
        if word in FILLERS:
            count += 1
        if index > 0 and f"{words[index - 1]} {word}" == "you know":
            count += 1
    return count


def count_repetitions(words: list[str]) -> int:
    return sum(1 for previous, current in zip(words, words[1:]) if previous == current)


def count_self_corrections(text: str) -> int:
    lowered = text.lower()
    return sum(lowered.count(marker) for marker in SELF_CORRECTION_MARKERS)


def fluency_confidence(request: SpeechAssessmentRequest, words: list[str]) -> float:
    confidence = 0.54
    if request.transcript:
        confidence += 0.1
    if request.duration_ms:
        confidence += 0.08
    if request.vad_segments:
        confidence += 0.14
        vad_probabilities = [item.speech_probability for item in request.vad_segments if item.speech_probability is not None]
        if vad_probabilities:
            confidence = (confidence + (sum(vad_probabilities) / len(vad_probabilities))) / 2
    if request.word_timestamps:
        confidence += 0.1
        timestamp_confidences = [item.confidence for item in request.word_timestamps if item.confidence is not None]
        if timestamp_confidences:
            confidence = (confidence + (sum(timestamp_confidences) / len(timestamp_confidences))) / 2
    if len(words) >= 30:
        confidence += 0.04
    return round(clamp(confidence, 0.35, 0.94), 2)


def word_duration(item: WordTimestamp) -> int:
    return max(0, item.end_ms - item.start_ms)


def segment_duration(item: VadSegment) -> int:
    return max(0, item.end_ms - item.start_ms)


def clamp(value: float, floor: float = 0.0, ceiling: float = 1.0) -> float:
    return min(max(value, floor), ceiling)
