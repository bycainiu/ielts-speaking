from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


PerformanceComponent = Literal["live_turn", "asr", "tts", "scoring", "report_generation", "agent_node"]


class PerformanceSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component: PerformanceComponent
    latency_ms: int = Field(ge=0)
    success: bool = True
    cache_hit: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComponentLatencyBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component: PerformanceComponent
    sample_count: int = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)
    p50_ms: int = Field(ge=0)
    p95_ms: int = Field(ge=0)
    max_ms: int = Field(ge=0)


class PerformanceBaselineReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_count: int = Field(ge=0)
    p50_ms: int = Field(ge=0)
    p95_ms: int = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)
    tts_cache_hit_rate: float | None = Field(default=None, ge=0, le=1)
    components: list[ComponentLatencyBaseline] = Field(default_factory=list)
    bottlenecks: list[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# Performance Baseline",
            "",
            f"- samples: {self.sample_count}",
            f"- p50_ms: {self.p50_ms}",
            f"- p95_ms: {self.p95_ms}",
            f"- error_rate: {self.error_rate:.3f}",
            f"- tts_cache_hit_rate: {self.tts_cache_hit_rate if self.tts_cache_hit_rate is not None else 'n/a'}",
            "",
            "| component | samples | p50_ms | p95_ms | error_rate |",
            "|---|---:|---:|---:|---:|",
        ]
        for component in self.components:
            lines.append(
                f"| {component.component} | {component.sample_count} | {component.p50_ms} | "
                f"{component.p95_ms} | {component.error_rate:.3f} |"
            )
        if self.bottlenecks:
            lines.extend(["", "## Bottlenecks"])
            lines.extend(f"- {item}" for item in self.bottlenecks)
        return "\n".join(lines)


class PerformanceBaselineRunner:
    def run(self, samples: list[PerformanceSample]) -> PerformanceBaselineReport:
        latencies = [sample.latency_ms for sample in samples]
        failed_count = sum(1 for sample in samples if not sample.success)
        tts_samples = [sample for sample in samples if sample.component == "tts" and sample.cache_hit is not None]
        tts_cache_hit_rate = (
            round(sum(1 for sample in tts_samples if sample.cache_hit) / len(tts_samples), 4)
            if tts_samples
            else None
        )
        components = [component_baseline(component, samples) for component in sorted({sample.component for sample in samples})]
        return PerformanceBaselineReport(
            sample_count=len(samples),
            p50_ms=percentile(latencies, 0.50),
            p95_ms=percentile(latencies, 0.95),
            error_rate=round(failed_count / len(samples), 4) if samples else 0.0,
            tts_cache_hit_rate=tts_cache_hit_rate,
            components=components,
            bottlenecks=[
                f"{item.component} p95={item.p95_ms}ms"
                for item in components
                if item.p95_ms >= 3000 or item.error_rate >= 0.05
            ],
        )


def component_baseline(component: PerformanceComponent, samples: list[PerformanceSample]) -> ComponentLatencyBaseline:
    scoped = [sample for sample in samples if sample.component == component]
    latencies = [sample.latency_ms for sample in scoped]
    failed_count = sum(1 for sample in scoped if not sample.success)
    return ComponentLatencyBaseline(
        component=component,
        sample_count=len(scoped),
        error_rate=round(failed_count / len(scoped), 4) if scoped else 0.0,
        p50_ms=percentile(latencies, 0.50),
        p95_ms=percentile(latencies, 0.95),
        max_ms=max(latencies) if latencies else 0,
    )


def percentile(values: list[int], quantile: float) -> int:
    sorted_values = sorted(values)
    if not sorted_values:
        return 0
    index = max(0, min(len(sorted_values) - 1, int((len(sorted_values) - 1) * quantile + 0.999999)))
    return sorted_values[index]


def default_performance_baseline_samples() -> list[PerformanceSample]:
    return [
        PerformanceSample(component="live_turn", latency_ms=820),
        PerformanceSample(component="live_turn", latency_ms=910),
        PerformanceSample(component="live_turn", latency_ms=980),
        PerformanceSample(component="asr", latency_ms=680),
        PerformanceSample(component="asr", latency_ms=740),
        PerformanceSample(component="asr", latency_ms=810),
        PerformanceSample(component="tts", latency_ms=120, cache_hit=True),
        PerformanceSample(component="tts", latency_ms=1180, cache_hit=False),
        PerformanceSample(component="tts", latency_ms=110, cache_hit=True),
        PerformanceSample(component="scoring", latency_ms=1360),
        PerformanceSample(component="scoring", latency_ms=1480),
        PerformanceSample(component="report_generation", latency_ms=420),
        PerformanceSample(component="report_generation", latency_ms=460),
        PerformanceSample(component="agent_node", latency_ms=210),
        PerformanceSample(component="agent_node", latency_ms=260),
    ]
