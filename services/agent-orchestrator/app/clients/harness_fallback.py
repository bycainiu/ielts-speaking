from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.protocols.schemas import AgentResponse, ConsumeAsrRequest, NextTurnRequest, PlanRequest, ScoreSessionRequest


logger = logging.getLogger("agent_orchestrator.harness_fallback")


class AgentHarnessFallbackClient:
    def __init__(self, base_url: str, *, timeout_seconds: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    @classmethod
    def from_settings(cls, settings: Settings) -> AgentHarnessFallbackClient | None:
        url = (settings.agent_harness_fallback_url or "").strip()
        if not url:
            return None
        return cls(url, timeout_seconds=max(settings.mimo_timeout_seconds * 2, 60.0))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def plan(self, session_id: str, request: PlanRequest) -> AgentResponse:
        return await self._post(session_id, "plan", request.model_dump(mode="json", exclude_none=True))

    async def consume_asr(self, session_id: str, request: ConsumeAsrRequest) -> AgentResponse:
        return await self._post(session_id, "consume-asr", request.model_dump(mode="json", exclude_none=True))

    async def next_turn(self, session_id: str, request: NextTurnRequest) -> AgentResponse:
        return await self._post(session_id, "next-turn", request.model_dump(mode="json", exclude_none=True))

    async def score_session(self, session_id: str, request: ScoreSessionRequest) -> AgentResponse:
        return await self._post(session_id, "score", request.model_dump(mode="json", exclude_none=True))

    async def _post(self, session_id: str, action: str, payload: dict[str, Any]) -> AgentResponse:
        url = f"{self.base_url}/agent/sessions/{session_id}/{action}"
        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()
        return _annotate_harness_fallback(AgentResponse.model_validate(body))


def _annotate_harness_fallback(response: AgentResponse) -> AgentResponse:
    state = dict(response.state or {})
    state["orchestrator_version"] = "harness_http_fallback"
    state["fallback_source"] = "agent_harness"
    return response.model_copy(update={"state": state})
