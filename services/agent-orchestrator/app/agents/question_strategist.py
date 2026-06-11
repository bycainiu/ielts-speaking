from __future__ import annotations

from typing import Any

from app.agents.base import BaseSpecialistAgent
from app.protocols.agent_message import RESULT_QUESTIONS_PLANNED, TASK_PLAN_QUESTIONS, AgentMessage
from app.protocols.schemas import PlanRequest
from app.rules.fallback_plan import build_fallback_question_plan


AUTHORIZED_TOOLS = [
    "search_questions",
    "get_cue_card",
    "get_followup_templates",
    "get_user_background",
    "get_session_history",
]


class QuestionStrategistAgent(BaseSpecialistAgent):
    agent_name = "question_strategist"

    async def _handle(self, message: AgentMessage) -> None:
        if message.message_type != TASK_PLAN_QUESTIONS:
            return
        plan_request = PlanRequest.model_validate(message.payload.get("plan_request") or message.payload)
        question_plan = await self._plan_questions(message, plan_request)
        await self._reply(
            message,
            {"question_plan": question_plan, "fallback_used": question_plan.get("fallback_used", False)},
            message_type=RESULT_QUESTIONS_PLANNED,
        )

    async def _plan_questions(self, message: AgentMessage, request: PlanRequest) -> dict[str, Any]:
        from app.core.config import get_settings

        settings = get_settings()
        if not settings.mock_model_enabled:
            loop_result = await self._tool_loop.run(
                run_id=message.run_id,
                agent_name=self.agent_name,
                task="question_planning",
                system_prompt="You are the Question Strategist for IELTS Speaking.",
                user_message=f"Plan questions for mode={request.mode}, user={request.user_id}",
                tools=AUTHORIZED_TOOLS,
                context=message.context,
            )
            if loop_result is not None and isinstance(loop_result.output, dict):
                if loop_result.output.get("question_plan"):
                    plan = loop_result.output["question_plan"]
                    plan["execution_kind"] = "llm"
                    return plan

        plan = build_fallback_question_plan(request)
        plan["execution_kind"] = "deterministic"
        return plan
