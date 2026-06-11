import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "packages" / "protocol" / "schemas" / "agent-api.schema.json"


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "agent-orchestrator"
    assert body["runtime"]["framework"] == "multi-agent-orchestration"
    assert "api_key" not in json.dumps(body)


def test_plan_session_returns_examiner_message() -> None:
    response = client.post(
        "/agent/sessions/sess_api_001/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["next_action"] == "wait_for_user_answer"
    assert body["run_id"]
    assert any(event["type"] == "examiner.message" for event in body["events"])
    assert body["state"]["question_plan"]["parts"][0]["timebox_seconds"] == 300
    assert len(body["state"]["question_plan"]["parts"][0]["questions"]) == 4
    assert body["state"]["status"] == "in_progress"
    assert body["state"]["orchestrator_version"] == "phase2_multi_agent"
    assert body["state"]["mode_policy"]["prompt_profile"] == "examiner_exam"

    trace_response = client.get(f"/agent/runs/{body['run_id']}/trace")
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert trace["run_id"] == body["run_id"]
    assert trace["status"] == "completed"


def test_score_session_returns_ready_report() -> None:
    response = client.post(
        "/agent/sessions/sess_api_score/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )
    state = response.json()["state"]
    score = client.post(
        "/agent/sessions/sess_api_score/score",
        json={
            "session_state": {
                **state,
                "answers": [
                    {
                        "turn_id": "turn_score_001",
                        "part": 1,
                        "question_text": "What do you like about your hometown?",
                        "asr_text": (
                            "I like my hometown because it is convenient and friendly. "
                            "For example, there is a library near my home."
                        ),
                        "asr_confidence": 0.88,
                    }
                ],
            }
        },
    )
    assert score.status_code == 200
    body = score.json()
    assert body["next_action"] == "finish_session"
    assert any(event["type"] == "report.ready" for event in body["events"])
    assert body["state"]["score_report"]["overall_band"] >= 0


def test_consume_asr_and_next_turn_flow() -> None:
    plan = client.post(
        "/agent/sessions/sess_api_flow/plan",
        json={"mode": "part_practice", "user_id": "user_001", "part": 1},
    ).json()
    consume = client.post(
        "/agent/sessions/sess_api_flow/consume-asr",
        json={
            "turn_id": "turn_001",
            "asr_text": "I like my hometown because it is peaceful and convenient for daily life.",
            "session_state": plan["state"],
        },
    )
    assert consume.status_code == 200
    consume_body = consume.json()
    assert consume_body["next_action"] in {"wait_for_user_answer", "ask_next_question"}

    next_turn = client.post(
        "/agent/sessions/sess_api_flow/next-turn",
        json={"session_state": consume_body["state"]},
    )
    assert next_turn.status_code == 200
    assert next_turn.json()["next_action"] in {"wait_for_user_answer", "score_session"}


def test_unknown_run_trace_returns_404() -> None:
    response = client.get("/agent/runs/run_missing/trace")
    assert response.status_code == 404


def test_agent_response_matches_json_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    import jsonschema

    response = client.post(
        "/agent/sessions/sess_api_schema/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )
    body = response.json()
    jsonschema.validate(body, schema)


def test_full_exam_can_complete_all_parts_and_enter_scoring() -> None:
    session_id = "sess_api_full_exam"
    plan = client.post(
        f"/agent/sessions/{session_id}/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    ).json()
    state = plan["state"]

    for turn_index in range(1, 8):
        consume = client.post(
            f"/agent/sessions/{session_id}/consume-asr",
            json={
                "turn_id": f"turn_{turn_index:03d}",
                "asr_text": (
                    "I enjoy discussing this topic because it reflects my daily experience. "
                    "For example, I often practice speaking with friends after work."
                ),
                "session_state": state,
            },
        )
        assert consume.status_code == 200
        consume_body = consume.json()
        state = consume_body["state"]
        if consume_body["next_action"] == "score_session":
            break
        next_turn = client.post(
            f"/agent/sessions/{session_id}/next-turn",
            json={"session_state": state},
        )
        assert next_turn.status_code == 200
        next_body = next_turn.json()
        state = next_body["state"]
        if next_body["next_action"] == "score_session":
            break

    score = client.post(
        f"/agent/sessions/{session_id}/score",
        json={"session_state": state},
    )
    assert score.status_code == 200
    score_body = score.json()
    assert score_body["next_action"] == "finish_session"
    assert score_body["state"]["score_report"]["overall_band"] >= 0


def event_payload(body: dict, event_type: str) -> dict:
    return next(event["payload"] for event in body["events"] if event["type"] == event_type)
