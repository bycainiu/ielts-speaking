from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evals.common import EvalCaseResult, EvalSuiteReport, build_suite_report


SpeechSampleSource = Literal["speechocean762", "authorized_internal", "synthetic_contract"]
AccentGroup = Literal["east_asian", "south_asian", "european", "middle_eastern", "latin_american", "mixed", "other"]
RecordingQuality = Literal["good", "fair", "poor"]
CalibrationSplit = Literal["calibration", "regression", "holdout"]
AudioQualityLabel = Literal["usable", "unknown", "low_quality"]


class SpeechCalibrationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gopt_sentence_score: float = Field(ge=0, le=1)
    gopt_accuracy: float | None = Field(default=None, ge=0, le=1)
    gopt_fluency: float | None = Field(default=None, ge=0, le=1)
    gopt_prosody: float | None = Field(default=None, ge=0, le=1)
    wpm: float = Field(ge=0)
    silence_ratio: float = Field(ge=0, le=1)
    long_pause_count: int = Field(ge=0)
    filler_ratio: float = Field(default=0, ge=0, le=1)
    audio_quality_label: AudioQualityLabel = "usable"
    confidence: float = Field(ge=0, le=1)


class SpeechCalibrationSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1)
    source: SpeechSampleSource
    audio_asset_id: str = Field(min_length=1)
    transcript: str = Field(min_length=1)
    part: Literal[1, 2, 3]
    accent_group: AccentGroup
    recording_quality: RecordingQuality
    human_pronunciation_band: float = Field(ge=0, le=9)
    human_fluency_band: float = Field(ge=0, le=9)
    source_license_id: str | None = None
    consent_record_id: str | None = None
    annotation_protocol_version: str = Field(min_length=1)
    annotator_count: int = Field(ge=1)
    split: CalibrationSplit = "regression"
    evidence: SpeechCalibrationEvidence
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_authorization(self) -> "SpeechCalibrationSample":
        if self.source == "speechocean762":
            if not (self.source_license_id or "").startswith("speechocean762:"):
                raise ValueError("speechocean762 samples require source_license_id prefixed with speechocean762:")
        if self.source == "authorized_internal":
            if not self.consent_record_id:
                raise ValueError("authorized_internal samples require consent_record_id")
            if self.annotator_count < 2:
                raise ValueError("authorized_internal samples require at least two annotators")
        if self.source == "synthetic_contract" and self.metadata.get("synthetic_contract") is not True:
            raise ValueError("synthetic_contract samples must set metadata.synthetic_contract=true")
        return self


class SpeechCalibrationDatasetAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_count: int = Field(ge=0)
    production_sample_count: int = Field(ge=0)
    synthetic_sample_count: int = Field(ge=0)
    authorization_passed: bool
    coverage_passed: bool
    regression_ready: bool
    passed: bool
    covered_band_buckets: list[float]
    covered_parts: list[int]
    covered_accent_groups: list[str]
    covered_recording_qualities: list[str]
    source_counts: dict[str, int]
    issues: list[str] = Field(default_factory=list)


class SpeechCalibrationRegressionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit: SpeechCalibrationDatasetAudit
    eval_report: EvalSuiteReport
    mean_absolute_error: float = Field(ge=0)
    max_absolute_error: float = Field(ge=0)
    model_version: str
    calibration_note: str

    def to_markdown(self) -> str:
        status = "PASS" if self.audit.passed and not self.eval_report.block_release else "FAIL"
        lines = [
            "# Speech Calibration Regression",
            "",
            f"- status: {status}",
            f"- model_version: {self.model_version}",
            f"- sample_count: {self.audit.sample_count}",
            f"- production_sample_count: {self.audit.production_sample_count}",
            f"- synthetic_sample_count: {self.audit.synthetic_sample_count}",
            f"- mean_absolute_error: {self.mean_absolute_error:.3f}",
            f"- max_absolute_error: {self.max_absolute_error:.3f}",
            f"- block_release: {str(self.eval_report.block_release).lower()}",
            f"- calibration_note: {self.calibration_note}",
            "",
            "## Dataset Audit",
            "",
            f"- authorization_passed: {str(self.audit.authorization_passed).lower()}",
            f"- coverage_passed: {str(self.audit.coverage_passed).lower()}",
            f"- regression_ready: {str(self.audit.regression_ready).lower()}",
            f"- covered_band_buckets: {', '.join(str(item) for item in self.audit.covered_band_buckets)}",
            f"- covered_parts: {', '.join(str(item) for item in self.audit.covered_parts)}",
            f"- covered_accent_groups: {', '.join(self.audit.covered_accent_groups)}",
            f"- covered_recording_qualities: {', '.join(self.audit.covered_recording_qualities)}",
        ]
        if self.audit.issues:
            lines.extend(["", "## Issues"])
            lines.extend(f"- {issue}" for issue in self.audit.issues)
        lines.extend(["", self.eval_report.to_markdown()])
        return "\n".join(lines)


def load_speech_calibration_manifest(path: str | Path) -> list[SpeechCalibrationSample]:
    samples: list[SpeechCalibrationSample] = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
        samples.append(SpeechCalibrationSample.model_validate(payload))
    return samples


def audit_speech_calibration_dataset(
    samples: list[SpeechCalibrationSample],
    *,
    allow_synthetic_contract: bool = False,
    min_production_samples: int = 200,
) -> SpeechCalibrationDatasetAudit:
    source_counts = Counter(sample.source for sample in samples)
    production_samples = [sample for sample in samples if sample.source != "synthetic_contract"]
    issues: list[str] = []
    if len(production_samples) < min_production_samples:
        issues.append(f"production_sample_count_below_{min_production_samples}")
    if source_counts.get("synthetic_contract", 0) and not allow_synthetic_contract:
        issues.append("synthetic_contract_samples_not_allowed_for_production_gate")
    if not any(sample.source == "speechocean762" for sample in production_samples) and min_production_samples > 0:
        issues.append("missing_speechocean762_source")
    if not any(sample.source == "authorized_internal" for sample in production_samples) and min_production_samples > 0:
        issues.append("missing_authorized_internal_source")

    covered_band_buckets = sorted({band_bucket(sample.human_pronunciation_band) for sample in samples})
    covered_parts = sorted({sample.part for sample in samples})
    covered_accent_groups = sorted({sample.accent_group for sample in samples})
    covered_recording_qualities = sorted({sample.recording_quality for sample in samples})
    if len(covered_band_buckets) < 5:
        issues.append("band_coverage_requires_at_least_5_buckets")
    if set(covered_parts) != {1, 2, 3}:
        issues.append("part_coverage_requires_1_2_3")
    if len(covered_accent_groups) < 4:
        issues.append("accent_coverage_requires_at_least_4_groups")
    if set(covered_recording_qualities) != {"fair", "good", "poor"}:
        issues.append("recording_quality_coverage_requires_good_fair_poor")

    authorization_passed = not any(issue.startswith("missing_") for issue in issues)
    coverage_passed = not any("coverage" in issue for issue in issues)
    regression_ready = bool(samples) and coverage_passed and (allow_synthetic_contract or len(production_samples) >= min_production_samples)
    passed = not issues
    return SpeechCalibrationDatasetAudit(
        sample_count=len(samples),
        production_sample_count=len(production_samples),
        synthetic_sample_count=source_counts.get("synthetic_contract", 0),
        authorization_passed=authorization_passed,
        coverage_passed=coverage_passed,
        regression_ready=regression_ready,
        passed=passed,
        covered_band_buckets=covered_band_buckets,
        covered_parts=covered_parts,
        covered_accent_groups=covered_accent_groups,
        covered_recording_qualities=covered_recording_qualities,
        source_counts=dict(sorted(source_counts.items())),
        issues=issues,
    )


class SpeechCalibrationRegressionRunner:
    def __init__(
        self,
        *,
        model_version: str = "speech-evidence-calibration-v0",
        max_case_absolute_error: float = 1.0,
        max_mean_absolute_error: float = 0.75,
    ) -> None:
        self.model_version = model_version
        self.max_case_absolute_error = max_case_absolute_error
        self.max_mean_absolute_error = max_mean_absolute_error

    def run(
        self,
        samples: list[SpeechCalibrationSample],
        *,
        allow_synthetic_contract: bool = False,
        min_production_samples: int = 200,
    ) -> SpeechCalibrationRegressionReport:
        audit = audit_speech_calibration_dataset(
            samples,
            allow_synthetic_contract=allow_synthetic_contract,
            min_production_samples=min_production_samples,
        )
        results = [self.evaluate(sample) for sample in samples]
        if not audit.passed:
            results.append(
                EvalCaseResult(
                    case_id="dataset_audit",
                    category="speech_calibration_dataset",
                    passed=False,
                    score=0,
                    reason=", ".join(audit.issues),
                    severity="critical",
                    metadata={"audit": audit.model_dump()},
                )
            )
        eval_report = build_suite_report(
            suite_name="speech_calibration_regression",
            results=results,
            threshold=0.95,
        )
        errors = [abs(result.metadata["absolute_error"]) for result in results if "absolute_error" in result.metadata]
        mae = round(sum(errors) / len(errors), 3) if errors else 0.0
        max_error = round(max(errors), 3) if errors else 0.0
        return SpeechCalibrationRegressionReport(
            audit=audit,
            eval_report=eval_report,
            mean_absolute_error=mae,
            max_absolute_error=max_error,
            model_version=self.model_version,
            calibration_note=(
                "This runner evaluates internal speech evidence calibration only; "
                "it must not publish direct IELTS band output from speech models."
            ),
        )

    def evaluate(self, sample: SpeechCalibrationSample) -> EvalCaseResult:
        predicted = estimate_internal_pronunciation_band(sample.evidence)
        absolute_error = round(abs(predicted - sample.human_pronunciation_band), 3)
        passed = absolute_error <= self.max_case_absolute_error
        return EvalCaseResult(
            case_id=sample.sample_id,
            category="speech_calibration_regression",
            passed=passed,
            score=round(max(0.0, 1.0 - (absolute_error / 3.0)), 3),
            reason=f"predicted={predicted:.1f} human={sample.human_pronunciation_band:.1f} abs_error={absolute_error:.1f}",
            severity="high" if absolute_error > self.max_case_absolute_error else "medium",
            metadata={
                "predicted_internal_band": predicted,
                "human_pronunciation_band": sample.human_pronunciation_band,
                "absolute_error": absolute_error,
                "part": sample.part,
                "accent_group": sample.accent_group,
                "recording_quality": sample.recording_quality,
                "confidence": sample.evidence.confidence,
                "transcript_excerpt": sample.transcript[:180],
                "source": sample.source,
                "split": sample.split,
            },
        )


def estimate_internal_pronunciation_band(evidence: SpeechCalibrationEvidence) -> float:
    base = 3.2 + evidence.gopt_sentence_score * 4.4
    if evidence.gopt_accuracy is not None:
        base += (evidence.gopt_accuracy - 0.7) * 0.8
    if evidence.gopt_prosody is not None:
        base += (evidence.gopt_prosody - 0.7) * 0.5
    if 95 <= evidence.wpm <= 170:
        base += 0.25
    else:
        base -= 0.25
    if evidence.silence_ratio > 0.35:
        base -= 0.35
    if evidence.long_pause_count >= 4:
        base -= 0.35
    if evidence.filler_ratio > 0.08:
        base -= 0.25
    if evidence.audio_quality_label == "unknown":
        base -= 0.25
    if evidence.audio_quality_label == "low_quality":
        base -= 0.65
    if evidence.confidence < 0.55:
        base -= 0.45
    return round_to_half(min(max(base, 2.0), 8.5))


def band_bucket(value: float) -> float:
    return round_to_half(value)


def round_to_half(value: float) -> float:
    return round(value * 2) / 2


def build_contract_speech_calibration_samples() -> list[SpeechCalibrationSample]:
    rows = [
        ("contract_p1_b4_east_poor", 1, 4.0, "east_asian", "poor", 0.55, 82, 0.45, 5, "low_quality"),
        ("contract_p2_b4_south_fair", 2, 4.0, "south_asian", "fair", 0.39, 88, 0.38, 4, "unknown"),
        ("contract_p3_b5_euro_fair", 3, 5.0, "european", "fair", 0.48, 102, 0.32, 3, "usable"),
        ("contract_p1_b5_middle_good", 1, 5.0, "middle_eastern", "good", 0.51, 110, 0.3, 2, "usable"),
        ("contract_p2_b6_latin_good", 2, 6.0, "latin_american", "good", 0.61, 124, 0.24, 2, "usable"),
        ("contract_p3_b6_mixed_fair", 3, 6.0, "mixed", "fair", 0.62, 132, 0.28, 2, "usable"),
        ("contract_p1_b7_east_good", 1, 7.0, "east_asian", "good", 0.74, 142, 0.18, 1, "usable"),
        ("contract_p2_b7_south_good", 2, 7.0, "south_asian", "good", 0.76, 150, 0.16, 1, "usable"),
        ("contract_p3_b8_euro_good", 3, 8.0, "european", "good", 0.86, 152, 0.12, 0, "usable"),
        ("contract_p1_b8_mixed_good", 1, 8.0, "mixed", "good", 0.88, 146, 0.1, 0, "usable"),
        ("contract_p2_b5_other_poor", 2, 5.0, "other", "poor", 0.55, 92, 0.4, 4, "unknown"),
        ("contract_p3_b6_middle_fair", 3, 6.0, "middle_eastern", "fair", 0.66, 118, 0.3, 3, "usable"),
    ]
    return [
        SpeechCalibrationSample(
            sample_id=sample_id,
            source="synthetic_contract",
            audio_asset_id=f"audio_{sample_id}",
            transcript="This is a synthetic calibration contract sample for regression checks.",
            part=part,  # type: ignore[arg-type]
            accent_group=accent,  # type: ignore[arg-type]
            recording_quality=quality,  # type: ignore[arg-type]
            human_pronunciation_band=band,
            human_fluency_band=band,
            annotation_protocol_version="speech-calibration-contract-v0",
            annotator_count=1,
            split="regression",
            evidence=SpeechCalibrationEvidence(
                gopt_sentence_score=gopt,
                gopt_accuracy=min(gopt + 0.02, 0.95),
                gopt_fluency=min(gopt + 0.01, 0.95),
                gopt_prosody=min(gopt, 0.95),
                wpm=wpm,
                silence_ratio=silence,
                long_pause_count=pauses,
                filler_ratio=0.02 if band >= 6 else 0.08,
                audio_quality_label=audio_quality,  # type: ignore[arg-type]
                confidence=0.72 if audio_quality == "usable" else 0.58,
            ),
            metadata={"synthetic_contract": True},
        )
        for sample_id, part, band, accent, quality, gopt, wpm, silence, pauses, audio_quality in rows
    ]
