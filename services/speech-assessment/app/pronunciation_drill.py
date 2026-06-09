from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from app.fluency_metrics import clamp, normalized_words
from app.schemas import (
    AssessmentPolicy,
    PhonemeHint,
    PronunciationDrillAlignment,
    PronunciationDrillPhonemeFeedback,
    PronunciationDrillRequest,
    PronunciationDrillResponse,
    PronunciationDrillWordFeedback,
    WordTimestamp,
)


MAX_DRILL_WORDS = 80
MAX_DRILL_PHONEMES = 320
DIGRAPH_PHONEMES = {
    "th": "TH",
    "sh": "SH",
    "ch": "CH",
    "ph": "F",
    "wh": "W",
    "ng": "NG",
    "oo": "UW",
    "ee": "IY",
    "ea": "IY",
    "ai": "EY",
    "ay": "EY",
    "ow": "AW",
    "ou": "AW",
    "oi": "OY",
}
VOWEL_PHONEMES = {
    "a": "AE",
    "e": "EH",
    "i": "IH",
    "o": "AA",
    "u": "AH",
    "y": "IY",
}


class PronunciationDrillAdapterError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def run_pronunciation_drill(request: PronunciationDrillRequest) -> PronunciationDrillResponse:
    if request.provider != "deterministic_mfa_kaldi_gop":
        raise PronunciationDrillAdapterError(
            f"{request.provider} is declared but not configured in this runtime",
            retryable=True,
        )

    target_words = normalized_words(request.target_text)[:MAX_DRILL_WORDS]
    spoken_words = normalized_spoken_words(request)
    duration_ms = infer_duration_ms(request)
    word_feedback = build_word_feedback(request, target_words, spoken_words, duration_ms)
    phoneme_feedback = build_phoneme_feedback(word_feedback, request.phoneme_hints)
    alignment = build_alignment(target_words, spoken_words, word_feedback)
    confidence = drill_confidence(word_feedback, alignment)
    warnings = build_warnings(request, target_words, spoken_words, phoneme_feedback)

    return PronunciationDrillResponse(
        drill_id=stable_drill_id(request),
        audio_asset_id=request.audio_asset_id,
        provider=request.provider,
        target_text=request.target_text,
        transcript=request.transcript,
        alignment=alignment,
        word_feedback=word_feedback,
        phoneme_feedback=phoneme_feedback,
        confidence=confidence,
        policy=AssessmentPolicy(
            consumer_instruction=(
                "Use this payload only for fixed-text pronunciation drills. It is separated from "
                "Mock Exam scoring and must not be mapped directly to an IELTS band."
            ),
            separated_paths=["mock_exam", "pronunciation_drill"],
        ),
        warnings=warnings,
    )


def normalized_spoken_words(request: PronunciationDrillRequest) -> list[str]:
    if request.transcript:
        return normalized_words(request.transcript)
    return [
        words[0]
        for timestamp in request.word_timestamps
        if (words := normalized_words(timestamp.word))
    ]


def infer_duration_ms(request: PronunciationDrillRequest) -> int:
    if request.duration_ms:
        return request.duration_ms
    if request.word_timestamps:
        return max(item.end_ms for item in request.word_timestamps) or 1000
    target_count = max(len(normalized_words(request.target_text)), 1)
    return max(1000, target_count * 650)


def build_word_feedback(
    request: PronunciationDrillRequest,
    target_words: list[str],
    spoken_words: list[str],
    duration_ms: int,
) -> list[PronunciationDrillWordFeedback]:
    feedback: list[PronunciationDrillWordFeedback] = []
    expected_slot_ms = duration_ms / max(len(target_words), 1)
    for index, target_word in enumerate(target_words):
        spoken_word = spoken_words[index] if index < len(spoken_words) else None
        timestamp = request.word_timestamps[index] if index < len(request.word_timestamps) else None
        status = word_status(target_word, spoken_word)
        timing = timing_label(timestamp, expected_slot_ms, status)
        gop_score = word_gop_score(target_word, spoken_word, timestamp, timing, status)
        feedback.append(
            PronunciationDrillWordFeedback(
                target_index=index,
                target_word=target_word,
                spoken_word=spoken_word,
                start_ms=timestamp.start_ms if timestamp else None,
                end_ms=timestamp.end_ms if timestamp else None,
                gop_score=gop_score,
                accuracy=gop_score,
                timing=timing,
                stress=stress_label(gop_score, timing, status),
                status=status,
                note=word_note(status, timing),
            )
        )
    return feedback


def word_status(target_word: str, spoken_word: str | None) -> str:
    if not spoken_word:
        return "missing"
    if target_word == spoken_word:
        return "matched"
    return "substituted"


def timing_label(timestamp: WordTimestamp | None, expected_slot_ms: float, status: str) -> str:
    if status == "missing":
        return "missing"
    if not timestamp:
        return "unknown"
    duration = max(0, timestamp.end_ms - timestamp.start_ms)
    if duration < expected_slot_ms * 0.45:
        return "fast"
    if duration > expected_slot_ms * 1.55:
        return "slow"
    return "on_time"


def word_gop_score(
    target_word: str,
    spoken_word: str | None,
    timestamp: WordTimestamp | None,
    timing: str,
    status: str,
) -> float:
    if status == "missing":
        return 0.35
    similarity = SequenceMatcher(a=target_word, b=spoken_word or "").ratio()
    timestamp_confidence = timestamp.confidence if timestamp and timestamp.confidence is not None else None
    if status == "matched":
        base = timestamp_confidence if timestamp_confidence is not None else 0.72
    else:
        base = 0.42 + (similarity * 0.34)
    timing_adjustment = {"on_time": 0.06, "unknown": -0.02, "fast": -0.07, "slow": -0.07, "missing": -0.2}[timing]
    return round(clamp(base + timing_adjustment, 0.25, 0.95), 2)


def stress_label(gop_score: float, timing: str, status: str) -> str:
    if status == "missing" or timing == "unknown":
        return "unknown"
    return "acceptable" if gop_score >= 0.68 and timing == "on_time" else "needs_review"


def word_note(status: str, timing: str) -> str:
    if status == "missing":
        return "Target word was not aligned; repeat this word in the fixed-text drill."
    if status == "substituted":
        return "Forced-alignment position differs from target text; review articulation before scoring."
    if timing in {"fast", "slow"}:
        return "Kaldi GOP-style timing evidence suggests this word needs rhythm review."
    if timing == "unknown":
        return "No word timestamp was supplied; feedback uses transcript-only deterministic evidence."
    return "MFA/Kaldi GOP-compatible word evidence is acceptable for this drill."


def build_phoneme_feedback(
    word_feedback: list[PronunciationDrillWordFeedback],
    phoneme_hints: list[PhonemeHint],
) -> list[PronunciationDrillPhonemeFeedback]:
    hints = hint_map(phoneme_hints)
    feedback: list[PronunciationDrillPhonemeFeedback] = []
    for word_item in word_feedback:
        phonemes = hints.get(word_item.target_word) or approximate_phonemes(word_item.target_word)
        for position, phoneme in enumerate(phonemes[:8]):
            if len(feedback) >= MAX_DRILL_PHONEMES:
                return feedback
            gop_score = phoneme_gop_score(word_item, position)
            status = phoneme_status(word_item.status, gop_score)
            feedback.append(
                PronunciationDrillPhonemeFeedback(
                    target_index=word_item.target_index,
                    word=word_item.target_word,
                    phoneme=phoneme,
                    position=position,
                    gop_score=gop_score,
                    accuracy=gop_score,
                    status=status,
                    note=phoneme_note(status, word_item.status),
                )
            )
    return feedback


def hint_map(phoneme_hints: list[PhonemeHint]) -> dict[str, list[str]]:
    hints: dict[str, list[str]] = {}
    for hint in phoneme_hints:
        words = normalized_words(hint.word)
        if words:
            hints[words[0]] = [normalize_phoneme(item) for item in hint.phonemes if item.strip()]
    return hints


def approximate_phonemes(word: str) -> list[str]:
    letters = re.sub(r"[^a-z]", "", word.lower())
    if not letters:
        return ["UNK"]
    phonemes: list[str] = []
    index = 0
    while index < len(letters):
        pair = letters[index : index + 2]
        if pair in DIGRAPH_PHONEMES:
            phonemes.append(DIGRAPH_PHONEMES[pair])
            index += 2
            continue
        letter = letters[index]
        phonemes.append(VOWEL_PHONEMES.get(letter, letter.upper()))
        index += 1
    compacted: list[str] = []
    for phoneme in phonemes:
        if not compacted or compacted[-1] != phoneme:
            compacted.append(phoneme)
    return compacted[:8]


def normalize_phoneme(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().upper())[:24] or "UNK"


def phoneme_gop_score(word_item: PronunciationDrillWordFeedback, position: int) -> float:
    if word_item.status == "missing":
        return 0.35
    position_penalty = min(position * 0.015, 0.07)
    timing_penalty = 0.04 if word_item.timing in {"fast", "slow", "unknown"} else 0
    return round(clamp(word_item.gop_score - position_penalty - timing_penalty, 0.25, 0.95), 2)


def phoneme_status(word_status_value: str, gop_score: float) -> str:
    if word_status_value == "missing":
        return "missing"
    return "acceptable" if gop_score >= 0.68 else "needs_review"


def phoneme_note(status: str, word_status_value: str) -> str:
    if status == "missing":
        return "No aligned word span is available for this expected phoneme."
    if word_status_value == "substituted":
        return "GOP-compatible phoneme evidence is low because the aligned word differs from target text."
    if status == "needs_review":
        return "Review this segment with fixed-text MFA/Kaldi GOP drill feedback."
    return "Segment-level GOP-compatible evidence is acceptable."


def build_alignment(
    target_words: list[str],
    spoken_words: list[str],
    word_feedback: list[PronunciationDrillWordFeedback],
) -> PronunciationDrillAlignment:
    missing = sum(1 for item in word_feedback if item.status == "missing")
    substituted = sum(1 for item in word_feedback if item.status == "substituted")
    aligned = sum(1 for item in word_feedback if item.status != "missing")
    target_count = len(target_words)
    if target_count == 0:
        alignment_confidence = 0.35
    else:
        match_quality = sum(item.gop_score for item in word_feedback) / target_count
        coverage = aligned / target_count
        alignment_confidence = round(clamp((match_quality * 0.65) + (coverage * 0.35), 0.25, 0.95), 2)
    return PronunciationDrillAlignment(
        target_word_count=target_count,
        spoken_word_count=len(spoken_words),
        aligned_word_count=aligned,
        missing_word_count=missing,
        substituted_word_count=substituted,
        alignment_confidence=alignment_confidence,
    )


def drill_confidence(
    word_feedback: list[PronunciationDrillWordFeedback],
    alignment: PronunciationDrillAlignment,
) -> float:
    if not word_feedback:
        return 0.35
    average_gop = sum(item.gop_score for item in word_feedback) / len(word_feedback)
    return round(clamp((average_gop * 0.6) + (alignment.alignment_confidence * 0.4), 0.25, 0.95), 2)


def build_warnings(
    request: PronunciationDrillRequest,
    target_words: list[str],
    spoken_words: list[str],
    phoneme_feedback: list[PronunciationDrillPhonemeFeedback],
) -> list[str]:
    warnings = ["deterministic_drill_provider: replace with MFA/Kaldi GOP adapters for production scoring"]
    if not request.word_timestamps:
        warnings.append("word_timestamps_missing: timing and stress feedback use transcript-only estimates")
    if not request.transcript:
        warnings.append("transcript_missing: spoken words were inferred from word timestamps")
    if len(normalized_words(request.target_text)) > MAX_DRILL_WORDS:
        warnings.append(f"target_text_truncated: first {MAX_DRILL_WORDS} words evaluated")
    if len(phoneme_feedback) >= MAX_DRILL_PHONEMES:
        warnings.append(f"phoneme_feedback_truncated: first {MAX_DRILL_PHONEMES} phoneme items returned")
    if spoken_words and target_words and len(spoken_words) != len(target_words):
        warnings.append("target_transcript_length_mismatch: review alignment before learner-facing feedback")
    return warnings


def stable_drill_id(request: PronunciationDrillRequest) -> str:
    raw = "|".join(
        [
            request.audio_asset_id,
            request.provider,
            request.target_text,
            request.transcript or "",
        ]
    )
    return f"pron_drill_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"
