from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.score_calibrator import ScoreCalibrator, ScoreCalibratorInput, ScoreCalibratorOutput
from app.content.anchor_samples import (
    AnchorDatasetAudit,
    AnchorSpeakingSample,
    audit_anchor_dataset,
    build_default_anchor_samples,
    to_calibration_anchor_samples,
)
from app.evals.common import EvalSuiteReport
from app.evals.deepeval_regression import DeepEvalRegressionRunner
from app.evals.multipa_open_response import (
    MultiPAAdapterOutput,
    MultiPAExperimentReport,
    MultiPAOpenResponseExperimentRunner,
    build_contract_multipa_outputs,
)
from app.evals.performance_baseline import (
    PerformanceBaselineReport,
    PerformanceBaselineRunner,
    PerformanceSample,
    default_performance_baseline_samples,
)
from app.evals.promptfoo_redteam import PromptfooRedTeamRunner
from app.evals.ragas_rag_eval import RagasRagEvaluator
from app.evals.speech_calibration import (
    SpeechCalibrationRegressionReport,
    SpeechCalibrationRegressionRunner,
    SpeechCalibrationSample,
    build_contract_speech_calibration_samples,
)


QualityGateStatus = Literal["passed", "needs_review", "blocked"]
QualityCheckStatus = Literal["passed", "needs_review", "blocked"]


class AnchorSamplesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit: AnchorDatasetAudit
    samples: list[AnchorSpeakingSample] = Field(default_factory=list)
    calibration_anchor_count: int = Field(ge=0)
    note: str


class SpeechCalibrationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    samples: list[SpeechCalibrationSample] = Field(default_factory=list)
    use_contract_samples: bool = False
    allow_synthetic_contract: bool = False
    min_production_samples: int = Field(default=200, ge=0)
    max_case_absolute_error: float = Field(default=1.0, gt=0)
    max_mean_absolute_error: float = Field(default=0.75, gt=0)
    model_version: str = Field(default="speech-evidence-calibration-v0", min_length=1)

    @model_validator(mode="after")
    def validate_sample_source(self) -> "SpeechCalibrationRunRequest":
        if not self.use_contract_samples and not self.samples:
            raise ValueError("provide samples or set use_contract_samples=true")
        return self


class MultiPAExperimentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    samples: list[SpeechCalibrationSample] = Field(default_factory=list)
    use_contract_samples: bool = False
    multipa_outputs: list[MultiPAAdapterOutput] = Field(default_factory=list)
    use_contract_multipa_outputs: bool = False
    max_mae_delta: float = Field(default=0.25, ge=0)
    max_p95_latency_ms: int = Field(default=3000, gt=0)

    @model_validator(mode="after")
    def validate_sample_source(self) -> "MultiPAExperimentRunRequest":
        if not self.use_contract_samples and not self.samples:
            raise ValueError("provide samples or set use_contract_samples=true")
        return self


class CalibrationQualityGateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_deepeval_regression: bool = True
    include_ragas_rag: bool = True
    include_promptfoo_redteam: bool = True
    include_performance_baseline: bool = True
    include_speech_calibration_contract: bool = True
    include_multipa_contract: bool = True
    performance_samples: list[PerformanceSample] = Field(default_factory=list)


class CalibrationQualityGateCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: QualityCheckStatus
    message: str
    block_release: bool
    sample_count: int = Field(ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)


class CalibrationQualityGateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    status: QualityGateStatus
    checks: list[CalibrationQualityGateCheck]
    anchor_audit: AnchorDatasetAudit
    deepeval_report: EvalSuiteReport | None = None
    ragas_report: EvalSuiteReport | None = None
    promptfoo_report: EvalSuiteReport | None = None
    performance_report: PerformanceBaselineReport | None = None
    speech_calibration_report: SpeechCalibrationRegressionReport | None = None
    multipa_experiment_report: MultiPAExperimentReport | None = None
    note: str


def build_anchor_samples_response(*, include_samples: bool = True) -> AnchorSamplesResponse:
    samples = build_default_anchor_samples()
    audit = audit_anchor_dataset(samples)
    calibration_anchors = to_calibration_anchor_samples(samples)
    return AnchorSamplesResponse(
        audit=audit,
        samples=samples if include_samples else [],
        calibration_anchor_count=len(calibration_anchors),
        note="Default anchor samples are synthetic internal calibration references for regression, not official IELTS scores.",
    )


def run_score_calibration(request: ScoreCalibratorInput) -> ScoreCalibratorOutput:
    return ScoreCalibrator().calibrate(request)


def run_speech_calibration(request: SpeechCalibrationRunRequest) -> SpeechCalibrationRegressionReport:
    samples = speech_samples_from_request(request)
    return SpeechCalibrationRegressionRunner(
        model_version=request.model_version,
        max_case_absolute_error=request.max_case_absolute_error,
        max_mean_absolute_error=request.max_mean_absolute_error,
    ).run(
        samples,
        allow_synthetic_contract=request.allow_synthetic_contract,
        min_production_samples=request.min_production_samples,
    )


def run_multipa_experiment(request: MultiPAExperimentRunRequest) -> MultiPAExperimentReport:
    samples = request.samples or (build_contract_speech_calibration_samples() if request.use_contract_samples else [])
    outputs = request.multipa_outputs or (build_contract_multipa_outputs() if request.use_contract_multipa_outputs else None)
    return MultiPAOpenResponseExperimentRunner(
        max_mae_delta=request.max_mae_delta,
        max_p95_latency_ms=request.max_p95_latency_ms,
    ).run(samples, multipa_outputs=outputs)


def run_calibration_quality_gate(request: CalibrationQualityGateRequest) -> CalibrationQualityGateResponse:
    anchor_response = build_anchor_samples_response(include_samples=False)
    checks: list[CalibrationQualityGateCheck] = [
        CalibrationQualityGateCheck(
            name="anchor_samples",
            status="passed" if anchor_response.audit.passed else "blocked",
            message="Anchor dataset covers Band 4-8 and all four scoring criteria."
            if anchor_response.audit.passed
            else "Anchor dataset audit failed.",
            block_release=not anchor_response.audit.passed,
            sample_count=anchor_response.audit.sample_count,
            metadata={
                "covered_bands": anchor_response.audit.covered_bands,
                "covered_criteria": anchor_response.audit.covered_criteria,
                "findings": anchor_response.audit.findings,
            },
        )
    ]

    deepeval_report: EvalSuiteReport | None = None
    ragas_report: EvalSuiteReport | None = None
    promptfoo_report: EvalSuiteReport | None = None
    performance_report: PerformanceBaselineReport | None = None
    speech_report: SpeechCalibrationRegressionReport | None = None
    multipa_report: MultiPAExperimentReport | None = None

    if request.include_deepeval_regression:
        deepeval_report = DeepEvalRegressionRunner().run()
        checks.append(check_from_eval_report("deepeval_regression", deepeval_report))
    if request.include_ragas_rag:
        ragas_report = RagasRagEvaluator().run()
        checks.append(check_from_eval_report("ragas_rag", ragas_report))
    if request.include_promptfoo_redteam:
        promptfoo_report = PromptfooRedTeamRunner().run()
        checks.append(check_from_eval_report("promptfoo_redteam", promptfoo_report))
    if request.include_performance_baseline:
        samples = request.performance_samples or default_performance_baseline_samples()
        performance_report = PerformanceBaselineRunner().run(samples)
        checks.append(check_from_performance_report(performance_report))
    if request.include_speech_calibration_contract:
        speech_report = run_speech_calibration(
            SpeechCalibrationRunRequest(
                use_contract_samples=True,
                allow_synthetic_contract=True,
                min_production_samples=0,
            )
        )
        checks.append(check_from_speech_report(speech_report))
    if request.include_multipa_contract:
        multipa_report = run_multipa_experiment(
            MultiPAExperimentRunRequest(
                use_contract_samples=True,
                use_contract_multipa_outputs=True,
            )
        )
        checks.append(check_from_multipa_report(multipa_report))

    return CalibrationQualityGateResponse(
        generated_at=datetime.now(UTC),
        status=aggregate_status(checks),
        checks=checks,
        anchor_audit=anchor_response.audit,
        deepeval_report=deepeval_report,
        ragas_report=ragas_report,
        promptfoo_report=promptfoo_report,
        performance_report=performance_report,
        speech_calibration_report=speech_report,
        multipa_experiment_report=multipa_report,
        note=(
            "This endpoint runs deterministic local quality gates. Speech and MultiPA contract checks use synthetic "
            "contract data only; production calibration still requires authorized real samples."
        ),
    )


def speech_samples_from_request(request: SpeechCalibrationRunRequest) -> list[SpeechCalibrationSample]:
    if request.samples:
        return request.samples
    if request.use_contract_samples:
        return build_contract_speech_calibration_samples()
    return []


def check_from_eval_report(name: str, report: EvalSuiteReport) -> CalibrationQualityGateCheck:
    passed = not report.block_release and report.pass_rate >= report.threshold
    return CalibrationQualityGateCheck(
        name=name,
        status="passed" if passed else "blocked",
        message=f"{name} pass_rate={report.pass_rate:.3f}, threshold={report.threshold:.3f}.",
        block_release=report.block_release or not passed,
        sample_count=report.sample_count,
        metadata={
            "pass_count": report.pass_count,
            "fail_count": report.fail_count,
            "improvement_items": report.improvement_items,
        },
    )


def check_from_performance_report(report: PerformanceBaselineReport) -> CalibrationQualityGateCheck:
    blocked = report.error_rate >= 0.05 or any(item.startswith("agent_node") for item in report.bottlenecks)
    needs_review = bool(report.bottlenecks)
    status: QualityCheckStatus = "blocked" if blocked else "needs_review" if needs_review else "passed"
    return CalibrationQualityGateCheck(
        name="performance_baseline",
        status=status,
        message=f"performance p95={report.p95_ms}ms error_rate={report.error_rate:.3f}.",
        block_release=blocked,
        sample_count=report.sample_count,
        metadata={
            "p50_ms": report.p50_ms,
            "p95_ms": report.p95_ms,
            "tts_cache_hit_rate": report.tts_cache_hit_rate,
            "bottlenecks": report.bottlenecks,
        },
    )


def check_from_speech_report(report: SpeechCalibrationRegressionReport) -> CalibrationQualityGateCheck:
    passed = report.audit.passed and not report.eval_report.block_release and report.mean_absolute_error <= 0.75
    return CalibrationQualityGateCheck(
        name="speech_calibration_contract",
        status="passed" if passed else "blocked",
        message=f"speech calibration mae={report.mean_absolute_error:.3f}, max_error={report.max_absolute_error:.3f}.",
        block_release=not passed,
        sample_count=report.audit.sample_count,
        metadata={
            "production_sample_count": report.audit.production_sample_count,
            "synthetic_sample_count": report.audit.synthetic_sample_count,
            "issues": report.audit.issues,
            "contract_only": report.audit.synthetic_sample_count == report.audit.sample_count,
        },
    )


def check_from_multipa_report(report: MultiPAExperimentReport) -> CalibrationQualityGateCheck:
    passed = report.status == "passed" and not report.eval_report.block_release
    return CalibrationQualityGateCheck(
        name="multipa_contract",
        status="passed" if passed else "needs_review",
        message=f"multipa status={report.status}, block_release={str(report.eval_report.block_release).lower()}.",
        block_release=report.eval_report.block_release,
        sample_count=report.benchmark_sample_count,
        metadata={
            "status": report.status,
            "risks": report.deployment_risks,
            "contract_only": True,
        },
    )


def aggregate_status(checks: list[CalibrationQualityGateCheck]) -> QualityGateStatus:
    if any(check.status == "blocked" or check.block_release for check in checks):
        return "blocked"
    if any(check.status == "needs_review" for check in checks):
        return "needs_review"
    return "passed"
