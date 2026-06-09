from app.agents.feedback_coach_agent import FeedbackCoachAgent, FeedbackCoachAnswer, FeedbackCoachInput
from app.mcp.report_mcp import CriterionScoreInput, ReportEvidence, ScoreReportInput


def test_feedback_coach_generates_actionable_feedback_reference_and_plan() -> None:
    report = make_score_report()
    output = FeedbackCoachAgent().generate(
        FeedbackCoachInput(
            session_id="session_feedback_001",
            score_report=report,
            answers=[
                FeedbackCoachAnswer(
                    turn_id="turn_1",
                    part=2,
                    question_text="Describe a place you enjoy visiting.",
                    topic="public library",
                    transcript=(
                        "I want to talk about a library near my home. It is quiet and useful. "
                        "I go there when I need to study because it helps me focus."
                    ),
                )
            ],
            user_background={"agent_facts": [{"fact_value": "I live in Hangzhou and study after work"}]},
        )
    )

    assert "6.0" in output.summary
    assert len(output.feedback_items) == 3
    assert output.feedback_items[0].category == "lexical_resource"
    assert output.feedback_items[0].evidence_refs[0]["turn_id"] == "turn_1"
    assert output.next_practice_plan[0].focus == "话题词与具体表达"
    assert output.reference_answers[0].turn_id == "turn_1"
    assert output.reference_answers[0].band_target == 6.5
    assert "逐句背诵" in output.reference_answers[0].personalization_notes
    assert "Hangzhou" in output.reference_answers[0].answer_text
    assert output.raw_output["reference_answer_policy"] == "flexible_model_not_memorization_script"


def make_score_report() -> ScoreReportInput:
    criteria = {
        "fluency_coherence": CriterionScoreInput(
            band=6.0,
            confidence=0.78,
            evidence=[ReportEvidence(turn_id="turn_1", quote="I go there when I need to study", reason="clear reason")],
            suggestions=["加入更明确的原因和例子，让信息推进更清楚。"],
        ),
        "lexical_resource": CriterionScoreInput(
            band=5.5,
            confidence=0.74,
            evidence=[ReportEvidence(turn_id="turn_1", quote="quiet and useful", reason="basic adjectives")],
            suggestions=["把 useful 替换为更具体的表达，例如 a productive study environment。"],
        ),
        "grammatical_range_accuracy": CriterionScoreInput(
            band=6.0,
            confidence=0.76,
            evidence=[ReportEvidence(turn_id="turn_1", quote="I go there when I need", reason="controlled clause")],
            suggestions=["增加一个对比句，但先保持主谓一致。"],
        ),
        "pronunciation": CriterionScoreInput(
            band=6.5,
            confidence=0.7,
            evidence=[ReportEvidence(turn_id="turn_1", quote="WPM 110", reason="stable pace")],
            suggestions=["继续按意群停顿。"],
        ),
    }
    return ScoreReportInput(
        session_id="session_feedback_001",
        overall_band=6.0,
        confidence=0.75,
        criteria=criteria,
        reviewer_notes=["Accepted."],
    )
