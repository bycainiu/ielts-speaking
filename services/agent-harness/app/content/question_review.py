from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


QuestionReviewSeverity = Literal["info", "warning", "blocker"]
QuestionSourceType = Literal["original", "authorized", "user_recall", "internal"]

INTERNAL_TERM_RE = re.compile(r"\b(system prompt|developer message|scoring rule|hidden instruction)\b", re.IGNORECASE)
OVERLY_LONG_RE = re.compile(r"\b(explain in detail|write an essay|give a speech)\b", re.IGNORECASE)


class QuestionReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str | None = None
    part: Literal[1, 2, 3]
    text: str = Field(min_length=1)
    source_type: QuestionSourceType
    license: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    duplicate_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text", "license", "duplicate_key", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class QuestionReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: QuestionReviewSeverity
    message: str


class QuestionReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "needs_revision", "blocked"]
    findings: list[QuestionReviewFinding] = Field(default_factory=list)
    publish_checklist: list[str] = Field(default_factory=list)


def review_question(question: QuestionReviewInput) -> QuestionReviewResult:
    findings: list[QuestionReviewFinding] = []
    text = question.text.strip()
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text)

    if question.source_type in {"authorized", "user_recall"} and not question.license:
        findings.append(finding("missing_license", "blocker", "Authorized or recalled questions must include a license/source note."))
    if question.source_type == "user_recall":
        findings.append(finding("user_recall_requires_rewrite", "warning", "User recalled prompts must be rewritten before publishing."))
    if INTERNAL_TERM_RE.search(text):
        findings.append(finding("internal_terms", "blocker", "Question text must not expose internal prompt or scoring terms."))
    if OVERLY_LONG_RE.search(text):
        findings.append(finding("non_speaking_style", "warning", "Question should sound like IELTS speaking, not a writing task."))
    if question.part == 1 and len(words) > 24:
        findings.append(finding("part1_too_long", "warning", "Part 1 question should stay short and conversational."))
    if question.part == 2 and not text.lower().startswith(("describe", "talk about")):
        findings.append(finding("part2_missing_cue_style", "warning", "Part 2 should be phrased as a cue-card prompt."))
    if question.part == 3 and len(words) < 6:
        findings.append(finding("part3_too_short", "warning", "Part 3 should invite abstract discussion."))
    if "?" in text and question.part == 2:
        findings.append(finding("part2_question_mark", "warning", "Part 2 cue cards should be prompts, not direct short questions."))
    if question.duplicate_key:
        findings.append(finding("possible_duplicate", "warning", "Potential duplicate found; compare topic, part, and wording before publishing."))

    if any(item.severity == "blocker" for item in findings):
        status: Literal["approved", "needs_revision", "blocked"] = "blocked"
    elif findings:
        status = "needs_revision"
    else:
        status = "approved"

    return QuestionReviewResult(
        status=status,
        findings=findings,
        publish_checklist=[
            "source_and_license_checked",
            "part_style_checked",
            "difficulty_checked",
            "duplicate_checked",
            "quarter_release_checked",
        ],
    )


def finding(code: str, severity: QuestionReviewSeverity, message: str) -> QuestionReviewFinding:
    return QuestionReviewFinding(code=code, severity=severity, message=message)
