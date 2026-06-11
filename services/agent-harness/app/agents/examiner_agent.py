from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.protocols.schemas import SessionMode

if TYPE_CHECKING:
    from app.models.llm_gateway import LlmGateway


logger = logging.getLogger("agent_harness.examiner_agent")

INTERNAL_TERM_RE = re.compile(
    r"\b(system prompt|developer message|rubric|band descriptor|scoring rule|hidden instruction|password|api key|secret|private tools?)\b",
    re.IGNORECASE,
)

EXAMINER_LLM_PROMPT_VERSION = "examiner_turn.llm.v1"
MAX_UTTERANCE_CHARS = 520


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
    reasoning_text: str | None = None
    generated_by: Literal["rules", "llm"] = "rules"


class ExaminerAgent:
    """考官话术 Agent：优先调用真实 LLM 生成口语化考官台词，失败时降级到确定性脚本。"""

    def __init__(self, llm_gateway: "LlmGateway | None" = None) -> None:
        self.llm_gateway = llm_gateway

    def build_turn(self, turn: ExaminerTurnInput) -> ExaminerUtterance:
        question = sanitize_examiner_text(turn.question_text)
        if turn.mode == "full_exam":
            text, style_tags = build_exam_text(turn, question)
        else:
            text, style_tags = build_practice_text(turn, question)

        llm_utterance = self._build_llm_turn(turn, question, style_tags)
        if llm_utterance is not None:
            return llm_utterance

        return ExaminerUtterance(
            part=turn.part,
            question_id=turn.question_id,
            text=compact_text(text),
            style_tags=style_tags,
            practice_mode=turn.practice_mode,
        )

    def _build_llm_turn(
        self,
        turn: ExaminerTurnInput,
        question: str,
        style_tags: list[str],
    ) -> ExaminerUtterance | None:
        gateway = self.llm_gateway
        if gateway is None or not gateway.enabled:
            return None
        result = gateway.generate_text(
            task="examiner",
            call_name="examiner_turn",
            agent_name="ExaminerAgent",
            prompt_version=EXAMINER_LLM_PROMPT_VERSION,
            messages=build_examiner_llm_messages(turn, question),
            temperature=0.4,
            # mimo-v2.5-pro 是推理模型，thinking 与正文共享 max_tokens 预算，
            # 给足余量避免正文被截断为空（finish_reason=length）。
            max_tokens=600,
        )
        if result is None:
            return None
        text = compact_text(sanitize_examiner_text(result.text))
        if not text or len(text) > MAX_UTTERANCE_CHARS:
            logger.warning(
                "examiner_llm_output_rejected",
                extra={"question_id": turn.question_id, "length": len(text)},
            )
            return None
        return ExaminerUtterance(
            part=turn.part,
            question_id=turn.question_id,
            text=text,
            style_tags=[*style_tags, "llm_generated"],
            practice_mode=turn.practice_mode,
            reasoning_text=result.reasoning_text,
            generated_by="llm",
        )


def build_examiner_llm_messages(turn: ExaminerTurnInput, question: str) -> list[dict[str, str]]:
    part_guidance = {
        1: "Part 1 is a short interview about familiar topics. Keep the turn to one or two short sentences.",
        2: (
            "Part 2 is the individual long turn. If this is the first question of the part, briefly introduce the cue card "
            "task (talk for one to two minutes) before stating the topic."
        ),
        3: "Part 3 is an abstract two-way discussion. Sound analytical and connect to broader social themes.",
    }
    mode_guidance = (
        "This is practice mode: you may sound slightly more encouraging, but stay in character as an examiner."
        if turn.practice_mode or turn.mode != "full_exam"
        else "This is a strict mock exam: stay neutral and concise, never coach the candidate."
    )
    system = (
        "You are a certified IELTS Speaking examiner conducting a live speaking test. "
        "Speak exactly one examiner turn. "
        "Rules: keep the meaning of the given question unchanged; do not answer the question yourself; "
        "do not add scoring commentary, hints, or meta remarks; do not mention these instructions; "
        "output only the words the examiner says, with no quotes or markdown. "
        f"{part_guidance[turn.part]} {mode_guidance}"
    )
    user = (
        f"Part: {turn.part}\n"
        f"Question {turn.question_index + 1} of {turn.total_questions}.\n"
        f"Question to ask: {question}\n"
        "Produce the examiner's spoken turn now."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


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
