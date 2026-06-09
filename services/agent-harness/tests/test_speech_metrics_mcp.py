import pytest

from app.mcp.security import McpAuthorizationError, McpToolContext
from app.mcp.speech_metrics_mcp import (
    PostgresSpeechMetricsSource,
    SpeechMetricsMcpTools,
    TurnAudioMetrics,
    build_turn_audio_metrics_select_sql,
    record_from_pg_row,
)


USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SESSION_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TURN_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def test_compute_wpm_counts_transcript_words_and_returns_confidence() -> None:
    tools = SpeechMetricsMcpTools()
    context = read_context(allowed_tools=["compute_wpm"])

    result = tools.compute_wpm(
        context,
        transcript="I really enjoy cooking at home with my family.",
        duration_ms=30000,
        asr_confidence=0.9,
    )

    assert result.words_count == 9
    assert result.wpm == 18.0
    assert result.confidence == 0.875


def test_detect_long_pauses_counts_thresholded_segments() -> None:
    tools = SpeechMetricsMcpTools()
    context = read_context(allowed_tools=["detect_long_pauses"])

    result = tools.detect_long_pauses(
        context,
        pauses=[
            {"start_ms": 1000, "end_ms": 1700},
            {"start_ms": 3000, "end_ms": 4500},
            {"start_ms": 6000, "end_ms": 8100},
        ],
        threshold_ms=1000,
        asr_confidence=0.8,
    )

    assert result.long_pause_count == 2
    assert result.total_pause_ms == 3600
    assert result.mean_pause_ms == 1800
    assert result.confidence == 0.825


def test_estimate_filler_ratio_counts_single_and_phrase_fillers() -> None:
    tools = SpeechMetricsMcpTools()
    context = read_context(allowed_tools=["estimate_filler_ratio"])

    result = tools.estimate_filler_ratio(
        context,
        transcript="Um I mean I like this city because, you know, it is kind of relaxing.",
        asr_confidence=0.92,
    )

    assert result.words_count == 15
    assert result.filler_count == 5
    assert result.filler_ratio == 0.3333
    assert result.confidence == 0.885


def test_get_asr_confidence_wraps_score_with_tool_confidence() -> None:
    tools = SpeechMetricsMcpTools()
    context = read_context(allowed_tools=["get_asr_confidence"])

    result = tools.get_asr_confidence(context, asr_confidence=0.91)

    assert result.asr_confidence == 0.91
    assert result.confidence == 0.91


def test_get_turn_audio_metrics_uses_context_scope_and_source() -> None:
    source = FakeSpeechMetricsSource(
        TurnAudioMetrics(
            metrics_id="metrics_1",
            turn_id=TURN_ID,
            audio_asset_id="audio_1",
            duration_ms=45000,
            words_count=90,
            wpm=120.0,
            long_pause_count=2,
            mean_pause_ms=700,
            total_pause_ms=1400,
            filler_count=3,
            filler_ratio=0.08,
            asr_confidence=0.91,
            raw_metrics={"mean_pause_ms": 700},
        )
    )
    tools = SpeechMetricsMcpTools(source)
    context = read_context(allowed_tools=["get_turn_audio_metrics"])

    result = tools.get_turn_audio_metrics(context, turn_id=TURN_ID)

    assert source.calls == [{"user_id": USER_ID, "session_id": SESSION_ID, "turn_id": TURN_ID}]
    assert result.metrics is not None
    assert result.metrics.wpm == 120.0
    assert result.metrics.raw_metrics["mean_pause_ms"] == 700
    assert result.confidence == 1.0


def test_speech_metrics_mcp_rejects_missing_scope_and_disallowed_tool() -> None:
    tools = SpeechMetricsMcpTools()

    with pytest.raises(McpAuthorizationError, match="missing required scope"):
        tools.compute_wpm(McpToolContext(user_id=USER_ID, session_id=SESSION_ID, scopes=[]), duration_ms=1000, words_count=1)

    with pytest.raises(McpAuthorizationError, match="tool is not allowed"):
        tools.compute_wpm(read_context(allowed_tools=["detect_long_pauses"]), duration_ms=1000, words_count=1)


def test_postgres_source_sql_and_row_mapping() -> None:
    sql, params = build_turn_audio_metrics_select_sql(user_id=USER_ID, session_id=SESSION_ID, turn_id=TURN_ID)
    row = (
        "dddddddd-dddd-dddd-dddd-dddddddddddd",
        TURN_ID,
        "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        45000,
        90,
        118.5,
        3,
        700.0,
        2100,
        4,
        0.125,
        0.91,
        '{"mean_pause_ms": 700}',
    )

    record = record_from_pg_row(row)

    assert "join practice_sessions ps" in sql
    assert "ps.user_id = %s::uuid" in sql
    assert "order by sm.created_at desc" in sql
    assert params == [TURN_ID, SESSION_ID, USER_ID]
    assert record.metrics_id == "dddddddd-dddd-dddd-dddd-dddddddddddd"
    assert record.duration_ms == 45000
    assert record.words_count == 90
    assert record.wpm == 118.5
    assert record.filler_count == 4
    assert record.raw_metrics == {"mean_pause_ms": 700}


def test_postgres_source_rejects_missing_database_url() -> None:
    with pytest.raises(ValueError, match="database_url is required"):
        PostgresSpeechMetricsSource("")


class FakeSpeechMetricsSource:
    def __init__(self, metrics: TurnAudioMetrics | None) -> None:
        self.metrics = metrics
        self.calls: list[dict[str, str]] = []

    def get_turn_audio_metrics(self, *, user_id: str, session_id: str, turn_id: str) -> TurnAudioMetrics | None:
        self.calls.append({"user_id": user_id, "session_id": session_id, "turn_id": turn_id})
        return self.metrics


def read_context(*, allowed_tools: list[str]) -> McpToolContext:
    return McpToolContext(
        user_id=USER_ID,
        session_id=SESSION_ID,
        scopes=["speech_metrics:read"],
        allowed_tools=allowed_tools,
    )
