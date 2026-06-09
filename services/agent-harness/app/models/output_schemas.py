from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimerPolicyOutput(StrictOutputModel):
    suggested_seconds: int = Field(gt=0)


class ExaminerMessageOutput(StrictOutputModel):
    part: Literal[1, 2, 3]
    question_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    timer_policy: TimerPolicyOutput


class FollowupDecisionOutput(StrictOutputModel):
    decision: Literal["ask_followup", "next_question", "finish_part", "finish_session"]
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    suggested_question: str | None = Field(default=None, min_length=1)


CriterionName = Literal[
    "fluency_coherence",
    "lexical_resource",
    "grammatical_range_accuracy",
    "pronunciation",
]


class CriterionScoreOutput(StrictOutputModel):
    criterion: CriterionName
    band: float = Field(ge=0, le=9)
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class FeedbackPlanOutput(StrictOutputModel):
    summary: str = Field(min_length=1)
    priority_actions: list[str] = Field(min_length=1)
    next_practice_plan: list[str] = Field(default_factory=list)
