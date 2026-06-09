from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.output_schemas import FollowupDecisionOutput
from app.protocols.schemas import SessionMode


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
    asr_text: str = Field(min_length=1)
    question_text: str | None = None
    question_index: int = Field(default=0, ge=0)
    followup_count: int = Field(default=0, ge=0)

    @field_validator("asr_text", mode="before")
    @classmethod
    def normalize_asr_text(cls, value: Any) -> str:
        if value is None:
            raise ValueError("asr_text is required")
        text = str(value).strip()
        if not text:
            raise ValueError("asr_text is empty")
        return text


class FollowupPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: FollowupDecisionOutput
    next_action: Literal["wait_for_user_answer", "ask_next_question", "score_session"]
    word_count: int = Field(ge=0)
    privacy_guarded: bool = False


class FollowupPlannerAgent:
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
