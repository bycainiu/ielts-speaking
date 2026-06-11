from __future__ import annotations

from typing import Any

from app.agents.base import BaseSpecialistAgent
from app.protocols.agent_message import (
    RESULT_EXAMINER_UTTERANCE,
    RESULT_FOLLOWUP_DECISION,
    TASK_DECIDE_FOLLOWUP,
    TASK_DELIVER_QUESTION,
    AgentMessage,
)
from app.rules.examiner_rules import build_exam_text, suggest_followup_question


AUTHORIZED_TOOLS = ["analyze_response_quality", "search_questions"]


class LiveExaminerAgent(BaseSpecialistAgent):
    agent_name = "live_examiner"

    async def _handle(self, message: AgentMessage) -> None:
        if message.message_type == TASK_DELIVER_QUESTION:
            await self._deliver_question(message)
            return
        if message.message_type == TASK_DECIDE_FOLLOWUP:
            await self._decide_followup(message)

    async def _deliver_question(self, message: AgentMessage) -> None:
        payload = message.payload
        question = payload.get("question") or {}
        part = int(payload.get("part") or message.context.current_part or 1)
        question_index = int(payload.get("question_index") or message.context.question_index or 0)
        practice_mode = message.context.mode != "full_exam"
        question_text = str(question.get("text") or question.get("topic") or "Let's continue.")
        text = build_exam_text(
            part=part,
            question_index=question_index,
            question_text=question_text,
            practice_mode=practice_mode,
        )
        if part == 1 and question_index == 0 and message.context.mode == "full_exam":
            text = (
                "Good afternoon. My name is Alex, and I will be your examiner today. "
                f"{text}"
            )
        await self._reply(
            message,
            {
                "text": text,
                "source": "rules_examiner",
                "question_id": question.get("question_id"),
                "part": part,
            },
            message_type=RESULT_EXAMINER_UTTERANCE,
        )

    async def _decide_followup(self, message: AgentMessage) -> None:
        asr_text = str(message.payload.get("asr_text") or "")
        part = int(message.payload.get("part") or message.context.current_part or 1)
        followup_count = int(message.payload.get("followup_count") or 0)
        interim = message.payload.get("interim_assessment") or {}
        quality = interim.get("quality") or {}

        ask_followup = False
        if followup_count < message.context.exam_constraints.max_followups_per_question:
            if quality.get("needs_followup") or quality.get("very_short"):
                ask_followup = len(asr_text.split()) >= 3

        followup_text: str | None = None
        if ask_followup:
            followup_text = suggest_followup_question(part=part)

        await self._reply(
            message,
            {
                "ask_followup": ask_followup,
                "followup_text": followup_text,
                "source": "rules_followup",
            },
            message_type=RESULT_FOLLOWUP_DECISION,
        )
