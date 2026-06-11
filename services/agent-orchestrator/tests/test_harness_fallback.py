import json

import httpx
import pytest

from app.clients.harness_fallback import AgentHarnessFallbackClient
from app.protocols.schemas import AgentResponse, PlanRequest


@pytest.mark.asyncio
async def test_harness_fallback_plan_parses_response() -> None:
    payload = {
        "run_id": "run_harness_001",
        "next_action": "wait_for_user_answer",
        "events": [],
        "state": {"status": "in_progress", "mode": "full_exam"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/agent/sessions/sess_fb/plan")
        body = json.loads(request.content)
        assert body["mode"] == "full_exam"
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = AgentHarnessFallbackClient("http://harness.test", timeout_seconds=5.0)
        client._client = http_client
        response = await client.plan("sess_fb", PlanRequest(mode="full_exam", user_id="user_001"))

    assert response.run_id == "run_harness_001"
    assert response.state["orchestrator_version"] == "harness_http_fallback"
    assert response.state["fallback_source"] == "agent_harness"
