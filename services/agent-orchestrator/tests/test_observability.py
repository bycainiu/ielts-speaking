from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.observability.persistence import _apply_reasoning_retention
from app.observability.trace import OrchestratorTraceRecorder
from app.protocols.schemas import AgentResponse


client = TestClient(app)


@dataclass
class FakeOrchestratorRepository:
    saved_runs: list[dict[str, Any]] = field(default_factory=list)

    def save_run_observability(self, **kwargs: Any) -> None:
        self.saved_runs.append(kwargs)

    def list_messages(self, run_id: str) -> list[dict[str, Any]]:
        for item in self.saved_runs:
            if item["trace"].run_id == run_id:
                return [
                    {
                        "message_id": message.message_id,
                        "source_agent": message.source_agent,
                        "target_agent": message.target_agent,
                        "message_type": message.message_type,
                    }
                    for message in item["messages"]
                ]
        return []

    def list_tool_iterations(self, run_id: str) -> list[dict[str, Any]]:
        return []


def test_plan_emits_orchestrator_stream_events() -> None:
    response = client.post(
        "/agent/sessions/sess_obs_001/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    events = client.get(f"/agent/runs/{run_id}/events").json()
    kinds = {item["kind"] for item in events}
    assert "run.started" in kinds
    assert "run.completed" in kinds
    assert "agent.activated" in kinds


def test_plan_stream_sse_returns_completed_run() -> None:
    plan = client.post(
        "/agent/sessions/sess_obs_002/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    ).json()
    with client.stream("GET", f"/agent/runs/{plan['run_id']}/stream") as stream:
        body = "".join(stream.iter_text())
    assert "run.completed" in body
    assert "agent.activated" in body


def test_trace_recorder_persists_on_completion() -> None:
    fake_repo = FakeOrchestratorRepository()
    settings = Settings(
        TRACE_PERSISTENCE_ENABLED=True,
        TRACE_DATABASE_URL="postgresql://example",
    )
    recorder = OrchestratorTraceRecorder(settings, repository=fake_repo)  # type: ignore[arg-type]

    async def _noop_call() -> AgentResponse:
        return AgentResponse(
            run_id="ignored",
            next_action="wait_for_user_answer",
            events=[],
            state={"status": "in_progress"},
        )

    asyncio.run(
        recorder.record_agent_call(
            session_id="sess_persist_001",
            workflow_node="plan_session",
            request=type("Req", (), {"run_id_override": "run_persist_001"})(),
            call=_noop_call,
        )
    )
    assert len(fake_repo.saved_runs) == 1
    assert fake_repo.saved_runs[0]["trace"].run_id == "run_persist_001"


def test_reasoning_retention_summary() -> None:
    text = "x" * 500
    summary = _apply_reasoning_retention(text, retention="summary")
    assert summary is not None
    assert summary.startswith("x" * 200)
    assert summary.endswith("x" * 200)


def test_session_timeline_lists_runs() -> None:
    client.post(
        "/agent/sessions/sess_obs_timeline/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )
    timeline = client.get("/agent/sessions/sess_obs_timeline/timeline")
    assert timeline.status_code == 200
    body = timeline.json()
    assert body["session_id"] == "sess_obs_timeline"
    assert len(body["runs"]) >= 1


def test_tool_iterations_endpoint_returns_list() -> None:
    plan = client.post(
        "/agent/sessions/sess_obs_tools/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    ).json()
    response = client.get(f"/agent/runs/{plan['run_id']}/tool-iterations")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
