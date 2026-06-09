import pytest

from app.mcp.security import (
    InMemoryMcpAuditSink,
    McpAuthorizationError,
    McpToolContext,
    authorize_tool_call,
    hash_user_id,
    reset_mcp_audit_sink,
    get_mcp_audit_sink,
)


def test_authorize_tool_call_records_allowed_audit_with_user_hash() -> None:
    sink = InMemoryMcpAuditSink()
    context = McpToolContext(
        user_id="user_001",
        session_id="sess_001",
        scopes=["question_bank:read"],
        allowed_tools=["search_questions"],
        request_id="req_001",
        audit_hash_salt="test-salt",
    )

    authorize_tool_call(
        context,
        tool_name="search_questions",
        required_scopes=["question_bank:read"],
        audit_sink=sink,
    )

    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.audit_id == "mcp_audit_0001"
    assert record.tool_name == "search_questions"
    assert record.user_id_hash == hash_user_id("user_001", salt="test-salt")
    assert record.user_id_hash.startswith("sha256:")
    assert "user_001" not in record.user_id_hash
    assert record.session_id == "sess_001"
    assert record.request_id == "req_001"
    assert record.status == "allowed"
    assert record.required_scopes == ["question_bank:read"]
    assert record.granted_scopes == ["question_bank:read"]


def test_authorize_tool_call_records_denied_missing_scope() -> None:
    sink = InMemoryMcpAuditSink()
    context = McpToolContext(user_id="user_001", session_id="sess_001", scopes=[])

    with pytest.raises(McpAuthorizationError, match="missing required scope"):
        authorize_tool_call(context, tool_name="search_questions", required_scopes=["question_bank:read"], audit_sink=sink)

    assert sink.records[0].status == "denied"
    assert sink.records[0].reason == "missing_scope:question_bank:read"


def test_authorize_tool_call_records_denied_allowlist() -> None:
    sink = InMemoryMcpAuditSink()
    context = McpToolContext(
        user_id="user_001",
        session_id="sess_001",
        scopes=["rubric:read"],
        allowed_tools=["get_anchor_samples"],
    )

    with pytest.raises(McpAuthorizationError, match="tool is not allowed"):
        authorize_tool_call(
            context,
            tool_name="retrieve_speaking_band_descriptor",
            required_scopes=["rubric:read"],
            audit_sink=sink,
        )

    assert sink.records[0].status == "denied"
    assert sink.records[0].reason == "tool_not_allowed"


def test_authorize_tool_call_blocks_disabled_tools() -> None:
    sink = InMemoryMcpAuditSink()
    context = McpToolContext(
        user_id="user_001",
        session_id="sess_001",
        scopes=["speech_metrics:read"],
        disabled_tools=["get_turn_audio_metrics"],
    )

    with pytest.raises(McpAuthorizationError, match="tool is disabled"):
        authorize_tool_call(
            context,
            tool_name="get_turn_audio_metrics",
            required_scopes=["speech_metrics:read"],
            audit_sink=sink,
        )

    assert sink.records[0].status == "denied"
    assert sink.records[0].reason == "tool_disabled"


def test_authorize_tool_call_can_disable_high_risk_tools() -> None:
    sink = InMemoryMcpAuditSink()
    context = McpToolContext(
        user_id="user_001",
        session_id="sess_001",
        scopes=["report:write"],
        disable_high_risk_tools=True,
    )

    with pytest.raises(McpAuthorizationError, match="tool is disabled"):
        authorize_tool_call(context, tool_name="save_score_report", required_scopes=["report:write"], audit_sink=sink)

    assert sink.records[0].reason == "tool_disabled"


def test_authorize_tool_call_keeps_default_high_risk_tools_when_explicit_none() -> None:
    sink = InMemoryMcpAuditSink()
    context = McpToolContext(
        user_id="user_001",
        session_id="sess_001",
        scopes=["report:write"],
        disable_high_risk_tools=True,
        high_risk_tools=None,
    )

    with pytest.raises(McpAuthorizationError, match="tool is disabled"):
        authorize_tool_call(context, tool_name="save_feedback", required_scopes=["report:write"], audit_sink=sink)

    assert sink.records[0].reason == "tool_disabled"


def test_default_audit_sink_can_be_reset_and_used_by_existing_tools() -> None:
    reset_mcp_audit_sink()
    sink = get_mcp_audit_sink()
    context = McpToolContext(user_id="user_001", session_id="sess_001", scopes=["profile:read"])

    authorize_tool_call(context, tool_name="get_privacy_exclusions", required_scopes=["profile:read"])

    assert len(sink.records) == 1
    assert sink.records[0].tool_name == "get_privacy_exclusions"
    reset_mcp_audit_sink()
    assert sink.records == []
