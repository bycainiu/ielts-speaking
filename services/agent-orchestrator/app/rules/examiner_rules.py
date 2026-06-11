from __future__ import annotations

from typing import Literal


def build_exam_text(*, part: int, question_index: int, question_text: str, practice_mode: bool) -> str:
    question = " ".join(question_text.strip().split())
    if practice_mode:
        if part == 2 and question_index == 0:
            return (
                "Let's practise a Part 2 long turn. Use the cue card and speak naturally. "
                f"{question}"
            )
        if question_index == 0:
            return f"Let's practise this part. {question}"
        return question

    if part == 1:
        if question_index == 0 and not _starts_with_transition(question):
            return f"Let's talk about a familiar topic. {question}"
        return question
    if part == 2:
        if question_index == 0:
            return (
                "Now I'm going to give you a topic. I'd like you to talk about it for one to two minutes. "
                f"{question}"
            )
        return question
    if question_index == 0:
        return f"We've been talking about this topic. {question}"
    return question


def suggest_followup_question(*, part: int) -> str:
    if part == 1:
        return "Could you tell me a little more about that?"
    if part == 2:
        return "Can you add one specific detail about why this experience was important to you?"
    return "Why do you think this matters to people more generally?"


def _starts_with_transition(text: str) -> bool:
    lowered = text.strip().lower()
    return lowered.startswith(("let's", "now", "we've", "i'd like", "describe", "do ", "what ", "why ", "how "))
