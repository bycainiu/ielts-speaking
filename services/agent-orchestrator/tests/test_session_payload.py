from app.rules.session_payload import cue_card_payload, examiner_message_payload, timer_started_payload


def test_examiner_message_payload_includes_part2_cue_card() -> None:
    question = {
        "question_id": "planner_fallback_p2_q1",
        "part": 2,
        "text": "Describe a place in your city that you enjoy visiting.",
        "cue_card": {
            "prompt": "Describe a place in your city that you enjoy visiting.",
            "bullet_points": ["where it is", "how often you go there", "what you do there", "why you enjoy it"],
            "preparation_seconds": 60,
            "speaking_seconds": 120,
        },
    }
    payload = examiner_message_payload(
        part=2,
        question=question,
        examiner_text="Now I'm going to give you a topic...",
        source="live_examiner",
    )
    assert payload["cue_card"]["prompt"] == question["cue_card"]["prompt"]
    assert len(payload["cue_card"]["bullet_points"]) == 4
    assert payload["timer_policy"]["preparation_seconds"] == 60


def test_cue_card_payload_falls_back_to_default_bullets() -> None:
    question = {"text": "Describe a book you recently read."}
    cue = cue_card_payload(question)
    assert cue["prompt"] == "Describe a book you recently read."
    assert cue["bullet_points"]


def test_timer_started_payload_for_part2_uses_preparation_phase() -> None:
    question = {"text": "Describe a place in your city that you enjoy visiting.", "cue_card": cue_card_payload({"text": "Describe a place in your city that you enjoy visiting."})}
    payload = timer_started_payload(part=2, question=question)
    assert payload["phase"] == "prepare_then_speak"
    assert payload["purpose"] == "preparation"
    assert payload["preparation_seconds"] == 60
