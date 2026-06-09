from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import BaseModel

from app.evals.multipa_open_response import (
    MultiPAExperimentReport,
    MultiPAOpenResponseExperimentRunner,
    build_contract_multipa_outputs,
    load_multipa_outputs,
)
from app.evals.speech_calibration import (
    SpeechCalibrationRegressionReport,
    SpeechCalibrationRegressionRunner,
    build_contract_speech_calibration_samples,
    load_speech_calibration_manifest,
)


Report = SpeechCalibrationRegressionReport | MultiPAExperimentReport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.evals.speech_eval_cli",
        description="Run speech calibration and MultiPA experiment gates.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    calibration = subparsers.add_parser("calibration", help="Run speech calibration dataset audit and regression.")
    add_manifest_args(calibration)
    calibration.add_argument("--max-case-absolute-error", type=float, default=1.0)
    calibration.add_argument("--max-mean-absolute-error", type=float, default=0.75)
    calibration.add_argument("--model-version", default="speech-evidence-calibration-v0")
    add_output_args(calibration)

    multipa = subparsers.add_parser("multipa", help="Run MultiPA open-response experiment comparison.")
    add_manifest_args(multipa)
    multipa.add_argument("--multipa-outputs", type=Path, help="JSONL file with MultiPAAdapterOutput records.")
    multipa.add_argument("--contract-multipa-outputs", action="store_true", help="Use synthetic contract MultiPA outputs.")
    multipa.add_argument("--allow-not-configured", action="store_true", help="Return 0 when MultiPA outputs are missing.")
    multipa.add_argument("--max-mae-delta", type=float, default=0.25)
    multipa.add_argument("--max-p95-latency-ms", type=int, default=3000)
    add_output_args(multipa)
    return parser


def add_manifest_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, help="Speech calibration JSONL manifest.")
    parser.add_argument("--contract-samples", action="store_true", help="Use synthetic contract samples for CI only.")
    parser.add_argument("--allow-synthetic-contract", action="store_true", help="Allow synthetic samples to pass the dataset audit.")
    parser.add_argument("--min-production-samples", type=int, default=200)


def add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-json", type=Path, help="Write full report JSON.")
    parser.add_argument("--output-md", type=Path, help="Write readable Markdown report.")
    parser.add_argument("--stdout-format", choices=["json", "markdown", "summary"], default="summary")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "calibration":
            report = run_calibration(args)
            write_outputs(report, args)
            print_report(report, args.stdout_format)
            return 0 if calibration_passed(report, args.max_mean_absolute_error) else 1
        report = run_multipa(args)
        write_outputs(report, args)
        print_report(report, args.stdout_format)
        return 0 if multipa_passed(report, allow_not_configured=args.allow_not_configured) else 1
    except Exception as exc:
        print(f"speech_eval_cli_error: {exc}", file=sys.stderr)
        return 2


def run_calibration(args: argparse.Namespace) -> SpeechCalibrationRegressionReport:
    samples = load_samples(args)
    return SpeechCalibrationRegressionRunner(
        model_version=args.model_version,
        max_case_absolute_error=args.max_case_absolute_error,
        max_mean_absolute_error=args.max_mean_absolute_error,
    ).run(
        samples,
        allow_synthetic_contract=args.allow_synthetic_contract,
        min_production_samples=args.min_production_samples,
    )


def run_multipa(args: argparse.Namespace) -> MultiPAExperimentReport:
    samples = load_samples(args)
    outputs = None
    if args.multipa_outputs:
        outputs = load_multipa_outputs(args.multipa_outputs)
    elif args.contract_multipa_outputs:
        outputs = build_contract_multipa_outputs()
    return MultiPAOpenResponseExperimentRunner(
        max_mae_delta=args.max_mae_delta,
        max_p95_latency_ms=args.max_p95_latency_ms,
    ).run(samples, multipa_outputs=outputs)


def load_samples(args: argparse.Namespace):
    if args.contract_samples:
        return build_contract_speech_calibration_samples()
    if args.manifest:
        return load_speech_calibration_manifest(args.manifest)
    raise ValueError("provide --manifest or --contract-samples")


def write_outputs(report: Report, args: argparse.Namespace) -> None:
    if args.output_json:
        ensure_parent(args.output_json)
        args.output_json.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    if args.output_md:
        ensure_parent(args.output_md)
        args.output_md.write_text(report.to_markdown(), encoding="utf-8")


def print_report(report: Report, stdout_format: str) -> None:
    if stdout_format == "json":
        print(report.model_dump_json(indent=2))
        return
    if stdout_format == "markdown":
        print(report.to_markdown())
        return
    if isinstance(report, SpeechCalibrationRegressionReport):
        passed = report.audit.passed and not report.eval_report.block_release
        print(
            "speech_calibration "
            f"passed={passed} "
            f"samples={report.audit.sample_count} "
            f"mae={report.mean_absolute_error:.3f} "
            f"max_error={report.max_absolute_error:.3f} "
            f"issues={len(report.audit.issues)}"
        )
        return
    print(
        "multipa_open_response "
        f"status={report.status} "
        f"samples={report.benchmark_sample_count} "
        f"block_release={str(report.eval_report.block_release).lower()} "
        f"risks={len(report.deployment_risks)}"
    )


def calibration_passed(report: SpeechCalibrationRegressionReport, max_mean_absolute_error: float) -> bool:
    return report.audit.passed and not report.eval_report.block_release and report.mean_absolute_error <= max_mean_absolute_error


def multipa_passed(report: MultiPAExperimentReport, *, allow_not_configured: bool = False) -> bool:
    if allow_not_configured and report.status == "not_configured":
        return True
    return report.status == "passed" and not report.eval_report.block_release


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
