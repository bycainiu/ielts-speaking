from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


AssessmentMode = Literal["mock_exam", "pronunciation_drill"]
TimestampProvider = Literal["deterministic", "faster_whisper"]
PronunciationDrillProvider = Literal["deterministic_mfa_kaldi_gop", "mfa_adapter", "kaldi_gop_adapter"]


class WordTimestamp(BaseModel):
    word: str = Field(min_length=1, max_length=80)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def end_must_follow_start(self) -> "WordTimestamp":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return self


class VadSegment(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    speech_probability: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def end_must_follow_start(self) -> "VadSegment":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return self


class SpeechAssessmentRequest(BaseModel):
    audio_asset_id: str = Field(min_length=1, max_length=120)
    mode: AssessmentMode = "mock_exam"
    session_id: str | None = Field(default=None, max_length=120)
    turn_id: str | None = Field(default=None, max_length=120)
    transcript: str | None = Field(default=None, max_length=12000)
    duration_ms: int | None = Field(default=None, ge=1, le=600_000)
    word_timestamps: list[WordTimestamp] = Field(default_factory=list)
    vad_segments: list[VadSegment] = Field(default_factory=list)
    target_text: str | None = Field(default=None, max_length=12000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def drill_requires_target_text(self) -> "SpeechAssessmentRequest":
        if self.mode == "pronunciation_drill" and not (self.target_text or "").strip():
            raise ValueError("pronunciation_drill requires target_text")
        return self


class TimestampTranscriptionRequest(BaseModel):
    audio_asset_id: str = Field(min_length=1, max_length=120)
    provider: TimestampProvider = "deterministic"
    audio_path: str | None = Field(default=None, max_length=2000)
    audio_url: str | None = Field(default=None, max_length=4000)
    audio_base64: str | None = Field(default=None, max_length=80_000_000)
    mime_type: str | None = Field(default=None, max_length=120)
    language_hint: str = Field(default="en", min_length=2, max_length=16)
    expected_transcript: str | None = Field(default=None, max_length=12000)
    duration_ms: int | None = Field(default=None, ge=1, le=600_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_provider_inputs(self) -> "TimestampTranscriptionRequest":
        if self.provider == "deterministic" and not (self.expected_transcript or "").strip():
            raise ValueError("deterministic timestamp provider requires expected_transcript")
        if self.provider == "faster_whisper" and not (self.audio_path or self.audio_base64):
            raise ValueError("faster_whisper timestamp provider requires audio_path or audio_base64")
        return self


class TimestampSegment(BaseModel):
    segment_id: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    words: list[WordTimestamp] = Field(default_factory=list)


class TimestampTranscriptionResponse(BaseModel):
    audio_asset_id: str
    provider: TimestampProvider
    model: str
    transcript: str
    language: str
    duration_ms: int
    word_timestamps: list[WordTimestamp]
    segments: list[TimestampSegment]
    asr_confidence: float = Field(ge=0, le=1)
    alignment_confidence: float = Field(ge=0, le=1)
    downstream_confidence: float = Field(ge=0, le=1)
    audio_quality_label: Literal["unknown", "usable", "low_quality"]
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PhonemeHint(BaseModel):
    word: str = Field(min_length=1, max_length=80)
    phonemes: list[str] = Field(min_length=1, max_length=24)
    primary_stress_index: int | None = Field(default=None, ge=0)


class PronunciationDrillRequest(BaseModel):
    audio_asset_id: str = Field(min_length=1, max_length=120)
    target_text: str = Field(min_length=1, max_length=12000)
    transcript: str | None = Field(default=None, max_length=12000)
    duration_ms: int | None = Field(default=None, ge=1, le=600_000)
    word_timestamps: list[WordTimestamp] = Field(default_factory=list)
    phoneme_hints: list[PhonemeHint] = Field(default_factory=list)
    provider: PronunciationDrillProvider = "deterministic_mfa_kaldi_gop"
    metadata: dict[str, Any] = Field(default_factory=dict)


class PronunciationDrillAlignment(BaseModel):
    target_word_count: int = Field(ge=0)
    spoken_word_count: int = Field(ge=0)
    aligned_word_count: int = Field(ge=0)
    missing_word_count: int = Field(ge=0)
    substituted_word_count: int = Field(ge=0)
    alignment_confidence: float = Field(ge=0, le=1)


class PronunciationDrillWordFeedback(BaseModel):
    target_index: int = Field(ge=0)
    target_word: str
    spoken_word: str | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    gop_score: float = Field(ge=0, le=1)
    accuracy: float = Field(ge=0, le=1)
    timing: Literal["unknown", "on_time", "fast", "slow", "missing"]
    stress: Literal["unknown", "acceptable", "needs_review"]
    status: Literal["matched", "substituted", "missing"]
    note: str


class PronunciationDrillPhonemeFeedback(BaseModel):
    target_index: int = Field(ge=0)
    word: str
    phoneme: str
    position: int = Field(ge=0)
    gop_score: float = Field(ge=0, le=1)
    accuracy: float = Field(ge=0, le=1)
    status: Literal["acceptable", "needs_review", "missing"]
    note: str


class PronunciationDrillResponse(BaseModel):
    drill_id: str
    audio_asset_id: str
    mode: Literal["pronunciation_drill"] = "pronunciation_drill"
    provider: PronunciationDrillProvider
    model: Literal["mfa-kaldi-gop-drill-v0"] = "mfa-kaldi-gop-drill-v0"
    target_text: str
    transcript: str | None = None
    alignment: PronunciationDrillAlignment
    word_feedback: list[PronunciationDrillWordFeedback]
    phoneme_feedback: list[PronunciationDrillPhonemeFeedback]
    confidence: float = Field(ge=0, le=1)
    policy: AssessmentPolicy
    warnings: list[str] = Field(default_factory=list)


class AudioQualityEvidence(BaseModel):
    duration_ms: int
    quality_label: Literal["unknown", "usable", "low_quality"]
    clipping_detected: bool
    estimated_snr_db: float | None = None
    confidence: float = Field(ge=0, le=1)


class FluencyEvidence(BaseModel):
    duration_sec: float = Field(ge=0)
    speech_duration_sec: float = Field(ge=0)
    silence_ratio: float = Field(ge=0, le=1)
    wpm: float = Field(ge=0)
    long_pause_count: int = Field(ge=0)
    mean_pause_ms: int = Field(ge=0)
    filler_count: int = Field(ge=0)
    filler_ratio: float = Field(ge=0, le=1)
    repetition_count: int = Field(ge=0)
    self_correction_count: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class WordPronunciationFeedback(BaseModel):
    word: str
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    accuracy: float = Field(ge=0, le=1)
    stress: Literal["unknown", "acceptable", "needs_review"]
    note: str


class PhonemePronunciationFeedback(BaseModel):
    word: str
    phoneme: str
    accuracy: float = Field(ge=0, le=1)
    note: str


class GoptEvidence(BaseModel):
    provider: Literal["deterministic_gopt", "gopt_adapter"]
    model: str
    sentence_score: float = Field(ge=0, le=1)
    accuracy: float = Field(ge=0, le=1)
    fluency: float = Field(ge=0, le=1)
    prosody: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    calibration_note: str


class PronunciationEvidence(BaseModel):
    evidence_level: Literal["none", "sentence", "word", "phoneme"]
    sentence_score: float | None = Field(default=None, ge=0, le=1)
    accuracy: float | None = Field(default=None, ge=0, le=1)
    fluency: float | None = Field(default=None, ge=0, le=1)
    prosody: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    gopt: GoptEvidence | None = None
    word_feedback: list[WordPronunciationFeedback] = Field(default_factory=list)
    phoneme_feedback: list[PhonemePronunciationFeedback] = Field(default_factory=list)


class AssessmentPolicy(BaseModel):
    ielts_band_output_allowed: Literal[False] = False
    consumer_instruction: str
    separated_paths: list[Literal["mock_exam", "pronunciation_drill"]]


class SpeechAssessmentResponse(BaseModel):
    evidence_id: str
    audio_asset_id: str
    mode: AssessmentMode
    provider: Literal["deterministic_speech_assessment"] = "deterministic_speech_assessment"
    model: Literal["speech-evidence-v0"] = "speech-evidence-v0"
    audio_quality: AudioQualityEvidence
    fluency: FluencyEvidence
    pronunciation: PronunciationEvidence
    confidence: float = Field(ge=0, le=1)
    policy: AssessmentPolicy
    warnings: list[str] = Field(default_factory=list)
