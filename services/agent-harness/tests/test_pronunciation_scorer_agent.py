from app.agents.pronunciation_scorer_agent import (
    PronunciationEvidenceInput,
    PronunciationScorerAgent,
    PronunciationScorerInput,
    PronunciationScoringTurn,
)
from app.mcp.speech_metrics_mcp import TurnAudioMetrics


def test_pronunciation_scorer_outputs_band_confidence_and_evidence() -> None:
    agent = PronunciationScorerAgent()
    result = agent.score(
        PronunciationScorerInput(
            session_id="session_001",
            turns=[
                PronunciationScoringTurn(
                    turn_id="turn_001",
                    transcript=(
                        "I usually speak more slowly when I explain a difficult idea because I want the listener "
                        "to follow the main words and examples clearly."
                    ),
                    metrics=TurnAudioMetrics(
                        turn_id="turn_001",
                        words_count=25,
                        wpm=118.0,
                        long_pause_count=1,
                        mean_pause_ms=420,
                        asr_confidence=0.91,
                    ),
                    pronunciation_evidence=PronunciationEvidenceInput(
                        turn_id="turn_001",
                        intelligibility_score=0.86,
                        pronunciation_score=0.84,
                        prosody_score=0.79,
                        unclear_segment_count=0,
                        audio_quality="good",
                        evidence_source="gopt_baseline",
                    ),
                )
            ],
            rubric_descriptors=["Pronunciation band 6+ is generally intelligible with some lapses."],
            anchor_sample_ids=["pron_anchor_6"],
        )
    )

    assert result.criterion == "pronunciation"
    assert result.band >= 6.5
    assert result.confidence >= 0.75
    assert any("Pronunciation evidence" in item.quote for item in result.evidence)
    assert any("Prosody evidence" in item.quote for item in result.evidence)
    assert result.to_report_criterion().band == result.band


def test_pronunciation_scorer_low_confidence_mentions_limitations() -> None:
    agent = PronunciationScorerAgent()
    result = agent.score(
        PronunciationScorerInput(
            session_id="session_001",
            turns=[
                PronunciationScoringTurn(
                    turn_id="turn_002",
                    transcript="I [unclear] want to talk about my [inaudible] because xxx it is important.",
                    metrics=TurnAudioMetrics(
                        turn_id="turn_002",
                        words_count=12,
                        wpm=42.0,
                        long_pause_count=5,
                        mean_pause_ms=1500,
                        asr_confidence=0.44,
                    ),
                    pronunciation_evidence=PronunciationEvidenceInput(
                        turn_id="turn_002",
                        unclear_segment_count=3,
                        audio_quality="poor",
                    ),
                )
            ],
        )
    )

    suggestions_text = " ".join(result.suggestions)
    assert result.band <= 5.0
    assert result.confidence < 0.55
    assert "置信度较低" in suggestions_text
    assert "录音质量" in suggestions_text
    assert "不可识别片段" in suggestions_text


def test_pronunciation_scorer_does_not_penalize_non_native_accent_label() -> None:
    agent = PronunciationScorerAgent()
    result = agent.score(
        PronunciationScorerInput(
            session_id="session_001",
            turns=[
                PronunciationScoringTurn(
                    turn_id="turn_003",
                    transcript=(
                        "I have a non-native accent, but my words are clear and the rhythm is easy to follow. "
                        "I pause after each idea and stress the key words."
                    ),
                    metrics=TurnAudioMetrics(
                        turn_id="turn_003",
                        words_count=27,
                        wpm=110.0,
                        long_pause_count=1,
                        mean_pause_ms=480,
                        asr_confidence=0.9,
                    ),
                    pronunciation_evidence=PronunciationEvidenceInput(
                        turn_id="turn_003",
                        intelligibility_score=0.84,
                        pronunciation_score=0.8,
                        prosody_score=0.76,
                        unclear_segment_count=0,
                        audio_quality="good",
                    ),
                )
            ],
        )
    )

    combined = " ".join([item.reason for item in result.evidence] + result.suggestions).lower()
    assert result.band >= 6.0
    assert "accent error" not in combined
    assert "口音错误" not in combined
    assert result.raw_output["dimension_boundary"] == (
        "pronunciation_only_intelligibility_rhythm_stress_no_accent_penalty"
    )
