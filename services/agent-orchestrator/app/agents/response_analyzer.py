from __future__ import annotations

from uuid import uuid4

from app.agents.base import BaseSpecialistAgent
from app.protocols.agent_message import (
    INFO_INTERIM_ASSESSMENT,
    RESULT_RESPONSE_ANALYSIS,
    RESULT_SCORE_REPORT,
    TASK_ANALYZE_RESPONSE,
    TASK_SCORE_SESSION,
    AgentMessage,
)
from app.rules.scoring_rules import build_interim_assessment, build_score_report


AUTHORIZED_TOOLS = [
    "compute_wpm",
    "detect_long_pauses",
    "estimate_filler_ratio",
    "get_rubric_descriptor",
    "get_anchor_samples",
    "analyze_response_quality",
]


class ResponseAnalyzerAgent(BaseSpecialistAgent):
    agent_name = "response_analyzer"

    async def _handle(self, message: AgentMessage) -> None:
        if message.message_type == TASK_ANALYZE_RESPONSE:
            await self._analyze_response(message)
            return
        if message.message_type == TASK_SCORE_SESSION:
            await self._score_session(message)

    async def _analyze_response(self, message: AgentMessage) -> None:
        asr_text = str(message.payload.get("asr_text") or "")
        part = int(message.payload.get("part") or message.context.current_part or 1)
        assessment = build_interim_assessment(asr_text=asr_text, part=part)

        await self._bus.send(
            AgentMessage(
                message_id=f"msg_{uuid4().hex}",
                run_id=message.run_id,
                session_id=message.session_id,
                source_agent=self.agent_name,
                target_agent="live_examiner",
                message_type=INFO_INTERIM_ASSESSMENT,
                payload={"assessment": assessment},
                context=message.context,
            )
        )
        await self._reply(
            message,
            {"assessment": assessment, "source": "rules_analyzer"},
            message_type=RESULT_RESPONSE_ANALYSIS,
        )

    async def _score_session(self, message: AgentMessage) -> None:
        session_state = message.payload.get("session_state") or {}
        answers = session_state.get("answers") or []
        report = build_score_report(answers)
        await self._reply(
            message,
            {"report": report, "source": "rules_scoring"},
            message_type=RESULT_SCORE_REPORT,
        )
