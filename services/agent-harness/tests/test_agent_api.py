import json

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model_provider"]["default_model"] == "mimo-v2.5-pro"
    assert "mimo-v2.5-asr" in body["model_provider"]["available_models"]
    assert "api_key" not in body["model_provider"]
    assert body["asr"]["model"] == "mimo-v2.5-asr"
    assert "audio/webm" in body["asr"]["supported_mime_types"]
    assert body["tts"]["model"] == "mimo-v2.5-tts"
    assert body["runtime"]["adapter"] == "microsoft-agent-framework"
    assert body["runtime"]["adapter_package"] == "agent-framework-core"
    assert body["runtime"]["framework"] == "deterministic-workflow"


def test_transcribe_audio_returns_mock_asr_result() -> None:
    response = client.post(
        "/agent/audio/transcribe",
        json={
            "audio_asset_id": "audio_api_001",
            "mime_type": "audio/webm",
            "duration_ms": 9500,
            "language_hint": "en",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["audio_asset_id"] == "audio_api_001"
    assert body["asr_text"] == "Mock IELTS speaking transcript for audio asset audio_api_001."
    assert body["language"] == "en"
    assert body["confidence"] >= 0.82
    assert body["provider"] == "mock_asr"
    assert body["model"] == "mimo-v2.5-asr"
    assert body["duration_ms"] == 9500
    assert body["metadata"]["mock"] is True
    assert body["metadata"]["source_type"] == "asset_reference"


def test_transcribe_audio_rejects_unsupported_mime_type() -> None:
    response = client.post(
        "/agent/audio/transcribe",
        json={"audio_asset_id": "audio_bad", "mime_type": "video/mp4"},
    )

    assert response.status_code == 415
    body = response.json()
    assert body["detail"]["error"] == "unsupported_audio_format"
    assert body["detail"]["retryable"] is False
    assert "audio/webm" in body["detail"]["supported_mime_types"]


def test_synthesize_speech_returns_mock_tts_audio() -> None:
    response = client.post(
        "/agent/audio/synthesize",
        json={
            "text": "Let's talk about your studies.",
            "voice_id": "examiner_voice_a",
            "speaking_rate": 1.05,
            "emotion": "neutral",
            "style": "examiner",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Let's talk about your studies."
    assert body["provider"] == "mock_tts"
    assert body["model"] == "mimo-v2.5-tts"
    assert body["voice_id"] == "examiner_voice_a"
    assert body["mime_type"] == "audio/wav"
    assert body["duration_ms"] >= 600
    assert body["metadata"]["mock"] is True
    assert len(body["audio_base64"]) > 20


def test_score_session_returns_ready_report() -> None:
    response = client.post(
        "/agent/sessions/sess_score_001/score",
        json={
            "session_state": {
                "answers": [
                    {
                        "turn_id": "turn_score_001",
                        "part": 1,
                        "question_text": "What do you like about your hometown?",
                        "asr_text": (
                            "I like my hometown because it is convenient and friendly. "
                            "For example, there is a library near my home, so I can study there after work."
                        ),
                        "asr_confidence": 0.88,
                        "speech_metrics": {
                            "duration_ms": 22000,
                            "words_count": 27,
                            "wpm": 112,
                            "long_pause_count": 1,
                            "filler_ratio": 0.02,
                            "asr_confidence": 0.88,
                        },
                        "pronunciation_evidence": {
                            "intelligibility_score": 0.8,
                            "pronunciation_score": 0.76,
                            "prosody_score": 0.74,
                            "audio_quality": "good",
                            "evidence_source": "sentence_level",
                        },
                    }
                ]
            },
            "topic_keywords": ["hometown", "library"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["next_action"] == "finish_session"
    assert body["state"]["status"] == "scored"
    assert "score_report" in body["state"]
    assert body["state"]["score_report"]["session_id"] == "sess_score_001"
    assert body["state"]["score_report"]["disclaimer"] == "AI 模拟评分仅用于练习参考，不代表 IELTS 官方成绩。"
    assert body["state"]["feedback_items"]
    assert body["state"]["reference_answers"]
    assert body["state"]["score_report"]["next_practice_plan"]
    assert event_payload(body, "report.ready")["overall_band"] == body["state"]["score_report"]["overall_band"]
    assert event_payload(body, "report.ready")["feedback_count"] >= 1

    trace_response = client.get(f"/agent/runs/{body['run_id']}/trace")
    assert trace_response.status_code == 200
    assert trace_response.json()["steps"][0]["workflow_node"] == "score_session"


def test_score_session_with_empty_transcripts_returns_empty_report() -> None:
    response = client.post(
        "/agent/sessions/sess_score_empty_asr/score",
        json={
            "session_state": {
                "answers": [
                    {
                        "turn_id": "turn_score_empty_asr",
                        "part": 2,
                        "question_text": "Describe a place you visited.",
                        "asr_text": "",
                        "audio_asset_id": "audio_score_empty_asr",
                    }
                ]
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    report = body["state"]["score_report"]

    assert body["next_action"] == "finish_session"
    assert body["state"]["status"] == "scored"
    assert body["state"]["scoring_warning"] == "no_transcript_recognized"
    assert "scoring_error" not in body["state"]
    assert report["overall_band"] == 0.0
    assert report["confidence"] == 0.1
    assert report["raw_report"]["scoring_status"] == "unscorable"
    assert body["state"]["feedback_items"]
    assert body["state"]["reference_answers"] == []
    assert event_payload(body, "report.ready")["unscorable"] is True


def test_plan_session_returns_examiner_message() -> None:
    response = client.post(
        "/agent/sessions/sess_001/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["next_action"] == "wait_for_user_answer"
    assert any(event["type"] == "examiner.message" for event in body["events"])
    examiner_message = event_payload(body, "examiner.message")
    assert "practice_hints" not in examiner_message
    assert examiner_message.get("practice_mode") is None
    assert body["state"]["question_plan"]["parts"][0]["timebox_seconds"] == 300
    assert len(body["state"]["question_plan"]["parts"][0]["questions"]) == 4
    assert body["state"]["status"] == "in_progress"
    assert body["state"]["mode_policy"]["prompt_profile"] == "examiner_exam"
    assert body["state"]["mode_policy"]["allow_structure_suggestions"] is False

    trace_response = client.get(f"/agent/runs/{body['run_id']}/trace")
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert trace["run_id"] == body["run_id"]
    assert trace["session_id"] == "sess_001"
    assert trace["mode"] == "full_exam"
    assert trace["part"] == 1
    assert trace["question_id"].startswith("planner_fallback_p1")
    assert trace["status"] == "completed"
    assert trace["user_id_hash"].startswith("sha256:")
    assert "user_001" not in trace["user_id_hash"]
    assert trace["steps"][0]["workflow_node"] == "plan_session"
    assert trace["steps"][0]["part"] == 1
    assert trace["steps"][0]["question_id"] == trace["question_id"]
    assert trace["steps"][0]["prompt_version"] == "mock.exam_workflow.v1"
    assert trace["steps"][0]["model_name"] is None
    assert trace["steps"][0]["latency_ms"] >= 0
    tool_calls = trace["steps"][0]["tool_calls"]
    assert tool_calls
    assert "search_questions" in {item["tool_name"] for item in tool_calls}
    assert {item["scope"] for item in tool_calls} == {"question_bank:read"}
    assert all(item["status"] in {"completed", "failed"} for item in tool_calls)
    if any(item["status"] == "failed" for item in tool_calls):
        assert body["state"]["question_plan"]["fallback_used"] is True
        assert any(item["error_code"] for item in tool_calls if item["status"] == "failed")

    run_response = client.get(f"/agent/runs/{body['run_id']}")
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "completed"


def test_full_exam_mode_policy_blocks_practice_ui_and_chinese_strategy_hints() -> None:
    response = client.post(
        "/agent/sessions/sess_exam_policy/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )

    assert response.status_code == 200
    body = response.json()

    for event in body["events"]:
        payload = event["payload"]
        policy = payload["mode_policy"]
        assert policy["prompt_profile"] == "examiner_exam"
        assert policy["ui_profile"] == "exam"
        assert policy["allow_practice_hints"] is False
        assert policy["allow_structure_suggestions"] is False
        assert policy["allow_chinese_strategy_hints"] is False
        assert "practice_hints" not in payload
        assert "practice_mode" not in payload
        assert "topic_guidance" not in payload
        assert not contains_cjk(json.dumps(payload, ensure_ascii=False))


def test_consume_asr_returns_followup_decision() -> None:
    response = client.post(
        "/agent/sessions/sess_001/consume-asr",
        json={"turn_id": "turn_001", "asr_text": "I come from Hangzhou and my email is learner@example.com."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["next_action"] == "ask_next_question"
    assert any(event["type"] == "asr.final" for event in body["events"])

    trace_response = client.get(f"/agent/runs/{body['run_id']}/trace")
    assert trace_response.status_code == 200
    trace = trace_response.json()
    input_summary = trace["steps"][0]["input_summary"]
    assert "turn_001" in input_summary
    assert "Hangzhou" not in input_summary
    assert "learner@example.com" not in input_summary


def test_consume_asr_short_answer_returns_followup_question() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_followup_001/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )
    assert plan_response.status_code == 200

    response = client.post(
        "/agent/sessions/sess_followup_001/consume-asr",
        json={
            "turn_id": "turn_short_001",
            "asr_text": "Yes, I do.",
            "session_state": plan_response.json()["state"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    followup = event_payload(body, "agent.followup_planned")
    examiner_message = event_payload(body, "examiner.message")

    assert body["next_action"] == "wait_for_user_answer"
    assert followup["decision"] == "ask_followup"
    assert followup["suggested_question"] == "Could you tell me a little more about that?"
    assert examiner_message["question_id"].startswith("followup_turn_short_001")
    assert examiner_message["text"] == followup["suggested_question"]
    assert body["state"]["followup_count"] == 1
    assert body["state"]["answers"][0]["turn_id"] == "turn_short_001"
    assert body["state"]["answers"][0]["part"] == 1
    assert body["state"]["answers"][0]["question_id"].startswith("planner_fallback_p1")
    assert body["state"]["answers"][0]["followup_decision"] == "ask_followup"

    trace_response = client.get(f"/agent/runs/{body['run_id']}/trace")
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert trace["part"] == 1
    assert trace["question_id"].startswith("planner_fallback_p1")
    assert trace["steps"][0]["workflow_node"] == "consume_asr"
    assert trace["steps"][0]["part"] == 1
    assert trace["steps"][0]["question_id"] == trace["question_id"]


def test_consume_asr_empty_transcript_continues_agent_flow() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_empty_asr/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )
    assert plan_response.status_code == 200

    response = client.post(
        "/agent/sessions/sess_empty_asr/consume-asr",
        json={
            "turn_id": "turn_empty_asr",
            "asr_text": "",
            "audio_asset_id": "audio_empty_asr",
            "session_state": plan_response.json()["state"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    asr_final = event_payload(body, "asr.final")
    followup = event_payload(body, "agent.followup_planned")

    assert body["next_action"] == "wait_for_user_answer"
    assert asr_final["text"] == ""
    assert followup["decision"] == "ask_followup"
    assert followup["word_count"] == 0
    assert body["state"]["answers"][0]["asr_text"] == ""


def test_consume_asr_practice_short_answer_keeps_practice_payload() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_followup_practice/plan",
        json={"mode": "part_practice", "user_id": "user_001", "part": 3},
    )
    assert plan_response.status_code == 200

    response = client.post(
        "/agent/sessions/sess_followup_practice/consume-asr",
        json={
            "turn_id": "turn_short_practice",
            "asr_text": "It is important.",
            "session_state": plan_response.json()["state"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    followup = event_payload(body, "agent.followup_planned")
    examiner_message = event_payload(body, "examiner.message")

    assert body["next_action"] == "wait_for_user_answer"
    assert followup["practice_mode"] is True
    assert examiner_message["practice_mode"] is True
    assert "practice_hints" in examiner_message
    assert examiner_message["text"] == "Why do you think this matters to people more generally?"


def test_cancel_run_updates_trace_status() -> None:
    response = client.post(
        "/agent/sessions/sess_cancel_001/plan",
        json={"mode": "full_exam", "user_id": "user_cancel"},
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    cancel_response = client.post(f"/agent/runs/{run_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    run_response = client.get(f"/agent/runs/{run_id}")
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "cancelled"


def test_unknown_run_trace_returns_404() -> None:
    response = client.get("/agent/runs/run_missing/trace")

    assert response.status_code == 404


def test_part_practice_plan_returns_practice_hints_and_cue_card() -> None:
    response = client.post(
        "/agent/sessions/sess_part_002/plan",
        json={"mode": "part_practice", "user_id": "user_001", "part": 2},
    )

    assert response.status_code == 200
    body = response.json()
    examiner_message = event_payload(body, "examiner.message")
    part_started = event_payload(body, "part.started")
    timer_started = event_payload(body, "timer.started")

    assert body["state"]["mode"] == "part_practice"
    assert body["state"]["status"] == "in_progress"
    assert body["state"]["mode_policy"]["prompt_profile"] == "coach_practice"
    assert body["state"]["mode_policy"]["allow_structure_suggestions"] is True
    assert body["state"]["practice_mode"] is True
    assert body["state"]["target_parts"] == [2]
    assert part_started["preparation_seconds"] == 60
    assert part_started["speaking_seconds"] == 120
    assert part_started["warning_seconds"] == [60, 30, 10]
    assert examiner_message["part"] == 2
    assert examiner_message["practice_mode"] is True
    assert len(examiner_message["practice_hints"]) >= 1
    assert examiner_message["cue_card"]["preparation_seconds"] == 60
    assert examiner_message["cue_card"]["speaking_seconds"] == 120
    assert examiner_message["timer_policy"]["preparation_seconds"] == 60
    assert examiner_message["timer_policy"]["speaking_seconds"] == 120
    assert examiner_message["timer_policy"]["warning_seconds"] == [60, 30, 10]
    assert timer_started["phase"] == "prepare_then_speak"
    assert timer_started["preparation_seconds"] == 60
    assert timer_started["speaking_seconds"] == 120


def test_practice_mode_policy_allows_structure_suggestions() -> None:
    response = client.post(
        "/agent/sessions/sess_practice_policy/plan",
        json={"mode": "part_practice", "user_id": "user_001", "part": 1},
    )

    assert response.status_code == 200
    body = response.json()
    part_started = event_payload(body, "part.started")
    examiner_message = event_payload(body, "examiner.message")
    timer_started = event_payload(body, "timer.started")

    for payload in [part_started, examiner_message, timer_started]:
        policy = payload["mode_policy"]
        assert policy["prompt_profile"] == "coach_practice"
        assert policy["ui_profile"] == "practice"
        assert policy["allow_practice_hints"] is True
        assert policy["allow_structure_suggestions"] is True
        assert policy["allow_reference_answer"] is True
        assert policy["scoring_strictness"] == "diagnostic"

    assert part_started["practice_hints"]
    assert examiner_message["practice_hints"]


def test_part_practice_can_select_part_one_two_and_three() -> None:
    for part in [1, 2, 3]:
        response = client.post(
            f"/agent/sessions/sess_part_select_{part}/plan",
            json={"mode": "part_practice", "user_id": "user_001", "part": part},
        )
        assert response.status_code == 200
        body = response.json()
        part_started = event_payload(body, "part.started")
        examiner_message = event_payload(body, "examiner.message")

        assert body["state"]["target_parts"] == [part]
        assert body["state"]["current_part"] == part
        assert body["state"]["status"] == "in_progress"
        assert part_started["part"] == part
        assert part_started["practice_mode"] is True
        assert "practice_hints" in part_started
        assert examiner_message["part"] == part
        assert examiner_message["practice_mode"] is True
        assert "practice_hints" in examiner_message


def test_part_practice_asr_state_records_answer() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_part_answer/plan",
        json={"mode": "part_practice", "user_id": "user_001", "part": 2},
    )
    assert plan_response.status_code == 200

    response = client.post(
        "/agent/sessions/sess_part_answer/consume-asr",
        json={
            "turn_id": "turn_part_answer_001",
            "asr_text": "I would like to describe a public library near my home.",
            "audio_asset_id": "audio_001",
            "asr_confidence": 0.88,
            "session_state": plan_response.json()["state"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    answer = body["state"]["answers"][0]

    assert answer["turn_id"] == "turn_part_answer_001"
    assert answer["part"] == 2
    assert answer["audio_asset_id"] == "audio_001"
    assert answer["asr_confidence"] == 0.88
    assert answer["practice_mode"] is True
    assert answer["question_id"].startswith("planner_fallback_p2")


def test_topic_practice_can_move_from_part_one_to_part_two() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_topic_001/plan",
        json={"mode": "topic_practice", "user_id": "user_001", "topic_ids": ["topic_city"]},
    )
    assert plan_response.status_code == 200
    state = plan_response.json()["state"]

    current_state = state
    for _ in range(3):
        next_question = client.post(
            "/agent/sessions/sess_topic_001/next-turn",
            json={"session_state": current_state},
        )
        assert next_question.status_code == 200
        assert next_question.json()["next_action"] == "wait_for_user_answer"
        current_state = next_question.json()["state"]

    part_two = client.post(
        "/agent/sessions/sess_topic_001/next-turn",
        json={"session_state": current_state},
    )
    assert part_two.status_code == 200
    body = part_two.json()
    part_started = event_payload(body, "part.started")
    examiner_message = event_payload(body, "examiner.message")

    assert part_started["part"] == 2
    assert part_started["practice_mode"] is True
    assert part_started["topic_ids"] == ["topic_city"]
    assert examiner_message["part"] == 2
    assert examiner_message["topic_ids"] == ["topic_city"]
    assert "practice_hints" in examiner_message
    assert body["next_action"] == "wait_for_user_answer"


def test_topic_practice_plan_returns_topic_guidance_and_rendered_questions() -> None:
    response = client.post(
        "/agent/sessions/sess_topic_guidance/plan",
        json={"mode": "topic_practice", "user_id": "user_001", "topic_ids": ["technology"]},
    )

    assert response.status_code == 200
    body = response.json()
    session_started = event_payload(body, "session.started")
    part_started = event_payload(body, "part.started")
    examiner_message = event_payload(body, "examiner.message")
    guidance = body["state"]["topic_guidance"]
    first_question = body["state"]["question_plan"]["parts"][0]["questions"][0]

    assert body["state"]["topic_ids"] == ["technology"]
    assert guidance["primary_topic"] == "technology"
    assert body["state"]["mode_policy"]["allow_topic_guidance"] is True
    assert "digital tools" in guidance["vocabulary"]
    assert len(guidance["useful_expressions"]) >= 1
    assert session_started["topic_guidance"] == guidance
    assert part_started["topic_guidance"] == guidance
    assert examiner_message["topic_guidance"] == guidance
    assert first_question["topic"] == "technology"
    assert "selected topic" not in first_question["text"].lower()
    assert "technology" in first_question["text"].lower()


def test_topic_practice_asr_and_completion_preserve_feedback_seed() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_topic_complete/plan",
        json={"mode": "topic_practice", "user_id": "user_001", "topic_ids": ["travel"], "part": 2},
    )
    assert plan_response.status_code == 200
    state = plan_response.json()["state"]

    asr_response = client.post(
        "/agent/sessions/sess_topic_complete/consume-asr",
        json={
            "turn_id": "turn_topic_001",
            "asr_text": "I want to describe a short trip I took with my classmates.",
            "session_state": state,
            "asr_confidence": 0.86,
        },
    )
    assert asr_response.status_code == 200
    state = asr_response.json()["state"]
    answer = state["answers"][0]

    assert answer["topic_ids"] == ["travel"]
    assert answer["topic_guidance"]["primary_topic"] == "travel"
    assert "itinerary" in answer["topic_guidance"]["vocabulary"]

    completed = client.post(
        "/agent/sessions/sess_topic_complete/next-turn",
        json={"session_state": state},
    )
    assert completed.status_code == 200
    body = completed.json()
    session_completed = event_payload(body, "session.completed")
    scoring_started = event_payload(body, "scoring.started")

    assert body["next_action"] == "score_session"
    assert body["state"]["status"] == "scoring"
    assert session_completed["topic_ids"] == ["travel"]
    assert session_completed["topic_guidance"]["primary_topic"] == "travel"
    assert scoring_started["run_reason"] == "practice_completed"
    assert scoring_started["mode_policy"]["allow_topic_guidance"] is True
    assert scoring_started["topic_guidance"]["useful_expressions"]


def test_full_exam_part_one_timebox_can_transition_to_part_two() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_part1_timebox/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )
    assert plan_response.status_code == 200
    state = plan_response.json()["state"]
    state["part_elapsed_seconds"] = 300

    response = client.post(
        "/agent/sessions/sess_part1_timebox/next-turn",
        json={"session_state": state},
    )

    assert response.status_code == 200
    body = response.json()
    part_completed = event_payload(body, "part.completed")
    part_started = event_payload(body, "part.started")
    examiner_message = event_payload(body, "examiner.message")
    timer_started = event_payload(body, "timer.started")

    assert part_completed["part"] == 1
    assert part_completed["reason"] == "timebox_reached"
    assert part_completed["elapsed_seconds"] == 300
    assert part_started["part"] == 2
    assert part_started["timebox_seconds"] == 180
    assert part_started["preparation_seconds"] == 60
    assert part_started["speaking_seconds"] == 120
    assert part_started["warning_seconds"] == [60, 30, 10]
    assert examiner_message["part"] == 2
    assert examiner_message["cue_card"]["preparation_seconds"] == 60
    assert examiner_message["cue_card"]["speaking_seconds"] == 120
    assert examiner_message["timer_policy"]["preparation_seconds"] == 60
    assert examiner_message["timer_policy"]["speaking_seconds"] == 120
    assert examiner_message["timer_policy"]["warning_seconds"] == [60, 30, 10]
    assert timer_started["phase"] == "prepare_then_speak"
    assert timer_started["preparation_seconds"] == 60
    assert timer_started["speaking_seconds"] == 120
    assert timer_started["warning_seconds"] == [60, 30, 10]
    assert body["state"]["current_part"] == 2
    assert body["state"]["part_elapsed_seconds"] == 0


def test_full_exam_part_two_can_transition_to_linked_part_three() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_part3_transition/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )
    assert plan_response.status_code == 200
    state = plan_response.json()["state"]
    state["part_elapsed_seconds"] = 300

    part_two_response = client.post(
        "/agent/sessions/sess_part3_transition/next-turn",
        json={"session_state": state},
    )
    assert part_two_response.status_code == 200
    part_two_state = part_two_response.json()["state"]

    part_three_response = client.post(
        "/agent/sessions/sess_part3_transition/next-turn",
        json={"session_state": part_two_state},
    )

    assert part_three_response.status_code == 200
    body = part_three_response.json()
    part_completed = event_payload(body, "part.completed")
    part_started = event_payload(body, "part.started")
    examiner_message = event_payload(body, "examiner.message")
    timer_started = event_payload(body, "timer.started")

    assert part_completed["part"] == 2
    assert part_started["part"] == 3
    assert part_started["discussion_level"] in {"social", "abstract"}
    assert part_started["discussion_focus"] == "public_places"
    assert part_started["linked_part2_question_id"].startswith("planner_fallback_p2")
    assert part_started["linked_part2_topic"] == "place"
    assert examiner_message["part"] == 3
    assert examiner_message["linked_part2_topic"] == "place"
    assert examiner_message["discussion_focus"] == "public_places"
    assert len(examiner_message["text"].split()) <= 18
    assert timer_started["part"] == 3
    assert timer_started["suggested_seconds"] == 45
    assert timer_started["timebox_seconds"] == 300
    assert body["state"]["current_part"] == 3
    assert body["state"]["question_index"] == 0
    assert body["next_action"] == "wait_for_user_answer"


def test_full_exam_can_complete_all_parts_and_enter_scoring() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_full_exam_complete/plan",
        json={"mode": "full_exam", "user_id": "user_001"},
    )
    assert plan_response.status_code == 200
    state = plan_response.json()["state"]

    asr_response = client.post(
        "/agent/sessions/sess_full_exam_complete/consume-asr",
        json={
            "turn_id": "turn_full_001",
            "asr_text": "I come from a small city, and I enjoy living there because it is calm and convenient.",
            "session_state": state,
            "asr_confidence": 0.91,
        },
    )
    assert asr_response.status_code == 200
    state = asr_response.json()["state"]
    assert state["answers"][0]["asr_confidence"] == 0.91

    state["part_elapsed_seconds"] = 300
    part_two_response = client.post(
        "/agent/sessions/sess_full_exam_complete/next-turn",
        json={"session_state": state},
    )
    assert part_two_response.status_code == 200
    state = part_two_response.json()["state"]
    assert state["current_part"] == 2
    assert state["answers"][0]["turn_id"] == "turn_full_001"

    part_three_response = client.post(
        "/agent/sessions/sess_full_exam_complete/next-turn",
        json={"session_state": state},
    )
    assert part_three_response.status_code == 200
    state = part_three_response.json()["state"]
    assert state["current_part"] == 3
    assert state["completed_parts"] == [1, 2]

    part_three_second_question = client.post(
        "/agent/sessions/sess_full_exam_complete/next-turn",
        json={"session_state": state},
    )
    assert part_three_second_question.status_code == 200
    state = part_three_second_question.json()["state"]
    assert state["current_part"] == 3
    assert state["question_index"] == 1

    completed = client.post(
        "/agent/sessions/sess_full_exam_complete/next-turn",
        json={"session_state": state},
    )
    assert completed.status_code == 200
    body = completed.json()
    session_completed = event_payload(body, "session.completed")
    scoring_started = event_payload(body, "scoring.started")

    assert body["next_action"] == "score_session"
    assert body["state"]["status"] == "scoring"
    assert body["state"]["completed_parts"] == [1, 2, 3]
    assert body["state"]["answers"][0]["turn_id"] == "turn_full_001"
    assert session_completed["completed_parts"] == [1, 2, 3]
    assert session_completed["status"] == "scoring"
    assert scoring_started["run_reason"] == "session_completed"
    assert scoring_started["completed_parts"] == [1, 2, 3]
    assert scoring_started["answer_count"] == 1


def test_part_practice_finishes_after_target_part() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_part_001/plan",
        json={"mode": "part_practice", "user_id": "user_001", "part": 1},
    )
    assert plan_response.status_code == 200
    state = plan_response.json()["state"]

    current_state = state
    for _ in range(3):
        next_response = client.post(
            "/agent/sessions/sess_part_001/next-turn",
            json={"session_state": current_state},
        )
        assert next_response.status_code == 200
        assert next_response.json()["next_action"] == "wait_for_user_answer"
        current_state = next_response.json()["state"]

    completed = client.post(
        "/agent/sessions/sess_part_001/next-turn",
        json={"session_state": current_state},
    )
    assert completed.status_code == 200
    body = completed.json()

    assert body["next_action"] == "score_session"
    assert any(event["type"] == "session.completed" for event in body["events"])
    assert any(event["type"] == "scoring.started" for event in body["events"])
    assert body["state"]["completed_parts"] == [1]
    assert body["state"]["status"] == "scoring"
    assert event_payload(body, "session.completed")["status"] == "scoring"
    assert event_payload(body, "scoring.started")["run_reason"] == "practice_completed"


def test_part_practice_part_two_finishes_immediately_after_long_turn() -> None:
    plan_response = client.post(
        "/agent/sessions/sess_part2_done/plan",
        json={"mode": "part_practice", "user_id": "user_001", "part": 2},
    )
    assert plan_response.status_code == 200

    completed = client.post(
        "/agent/sessions/sess_part2_done/next-turn",
        json={"session_state": plan_response.json()["state"]},
    )

    assert completed.status_code == 200
    body = completed.json()
    scoring_started = event_payload(body, "scoring.started")

    assert body["next_action"] == "score_session"
    assert body["state"]["completed_parts"] == [2]
    assert body["state"]["status"] == "scoring"
    assert scoring_started["practice_mode"] is True
    assert scoring_started["completed_parts"] == [2]


def event_payload(body: dict, event_type: str) -> dict:
    return next(event["payload"] for event in body["events"] if event["type"] == event_type)


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)
