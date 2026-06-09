from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.mcp.report_mcp import CriterionScoreInput
from app.rag.chunk_schema import ScoringCriterion


REQUIRED_CRITERIA: set[ScoringCriterion] = {
    "fluency_coherence",
    "lexical_resource",
    "grammatical_range_accuracy",
    "pronunciation",
}


class CalibrationAnchorSample(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    anchor_sample_id: str = Field(min_length=1)
    criterion: ScoringCriterion
    band: float = Field(ge=0, le=9)
    score: float = Field(default=1.0, ge=0, le=1)
    rationale: str | None = None
    content: str | None = None

    @field_validator("band", mode="before")
    @classmethod
    def normalize_band(cls, value: Any) -> float:
        numeric = float(value)
        if numeric * 2 != int(numeric * 2):
            raise ValueError("band must be in 0.5 increments")
        return numeric

    @field_validator("anchor_sample_id", mode="before")
    @classmethod
    def normalize_anchor_id(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("anchor_sample_id is required")
        return text

    @field_validator("content", "rationale", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class ScoreCalibratorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    criteria: dict[ScoringCriterion, CriterionScoreInput]
    anchor_samples: list[CalibrationAnchorSample] = Field(default_factory=list)
    min_similarity: float = Field(default=0.35, ge=0, le=1)
    adjustment_threshold: float = Field(default=0.75, ge=0.5, le=2.0)
    max_adjustment: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode="after")
    def validate_required_criteria(self) -> "ScoreCalibratorInput":
        missing = REQUIRED_CRITERIA.difference(self.criteria)
        if missing:
            raise ValueError(f"criteria missing required items: {', '.join(sorted(missing))}")
        if self.max_adjustment * 2 != int(self.max_adjustment * 2):
            raise ValueError("max_adjustment must be in 0.5 increments")
        return self


class ScoreCalibrationAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: ScoringCriterion
    before_band: float = Field(ge=0, le=9)
    after_band: float = Field(ge=0, le=9)
    anchor_mean_band: float = Field(ge=0, le=9)
    deviation: float
    action: Literal["unchanged", "adjusted", "insufficient_anchors"]
    reason: str = Field(min_length=1)
    anchor_sample_ids: list[str] = Field(default_factory=list)


class ScoreCalibratorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["calibrated", "unchanged", "insufficient_anchors"]
    calibrated_criteria: dict[ScoringCriterion, CriterionScoreInput]
    adjustments: list[ScoreCalibrationAdjustment] = Field(default_factory=list)
    raw_output: dict[str, Any] = Field(default_factory=dict)


class ScoreCalibrator:
    calibrator_version = "score_calibrator.v1"

    def calibrate(self, calibrator_input: ScoreCalibratorInput) -> ScoreCalibratorOutput:
        calibrated_criteria = deepcopy(calibrator_input.criteria)
        anchors_by_criterion = group_anchors(
            calibrator_input.anchor_samples,
            min_similarity=calibrator_input.min_similarity,
        )
        adjustments: list[ScoreCalibrationAdjustment] = []

        for criterion in sorted(REQUIRED_CRITERIA):
            score = calibrator_input.criteria[criterion]
            anchors = anchors_by_criterion.get(criterion, [])
            adjustment = calibrate_criterion(
                criterion,
                score,
                anchors,
                threshold=calibrator_input.adjustment_threshold,
                max_adjustment=calibrator_input.max_adjustment,
            )
            adjustments.append(adjustment)
            if adjustment.action == "adjusted":
                calibrated_criteria[criterion] = apply_adjustment(score, adjustment)
            else:
                calibrated_criteria[criterion] = annotate_unchanged(score, adjustment)

        status: Literal["calibrated", "unchanged", "insufficient_anchors"]
        if any(item.action == "adjusted" for item in adjustments):
            status = "calibrated"
        elif all(item.action == "insufficient_anchors" for item in adjustments):
            status = "insufficient_anchors"
        else:
            status = "unchanged"

        return ScoreCalibratorOutput(
            status=status,
            calibrated_criteria=calibrated_criteria,
            adjustments=adjustments,
            raw_output={
                "calibrator_version": self.calibrator_version,
                "session_id": calibrator_input.session_id,
                "anchor_count": len(calibrator_input.anchor_samples),
                "usable_anchor_count": sum(len(items) for items in anchors_by_criterion.values()),
                "min_similarity": calibrator_input.min_similarity,
                "adjustment_threshold": calibrator_input.adjustment_threshold,
                "max_adjustment": calibrator_input.max_adjustment,
            },
        )


def group_anchors(
    anchors: list[CalibrationAnchorSample],
    *,
    min_similarity: float,
) -> dict[ScoringCriterion, list[CalibrationAnchorSample]]:
    grouped: dict[ScoringCriterion, list[CalibrationAnchorSample]] = {}
    for anchor in anchors:
        if anchor.score < min_similarity:
            continue
        grouped.setdefault(anchor.criterion, []).append(anchor)
    return grouped


def calibrate_criterion(
    criterion: ScoringCriterion,
    score: CriterionScoreInput,
    anchors: list[CalibrationAnchorSample],
    *,
    threshold: float,
    max_adjustment: float,
) -> ScoreCalibrationAdjustment:
    if not anchors:
        return ScoreCalibrationAdjustment(
            criterion=criterion,
            before_band=score.band,
            after_band=score.band,
            anchor_mean_band=score.band,
            deviation=0.0,
            action="insufficient_anchors",
            reason=f"{criterion} 没有达到相似度阈值的 anchor sample，保留复核后分数。",
            anchor_sample_ids=[],
        )

    anchor_mean = weighted_anchor_band(anchors)
    deviation = round(score.band - anchor_mean, 3)
    if abs(deviation) < threshold or max_adjustment == 0:
        return ScoreCalibrationAdjustment(
            criterion=criterion,
            before_band=score.band,
            after_band=score.band,
            anchor_mean_band=anchor_mean,
            deviation=deviation,
            action="unchanged",
            reason=f"{criterion} 与相似 anchor 均值偏差 {abs(deviation):.1f}，低于校准阈值，保留原分。",
            anchor_sample_ids=[anchor.anchor_sample_id for anchor in anchors],
        )

    direction = -1 if deviation > 0 else 1
    adjustment_size = min(max_adjustment, round_down_half_step(abs(deviation)))
    if adjustment_size <= 0:
        adjustment_size = min(max_adjustment, 0.5)
    after_band = clamp_half_band(score.band + direction * adjustment_size)
    trend = "下调" if after_band < score.band else "上调"
    return ScoreCalibrationAdjustment(
        criterion=criterion,
        before_band=score.band,
        after_band=after_band,
        anchor_mean_band=anchor_mean,
        deviation=deviation,
        action="adjusted",
        reason=f"{criterion} 与相似 anchor 均值偏差 {abs(deviation):.1f}，按保守策略{trend} {abs(after_band - score.band):.1f} band。",
        anchor_sample_ids=[anchor.anchor_sample_id for anchor in anchors],
    )


def apply_adjustment(score: CriterionScoreInput, adjustment: ScoreCalibrationAdjustment) -> CriterionScoreInput:
    raw_output = dict(score.raw_output)
    raw_output["calibration"] = {
        "status": adjustment.action,
        "before_band": adjustment.before_band,
        "after_band": adjustment.after_band,
        "anchor_mean_band": adjustment.anchor_mean_band,
        "deviation": adjustment.deviation,
        "reason": adjustment.reason,
        "anchor_sample_ids": adjustment.anchor_sample_ids,
    }
    confidence = max(0.35, round(score.confidence - 0.04, 3))
    return score.model_copy(update={"band": adjustment.after_band, "confidence": confidence, "raw_output": raw_output})


def annotate_unchanged(score: CriterionScoreInput, adjustment: ScoreCalibrationAdjustment) -> CriterionScoreInput:
    raw_output = dict(score.raw_output)
    raw_output["calibration"] = {
        "status": adjustment.action,
        "before_band": adjustment.before_band,
        "after_band": adjustment.after_band,
        "anchor_mean_band": adjustment.anchor_mean_band,
        "deviation": adjustment.deviation,
        "reason": adjustment.reason,
        "anchor_sample_ids": adjustment.anchor_sample_ids,
    }
    return score.model_copy(update={"raw_output": raw_output})


def weighted_anchor_band(anchors: list[CalibrationAnchorSample]) -> float:
    total_weight = sum(max(anchor.score, 0.01) for anchor in anchors)
    weighted_sum = sum(anchor.band * max(anchor.score, 0.01) for anchor in anchors)
    return clamp_half_band(weighted_sum / total_weight)


def round_down_half_step(value: float) -> float:
    return int(value * 2) / 2


def clamp_half_band(value: float) -> float:
    rounded = round(value * 2) / 2
    return max(0.0, min(9.0, rounded))
