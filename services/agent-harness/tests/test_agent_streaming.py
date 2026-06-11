from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_agent_run_stream_events_are_created_and_replayed() -> None:
    response = client.post(
        "/agent/sessions/sess_stream_plan/plan",
        json={"mode": "full_exam", "user_id": "user_stream"},
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    events_response = client.get(f"/agent/runs/{run_id}/events")
    assert events_response.status_code == 200
    events = events_response.json()
    kinds = [event["kind"] for event in events]

    assert kinds[0] == "run.started"
    assert "step.started" in kinds
    assert "question.requested" in kinds
    assert "message.delta" in kinds
    assert kinds[-1] == "run.completed"
    assert events == sorted(events, key=lambda item: item["seq"])

    with client.stream("GET", f"/agent/runs/{run_id}/stream") as stream_response:
        assert stream_response.status_code == 200
        body = "".join(stream_response.iter_text())

    assert "event: run.started" in body
    assert "event: run.completed" in body


def test_agent_run_list_can_filter_by_status() -> None:
    response = client.post(
        "/agent/sessions/sess_stream_list/plan",
        json={"mode": "full_exam", "user_id": "user_stream"},
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    runs_response = client.get("/agent/runs", params={"status": "completed", "limit": 20})
    assert runs_response.status_code == 200
    run_ids = {item["run_id"] for item in runs_response.json()}

    assert run_id in run_ids


def test_agent_stream_contains_reasoning_delta_for_followup_decision() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_stream_reasoning/plan",
        json={"mode": "full_exam", "user_id": "user_stream"},
    )
    assert plan_response.status_code == 200
    state = plan_response.json()["state"]

    consume_response = client.post(
        "/agent/sessions/sess_stream_reasoning/consume-asr",
        json={
            "turn_id": "turn_stream_reasoning_001",
            "asr_text": "I like my hometown because it is quiet and my family lives there.",
            "session_state": state,
        },
    )
    assert consume_response.status_code == 200
    run_id = consume_response.json()["run_id"]

    trace_response = client.get(f"/agent/runs/{run_id}/trace")
    assert trace_response.status_code == 200
    trace = trace_response.json()
    reasoning_events = [event for event in trace["stream_events"] if event["kind"] == "reasoning.delta"]

    assert reasoning_events
    assert reasoning_events[0]["reasoning_delta"]
    assert reasoning_events[0]["visibility"] == "reasoning"


def test_cancel_run_adds_stream_cancel_event() -> None:
    response = client.post(
        "/agent/sessions/sess_stream_cancel/plan",
        json={"mode": "full_exam", "user_id": "user_stream"},
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    cancel_response = client.post(f"/agent/runs/{run_id}/cancel")
    assert cancel_response.status_code == 200
    events_response = client.get(f"/agent/runs/{run_id}/events")
    assert events_response.status_code == 200

    assert events_response.json()[-1]["kind"] == "run.cancelled"
