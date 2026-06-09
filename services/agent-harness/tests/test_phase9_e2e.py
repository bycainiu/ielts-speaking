from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_phase9_full_exam_happy_path_generates_report_and_observability_summary() -> None:
    session_id = "sess_phase9_full_exam"
    plan = client.post(f"/agent/sessions/{session_id}/plan", json={"mode": "full_exam", "user_id": "user_phase9_e2e"})
    assert plan.status_code == 200
    state = plan.json()["state"]

    asr = client.post(
        f"/agent/sessions/{session_id}/consume-asr",
        json={
            "turn_id": "turn_phase9_full_001",
            "asr_text": "I come from a compact city, and I like it because public transport is convenient and the library near my home is quiet.",
            "asr_confidence": 0.9,
            "session_state": state,
        },
    )
    assert asr.status_code == 200
    state = asr.json()["state"]

    state["part_elapsed_seconds"] = 300
    part_two = client.post(f"/agent/sessions/{session_id}/next-turn", json={"session_state": state})
    assert part_two.status_code == 200
    state = part_two.json()["state"]

    part_three = client.post(f"/agent/sessions/{session_id}/next-turn", json={"session_state": state})
    assert part_three.status_code == 200
    state = part_three.json()["state"]

    second_part_three = client.post(f"/agent/sessions/{session_id}/next-turn", json={"session_state": state})
    assert second_part_three.status_code == 200
    state = second_part_three.json()["state"]

    completed = client.post(f"/agent/sessions/{session_id}/next-turn", json={"session_state": state})
    assert completed.status_code == 200
    assert completed.json()["next_action"] == "score_session"

    score = client.post(
        f"/agent/sessions/{session_id}/score",
        json={"session_state": completed.json()["state"], "topic_keywords": ["city", "library"]},
    )
    assert score.status_code == 200
    scored = score.json()
    assert scored["next_action"] == "finish_session"
    assert scored["state"]["score_report"]["overall_band"] is not None
    assert scored["state"]["reference_answers"]

    trace = client.get(f"/agent/runs/{scored['run_id']}/trace")
    assert trace.status_code == 200
    assert trace.json()["steps"][0]["workflow_node"] == "score_session"
    assert trace.json()["steps"][0]["scoring_result"]["disclaimer_present"] is True

    summary = client.get("/agent/observability/summary", params={"session_id": session_id})
    assert summary.status_code == 200
    assert summary.json()["run_count"] >= 5
    assert summary.json()["failed_count"] == 0


def test_phase9_part_practice_happy_path_generates_report() -> None:
    session_id = "sess_phase9_part_practice"
    plan = client.post(
        f"/agent/sessions/{session_id}/plan",
        json={"mode": "part_practice", "user_id": "user_phase9_practice", "part": 2},
    )
    assert plan.status_code == 200

    asr = client.post(
        f"/agent/sessions/{session_id}/consume-asr",
        json={
            "turn_id": "turn_phase9_part_001",
            "asr_text": "I would like to describe a public library near my home. I went there every weekend when I was preparing for a test, and it helped me focus.",
            "asr_confidence": 0.89,
            "session_state": plan.json()["state"],
        },
    )
    assert asr.status_code == 200

    completed = client.post(f"/agent/sessions/{session_id}/next-turn", json={"session_state": asr.json()["state"]})
    assert completed.status_code == 200
    assert completed.json()["next_action"] == "score_session"

    score = client.post(
        f"/agent/sessions/{session_id}/score",
        json={"session_state": completed.json()["state"], "topic_keywords": ["library", "study"]},
    )
    assert score.status_code == 200
    assert score.json()["state"]["score_report"]["disclaimer"] == "AI 模拟评分仅用于练习参考，不代表 IELTS 官方成绩。"
