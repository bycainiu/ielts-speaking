from __future__ import annotations

from typing import Any

from app.rules.fallback_plan import default_cue_card


PART2_WARNING_SECONDS = [60, 30, 10]


def cue_card_payload(question: dict[str, Any]) -> dict[str, Any]:
    cue_card = question.get("cue_card")
    if isinstance(cue_card, dict):
        return cue_card
    prompt = str(question.get("text") or question.get("topic") or "")
    return default_cue_card(prompt)


def part2_timer_policy(question: dict[str, Any]) -> dict[str, Any]:
    cue = cue_card_payload(question)
    preparation_seconds = int(cue.get("preparation_seconds") or 60)
    speaking_seconds = int(cue.get("speaking_seconds") or 120)
    return {
        "suggested_seconds": preparation_seconds,
        "preparation_seconds": preparation_seconds,
        "speaking_seconds": speaking_seconds,
        "warning_seconds": PART2_WARNING_SECONDS,
    }


def part_started_payload(*, part: int, part_plan: dict[str, Any] | None, question: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "part": part,
        "title": (part_plan or {}).get("title") or f"Part {part}",
        "timebox_seconds": int((part_plan or {}).get("timebox_seconds") or (300 if part in {1, 3} else 180)),
    }
    if part == 2:
        timer = part2_timer_policy(question)
        payload.update(
            {
                "preparation_seconds": timer["preparation_seconds"],
                "speaking_seconds": timer["speaking_seconds"],
                "warning_seconds": timer["warning_seconds"],
            }
        )
    if part == 3:
        if question.get("linked_part2_question_id"):
            payload["linked_part2_question_id"] = question["linked_part2_question_id"]
        if question.get("linked_part2_topic"):
            payload["linked_part2_topic"] = question["linked_part2_topic"]
    return payload


def timer_started_payload(*, part: int, question: dict[str, Any], suggested_seconds: int | None = None) -> dict[str, Any]:
    if part == 2:
        timer = part2_timer_policy(question)
        return {
            "part": part,
            "phase": "prepare_then_speak",
            "purpose": "preparation",
            "suggested_seconds": timer["preparation_seconds"],
            "preparation_seconds": timer["preparation_seconds"],
            "speaking_seconds": timer["speaking_seconds"],
            "warning_seconds": timer["warning_seconds"],
        }
    seconds = suggested_seconds
    if seconds is None:
        timer_policy = question.get("timer_policy") or {}
        seconds = int(timer_policy.get("suggested_seconds") or (30 if part == 1 else 45))
    return {
        "part": part,
        "suggested_seconds": seconds,
        "duration_seconds": seconds,
    }


def examiner_message_payload(
    *,
    part: int,
    question: dict[str, Any],
    examiner_text: str,
    source: str | None = None,
    is_followup: bool = False,
) -> dict[str, Any]:
    timer_policy = question.get("timer_policy") or {}
    suggested_seconds = int(timer_policy.get("suggested_seconds") or (30 if part == 1 else 120 if part == 2 else 45))
    payload: dict[str, Any] = {
        "part": part,
        "question_id": question.get("question_id"),
        "text": examiner_text,
        "timer_policy": {"suggested_seconds": suggested_seconds},
    }
    if source:
        payload["source"] = source
    if is_followup:
        payload["is_followup"] = True
    if question.get("topic"):
        payload["topic"] = question["topic"]
    if part == 2 and not is_followup:
        payload["cue_card"] = cue_card_payload(question)
        payload["timer_policy"] = part2_timer_policy(question)
    if part == 3:
        if question.get("linked_part2_question_id"):
            payload["linked_part2_question_id"] = question["linked_part2_question_id"]
        if question.get("linked_part2_topic"):
            payload["linked_part2_topic"] = question["linked_part2_topic"]
    return payload
