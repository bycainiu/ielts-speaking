from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.mcp.report_mcp import CriterionScoreInput
from app.rag.chunk_schema import ScoringCriterion


REQUIRED_CRITERIA: set[ScoringCriterion] = {
    "fluency_coherence",
    "lexical_resource",
    "grammatical_range_accuracy",
    "pronunciation",
}
EXPECTED_BOUNDARY_HINTS: dict[ScoringCriterion, str] = {
    "fluency_coherence": "fluency_coherence",
    "lexical_resource": "lexical_resource",
    "grammatical_range_accuracy": "grammar",
    "pronunciation": "pronunciation",
}
DIMENSION_TERMS: dict[ScoringCriterion, set[str]] = {
    "fluency_coherence": {"wpm", "pause", "停顿", "coherence", "连贯", "filler"},
    "lexical_resource": {"word", "vocabulary", "词汇", "表达", "topic vocabulary", "replacement"},
    "grammatical_range_accuracy": {"grammar", "tense", "subject", "语法", "句型", "rewrite"},
    "pronunciation": {"pronunciation", "prosody", "asr", "发音", "重音", "节奏", "可懂度"},
}


class ScoreReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: ScoringCriterion
    severity: Literal["info", "warning", "error"]
    issue: str = Field(min_length=1)
    action: Literal["accepted", "lower_confidence", "request_rescore"]
    suggested_confidence: float | None = Field(default=None, ge=0, le=1)
    reviewer_note: str = Field(min_length=1)


class ScoreReviewerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    criteria: dict[ScoringCriterion, CriterionScoreInput]
    min_evidence_count: int = Field(default=1, ge=1)
    high_confidence_threshold: float = Field(default=0.78, ge=0, le=1)

    @model_validator(mode="after")
    def validate_required_criteria(self) -> "ScoreReviewerInput":
        missing = REQUIRED_CRITERIA.difference(self.criteria)
        if missing:
            raise ValueError(f"criteria missing required items: {', '.join(sorted(missing))}")
        return self


class ScoreReviewerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "needs_rescore"]
    reviewed_criteria: dict[ScoringCriterion, CriterionScoreInput]
    findings: list[ScoreReviewFinding] = Field(default_factory=list)
    reviewer_notes: list[str] = Field(default_factory=list)
    raw_output: dict[str, Any] = Field(default_factory=dict)


class ScoreReviewerAgent:
    reviewer_version = "score_reviewer.v1"

    def review(self, reviewer_input: ScoreReviewerInput) -> ScoreReviewerOutput:
        reviewed_criteria = deepcopy(reviewer_input.criteria)
        findings: list[ScoreReviewFinding] = []

        for criterion, score in reviewer_input.criteria.items():
            findings.extend(review_evidence(criterion, score, reviewer_input))
            findings.extend(review_dimension_boundary(criterion, score))
            findings.extend(review_dimension_terms(criterion, score))

        for finding in findings:
            if finding.action == "lower_confidence" and finding.suggested_confidence is not None:
                current = reviewed_criteria[finding.criterion]
                reviewed_criteria[finding.criterion] = current.model_copy(
                    update={"confidence": min(current.confidence, finding.suggested_confidence)}
                )

        status = "needs_rescore" if any(item.action == "request_rescore" for item in findings) else "accepted"
        reviewer_notes = build_reviewer_notes(findings)
        if not reviewer_notes:
            reviewer_notes = ["四维评分证据、置信度和维度边界通过自动复核。"]

        return ScoreReviewerOutput(
            status=status,
            reviewed_criteria=reviewed_criteria,
            findings=findings,
            reviewer_notes=reviewer_notes,
            raw_output={
                "reviewer_version": self.reviewer_version,
                "finding_count": len(findings),
                "criteria_reviewed": sorted(reviewer_input.criteria),
                "rules": [
                    "evidence_sufficiency",
                    "high_confidence_with_weak_evidence",
                    "dimension_boundary_match",
                    "dimension_term_alignment",
                ],
            },
        )


def review_evidence(
    criterion: ScoringCriterion,
    score: CriterionScoreInput,
    reviewer_input: ScoreReviewerInput,
) -> list[ScoreReviewFinding]:
    findings: list[ScoreReviewFinding] = []
    if len(score.evidence) < reviewer_input.min_evidence_count:
        action: Literal["lower_confidence", "request_rescore"] = "lower_confidence"
        severity: Literal["warning", "error"] = "warning"
        suggested_confidence = min(score.confidence, 0.62)
        if score.confidence >= reviewer_input.high_confidence_threshold:
            action = "request_rescore"
            severity = "error"
        findings.append(
            ScoreReviewFinding(
                criterion=criterion,
                severity=severity,
                issue="insufficient_evidence",
                action=action,
                suggested_confidence=suggested_confidence,
                reviewer_note=f"{criterion} 证据数量不足，当前 evidence={len(score.evidence)}，不应维持过高置信度。",
            )
        )
    if score.confidence >= reviewer_input.high_confidence_threshold and len(score.evidence) == reviewer_input.min_evidence_count:
        findings.append(
            ScoreReviewFinding(
                criterion=criterion,
                severity="warning",
                issue="high_confidence_with_minimal_evidence",
                action="lower_confidence",
                suggested_confidence=0.74,
                reviewer_note=f"{criterion} 仅满足最低证据数量但 confidence={score.confidence}，建议保守降置信。",
            )
        )
    return findings


def review_dimension_boundary(
    criterion: ScoringCriterion,
    score: CriterionScoreInput,
) -> list[ScoreReviewFinding]:
    boundary = str(score.raw_output.get("dimension_boundary", "")).lower()
    expected = EXPECTED_BOUNDARY_HINTS[criterion]
    if not boundary:
        return [
            ScoreReviewFinding(
                criterion=criterion,
                severity="warning",
                issue="missing_dimension_boundary",
                action="lower_confidence",
                suggested_confidence=min(score.confidence, 0.68),
                reviewer_note=f"{criterion} 缺少 dimension_boundary，难以审计维度归因。",
            )
        ]
    if expected not in boundary:
        return [
            ScoreReviewFinding(
                criterion=criterion,
                severity="error",
                issue="dimension_boundary_mismatch",
                action="request_rescore",
                reviewer_note=f"{criterion} 的 dimension_boundary 与维度不匹配，需要重新评分。",
            )
        ]
    return []


def review_dimension_terms(
    criterion: ScoringCriterion,
    score: CriterionScoreInput,
) -> list[ScoreReviewFinding]:
    if not score.evidence:
        return []
    expected_terms = DIMENSION_TERMS[criterion]
    evidence_text = " ".join(f"{item.quote} {item.reason}" for item in score.evidence).lower()
    if any(term.lower() in evidence_text for term in expected_terms):
        return []
    return [
        ScoreReviewFinding(
            criterion=criterion,
            severity="warning",
            issue="weak_dimension_alignment",
            action="lower_confidence",
            suggested_confidence=min(score.confidence, 0.7),
            reviewer_note=f"{criterion} evidence 缺少清晰的本维度信号，建议降低 confidence 或补充证据。",
        )
    ]


def build_reviewer_notes(findings: list[ScoreReviewFinding]) -> list[str]:
    notes: list[str] = []
    for finding in findings:
        if finding.reviewer_note not in notes:
            notes.append(finding.reviewer_note)
    return notes[:8]
