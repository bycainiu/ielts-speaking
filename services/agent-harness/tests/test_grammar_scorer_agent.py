from app.agents.grammar_scorer_agent import (
    GrammarScorerAgent,
    GrammarScorerInput,
    GrammarScoringTurn,
)


def test_grammar_scorer_outputs_band_confidence_and_range_evidence() -> None:
    agent = GrammarScorerAgent()
    result = agent.score(
        GrammarScorerInput(
            session_id="session_001",
            turns=[
                GrammarScoringTurn(
                    turn_id="turn_001",
                    transcript=(
                        "Last year I joined a volunteer program because I wanted to meet people outside my office. "
                        "Although it was demanding, I learned how to explain simple tasks clearly, which helped me "
                        "become more confident when I spoke with strangers."
                    ),
                )
            ],
            rubric_descriptors=["Band 6 grammar has a mix of simple and complex forms with some errors."],
            anchor_sample_ids=["grammar_anchor_6"],
        )
    )

    assert result.criterion == "grammatical_range_accuracy"
    assert result.band >= 6.5
    assert result.confidence >= 0.75
    assert any("复杂结构标记" in item.reason for item in result.evidence)
    assert result.to_report_criterion().band == result.band
    assert result.raw_output["dimension_boundary"] == "grammar_range_accuracy_only_natural_spoken_rewrites"


def test_grammar_scorer_flags_major_errors_with_specific_rewrites() -> None:
    agent = GrammarScorerAgent()
    result = agent.score(
        GrammarScorerInput(
            session_id="session_001",
            turns=[
                GrammarScoringTurn(
                    turn_id="turn_002",
                    transcript=(
                        "He go to the park yesterday and she have a nice time. "
                        "People is friendly there, but last year I go there only once."
                    ),
                )
            ],
        )
    )

    evidence_text = " ".join(item.reason for item in result.evidence)
    suggestions_text = " ".join(result.suggestions)
    feature_summary = result.raw_output["feature_summary"]
    assert result.band <= 4.5
    assert feature_summary["major_error_count"] >= 3
    assert "subject_verb_agreement" in evidence_text
    assert "plural_subject_be_verb" in evidence_text
    assert "past_time_tense_control" in evidence_text
    assert "He goes" in suggestions_text
    assert "yesterday I went" in suggestions_text


def test_grammar_scorer_distinguishes_minor_article_gap_from_major_errors() -> None:
    agent = GrammarScorerAgent()
    result = agent.score(
        GrammarScorerInput(
            session_id="session_001",
            turns=[
                GrammarScoringTurn(
                    turn_id="turn_003",
                    transcript=(
                        "Yesterday I went to park because I wanted to read quietly. "
                        "After that, I met my friend and we talked about our exams."
                    ),
                )
            ],
        )
    )

    suggestions_text = " ".join(result.suggestions).lower()
    feature_summary = result.raw_output["feature_summary"]
    assert feature_summary["major_error_count"] == 0
    assert feature_summary["minor_error_count"] == 1
    assert feature_summary["errors"][0]["kind"] == "article_gap"
    assert result.band >= 5.0
    assert "formal" not in suggestions_text
    assert "academic" not in suggestions_text
