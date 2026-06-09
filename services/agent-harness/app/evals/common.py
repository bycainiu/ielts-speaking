from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


EvalSeverity = Literal["low", "medium", "high", "critical"]


class EvalCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    category: str
    passed: bool
    score: float = Field(ge=0, le=1)
    reason: str
    severity: EvalSeverity = "medium"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalSuiteReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sample_count: int = Field(ge=0)
    pass_count: int = Field(ge=0)
    fail_count: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    block_release: bool
    results: list[EvalCaseResult] = Field(default_factory=list)
    improvement_items: list[dict[str, Any]] = Field(default_factory=list)

    def to_markdown(self) -> str:
        status = "PASS" if not self.block_release and self.pass_rate >= self.threshold else "FAIL"
        lines = [
            f"# {self.suite_name}",
            "",
            f"- status: {status}",
            f"- samples: {self.sample_count}",
            f"- pass_rate: {self.pass_rate:.3f}",
            f"- threshold: {self.threshold:.3f}",
            f"- block_release: {str(self.block_release).lower()}",
            "",
            "| case_id | category | passed | score | reason |",
            "|---|---|---:|---:|---|",
        ]
        for result in self.results:
            reason = result.reason.replace("|", "/")
            lines.append(
                f"| {result.case_id} | {result.category} | {str(result.passed).lower()} | "
                f"{result.score:.3f} | {reason} |"
            )
        if self.improvement_items:
            lines.extend(["", "## Improvement Items"])
            for item in self.improvement_items:
                lines.append(f"- {item.get('case_id')}: {item.get('reason')}")
        return "\n".join(lines)


def build_suite_report(
    *,
    suite_name: str,
    results: list[EvalCaseResult],
    threshold: float,
) -> EvalSuiteReport:
    pass_count = sum(1 for result in results if result.passed)
    fail_count = len(results) - pass_count
    block_release = any(
        (not result.passed) and result.severity in {"high", "critical"}
        for result in results
    )
    return EvalSuiteReport(
        suite_name=suite_name,
        sample_count=len(results),
        pass_count=pass_count,
        fail_count=fail_count,
        pass_rate=round(pass_count / len(results), 4) if results else 1.0,
        threshold=threshold,
        block_release=block_release,
        results=results,
        improvement_items=[
            {
                "case_id": result.case_id,
                "category": result.category,
                "severity": result.severity,
                "reason": result.reason,
            }
            for result in results
            if not result.passed
        ],
    )
