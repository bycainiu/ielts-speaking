from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


BandStyle = Literal["band_5", "band_6", "band_7"]

FORMAL_PHRASES = {
    "aforementioned",
    "henceforth",
    "in conclusion",
    "moreover",
    "therefore",
    "notwithstanding",
}


class ReferenceAnswerStyleProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    band_style: BandStyle
    min_words: int = Field(ge=1)
    max_words: int = Field(ge=1)
    skeleton_steps: list[str] = Field(min_length=1)
    lexical_target: str
    grammar_target: str


class ReferenceAnswerStyleReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    band_style: BandStyle
    word_count: int = Field(ge=0)
    findings: list[str] = Field(default_factory=list)


def style_profile_for_band(band_target: float | None) -> ReferenceAnswerStyleProfile:
    if band_target is not None and band_target >= 7:
        return ReferenceAnswerStyleProfile(
            band_style="band_7",
            min_words=70,
            max_words=150,
            skeleton_steps=["position", "reason", "specific_example", "balance_or_reflection"],
            lexical_target="natural topic collocations with limited paraphrase",
            grammar_target="clear complex sentences without written-style density",
        )
    if band_target is not None and band_target <= 5.5:
        return ReferenceAnswerStyleProfile(
            band_style="band_5",
            min_words=35,
            max_words=95,
            skeleton_steps=["direct_answer", "simple_reason", "short_example"],
            lexical_target="common words used accurately",
            grammar_target="mostly simple clauses with controlled linking",
        )
    return ReferenceAnswerStyleProfile(
        band_style="band_6",
        min_words=50,
        max_words=120,
        skeleton_steps=["direct_answer", "reason", "example", "extension"],
        lexical_target="topic words and a few natural collocations",
        grammar_target="mix of simple and some complex clauses",
    )


def validate_reference_answer_style(
    *,
    answer_text: str,
    skeleton: dict[str, object],
    band_target: float | None,
) -> ReferenceAnswerStyleReport:
    profile = style_profile_for_band(band_target)
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", answer_text)
    lowered = answer_text.lower()
    findings: list[str] = []

    if len(words) < profile.min_words:
        findings.append("too_short")
    if len(words) > profile.max_words:
        findings.append("too_long")
    if not skeleton:
        findings.append("missing_skeleton")
    if any(phrase in lowered for phrase in FORMAL_PHRASES):
        findings.append("overly_written_style")
    if "memorize" in lowered and "do not" not in lowered:
        findings.append("memorization_risk")

    return ReferenceAnswerStyleReport(
        passed=not findings,
        band_style=profile.band_style,
        word_count=len(words),
        findings=findings,
    )


def skeleton_for_part(part: int | None, band_target: float | None) -> dict[str, str]:
    profile = style_profile_for_band(band_target)
    if part == 2:
        labels = ["opening", "detail_1", "detail_2", "reflection"]
    elif part == 3:
        labels = ["position", "reason", "example", "balance"]
    else:
        labels = profile.skeleton_steps
    return {label: readable_step(label) for label in labels}


def readable_step(label: str) -> str:
    return label.replace("_", " ")
