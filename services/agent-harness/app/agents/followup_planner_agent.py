from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.output_schemas import FollowupDecisionOutput
from app.protocols.schemas import SessionMode

if TYPE_CHECKING:
    from app.models.llm_gateway import LlmGateway


logger = logging.getLogger("agent_harness.followup_planner")

FOLLOWUP_LLM_PROMPT_VERSION = "followup_planner.llm.v1"


WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
SENSITIVE_HINT_RE = re.compile(
    r"\b(address|phone number|email|passport|id card|salary|bank|password|workplace)\b",
    re.IGNORECASE,
)
MIN_WORDS_BY_PART = {1: 8, 2: 35, 3: 16}
MAX_FOLLOWUPS_PER_QUESTION = 1


class FollowupPlannerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: SessionMode = "full_exam"
    part: Literal[1, 2, 3] = 1
    asr_text: str
    question_text: str | None = None
    question_index: int = Field(default=0, ge=0)
    followup_count: int = Field(default=0, ge=0)

    @field_validator("asr_text", mode="before")
    @classmethod
    def normalize_asr_text(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()


class FollowupPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: FollowupDecisionOutput
    next_action: Literal["wait_for_user_answer", "ask_next_question", "score_session"]
    word_count: int = Field(ge=0)
    privacy_guarded: bool = False


class FollowupPlannerAgent:
    """追问规划 Agent：隐私守卫始终走确定性规则；追问决策优先交给真实 LLM，失败时回退规则。"""

    def __init__(self, llm_gateway: "LlmGateway | None" = None) -> None:
        self.llm_gateway = llm_gateway

    def plan(self, planner_input: FollowupPlannerInput) -> FollowupPlan:
        word_count = count_words(planner_input.asr_text)
        if contains_sensitive_signal(planner_input.asr_text):
            return FollowupPlan(
                decision=FollowupDecisionOutput(
                    decision="next_question",
                    reason="回答包含敏感信息线索，追问规划跳过私人细节，进入下一题。",
                    confidence=0.9,
                ),
                next_action="ask_next_question",
                word_count=word_count,
                privacy_guarded=True,
            )

        llm_plan = self._build_llm_plan(planner_input, word_count)
        if llm_plan is not None:
            return llm_plan

        if (
            word_count < MIN_WORDS_BY_PART[planner_input.part]
            and planner_input.followup_count < MAX_FOLLOWUPS_PER_QUESTION
        ):
            return FollowupPlan(
                decision=FollowupDecisionOutput(
                    decision="ask_followup",
                    reason=f"Part {planner_input.part} 回答偏短，需要一个自然追问来获得更多可评分证据。",
                    confidence=0.82,
                    suggested_question=suggest_followup_question(planner_input),
                ),
                next_action="wait_for_user_answer",
                word_count=word_count,
            )

        return FollowupPlan(
            decision=FollowupDecisionOutput(
                decision="next_question",
                reason="回答长度和内容足以进入下一题，避免过度追问。",
                confidence=0.78,
            ),
            next_action="ask_next_question",
            word_count=word_count,
        )

    def _build_llm_plan(self, planner_input: FollowupPlannerInput, word_count: int) -> FollowupPlan | None:
        gateway = self.llm_gateway
        if gateway is None or not gateway.enabled:
            return None
        decision = gateway.generate_structured(
            task="followup_planning",
            call_name="followup_plan",
            agent_name="FollowupPlannerAgent",
            prompt_version=FOLLOWUP_LLM_PROMPT_VERSION,
            messages=build_followup_llm_messages(planner_input, word_count),
            output_model=FollowupDecisionOutput,
            temperature=0.2,
            # 推理模型 thinking 与 JSON 正文共享 max_tokens 预算，需留足余量。
            max_tokens=700,
        )
        if decision is None:
            return None
        return self._plan_from_decision(planner_input, decision, word_count)

    def _plan_from_decision(
        self,
        planner_input: FollowupPlannerInput,
        decision: FollowupDecisionOutput,
        word_count: int,
    ) -> FollowupPlan:
        if decision.decision == "ask_followup":
            if planner_input.followup_count >= MAX_FOLLOWUPS_PER_QUESTION:
                logger.info("followup_llm_decision_capped", extra={"followup_count": planner_input.followup_count})
                decision = FollowupDecisionOutput(
                    decision="next_question",
                    reason=f"已达到单题追问上限（{MAX_FOLLOWUPS_PER_QUESTION} 次），进入下一题。",
                    confidence=decision.confidence,
                )
            elif not decision.suggested_question:
                decision = decision.model_copy(update={"suggested_question": suggest_followup_question(planner_input)})
        next_action_map = {
            "ask_followup": "wait_for_user_answer",
            "next_question": "ask_next_question",
            "finish_part": "ask_next_question",
            "finish_session": "score_session",
        }
        return FollowupPlan(
            decision=decision,
            next_action=next_action_map[decision.decision],
            word_count=word_count,
        )


def build_followup_llm_messages(planner_input: FollowupPlannerInput, word_count: int) -> list[dict[str, str]]:
    min_words = MIN_WORDS_BY_PART[planner_input.part]
    system = (
        "You are the follow-up planning module of an IELTS Speaking examiner agent. "
        "Decide whether the examiner should ask one natural follow-up question or move on. "
        "Policy: ask a follow-up only when the answer is too short or too vague to provide scorable evidence "
        f"(rough benchmark: fewer than {min_words} words for Part {planner_input.part}), "
        f"and never exceed {MAX_FOLLOWUPS_PER_QUESTION} follow-up per question. "
        "Never ask about private personal details. "
        "Respond with JSON only, matching this schema: "
        '{"decision": "ask_followup|next_question|finish_part|finish_session", '
        '"reason": "<short Chinese explanation>", "confidence": 0.0-1.0, '
        '"suggested_question": "<the follow-up question in English, required when decision=ask_followup>"}'
    )
    user = (
        f"Part: {planner_input.part}\n"
        f"Current question: {planner_input.question_text or '(unknown)'}\n"
        f"Candidate answer (ASR transcript): {planner_input.asr_text or '(empty)'}\n"
        f"Answer word count: {word_count}\n"
        f"Follow-ups already asked for this question: {planner_input.followup_count}\n"
        "Return the JSON decision now."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def suggest_followup_question(planner_input: FollowupPlannerInput) -> str:
    if planner_input.part == 1:
        return "Could you tell me a little more about that?"
    if planner_input.part == 2:
        return "Can you add one specific detail about why this experience was important to you?"
    return "Why do you think this matters to people more generally?"


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def contains_sensitive_signal(text: str) -> bool:
    return bool(EMAIL_RE.search(text) or PHONE_RE.search(text) or SENSITIVE_HINT_RE.search(text))
