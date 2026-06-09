from app.agents.followup_planner_agent import FollowupPlannerAgent, FollowupPlannerInput, contains_sensitive_signal, count_words


def test_followup_planner_asks_natural_followup_for_short_part_one_answer() -> None:
    plan = FollowupPlannerAgent().plan(
        FollowupPlannerInput(mode="full_exam", part=1, asr_text="Yes, I do.", question_index=0)
    )

    assert plan.decision.decision == "ask_followup"
    assert plan.next_action == "wait_for_user_answer"
    assert plan.decision.suggested_question == "Could you tell me a little more about that?"
    assert plan.word_count == 3


def test_followup_planner_uses_more_abstract_part_three_followup() -> None:
    plan = FollowupPlannerAgent().plan(
        FollowupPlannerInput(mode="full_exam", part=3, asr_text="Because it is useful.", question_index=0)
    )

    assert plan.decision.decision == "ask_followup"
    assert plan.decision.suggested_question == "Why do you think this matters to people more generally?"


def test_followup_planner_skips_sensitive_private_details() -> None:
    plan = FollowupPlannerAgent().plan(
        FollowupPlannerInput(mode="full_exam", part=1, asr_text="My email is learner@example.com.", question_index=0)
    )

    assert plan.decision.decision == "next_question"
    assert plan.next_action == "ask_next_question"
    assert plan.privacy_guarded is True
    assert plan.decision.suggested_question is None


def test_followup_planner_does_not_over_followup_same_question() -> None:
    plan = FollowupPlannerAgent().plan(
        FollowupPlannerInput(
            mode="part_practice",
            part=2,
            asr_text="It was nice.",
            question_index=0,
            followup_count=1,
        )
    )

    assert plan.decision.decision == "next_question"
    assert plan.next_action == "ask_next_question"


def test_followup_helpers_count_words_and_detect_sensitive_signals() -> None:
    assert count_words("Well, I've lived there for five years.") == 7
    assert contains_sensitive_signal("My phone number is 138 0000 0000") is True
