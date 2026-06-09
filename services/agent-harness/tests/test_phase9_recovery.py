from fastapi.testclient import TestClient

from app.main import app
from app.recovery.error_policy import RecoveryPolicyRequest, recovery_directive_for


client = TestClient(app)


def test_asr_failure_retries_then_allows_manual_text_input() -> None:
    retry = recovery_directive_for(RecoveryPolicyRequest(error_type="asr_failed", workflow_node="asr", retry_count=1))
    fallback = recovery_directive_for(RecoveryPolicyRequest(error_type="asr_failed", workflow_node="asr", retry_count=2))

    assert retry.retryable is True
    assert retry.next_action == "retry_current_node"
    assert fallback.retryable is False
    assert fallback.next_action == "manual_text_input"
    assert fallback.manual_input_allowed is True
    assert fallback.preserve_session_state is True


def test_tts_failure_degrades_to_text_only_examiner_message() -> None:
    directive = recovery_directive_for(RecoveryPolicyRequest(error_type="tts_timeout", workflow_node="tts", retry_count=1))

    assert directive.severity == "degraded"
    assert directive.next_action == "text_only_examiner_message"
    assert directive.preserve_session_state is True


def test_structured_output_error_uses_safe_fallback_after_retries() -> None:
    directive = recovery_directive_for(
        RecoveryPolicyRequest(error_type="structured_output_invalid", workflow_node="score_session", retry_count=2)
    )

    assert directive.next_action == "safe_fallback_response"
    assert directive.retryable is False
    assert "schema" in directive.telemetry_tags


def test_websocket_disconnect_directive_restores_session() -> None:
    directive = recovery_directive_for(RecoveryPolicyRequest(error_type="websocket_disconnected", workflow_node="live_ui"))

    assert directive.next_action == "reconnect_and_restore_session"
    assert directive.retryable is True
    assert directive.max_retries == 5


def test_recovery_directive_api_endpoint() -> None:
    response = client.post(
        "/agent/recovery/directive",
        json={"error_type": "asr_failed", "workflow_node": "asr", "retry_count": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["next_action"] == "manual_text_input"
    assert body["manual_input_allowed"] is True
