from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.protocols.schemas import SessionMode


INTERNAL_TERM_RE = re.compile(
    r"\b(system prompt|developer message|rubric|band descriptor|scoring rule|hidden instruction|password|api key|secret|private tools?)\b",
    re.IGNORECASE,
)


class ExaminerTurnInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: SessionMode
    part: Literal[1, 2, 3]
    question_id: str = Field(min_length=1)
    question_text: str = Field(min_length=1)
    question_index: int = Field(ge=0)
    total_questions: int = Field(ge=1)
    practice_mode: bool = False

    @model_validator(mode="after")
    def validate_mode_flags(self) -> "ExaminerTurnInput":
        if self.mode == "full_exam" and self.practice_mode:
            raise ValueError("full_exam cannot be marked as practice_mode")
        return self

    @field_validator("question_id", "question_text", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        if value is None:
            raise ValueError("required text is missing")
        text = str(value).strip()
        if not text:
            raise ValueError("required text is empty")
        return text


class ExaminerUtterance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part: Literal[1, 2, 3]
    question_id: str
    text: str = Field(min_length=1, max_length=520)
    style_tags: list[str] = Field(default_factory=list)
    practice_mode: bool = False


class ExaminerAgent:
    def build_turn(self, turn: ExaminerTurnInput) -> ExaminerUtterance:
        question = sanitize_examiner_text(turn.question_text)
        if turn.mode == "full_exam":
            text, style_tags = build_exam_text(turn, question)
        else:
            text, style_tags = build_practice_text(turn, question)

        return ExaminerUtterance(
            part=turn.part,
            question_id=turn.question_id,
            text=compact_text(text),
            style_tags=style_tags,
            practice_mode=turn.practice_mode,
        )


def build_exam_text(turn: ExaminerTurnInput, question: str) -> tuple[str, list[str]]:
    if turn.part == 1:
        if turn.question_index == 0 and not starts_with_transition(question):
            return f"Let's talk about a familiar topic. {question}", ["exam", "part_1", "concise"]
        return question, ["exam", "part_1", "concise"]

    if turn.part == 2:
        if turn.question_index == 0:
            return (
                "Now I'm going to give you a topic. I'd like you to talk about it for one to two minutes. "
                f"{question}"
            ), ["exam", "part_2", "cue_card_intro"]
        return question, ["exam", "part_2", "concise"]

    if turn.question_index == 0:
        return f"We've been talking about this topic. {question}", ["exam", "part_3", "abstract_discussion"]
    return question, ["exam", "part_3", "abstract_discussion"]


def build_practice_text(turn: ExaminerTurnInput, question: str) -> tuple[str, list[str]]:
    if turn.part == 2 and turn.question_index == 0:
        return (
            "Let's practise a Part 2 long turn. Use the cue card and speak naturally. "
            f"{question}"
        ), ["practice", "part_2", "coaching_allowed"]
    if turn.question_index == 0:
        return f"Let's practise this part. {question}", ["practice", f"part_{turn.part}", "coaching_allowed"]
    return question, ["practice", f"part_{turn.part}", "concise"]


def starts_with_transition(text: str) -> bool:
    lowered = text.strip().lower()
    return lowered.startswith(("let's", "now", "we've", "i'd like", "describe", "do ", "what ", "why ", "how "))


def sanitize_examiner_text(text: str) -> str:
    cleaned = INTERNAL_TERM_RE.sub("exam instruction", text)
    return compact_text(cleaned)


def compact_text(text: str) -> str:
    return " ".join(text.strip().split())
