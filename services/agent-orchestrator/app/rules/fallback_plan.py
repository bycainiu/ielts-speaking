from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.protocols.schemas import PlanRequest, SessionMode


PART_TIMER_SECONDS = {1: 30, 2: 120, 3: 45}
PART_TIMEBOX_SECONDS = {1: 300, 2: 180, 3: 300}
DEFAULT_PART_COUNTS = {1: 4, 2: 1, 3: 2}

FALLBACK_CATALOG: dict[int, list[dict[str, str]]] = {
    1: [
        {"topic": "hometown", "text": "Let's talk about your hometown. Where is your hometown?"},
        {"topic": "hometown", "text": "What do you like most about your hometown?"},
        {"topic": "work_or_study", "text": "Do you work or are you a student?"},
        {"topic": "daily_routine", "text": "What do you usually do after work or study?"},
    ],
    2: [
        {"topic": "place", "text": "Describe a place in your city that you enjoy visiting."},
    ],
    3: [
        {"topic": "city_life", "text": "Why do some people prefer living in big cities?"},
        {"topic": "city_life", "text": "How can cities become more comfortable for young people?"},
    ],
}


class PlannedQuestionDict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    part: int = Field(ge=1, le=3)
    text: str
    topic: str | None = None
    timer_policy: dict[str, int]
    cue_card: dict[str, Any] | None = None


def target_parts_for_mode(mode: SessionMode, part: int | None) -> list[int]:
    if mode == "part_practice":
        return [part or 1]
    if mode == "topic_practice":
        return [1, 2, 3]
    return [1, 2, 3]


def default_cue_card(prompt: str) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "bullet_points": [
            "what it is",
            "when or where it happened",
            "who was involved",
            "why it was important to you",
        ],
        "preparation_seconds": 60,
        "speaking_seconds": PART_TIMER_SECONDS[2],
    }


def build_fallback_question_plan(request: PlanRequest) -> dict[str, Any]:
    target_parts = target_parts_for_mode(request.mode, request.part)
    parts: list[dict[str, Any]] = []
    part2_context: dict[str, str] | None = None

    for part in target_parts:
        count = DEFAULT_PART_COUNTS.get(part, 1)
        catalog = FALLBACK_CATALOG.get(part, [])
        selected = catalog[:count]
        questions: list[dict[str, Any]] = []
        for index, item in enumerate(selected):
            text = item["text"]
            question_id = f"planner_fallback_p{part}_q{index + 1}"
            entry: dict[str, Any] = {
                "question_id": question_id,
                "part": part,
                "text": text,
                "topic": item.get("topic"),
                "timer_policy": {"suggested_seconds": PART_TIMER_SECONDS[part]},
                "evidence": {"source": "fallback_catalog"},
            }
            if part == 2:
                entry["cue_card"] = default_cue_card(text)
                part2_context = {"question_id": question_id, "topic": item.get("topic") or "place", "prompt": text}
            if part == 3 and part2_context:
                entry["linked_part2_question_id"] = part2_context["question_id"]
                entry["linked_part2_topic"] = part2_context["topic"]
            questions.append(entry)

        parts.append(
            {
                "part": part,
                "title": f"Part {part}",
                "suggested_seconds": PART_TIMER_SECONDS[part] * max(1, len(questions)),
                "timebox_seconds": PART_TIMEBOX_SECONDS[part],
                "questions": questions,
            }
        )

    return {
        "planner_version": "orchestrator.fallback.v1",
        "mode": request.mode,
        "user_id": request.user_id,
        "target_parts": target_parts,
        "parts": parts,
        "fallback_used": True,
        "source": "rules_fallback",
        "rationale": ["Used deterministic fallback catalog aligned with agent-harness."],
    }
