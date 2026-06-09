from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.evals.common import EvalCaseResult, EvalSuiteReport, build_suite_report
from app.evals.speech_calibration import (
    SpeechCalibrationSample,
    build_contract_speech_calibration_samples,
    estimate_internal_pronunciation_band,
)


ExperimentProvider = Literal["gopt_baseline", "multipa_adapter"]
ExperimentStatus = Literal["passed", "needs_review", "not_configured"]


class MultiPAAdapterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1)
    provider: Literal["multipa_adapter"] = "multipa_adapter"
    predicted_pronunciation_band: float = Field(ge=0, le=9)
    latency_ms: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    deployment_notes: list[str] = Field(default_factory=list)


class ProviderComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ExperimentProvider
    sample_count: int = Field(ge=0)
    mean_absolute_error: float = Field(ge=0)
    max_absolute_error: float = Field(ge=0)
    p95_latency_ms: int = Field(ge=0)
    estimated_total_cost_usd: float = Field(ge=0)
    deployment_complexity: Literal["low", "medium", "high"]


class MultiPAExperimentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ExperimentStatus
    benchmark_sample_count: int = Field(ge=0)
    comparisons: list[ProviderComparison]
    eval_report: EvalSuiteReport
    recommendation: str
    deployment_risks: list[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# MultiPA Open Response Experiment",
            "",
            f"- status: {self.status}",
            f"- benchmark_sample_count: {self.benchmark_sample_count}",
            f"- block_release: {str(self.eval_report.block_release).lower()}",
            f"- recommendation: {self.recommendation}",
            "",
            "| provider | samples | mae | max_error | p95_latency_ms | estimated_cost_usd | complexity |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
        for comparison in self.comparisons:
            lines.append(
                f"| {comparison.provider} | {comparison.sample_count} | "
                f"{comparison.mean_absolute_error:.3f} | {comparison.max_absolute_error:.3f} | "
                f"{comparison.p95_latency_ms} | {comparison.estimated_total_cost_usd:.4f} | "
                f"{comparison.deployment_complexity} |"
            )
        if self.deployment_risks:
            lines.extend(["", "## Deployment Risks"])
            lines.extend(f"- {risk}" for risk in self.deployment_risks)
        lines.extend(["", self.eval_report.to_markdown()])
        return "\n".join(lines)


class MultiPAOpenResponseExperimentRunner:
    def __init__(self, *, max_mae_delta: float = 0.25, max_p95_latency_ms: int = 3000) -> None:
        self.max_mae_delta = max_mae_delta
        self.max_p95_latency_ms = max_p95_latency_ms

    def run(
        self,
        samples: list[SpeechCalibrationSample],
        *,
        multipa_outputs: list[MultiPAAdapterOutput] | None = None,
    ) -> MultiPAExperimentReport:
        baseline = compare_gopt_baseline(samples)
        output_by_sample = {output.sample_id: output for output in (multipa_outputs or [])}
        results = [self.evaluate_sample(sample, output_by_sample.get(sample.sample_id)) for sample in samples]
        if not multipa_outputs:
            results.append(
                EvalCaseResult(
                    case_id="multipa_adapter",
                    category="multipa_open_response",
                    passed=False,
                    score=0,
                    reason="MultiPA adapter outputs are not configured; experiment remains a dry-run contract.",
                    severity="high",
                )
            )
        eval_report = build_suite_report(
            suite_name="multipa_open_response_experiment",
            results=results,
            threshold=0.9,
        )
        comparisons = [baseline]
        multipa_comparison = compare_multipa_outputs(samples, multipa_outputs or [])
        if multipa_comparison:
            comparisons.append(multipa_comparison)
        status = experiment_status(eval_report, baseline, multipa_comparison, self.max_mae_delta, self.max_p95_latency_ms)
        return MultiPAExperimentReport(
            status=status,
            benchmark_sample_count=len(samples),
            comparisons=comparisons,
            eval_report=eval_report,
            recommendation=recommendation_for(status, baseline, multipa_comparison),
            deployment_risks=deployment_risks_for(multipa_comparison),
        )

    def evaluate_sample(self, sample: SpeechCalibrationSample, output: MultiPAAdapterOutput | None) -> EvalCaseResult:
        if output is None:
            return EvalCaseResult(
                case_id=sample.sample_id,
                category="multipa_open_response",
                passed=False,
                score=0,
                reason="missing MultiPA output for fixed benchmark sample",
                severity="medium",
                metadata={"source": sample.source},
            )
        absolute_error = round(abs(output.predicted_pronunciation_band - sample.human_pronunciation_band), 3)
        latency_passed = output.latency_ms <= self.max_p95_latency_ms
        accuracy_passed = absolute_error <= 1.0
        return EvalCaseResult(
            case_id=sample.sample_id,
            category="multipa_open_response",
            passed=accuracy_passed and latency_passed,
            score=round(max(0.0, 1.0 - absolute_error / 3.0), 3),
            reason=(
                f"multipa={output.predicted_pronunciation_band:.1f} "
                f"human={sample.human_pronunciation_band:.1f} abs_error={absolute_error:.1f} "
                f"latency_ms={output.latency_ms}"
            ),
            severity="high" if not latency_passed else "medium",
            metadata={
                "absolute_error": absolute_error,
                "latency_ms": output.latency_ms,
                "estimated_cost_usd": output.estimated_cost_usd,
            },
        )


def load_multipa_outputs(path: str | Path) -> list[MultiPAAdapterOutput]:
    outputs: list[MultiPAAdapterOutput] = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
        outputs.append(MultiPAAdapterOutput.model_validate(payload))
    return outputs


def compare_gopt_baseline(samples: list[SpeechCalibrationSample]) -> ProviderComparison:
    errors = [abs(estimate_internal_pronunciation_band(sample.evidence) - sample.human_pronunciation_band) for sample in samples]
    return ProviderComparison(
        provider="gopt_baseline",
        sample_count=len(samples),
        mean_absolute_error=round(mean(errors), 3) if errors else 0.0,
        max_absolute_error=round(max(errors), 3) if errors else 0.0,
        p95_latency_ms=650,
        estimated_total_cost_usd=0,
        deployment_complexity="low",
    )


def compare_multipa_outputs(
    samples: list[SpeechCalibrationSample],
    outputs: list[MultiPAAdapterOutput],
) -> ProviderComparison | None:
    if not outputs:
        return None
    samples_by_id = {sample.sample_id: sample for sample in samples}
    errors = [
        abs(output.predicted_pronunciation_band - samples_by_id[output.sample_id].human_pronunciation_band)
        for output in outputs
        if output.sample_id in samples_by_id
    ]
    latencies = sorted(output.latency_ms for output in outputs)
    p95_index = min(len(latencies) - 1, round(len(latencies) * 0.95) - 1) if latencies else 0
    complexity = "high" if any(output.latency_ms > 3000 for output in outputs) else "medium"
    return ProviderComparison(
        provider="multipa_adapter",
        sample_count=len(outputs),
        mean_absolute_error=round(mean(errors), 3) if errors else 0.0,
        max_absolute_error=round(max(errors), 3) if errors else 0.0,
        p95_latency_ms=latencies[p95_index] if latencies else 0,
        estimated_total_cost_usd=round(sum(output.estimated_cost_usd for output in outputs), 4),
        deployment_complexity=complexity,  # type: ignore[arg-type]
    )


def experiment_status(
    eval_report: EvalSuiteReport,
    baseline: ProviderComparison,
    multipa: ProviderComparison | None,
    max_mae_delta: float,
    max_p95_latency_ms: int,
) -> ExperimentStatus:
    if multipa is None:
        return "not_configured"
    if eval_report.block_release:
        return "needs_review"
    if multipa.mean_absolute_error <= baseline.mean_absolute_error + max_mae_delta and multipa.p95_latency_ms <= max_p95_latency_ms:
        return "passed"
    return "needs_review"


def recommendation_for(
    status: ExperimentStatus,
    baseline: ProviderComparison,
    multipa: ProviderComparison | None,
) -> str:
    if status == "not_configured":
        return "Keep MultiPA outside the MVP path until real adapter outputs are evaluated on the fixed benchmark."
    if status == "passed" and multipa is not None:
        return (
            f"MultiPA is within MAE tolerance against baseline ({multipa.mean_absolute_error:.2f} vs "
            f"{baseline.mean_absolute_error:.2f}); consider a gated experiment behind feature flags."
        )
    return "Do not promote MultiPA to the main scoring path until accuracy, latency, and cost risks are reduced."


def deployment_risks_for(multipa: ProviderComparison | None) -> list[str]:
    if multipa is None:
        return ["adapter_not_configured", "no_real_cost_latency_data"]
    risks: list[str] = []
    if multipa.p95_latency_ms > 3000:
        risks.append("p95_latency_above_3s")
    if multipa.estimated_total_cost_usd > 0.5:
        risks.append("cost_requires_budget_review")
    if multipa.deployment_complexity == "high":
        risks.append("high_deployment_complexity")
    return risks


def build_contract_multipa_outputs() -> list[MultiPAAdapterOutput]:
    outputs: list[MultiPAAdapterOutput] = []
    for sample in build_contract_speech_calibration_samples():
        baseline = estimate_internal_pronunciation_band(sample.evidence)
        outputs.append(
            MultiPAAdapterOutput(
                sample_id=sample.sample_id,
                predicted_pronunciation_band=baseline,
                latency_ms=1280 if sample.part != 3 else 1540,
                estimated_cost_usd=0.012,
                deployment_notes=["synthetic contract adapter output for regression only"],
            )
        )
    return outputs
