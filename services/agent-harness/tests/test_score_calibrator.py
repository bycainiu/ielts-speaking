from app.agents.score_calibrator import CalibrationAnchorSample, ScoreCalibrator, ScoreCalibratorInput
from app.mcp.report_mcp import CriterionScoreInput, ReportEvidence


def criterion(
    *,
    band: float = 6.5,
    confidence: float = 0.78,
    boundary: str,
) -> CriterionScoreInput:
    return CriterionScoreInput(
        band=band,
        confidence=confidence,
        evidence=[
            ReportEvidence(
                turn_id="turn_1",
                quote="WPM and pause evidence",
                reason="Dimension-specific evidence is available.",
            )
        ],
        suggestions=["Keep feedback specific."],
        raw_output={"dimension_boundary": boundary},
    )


def full_criteria(**overrides: CriterionScoreInput) -> dict[str, CriterionScoreInput]:
    criteria = {
        "fluency_coherence": criterion(boundary="fluency_coherence_only_no_grammar_penalty"),
        "lexical_resource": criterion(boundary="lexical_resource_only_no_fluency_penalty"),
        "grammatical_range_accuracy": criterion(boundary="grammar_range_accuracy_only_natural_spoken_rewrites"),
        "pronunciation": criterion(boundary="pronunciation_only_no_accent_penalty"),
    }
    criteria.update(overrides)
    return criteria


def test_score_calibrator_adjusts_toward_anchor_mean_with_reason() -> None:
    calibrator = ScoreCalibrator()
    result = calibrator.calibrate(
        ScoreCalibratorInput(
            session_id="session_001",
            criteria=full_criteria(
                pronunciation=criterion(
                    band=7.5,
                    confidence=0.82,
                    boundary="pronunciation_only_no_accent_penalty",
                )
            ),
            anchor_samples=[
                CalibrationAnchorSample(
                    anchor_sample_id="anchor_pronunciation_6",
                    criterion="pronunciation",
                    band=6.0,
                    score=0.92,
                    rationale="Similar intelligibility and prosody evidence.",
                ),
                CalibrationAnchorSample(
                    anchor_sample_id="anchor_pronunciation_6_5",
                    criterion="pronunciation",
                    band=6.5,
                    score=0.72,
                ),
            ],
        )
    )

    assert result.status == "calibrated"
    assert result.calibrated_criteria["pronunciation"].band == 7.0
    assert result.calibrated_criteria["pronunciation"].confidence == 0.78
    adjustment = next(item for item in result.adjustments if item.criterion == "pronunciation")
    assert adjustment.before_band == 7.5
    assert adjustment.after_band == 7.0
    assert adjustment.anchor_mean_band == 6.0
    assert adjustment.action == "adjusted"
    assert "下调" in adjustment.reason
    assert result.calibrated_criteria["pronunciation"].raw_output["calibration"]["before_band"] == 7.5
    assert result.calibrated_criteria["pronunciation"].raw_output["calibration"]["after_band"] == 7.0


def test_score_calibrator_keeps_score_when_deviation_is_within_threshold() -> None:
    calibrator = ScoreCalibrator()
    result = calibrator.calibrate(
        ScoreCalibratorInput(
            session_id="session_001",
            criteria=full_criteria(
                lexical_resource=criterion(
                    band=6.5,
                    confidence=0.76,
                    boundary="lexical_resource_only_no_fluency_penalty",
                )
            ),
            anchor_samples=[
                CalibrationAnchorSample(
                    anchor_sample_id="anchor_lexical_6",
                    criterion="lexical_resource",
                    band=6.0,
                    score=0.9,
                )
            ],
        )
    )

    lexical_adjustment = next(item for item in result.adjustments if item.criterion == "lexical_resource")
    assert result.status == "unchanged"
    assert lexical_adjustment.action == "unchanged"
    assert lexical_adjustment.deviation == 0.5
    assert result.calibrated_criteria["lexical_resource"].band == 6.5
    assert result.calibrated_criteria["lexical_resource"].raw_output["calibration"]["status"] == "unchanged"


def test_score_calibrator_reports_insufficient_anchors_without_changing_bands() -> None:
    calibrator = ScoreCalibrator()
    result = calibrator.calibrate(
        ScoreCalibratorInput(
            session_id="session_001",
            criteria=full_criteria(),
            anchor_samples=[
                CalibrationAnchorSample(
                    anchor_sample_id="low_similarity_anchor",
                    criterion="fluency_coherence",
                    band=5.0,
                    score=0.2,
                )
            ],
        )
    )

    assert result.status == "insufficient_anchors"
    assert all(item.action == "insufficient_anchors" for item in result.adjustments)
    assert result.calibrated_criteria["fluency_coherence"].band == 6.5
    assert result.raw_output["usable_anchor_count"] == 0


def test_score_calibrator_can_adjust_up_but_only_by_max_half_band() -> None:
    calibrator = ScoreCalibrator()
    result = calibrator.calibrate(
        ScoreCalibratorInput(
            session_id="session_001",
            criteria=full_criteria(
                fluency_coherence=criterion(
                    band=5.0,
                    confidence=0.7,
                    boundary="fluency_coherence_only_no_grammar_penalty",
                )
            ),
            anchor_samples=[
                CalibrationAnchorSample(
                    anchor_sample_id="anchor_fluency_7",
                    criterion="fluency_coherence",
                    band=7.0,
                    score=0.88,
                )
            ],
        )
    )

    adjustment = next(item for item in result.adjustments if item.criterion == "fluency_coherence")
    assert adjustment.action == "adjusted"
    assert adjustment.before_band == 5.0
    assert adjustment.after_band == 5.5
    assert "上调" in adjustment.reason
