from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "agent-orchestrator"
    assert body["runtime"]["framework"] == "multi-agent-orchestration"


def test_plan_session_returns_examiner_message() -> None:
    response = client.post(
        "/agent/sessions/sess_orchestrator_001/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["next_action"] == "wait_for_user_answer"
    assert any(event["type"] == "examiner.message" for event in body["events"])
    assert body["state"]["question_plan"]["parts"][0]["timebox_seconds"] == 300
    assert len(body["state"]["question_plan"]["parts"][0]["questions"]) == 4
    assert body["state"]["status"] == "in_progress"
    assert body["state"]["orchestrator_version"] == "phase2_multi_agent"
    assert body["state"]["question_plan"]["parts"][0]["questions"][0]["question_id"].startswith("planner_fallback_p1")


def test_plan_session_records_agent_messages() -> None:
    response = client.post(
        "/agent/sessions/sess_orchestrator_002/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    messages = client.get(f"/agent/runs/{run_id}/messages")
    assert messages.status_code == 200
    payload = messages.json()
    assert len(payload) >= 4
    assert {item["source_agent"] for item in payload} >= {"exam_director", "question_strategist", "live_examiner"}


def test_consume_asr_and_next_turn_flow() -> None:
    plan = client.post(
        "/agent/sessions/sess_orchestrator_003/plan",
        json={"mode": "part_practice", "user_id": "user_001", "part": 1},
    ).json()
    state = plan["state"]
    consume = client.post(
        "/agent/sessions/sess_orchestrator_003/consume-asr",
        json={
            "turn_id": "turn_001",
            "asr_text": "I like my hometown because it is peaceful and convenient for daily life.",
            "session_state": state,
        },
    )
    assert consume.status_code == 200
    consume_body = consume.json()
    assert consume_body["next_action"] in {"wait_for_user_answer", "ask_next_question"}

    next_turn = client.post(
        "/agent/sessions/sess_orchestrator_003/next-turn",
        json={"session_state": consume_body["state"]},
    )
    assert next_turn.status_code == 200
    next_body = next_turn.json()
    assert next_body["next_action"] in {"wait_for_user_answer", "score_session"}


def test_score_session_returns_report() -> None:
    response = client.post(
        "/agent/sessions/sess_orchestrator_004/score",
        json={"session_state": {"answers": [], "mode": "full_exam"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["next_action"] == "finish_session"
    assert any(event["type"] == "report.ready" for event in body["events"])
    assert body["state"]["score_report"]["overall_band"] == 5.5
    assert body["state"]["score_report"]["source"] == "rules_scoring"
    criteria = body["state"]["score_report"]["criteria"]
    assert isinstance(criteria["fluency_coherence"]["band"], float)
    assert isinstance(criteria["fluency_coherence"]["confidence"], float)
    assert body["state"]["score_report"]["confidence"] >= 0
    assert body["state"]["score_report"]["disclaimer"]


def test_part2_next_turn_includes_cue_card_and_timer() -> None:
    plan = client.post(
        "/agent/sessions/sess_orchestrator_part2/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    ).json()
    state = plan["state"]
    state["question_index"] = 3
    response = client.post(
        "/agent/sessions/sess_orchestrator_part2/next-turn",
        json={"session_state": state},
    )
    assert response.status_code == 200
    body = response.json()
    examiner_events = [event for event in body["events"] if event["type"] == "examiner.message"]
    timer_events = [event for event in body["events"] if event["type"] == "timer.started"]
    part_started = [event for event in body["events"] if event["type"] == "part.started"]
    assert examiner_events
    payload = examiner_events[-1]["payload"]
    assert payload["part"] == 2
    assert payload["cue_card"]["prompt"]
    assert payload["cue_card"]["bullet_points"]
    assert payload["timer_policy"]["preparation_seconds"] == 60
    assert timer_events
    assert timer_events[-1]["payload"]["phase"] == "prepare_then_speak"
    assert part_started and part_started[-1]["payload"]["part"] == 2


def test_run_stream_events_available_after_plan() -> None:
    plan = client.post(
        "/agent/sessions/sess_orchestrator_005/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    ).json()
    events = client.get(f"/agent/runs/{plan['run_id']}/events")
    assert events.status_code == 200
    kinds = {item["kind"] for item in events.json()}
    assert "run.started" in kinds
    assert "run.completed" in kinds
    route_events = [item for item in events.json() if item["kind"] == "director.route_change"]
    assert route_events
