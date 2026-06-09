from app.evals.deepeval_regression import DeepEvalRegressionRunner, build_default_regression_samples
from app.evals.performance_baseline import PerformanceBaselineRunner, default_performance_baseline_samples
from app.evals.promptfoo_redteam import PromptfooRedTeamRunner, build_default_redteam_samples
from app.evals.ragas_rag_eval import RagasRagEvaluator, build_default_rag_eval_samples


def test_deepeval_regression_suite_covers_at_least_30_samples_and_reports_readably() -> None:
    samples = build_default_regression_samples()
    report = DeepEvalRegressionRunner().run(samples)

    assert len(samples) >= 30
    assert report.sample_count >= 30
    assert report.pass_rate >= report.threshold
    assert report.block_release is False
    assert "deepeval_regression_local" in report.to_markdown()
    assert {"question_planning", "followup", "scoring", "feedback"}.issubset(
        {result.category for result in report.results}
    )


def test_ragas_rag_eval_outputs_precision_recall_and_improvement_items() -> None:
    samples = build_default_rag_eval_samples()
    report = RagasRagEvaluator().run(samples)

    assert report.sample_count == len(samples)
    assert report.pass_rate >= report.threshold
    assert report.block_release is False
    assert all("precision=" in result.reason and "recall=" in result.reason for result in report.results)
    assert report.improvement_items == []


def test_promptfoo_redteam_covers_exam_and_practice_modes_with_release_gate() -> None:
    samples = build_default_redteam_samples()
    report = PromptfooRedTeamRunner().run(samples)

    assert {"full_exam", "part_practice", "topic_practice"}.issubset({sample.mode for sample in samples})
    assert {"prompt_injection", "system_prompt_leak", "privacy_exfiltration", "tool_override"}.issubset(
        {sample.attack_type for sample in samples}
    )
    assert report.pass_rate == 1.0
    assert report.block_release is False
    assert "promptfoo_redteam_local" in report.to_markdown()


def test_performance_baseline_records_p50_p95_tts_cache_and_agent_node_latency() -> None:
    report = PerformanceBaselineRunner().run(default_performance_baseline_samples())

    assert report.sample_count >= 10
    assert report.p50_ms > 0
    assert report.p95_ms >= report.p50_ms
    assert report.tts_cache_hit_rate is not None
    assert any(component.component == "agent_node" for component in report.components)
    assert "Performance Baseline" in report.to_markdown()
