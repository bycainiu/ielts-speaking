from __future__ import annotations

from app.protocols.agent_message import ExamConstraints, SessionContext


class ExamConstraintViolation(ValueError):
    pass


def validate_question_plan(context: SessionContext, question_plan: dict) -> None:
    constraints = context.exam_constraints
    parts = question_plan.get("parts") or []
    for entry in parts:
        part = int(entry.get("part") or 0)
        questions = entry.get("questions") or []
        max_count = constraints.max_questions_per_part.get(part)
        if max_count is not None and len(questions) > max_count:
            raise ExamConstraintViolation(f"part {part} exceeds max questions ({max_count})")


def validate_followup(context: SessionContext, followup_count: int) -> None:
    if followup_count > context.exam_constraints.max_followups_per_question:
        raise ExamConstraintViolation("followup limit exceeded")


def default_constraints() -> ExamConstraints:
    return ExamConstraints()
