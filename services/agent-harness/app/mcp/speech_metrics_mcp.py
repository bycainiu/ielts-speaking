from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.mcp.security import McpToolContext, authorize_tool_call
from app.rag.llamaindex_service import load_psycopg


SPEECH_METRICS_READ_SCOPE = "speech_metrics:read"
WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
DEFAULT_FILLER_WORDS = {
    "um",
    "uh",
    "er",
    "erm",
    "ah",
    "like",
    "you know",
    "i mean",
    "sort of",
    "kind of",
}


class PauseSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    @field_validator("end_ms")
    @classmethod
    def validate_end_ms(cls, value: int, info: Any) -> int:
        start_ms = info.data.get("start_ms")
        if start_ms is not None and value < start_ms:
            raise ValueError("end_ms must be >= start_ms")
        return value

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


class WpmResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "compute_wpm"
    session_id: str
    words_count: int = Field(ge=0)
    duration_ms: int = Field(gt=0)
    wpm: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class LongPauseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "detect_long_pauses"
    session_id: str
    threshold_ms: int = Field(gt=0)
    long_pause_count: int = Field(ge=0)
    mean_pause_ms: float | None = Field(default=None, ge=0)
    total_pause_ms: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class FillerRatioResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "estimate_filler_ratio"
    session_id: str
    filler_count: int = Field(ge=0)
    words_count: int = Field(ge=0)
    filler_ratio: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)


class AsrConfidenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "get_asr_confidence"
    session_id: str
    asr_confidence: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(ge=0, le=1)


class TurnAudioMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics_id: str | None = None
    turn_id: str
    audio_asset_id: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    words_count: int | None = Field(default=None, ge=0)
    wpm: float | None = Field(default=None, ge=0)
    long_pause_count: int | None = Field(default=None, ge=0)
    mean_pause_ms: float | None = Field(default=None, ge=0)
    total_pause_ms: int | None = Field(default=None, ge=0)
    filler_count: int | None = Field(default=None, ge=0)
    filler_ratio: float | None = Field(default=None, ge=0, le=1)
    asr_confidence: float | None = Field(default=None, ge=0, le=1)
    raw_metrics: dict[str, Any] = Field(default_factory=dict)


class TurnAudioMetricsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = "get_turn_audio_metrics"
    session_id: str
    turn_id: str
    metrics: TurnAudioMetrics | None = None
    confidence: float = Field(ge=0, le=1)


class SpeechMetricsSource(Protocol):
    def get_turn_audio_metrics(self, *, user_id: str, session_id: str, turn_id: str) -> TurnAudioMetrics | None:
        ...


class SpeechMetricsMcpTools:
    def __init__(self, source: SpeechMetricsSource | None = None) -> None:
        self.source = source

    def compute_wpm(
        self,
        context: McpToolContext,
        *,
        duration_ms: int,
        words_count: int | None = None,
        transcript: str | None = None,
        asr_confidence: float | None = None,
    ) -> WpmResult:
        authorize_tool_call(context, tool_name="compute_wpm", required_scopes=[SPEECH_METRICS_READ_SCOPE])
        if duration_ms <= 0:
            raise ValueError("duration_ms must be > 0")
        count = words_count if words_count is not None else count_words(transcript or "")
        if count < 0:
            raise ValueError("words_count must be >= 0")
        wpm = round(count / (duration_ms / 60000), 2)
        return WpmResult(
            session_id=context.session_id,
            words_count=count,
            duration_ms=duration_ms,
            wpm=wpm,
            confidence=metric_confidence(has_required_signal=count > 0, asr_confidence=asr_confidence),
        )

    def detect_long_pauses(
        self,
        context: McpToolContext,
        *,
        pauses: Sequence[PauseSegment | Mapping[str, Any]],
        threshold_ms: int = 1000,
        asr_confidence: float | None = None,
    ) -> LongPauseResult:
        authorize_tool_call(context, tool_name="detect_long_pauses", required_scopes=[SPEECH_METRICS_READ_SCOPE])
        if threshold_ms <= 0:
            raise ValueError("threshold_ms must be > 0")
        normalized = [item if isinstance(item, PauseSegment) else PauseSegment.model_validate(dict(item)) for item in pauses]
        long_pauses = [pause for pause in normalized if pause.duration_ms >= threshold_ms]
        total_pause_ms = sum(pause.duration_ms for pause in long_pauses)
        mean_pause_ms = round(total_pause_ms / len(long_pauses), 2) if long_pauses else None
        return LongPauseResult(
            session_id=context.session_id,
            threshold_ms=threshold_ms,
            long_pause_count=len(long_pauses),
            mean_pause_ms=mean_pause_ms,
            total_pause_ms=total_pause_ms,
            confidence=metric_confidence(has_required_signal=bool(normalized), asr_confidence=asr_confidence),
        )

    def estimate_filler_ratio(
        self,
        context: McpToolContext,
        *,
        transcript: str,
        filler_words: Sequence[str] | None = None,
        asr_confidence: float | None = None,
    ) -> FillerRatioResult:
        authorize_tool_call(context, tool_name="estimate_filler_ratio", required_scopes=[SPEECH_METRICS_READ_SCOPE])
        transcript = _required_text(transcript, field_name="transcript")
        words_count = count_words(transcript)
        filler_count = count_fillers(transcript, filler_words=filler_words)
        filler_ratio = round(filler_count / words_count, 4) if words_count else 0.0
        return FillerRatioResult(
            session_id=context.session_id,
            filler_count=filler_count,
            words_count=words_count,
            filler_ratio=filler_ratio,
            confidence=metric_confidence(has_required_signal=words_count > 0, asr_confidence=asr_confidence),
        )

    def get_asr_confidence(self, context: McpToolContext, *, asr_confidence: float | None = None) -> AsrConfidenceResult:
        authorize_tool_call(context, tool_name="get_asr_confidence", required_scopes=[SPEECH_METRICS_READ_SCOPE])
        if asr_confidence is not None and (asr_confidence < 0 or asr_confidence > 1):
            raise ValueError("asr_confidence must be between 0 and 1")
        return AsrConfidenceResult(
            session_id=context.session_id,
            asr_confidence=asr_confidence,
            confidence=asr_confidence if asr_confidence is not None else 0.4,
        )

    def get_turn_audio_metrics(self, context: McpToolContext, *, turn_id: str) -> TurnAudioMetricsResult:
        authorize_tool_call(context, tool_name="get_turn_audio_metrics", required_scopes=[SPEECH_METRICS_READ_SCOPE])
        turn_id = _required_text(turn_id, field_name="turn_id")
        metrics = None
        if self.source is not None:
            metrics = self.source.get_turn_audio_metrics(
                user_id=context.user_id,
                session_id=context.session_id,
                turn_id=turn_id,
            )
        return TurnAudioMetricsResult(
            session_id=context.session_id,
            turn_id=turn_id,
            metrics=metrics,
            confidence=metrics_confidence(metrics),
        )


class PostgresSpeechMetricsSource:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self.database_url = database_url

    def get_turn_audio_metrics(self, *, user_id: str, session_id: str, turn_id: str) -> TurnAudioMetrics | None:
        psycopg, _ = load_psycopg()
        sql, params = build_turn_audio_metrics_select_sql(user_id=user_id, session_id=session_id, turn_id=turn_id)
        with psycopg.connect(self.database_url) as conn:
            row = conn.execute(sql, params).fetchone()
        return record_from_pg_row(row) if row else None


def build_turn_audio_metrics_select_sql(*, user_id: str, session_id: str, turn_id: str) -> tuple[str, list[Any]]:
    return (
        """
        select
            sm.id::text as metrics_id,
            st.id::text as turn_id,
            coalesce(sm.audio_asset_id::text, aa.id::text) as audio_asset_id,
            coalesce(sm.duration_ms, aa.duration_ms) as duration_ms,
            sm.words_count,
            sm.wpm::float8,
            sm.long_pause_count,
            sm.mean_pause_ms::float8,
            sm.total_pause_ms,
            sm.filler_count,
            sm.filler_ratio::float8,
            sm.asr_confidence::float8,
            sm.raw_metrics::text
        from session_turns st
        join practice_sessions ps on ps.id = st.session_id
        left join lateral (
            select *
            from speech_metrics sm
            where sm.turn_id = st.id
            order by sm.created_at desc
            limit 1
        ) sm on true
        left join audio_assets aa on aa.id = sm.audio_asset_id or (
            sm.audio_asset_id is null and aa.turn_id = st.id and aa.kind = 'user_recording'
        )
        where st.id = %s::uuid
          and st.session_id = %s::uuid
          and ps.user_id = %s::uuid
          and ps.deleted_at is null
        order by aa.created_at desc nulls last
        limit 1
        """,
        [_required_text(turn_id, field_name="turn_id"), _required_text(session_id, field_name="session_id"), _required_text(user_id, field_name="user_id")],
    )


def record_from_pg_row(row: Sequence[Any]) -> TurnAudioMetrics:
    return TurnAudioMetrics(
        metrics_id=_optional_text(row[0]),
        turn_id=_required_text(row[1], field_name="turn_id"),
        audio_asset_id=_optional_text(row[2]),
        duration_ms=row[3],
        words_count=row[4],
        wpm=row[5],
        long_pause_count=row[6],
        mean_pause_ms=row[7],
        total_pause_ms=row[8],
        filler_count=row[9],
        filler_ratio=row[10],
        asr_confidence=row[11],
        raw_metrics=json.loads(row[12] or "{}"),
    )


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def count_fillers(text: str, *, filler_words: Sequence[str] | None = None) -> int:
    normalized_text = f" {text.lower()} "
    fillers = {item.strip().lower() for item in (filler_words or DEFAULT_FILLER_WORDS) if item.strip()}
    count = 0
    for filler in fillers:
        if " " in filler:
            pattern = r"\b" + r"\s+".join(re.escape(part) for part in filler.split()) + r"\b"
            count += len(re.findall(pattern, normalized_text))
        else:
            count += len(re.findall(rf"\b{re.escape(filler)}\b", normalized_text))
    return count


def metric_confidence(*, has_required_signal: bool, asr_confidence: float | None = None) -> float:
    if asr_confidence is not None and (asr_confidence < 0 or asr_confidence > 1):
        raise ValueError("asr_confidence must be between 0 and 1")
    base = 0.85 if has_required_signal else 0.45
    if asr_confidence is None:
        return base
    return round((base + asr_confidence) / 2, 3)


def metrics_confidence(metrics: TurnAudioMetrics | None) -> float:
    if metrics is None:
        return 0.0
    signals = [
        metrics.duration_ms is not None,
        metrics.words_count is not None,
        metrics.wpm is not None,
        metrics.long_pause_count is not None,
        metrics.mean_pause_ms is not None,
        metrics.total_pause_ms is not None,
        metrics.filler_count is not None,
        metrics.filler_ratio is not None,
        metrics.asr_confidence is not None,
    ]
    return round(sum(1 for item in signals if item) / len(signals), 3)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: Any, *, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"{field_name} is required")
    return text
