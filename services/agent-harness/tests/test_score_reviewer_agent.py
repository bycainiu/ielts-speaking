from app.agents.score_reviewer_agent import ScoreReviewerAgent, ScoreReviewerInput
from app.mcp.report_mcp import CriterionScoreInput, ReportEvidence


def criterion(
    *,
    band: float = 6.0,
    confidence: float = 0.72,
    criterion_name: str,
    evidence_reason: str,
    evidence_count: int = 2,
    boundary: str | None = None,
) -> CriterionScoreInput:
    evidence = [
        ReportEvidence(
            turn_id=f"turn_{index}",
            quote=f"{criterion_name} evidence {index}",
            reason=evidence_reason,
        )
        for index in range(evidence_count)
    ]
    return CriterionScoreInput(
        band=band,
        confidence=confidence,
        evidence=evidence,
        suggestions=["Keep the advice focused and specific."],
        raw_output={"dimension_boundary": boundary or f"{criterion_name}_boundary"},
    )


def full_criteria(**overrides: CriterionScoreInput) -> dict[str, CriterionScoreInput]:
    criteria = {
        "fluency_coherence": criterion(
            criterion_name="fluency_coherence",
            evidence_reason="WPM and pause evidence shows fluency and coherence.",
        ),
        "lexical_resource": criterion(
            criterion_name="lexical_resource",
            evidence_reason="Vocabulary and replacement evidence shows lexical resource.",
        ),
        "grammatical_range_accuracy": criterion(
            criterion_name="grammar",
            evidence_reason="Grammar rewrite and sentence range evidence shows grammatical control.",
            boundary="grammar_range_accuracy_only_natural_spoken_rewrites",
        ),
        "pronunciation": criterion(
            criterion_name="pronunciation",
            evidence_reason="Pronunciation, prosody, ASR and rhythm evidence shows intelligibility.",
        ),
    }
    criteria.update(overrides)
    return criteria


def test_score_reviewer_requests_rescore_for_high_confidence_without_evidence() -> None:
    reviewer = ScoreReviewerAgent()
    result = reviewer.review(
        ScoreReviewerInput(
            session_id="session_001",
            criteria=full_criteria(
                pronunciation=criterion(
                    criterion_name="pronunciation",
                    evidence_reason="Pronunciation evidence.",
                    evidence_count=0,
                    confidence=0.86,
                )
            ),
        )
    )

    assert result.status == "needs_rescore"
    assert any(item.issue == "insufficient_evidence" for item in result.findings)
    assert any(item.action == "request_rescore" for item in result.findings)
    assert any("证据数量不足" in note for note in result.reviewer_notes)


def test_score_reviewer_requests_rescore_for_dimension_boundary_mismatch() -> None:
    reviewer = ScoreReviewerAgent()
    result = reviewer.review(
        ScoreReviewerInput(
            session_id="session_001",
            criteria=full_criteria(
                lexical_resource=criterion(
                    criterion_name="lexical_resource",
                    evidence_reason="Vocabulary evidence.",
                    boundary="fluency_coherence_only_no_grammar_penalty",
                )
            ),
        )
    )

    assert result.status == "needs_rescore"
    assert any(item.issue == "dimension_boundary_mismatch" for item in result.findings)
    assert any("重新评分" in note for note in result.reviewer_notes)


def test_score_reviewer_lowers_confidence_for_minimal_evidence() -> None:
    reviewer = ScoreReviewerAgent()
    result = reviewer.review(
        ScoreReviewerInput(
            session_id="session_001",
            criteria=full_criteria(
                fluency_coherence=criterion(
                    criterion_name="fluency_coherence",
                    evidence_reason="WPM and pause evidence.",
                    evidence_count=1,
                    confidence=0.84,
                )
            ),
        )
    )

    assert result.status == "accepted"
    assert result.reviewed_criteria["fluency_coherence"].confidence == 0.74
    assert any(item.issue == "high_confidence_with_minimal_evidence" for item in result.findings)


def test_score_reviewer_accepts_well_supported_criteria() -> None:
    reviewer = ScoreReviewerAgent()
    result = reviewer.review(
        ScoreReviewerInput(
            session_id="session_001",
            criteria=full_criteria(),
        )
    )

    assert result.status == "accepted"
    assert result.findings == []
    assert result.reviewer_notes == ["四维评分证据、置信度和维度边界通过自动复核。"]
    assert result.raw_output["finding_count"] == 0
