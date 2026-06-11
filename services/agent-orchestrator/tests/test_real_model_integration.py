import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.llm.gateway import LlmGateway
from app.main import app


pytestmark = pytest.mark.real_model


def _real_model_enabled() -> bool:
    settings = Settings()
    return os.getenv("REAL_MODEL_TESTS") == "1" and (not settings.mock_model_enabled) and settings.mimo_api_key not in {"", "change-me"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    if not _real_model_enabled():
        pytest.skip("REAL_MODEL_TESTS=1 and valid MIMO_API_KEY required")
    get_settings.cache_clear()
    return TestClient(app)


@pytest.fixture
def gateway() -> LlmGateway:
    if not _real_model_enabled():
        pytest.skip("REAL_MODEL_TESTS=1 and valid MIMO_API_KEY required")
    get_settings.cache_clear()
    return LlmGateway.from_settings()


@pytest.mark.asyncio
async def test_gateway_real_simple_completion(gateway: LlmGateway) -> None:
    response = await gateway.complete_with_tools(
        task="cheap",
        messages=[
            {"role": "system", "content": "Reply with JSON only."},
            {"role": "user", "content": 'Return {"answer":"ok"}'},
        ],
        tools=[],
        max_tokens=128,
    )
    assert response is not None
    assert response.model_name
    assert response.content or response.tool_calls


@pytest.mark.asyncio
async def test_gateway_real_tool_calling(gateway: LlmGateway) -> None:
    response = await gateway.complete_with_tools(
        task="question_planning",
        messages=[
            {"role": "system", "content": "You are an IELTS question planner. Use tools when helpful."},
            {"role": "user", "content": "Search Part 1 questions about technology."},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "search_questions",
                    "description": "Search question bank",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}, "part": {"type": "integer"}},
                        "required": ["query", "part"],
                    },
                },
            }
        ],
        max_tokens=512,
    )
    assert response is not None
    assert response.model_name
    assert response.content or response.tool_calls


def test_real_plan_session(client: TestClient) -> None:
    response = client.post(
        "/agent/sessions/sess_real_plan/plan",
        json={"mode": "full_exam", "user_id": "user_real_001"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["next_action"] == "wait_for_user_answer"
    assert body["state"]["question_plan"]["parts"]
    run_id = body["run_id"]

    events = client.get(f"/agent/runs/{run_id}/events").json()
    kinds = {item["kind"] for item in events}
    assert "run.completed" in kinds

    messages = client.get(f"/agent/runs/{run_id}/messages").json()
    assert len(messages) >= 3
    agents = {item["source_agent"] for item in messages}
    assert "exam_director" in agents


def test_real_consume_asr_flow(client: TestClient) -> None:
    plan = client.post(
        "/agent/sessions/sess_real_asr/plan",
        json={"mode": "part_practice", "user_id": "user_real_001", "part": 1},
    ).json()
    consume = client.post(
        "/agent/sessions/sess_real_asr/consume-asr",
        json={
            "turn_id": "turn_real_001",
            "asr_text": (
                "I really enjoy learning English because it helps me communicate with people from different cultures. "
                "For instance, I joined a conversation club last year and made several international friends."
            ),
            "session_state": plan["state"],
        },
    )
    assert consume.status_code == 200
    body = consume.json()
    assert body["next_action"] in {"wait_for_user_answer", "ask_next_question"}
    assert any(event["type"] in {"asr.final", "agent.followup_planned"} for event in body["events"])


def test_real_score_session(client: TestClient) -> None:
    score = client.post(
        "/agent/sessions/sess_real_score/score",
        json={
            "session_state": {
                "mode": "full_exam",
                "answers": [
                    {
                        "turn_id": "turn_real_score",
                        "part": 1,
                        "question_text": "Do you like reading?",
                        "asr_text": (
                            "Yes, I enjoy reading because it broadens my perspective. "
                            "I usually read non-fiction books about psychology and communication."
                        ),
                        "asr_confidence": 0.9,
                    }
                ],
            }
        },
    )
    assert score.status_code == 200
    body = score.json()
    assert body["next_action"] == "finish_session"
    report = body["state"]["score_report"]
    assert report["overall_band"] >= 4.0
    assert report["criteria"]


def test_real_full_exam_plan_to_score(client: TestClient) -> None:
    session_id = "sess_real_full"
    plan = client.post(
        f"/agent/sessions/{session_id}/plan",
        json={"mode": "full_exam", "user_id": "user_real_001"},
    ).json()
    state = plan["state"]

    for turn_index in range(1, 6):
        consume = client.post(
            f"/agent/sessions/{session_id}/consume-asr",
            json={
                "turn_id": f"turn_real_{turn_index:03d}",
                "asr_text": (
                    "I think this topic is interesting because it connects to my daily routine. "
                    "For example, I often discuss similar ideas with classmates after lectures."
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

    trace = client.get(f"/agent/runs/{score_body['run_id']}/trace").json()
    assert trace["status"] == "completed"
