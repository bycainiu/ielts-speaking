from app.agents.lexical_scorer_agent import (
    LexicalResourceScorerAgent,
    LexicalResourceScorerInput,
    LexicalScoringTurn,
)


def test_lexical_scorer_outputs_band_confidence_and_report_criterion() -> None:
    agent = LexicalResourceScorerAgent()
    result = agent.score(
        LexicalResourceScorerInput(
            session_id="session_001",
            turns=[
                LexicalScoringTurn(
                    turn_id="turn_001",
                    transcript=(
                        "Online learning is convenient for commuters because recorded lectures, discussion boards, "
                        "and flexible schedules help students review difficult modules after work. For example, "
                        "a language learner can replay pronunciation tasks and compare different answers."
                    ),
                    topic="education",
                )
            ],
            rubric_descriptors=["Band 6 lexical resource uses an adequate range for familiar and unfamiliar topics."],
            anchor_sample_ids=["lexical_anchor_6"],
            topic_keywords=["online learning", "lecture", "pronunciation", "schedule"],
        )
    )

    assert result.criterion == "lexical_resource"
    assert result.band >= 6.0
    assert result.confidence >= 0.75
    assert any("Topic vocabulary" in item.quote for item in result.evidence)
    assert result.to_report_criterion().band == result.band
    assert result.raw_output["dimension_boundary"] == "lexical_resource_only_no_rare_word_stuffing"


def test_lexical_scorer_flags_repeated_words_and_low_value_expressions() -> None:
    agent = LexicalResourceScorerAgent()
    result = agent.score(
        LexicalResourceScorerInput(
            session_id="session_001",
            turns=[
                LexicalScoringTurn(
                    turn_id="turn_002",
                    transcript=(
                        "The museum was good because the guide was good and the rooms were good. "
                        "It had many things and interesting stuff, so I think it was very very good."
                    ),
                )
            ],
        )
    )

    evidence_text = " ".join(item.quote for item in result.evidence)
    suggestions_text = " ".join(result.suggestions)
    assert result.band <= 5.0
    assert "Repeated words" in evidence_text
    assert "Low-value expressions" in evidence_text
    assert "good" in suggestions_text
    assert "useful / enjoyable / well-organized" in suggestions_text


def test_lexical_scorer_discourages_rare_word_stuffing_for_topic_vocabulary() -> None:
    agent = LexicalResourceScorerAgent()
    result = agent.score(
        LexicalResourceScorerInput(
            session_id="session_001",
            turns=[
                LexicalScoringTurn(
                    turn_id="turn_003",
                    transcript=(
                        "I like this activity because it helps me relax after work. "
                        "It is simple, and I can do it with friends on weekends."
                    ),
                )
            ],
            topic_keywords=["community garden", "sustainable", "neighbourhood"],
        )
    )

    suggestions_text = " ".join(result.suggestions)
    assert result.band <= 5.5
    assert "不要堆砌生僻词" in suggestions_text
    assert "rare" not in suggestions_text.lower()
    assert "advanced words" not in suggestions_text.lower()
