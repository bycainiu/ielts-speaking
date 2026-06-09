from __future__ import annotations

from app.fluency_metrics import clamp, normalized_words
from app.schemas import (
    FluencyEvidence,
    GoptEvidence,
    PhonemePronunciationFeedback,
    PronunciationEvidence,
    SpeechAssessmentRequest,
    WordPronunciationFeedback,
)


def build_pronunciation_evidence(request: SpeechAssessmentRequest, fluency: FluencyEvidence) -> PronunciationEvidence:
    gopt = score_gopt_evidence(request, fluency)
    if request.mode == "pronunciation_drill":
        word_feedback = drill_word_feedback(request)
        phoneme_feedback = drill_phoneme_feedback(word_feedback)
        return PronunciationEvidence(
            evidence_level="phoneme",
            sentence_score=gopt.sentence_score,
            accuracy=gopt.accuracy,
            fluency=gopt.fluency,
            prosody=gopt.prosody,
            confidence=gopt.confidence,
            gopt=gopt,
            word_feedback=word_feedback,
            phoneme_feedback=phoneme_feedback,
        )
    return PronunciationEvidence(
        evidence_level="sentence",
        sentence_score=gopt.sentence_score,
        accuracy=gopt.accuracy,
        fluency=gopt.fluency,
        prosody=gopt.prosody,
        confidence=gopt.confidence,
        gopt=gopt,
    )


def score_gopt_evidence(request: SpeechAssessmentRequest, fluency: FluencyEvidence) -> GoptEvidence:
    timestamp_confidence = average_timestamp_confidence(request)
    base_confidence = max(fluency.confidence, timestamp_confidence)
    silence_penalty = fluency.silence_ratio * 0.16
    filler_penalty = min(fluency.filler_ratio * 0.22, 0.08)
    repetition_penalty = min(fluency.repetition_count * 0.015, 0.06)
    short_answer_penalty = 0.05 if fluency.duration_sec < 5 else 0.0

    accuracy = clamp(0.72 + (timestamp_confidence - 0.65) * 0.25 - repetition_penalty)
    fluency_score = clamp(0.72 + (fluency.confidence - 0.65) * 0.22 - silence_penalty - filler_penalty - short_answer_penalty)
    prosody = clamp(0.7 + (fluency.speech_duration_sec / max(fluency.duration_sec, 1)) * 0.12 - (fluency.long_pause_count * 0.025))
    sentence_score = round((accuracy * 0.4) + (fluency_score * 0.35) + (prosody * 0.25), 2)
    confidence = round(clamp((base_confidence * 0.72) + (coverage_confidence(request) * 0.28), 0.35, 0.92), 2)

    return GoptEvidence(
        provider="deterministic_gopt",
        model="gopt-evidence-v0",
        sentence_score=sentence_score,
        accuracy=round(accuracy, 2),
        fluency=round(fluency_score, 2),
        prosody=round(prosody, 2),
        confidence=confidence,
        calibration_note=(
            "Deterministic GOPT-compatible evidence. Use as pronunciation evidence only; "
            "do not map directly to IELTS band."
        ),
    )


def average_timestamp_confidence(request: SpeechAssessmentRequest) -> float:
    values = [item.confidence for item in request.word_timestamps if item.confidence is not None]
    if not values:
        return 0.62 if request.transcript else 0.42
    return sum(values) / len(values)


def coverage_confidence(request: SpeechAssessmentRequest) -> float:
    words = normalized_words(request.transcript or request.target_text or "")
    if not words:
        return 0.35
    if not request.word_timestamps:
        return 0.5
    return clamp(len(request.word_timestamps) / len(words), 0.35, 1.0)


def drill_word_feedback(request: SpeechAssessmentRequest) -> list[WordPronunciationFeedback]:
    target_words = normalized_words(request.target_text or "")[:20]
    by_word = {item.word.lower(): item for item in request.word_timestamps}
    feedback: list[WordPronunciationFeedback] = []
    for word in target_words:
        timestamp = by_word.get(word)
        has_timestamp = timestamp is not None
        confidence = timestamp.confidence if timestamp and timestamp.confidence is not None else 0.62
        accuracy = round(clamp(confidence if has_timestamp else 0.58, 0.35, 0.92), 2)
        feedback.append(
            WordPronunciationFeedback(
                word=word,
                start_ms=timestamp.start_ms if timestamp else None,
                end_ms=timestamp.end_ms if timestamp else None,
                accuracy=accuracy,
                stress="acceptable" if accuracy >= 0.68 else "needs_review",
                note="GOPT-compatible word evidence from alignment." if has_timestamp else "No aligned timestamp yet; review in fixed-text drill.",
            )
        )
    return feedback


def drill_phoneme_feedback(word_feedback: list[WordPronunciationFeedback]) -> list[PhonemePronunciationFeedback]:
    feedback: list[PhonemePronunciationFeedback] = []
    for item in word_feedback[:8]:
        if item.accuracy < 0.68:
            feedback.append(
                PhonemePronunciationFeedback(
                    word=item.word,
                    phoneme="primary-stress",
                    accuracy=item.accuracy,
                    note="GOP-style stress or segment timing needs review in fixed-text drill.",
                )
            )
    return feedback
