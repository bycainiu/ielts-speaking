from app.agents.fluency_scorer_agent import (
    FluencyCoherenceScorerAgent,
    FluencyCoherenceScorerInput,
    FluencyScoringTurn,
)
from app.mcp.speech_metrics_mcp import TurnAudioMetrics


def test_fluency_scorer_outputs_band_confidence_and_metric_evidence() -> None:
    agent = FluencyCoherenceScorerAgent()
    result = agent.score(
        FluencyCoherenceScorerInput(
            session_id="session_001",
            turns=[
                FluencyScoringTurn(
                    turn_id="turn_001",
                    transcript=(
                        "I think public libraries are useful because they give people a quiet place to study. "
                        "For example, students can read there after school, and as a result they can build a "
                        "regular learning habit without spending much money."
                    ),
                    metrics=TurnAudioMetrics(
                        turn_id="turn_001",
                        duration_ms=30000,
                        words_count=42,
                        wpm=124.0,
                        long_pause_count=1,
                        filler_ratio=0.02,
                        asr_confidence=0.92,
                    ),
                )
            ],
            rubric_descriptors=["Band 6+ fluency has generally clear speech with some hesitation."],
        )
    )

    assert result.criterion == "fluency_coherence"
    assert result.band >= 6.5
    assert result.confidence >= 0.75
    assert any("WPM" in item.quote for item in result.evidence)
    assert any("Long pauses" in item.quote for item in result.evidence)
    assert result.to_report_criterion().band == result.band


def test_fluency_scorer_penalizes_pauses_fillers_and_short_development() -> None:
    agent = FluencyCoherenceScorerAgent()
    result = agent.score(
        FluencyCoherenceScorerInput(
            session_id="session_001",
            turns=[
                FluencyScoringTurn(
                    turn_id="turn_002",
                    transcript="Um I mean I like it because it is good and um you know it is good.",
                    metrics=TurnAudioMetrics(
                        turn_id="turn_002",
                        duration_ms=25000,
                        words_count=16,
                        wpm=38.0,
                        long_pause_count=6,
                        filler_ratio=0.25,
                        asr_confidence=0.78,
                    ),
                )
            ],
        )
    )

    assert result.band <= 4.5
    assert result.confidence >= 0.55
    assert any("长时间空白" in suggestion or "um" in suggestion for suggestion in result.suggestions)
    assert result.evidence[0].turn_id == "turn_002"


def test_fluency_scorer_does_not_treat_grammar_as_primary_fluency_evidence() -> None:
    agent = FluencyCoherenceScorerAgent()
    result = agent.score(
        FluencyCoherenceScorerInput(
            session_id="session_001",
            turns=[
                FluencyScoringTurn(
                    turn_id="turn_003",
                    transcript=(
                        "He go to the park yesterday and I think it is interesting because people can relax "
                        "there and for example families can spend time together."
                    ),
                    metrics=TurnAudioMetrics(
                        turn_id="turn_003",
                        words_count=25,
                        wpm=108.0,
                        long_pause_count=1,
                        filler_ratio=0.0,
                        asr_confidence=0.88,
                    ),
                )
            ],
        )
    )

    combined_reasons = " ".join(item.reason.lower() for item in result.evidence)
    combined_suggestions = " ".join(item.lower() for item in result.suggestions)
    assert "grammar" not in combined_reasons
    assert "tense" not in combined_reasons
    assert "subject-verb" not in combined_reasons
    assert "语法" not in combined_suggestions
