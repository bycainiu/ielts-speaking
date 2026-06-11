from __future__ import annotations

import re


_NUMBERING_RE = re.compile(r"^\d+[\.\):：、-]*\s*")
_LABEL_RE = re.compile(r"^(question|follow-?up(?: question)?|part \d+)\s*[:：-]\s*", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")

_PLACEHOLDER_EXACT = {
    "待补充",
    "待完善",
    "待填写",
    "待确认",
    "todo",
    "tbd",
    "placeholder",
    "to be added",
    "to be completed",
    "to be filled",
}
_PLACEHOLDER_PREFIX = ("待补充", "待完善", "todo", "tbd", "placeholder")


def normalize_question_text(value: str | None) -> str:
    if value is None:
        return ""
    text = _WHITESPACE_RE.sub(" ", str(value).strip())
    if not text:
        return ""

    text = text.strip("\"'`“”‘’《》「」『』()[]{}")
    text = _LABEL_RE.sub("", text)
    text = _NUMBERING_RE.sub("", text)
    text = text.strip("\"'`“”‘’《》「」『』()[]{}")
    text = text.rstrip(" .?!？！。,:：;；\"'`“”‘’")
    return _WHITESPACE_RE.sub(" ", text).strip().lower()


def is_placeholder_question_text(value: str | None) -> bool:
    normalized = normalize_question_text(value)
    if not normalized:
        return False
    if normalized in _PLACEHOLDER_EXACT:
        return True
    return any(
        normalized.startswith(f"{prefix}:") or normalized.startswith(f"{prefix} ")
        for prefix in _PLACEHOLDER_PREFIX
    )
