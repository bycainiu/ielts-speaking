from __future__ import annotations

import re
from typing import Any

WORD_RE = re.compile(r"[a-z0-9']+", re.IGNORECASE)

IELTS_DISCLAIMER = "AI 模拟评分仅用于练习参考，不代表 IELTS 官方成绩。"

REQUIRED_CRITERIA = (
    "fluency_coherence",
    "lexical_resource",
    "grammatical_range_accuracy",
    "pronunciation",
)


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def analyze_response_quality(*, asr_text: str, part: int) -> dict[str, Any]:
    words = count_words(asr_text)
    return {
        "word_count": words,
        "part": part,
        "adequate_length": words >= 12,
        "very_short": words < 5,
        "needs_followup": 5 <= words < 20 and part in {1, 3},
    }


def build_interim_assessment(*, asr_text: str, part: int) -> dict[str, Any]:
    quality = analyze_response_quality(asr_text=asr_text, part=part)
    weak_areas: list[str] = []
    strong_areas: list[str] = []
    if quality["very_short"]:
        weak_areas.append("response_too_short")
    elif quality["adequate_length"]:
        strong_areas.append("adequate_length")
    if quality["needs_followup"]:
        weak_areas.append("needs_elaboration")
    return {
        "estimated_band": 6.0 if quality["adequate_length"] else 5.0,
        "fluency_indicators": {"word_count": float(quality["word_count"])},
        "weak_areas": weak_areas,
        "strong_areas": strong_areas,
        "turn_count": 1,
        "quality": quality,
    }


def _half_band(value: float) -> float:
    return round(value * 2) / 2


def _criterion_score(band: float, *, confidence: float = 0.72) -> dict[str, Any]:
    return {
        "band": _half_band(band),
        "confidence": round(confidence, 3),
        "evidence": [],
        "suggestions": [],
        "raw_output": {"source": "orchestrator.rules_scoring"},
    }


def build_score_report(answers: list[dict[str, Any]]) -> dict[str, Any]:
    total_words = sum(count_words(str(item.get("asr_text") or "")) for item in answers)
    avg_words = total_words / max(1, len(answers))
    base = 5.5 if avg_words < 15 else 6.0 if avg_words < 40 else 6.5
    criteria = {key: _criterion_score(base) for key in REQUIRED_CRITERIA}
    overall_band = _half_band(sum(item["band"] for item in criteria.values()) / len(criteria))
    confidence = round(sum(item["confidence"] for item in criteria.values()) / len(criteria), 3)
    return {
        "overall_band": overall_band,
        "confidence": confidence,
        "criteria": criteria,
        "source": "rules_scoring",
        "disclaimer": IELTS_DISCLAIMER,
        "version": 1,
        "status": "ready",
        "answer_count": len(answers),
        "avg_words": round(avg_words, 1),
        "reviewer_notes": [],
        "next_practice_plan": [],
        "raw_report": {
            "source": "orchestrator.rules_scoring",
            "answer_count": len(answers),
            "avg_words": round(avg_words, 1),
        },
    }
