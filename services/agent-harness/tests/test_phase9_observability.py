from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.observability.langfuse_client import (
    AgentRunTrace,
    TraceLlmCall,
    TraceStep,
    TraceStore,
    TraceToolCall,
    build_observability_summary,
    build_prometheus_metrics,
    evaluate_observability_alerts,
    estimate_model_cost_usd,
)
from app.main import app


client = TestClient(app)


def test_observability_summary_can_filter_by_session_and_run() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_phase9_obs/plan",
        json={"mode": "full_exam", "user_id": "user_phase9"},
    )
    assert plan_response.status_code == 200
    run_id = plan_response.json()["run_id"]

    summary_response = client.get("/agent/observability/summary", params={"session_id": "sess_phase9_obs"})
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["run_count"] >= 1
    assert summary["completed_count"] >= 1
    assert summary["error_rate"] == 0
    assert summary["latency"]["p95_ms"] >= 0
    assert summary["structured_output_validity_rate"] == 1
    assert summary["input_token_count"] == 0
    assert summary["output_token_count"] == 0
    assert summary["estimated_model_cost_usd"] == 0
    assert summary["recent_runs"][0]["session_id"] == "sess_phase9_obs"
    assert summary["recent_runs"][0]["part"] == 1
    assert summary["recent_runs"][0]["question_id"].startswith("planner_fallback_p1")

    run_summary_response = client.get("/agent/observability/summary", params={"run_id": run_id})
    assert run_summary_response.status_code == 200
    assert run_summary_response.json()["recent_runs"][0]["run_id"] == run_id


def test_metrics_endpoint_exposes_prometheus_compatible_metrics() -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert "agent_harness_runs_total" in body
    assert "agent_harness_latency_p95_ms" in body
    assert "agent_harness_structured_output_validity_rate" in body
    assert "agent_harness_estimated_model_cost_usd" in body


def test_alert_policy_detects_error_rate_latency_and_tool_failures() -> None:
    now = datetime.now(UTC)
    failed_trace = AgentRunTrace(
        run_id="run_failed_obs",
        session_id="sess_alert",
        mode="full_exam",
        status="failed",
        started_at=now,
        finished_at=now,
        steps=[
            TraceStep(
                step_id="step_failed",
                workflow_node="score_session",
                status="failed",
                input_tokens=30,
                output_tokens=20,
                estimated_cost_usd=0.001,
                structured_output_validity=False,
                latency_ms=9000,
                error_code="structured_output_invalid",
                error_type="structured_output_invalid",
                started_at=now,
                finished_at=now,
                tool_calls=[
                    TraceToolCall(
                        tool_name="save_score_report",
                        scope="report:write",
                        status="failed",
                        latency_ms=12,
                        error_code="tool_disabled",
                    )
                ],
            )
        ],
    )
    summary = build_observability_summary([failed_trace], filters={"session_id": "sess_alert"})

    alerts = evaluate_observability_alerts(
        summary,
        error_rate_threshold=0.1,
        latency_p95_threshold_ms=5000,
    )

    assert {alert.alert_id for alert in alerts} >= {
        "agent_error_rate_high",
        "agent_latency_p95_high",
        "agent_tool_success_rate_low",
    }
    assert summary.errors_by_code["structured_output_invalid"] == 1
    assert summary.structured_output_validity_rate == 0
    assert summary.input_token_count == 0
    assert summary.output_token_count == 0
    assert summary.estimated_model_cost_usd == 0


def test_trace_store_eviction_and_summary_are_deterministic() -> None:
    store = TraceStore(max_runs=1)
    now = datetime.now(UTC)
    first = AgentRunTrace(run_id="run_old", session_id="sess", status="completed", started_at=now, finished_at=now)
    second = AgentRunTrace(run_id="run_new", session_id="sess", status="completed", started_at=now, finished_at=now)

    store.save(first)
    store.save(second)

    assert store.get("run_old") is None
    assert store.get("run_new") is not None
    assert store.summary(session_id="sess").run_count == 1


def test_prometheus_metrics_include_workflow_labels() -> None:
    now = datetime.now(UTC)
    summary = build_observability_summary(
        [
            AgentRunTrace(
                run_id="run_metrics",
                session_id="sess_metrics",
                status="completed",
                started_at=now,
                finished_at=now,
                steps=[
                    TraceStep(
                        step_id="step_metrics",
                        workflow_node="plan_session",
                        status="completed",
                        latency_ms=20,
                        started_at=now,
                        finished_at=now,
                    )
                ],
            )
        ],
        filters={},
    )

    metrics = build_prometheus_metrics(summary)

    assert 'workflow_node="plan_session"' in metrics
    assert "agent_harness_workflow_node_latency_p95_ms" in metrics
    assert "agent_harness_structured_output_validity_rate" in metrics


def test_recent_runs_include_user_hash_and_call_counts() -> None:
    now = datetime.now(UTC)
    summary = build_observability_summary(
        [
            AgentRunTrace(
                run_id="run_counts",
                session_id="sess_counts",
                user_id_hash="sha256:test",
                status="completed",
                started_at=now,
                finished_at=now,
                steps=[
                    TraceStep(
                        step_id="step_counts",
                        workflow_node="plan_session",
                        status="completed",
                        started_at=now,
                        finished_at=now,
                        llm_calls=[
                            TraceLlmCall(
                                llm_call_id="llm_derived_counts",
                                call_name="derived_plan_session",
                                status="completed",
                                started_at=now,
                                finished_at=now,
                            ),
                            TraceLlmCall(
                                llm_call_id="llm_captured_counts",
                                call_name="provider_plan_session",
                                execution_kind="llm",
                                payload_origin="captured",
                                provider="mimo",
                                model_name="mimo-v2.5-pro",
                                status="completed",
                                input_tokens=11,
                                output_tokens=7,
                                started_at=now,
                                finished_at=now,
                            )
                        ],
                        tool_calls=[
                            TraceToolCall(
                                tool_name="search_questions",
                                status="completed",
                                latency_ms=10,
                            )
                        ],
                    )
                ],
            )
        ],
        filters={},
    )

    recent = summary.recent_runs[0]
    assert recent.user_id_hash == "sha256:test"
    assert recent.llm_call_count == 1
    assert recent.tool_call_count == 1
    assert summary.input_token_count == 11
    assert summary.output_token_count == 7


def test_observability_threshold_settings_validate_runtime() -> None:
    settings = Settings(OBSERVABILITY_ERROR_RATE_ALERT_THRESHOLD=0.2, OBSERVABILITY_LATENCY_P95_ALERT_MS=3000)

    settings.validate_runtime()
    assert settings.observability_error_rate_alert_threshold == 0.2


def test_model_cost_estimation_uses_configured_token_rates() -> None:
    settings = Settings(
        MIMO_INPUT_COST_USD_PER_1K_TOKENS=0.01,
        MIMO_OUTPUT_COST_USD_PER_1K_TOKENS=0.03,
    )

    assert estimate_model_cost_usd(1000, 500, settings) == 0.025
