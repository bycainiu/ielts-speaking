from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

import import_ieltsbro_pdf_question_bank as pdf_question_bank  # noqa: E402


def test_filter_followup_questions_skips_placeholder_text() -> None:
    followups = pdf_question_bank.filter_followup_questions(
        [
            "Why do some people enjoy travelling alone?",
            "待补充",
            "TODO: add one more follow-up",
        ]
    )

    assert followups == ["Why do some people enjoy travelling alone?"]
