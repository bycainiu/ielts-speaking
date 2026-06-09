from app.mcp.report_mcp import IELTS_DISCLAIMER, ScoreReportInput
from app.workflows.scoring_workflow import ScoreSessionRequest, ScoringWorkflow


def test_scoring_workflow_generates_schema_valid_report_from_session_state() -> None:
    workflow = ScoringWorkflow()
    response = workflow.score_session(
        "session_001",
        ScoreSessionRequest(
            session_state={"answers": [answer_record()]},
            rubric_descriptors={
                "fluency_coherence": ["Band 6 keeps speaking with some hesitation."],
                "lexical_resource": ["Band 6 uses enough vocabulary for familiar topics."],
                "grammatical_range_accuracy": ["Band 6 mixes simple and complex forms."],
                "pronunciation": ["Band 6 is generally intelligible."],
            },
            anchor_samples=[
                {
                    "anchor_sample_id": "anchor_pronunciation_6",
                    "criterion": "pronunciation",
                    "band": 6.0,
                    "score": 0.9,
                    "rationale": "Similar intelligibility and rhythm.",
                }
            ],
            topic_keywords=["library", "community", "quiet"],
        ),
    )

    assert response.next_action == "finish_session"
    assert response.state["status"] == "scored"
    assert response.state["feedback_items"]
    assert response.state["reference_answers"]
    assert any(event.type == "scoring.dimension_completed" for event in response.events)
    assert any(event.type == "scoring.review_completed" for event in response.events)
    assert any(event.type == "report.ready" for event in response.events)

    report = ScoreReportInput.model_validate(response.state["score_report"])
    assert report.session_id == "session_001"
    assert report.disclaimer == IELTS_DISCLAIMER
    assert report.overall_band in {6.0, 6.5, 7.0}
    assert set(report.criteria) == {
        "fluency_coherence",
        "lexical_resource",
        "grammatical_range_accuracy",
        "pronunciation",
    }
    assert report.raw_report["workflow_version"] == "scoring_workflow.v1"
    assert report.next_practice_plan
    assert report.raw_report["feedback"]["coach_version"] == "feedback_coach.v1"
    assert report.raw_report["calibration"]["anchor_count"] == 1
    assert report.criteria["pronunciation"].raw_output["calibration"]["anchor_sample_ids"] == ["anchor_pronunciation_6"]


def test_scoring_workflow_returns_retryable_error_when_no_answers_exist() -> None:
    workflow = ScoringWorkflow()
    response = workflow.score_session("session_empty", ScoreSessionRequest(session_state={"answers": []}))

    assert response.next_action == "retry_current_node"
    assert response.state["scoring_error"] == "no_scorable_answers"
    assert response.events[0].type == "error.recoverable"
    assert response.events[0].payload["retry_node"] == "scoring_workflow"


def answer_record() -> dict:
    return {
        "turn_id": "turn_1",
        "part": 2,
        "question_text": "Describe a public place you enjoy visiting.",
        "asr_text": (
            "I would like to describe a public library in my community. "
            "I go there when I need a quiet place to study, because it has useful books, "
            "comfortable desks, and a calm atmosphere. For example, last month I prepared "
            "a presentation there and it helped me organize my ideas clearly."
        ),
        "audio_asset_id": "audio_1",
        "asr_confidence": 0.9,
        "speech_metrics": {
            "duration_ms": 42000,
            "words_count": 52,
            "wpm": 120,
            "long_pause_count": 1,
            "mean_pause_ms": 650,
            "filler_count": 1,
            "filler_ratio": 0.019,
            "asr_confidence": 0.9,
        },
        "pronunciation_evidence": {
            "intelligibility_score": 0.82,
            "pronunciation_score": 0.78,
            "prosody_score": 0.76,
            "unclear_segment_count": 0,
            "audio_quality": "good",
            "evidence_source": "gopt_sentence_level",
        },
        "topic_guidance": {"vocabulary": ["library", "community", "presentation"]},
    }
