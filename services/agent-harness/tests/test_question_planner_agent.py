from app.agents.question_planner_agent import QuestionSetPlannerAgent, extract_question_text
from app.mcp.question_bank_mcp import McpSourceRef, QuestionSearchItem, SearchQuestionsResult
from app.mcp.security import McpToolContext
from app.protocols.schemas import PlanRequest


def test_full_exam_question_plan_contains_all_parts_with_default_counts() -> None:
    planner = QuestionSetPlannerAgent()

    plan = planner.plan(PlanRequest(mode="full_exam", user_id="user_001"))

    assert plan.target_parts == [1, 2, 3]
    assert [part.part for part in plan.parts] == [1, 2, 3]
    assert [len(part.questions) for part in plan.parts] == [4, 1, 2]
    assert plan.fallback_used is True
    assert all(question.question_id for part in plan.parts for question in part.questions)
    assert {question.topic for question in plan.parts[0].questions} == {
        "hometown",
        "work_or_study",
        "daily_routine",
    }


def test_part_three_questions_are_linked_to_part_two_context() -> None:
    planner = QuestionSetPlannerAgent()

    plan = planner.plan(PlanRequest(mode="full_exam", user_id="user_001"))

    part_two_question = plan.parts[1].questions[0]
    part_three_questions = plan.parts[2].questions

    assert all(question.linked_part2_question_id == part_two_question.question_id for question in part_three_questions)
    assert all(question.linked_part2_topic == part_two_question.topic for question in part_three_questions)
    assert {question.discussion_level for question in part_three_questions}.issubset({"social", "abstract"})
    assert {question.discussion_focus for question in part_three_questions} == {"public_places"}
    assert all(len(question.text.split()) <= 14 for question in part_three_questions)


def test_part_practice_question_plan_only_contains_target_part_and_cue_card() -> None:
    planner = QuestionSetPlannerAgent()

    plan = planner.plan(PlanRequest(mode="part_practice", user_id="user_001", part=2))

    assert plan.target_parts == [2]
    assert [part.part for part in plan.parts] == [2]
    assert plan.parts[0].questions[0].cue_card is not None
    assert plan.parts[0].questions[0].timer_policy == {"suggested_seconds": 120}


def test_topic_practice_question_plan_preserves_topics_and_all_parts() -> None:
    planner = QuestionSetPlannerAgent()

    plan = planner.plan(
        PlanRequest(mode="topic_practice", user_id="user_001", topic_ids=["work", "technology"])
    )

    assert plan.target_parts == [1, 2, 3]
    assert plan.topic_ids == ["work", "technology"]
    assert plan.parts[0].questions[0].topic == "work"
    assert "selected topic" not in plan.parts[0].questions[0].text.lower()
    assert "work" in plan.parts[0].questions[0].text.lower()
    assert "work" in plan.parts[1].questions[0].text.lower()
    assert plan.parts[2].questions[0].linked_part2_topic == "work"
    assert plan.parts[2].questions[0].discussion_focus == "education_and_work"


def test_question_bank_candidates_are_cleaned_and_deduplicated() -> None:
    planner = QuestionSetPlannerAgent(FakeQuestionBankTools(), part_counts={1: 2})

    plan = planner.plan(PlanRequest(mode="part_practice", user_id="user_001", part=1, season_id="season_001"))

    questions = plan.parts[0].questions
    assert plan.fallback_used is False
    assert [question.question_id for question in questions] == ["q_city_1", "q_transport_1"]
    assert questions[0].text == "Do you like parks in your city?"
    assert "Question:" not in questions[0].text
    assert all(question.evidence.source == "question_bank" for question in questions)


def test_seeded_question_bank_plan_varies_between_sessions() -> None:
    planner = QuestionSetPlannerAgent(FakeDiverseQuestionBankTools(), part_counts={1: 2})

    first = planner.plan(PlanRequest(mode="part_practice", user_id="user_001", part=1, session_seed="session_alpha"))
    second = planner.plan(PlanRequest(mode="part_practice", user_id="user_001", part=1, session_seed="session_beta"))
    repeat = planner.plan(PlanRequest(mode="part_practice", user_id="user_001", part=1, session_seed="session_alpha"))

    first_ids = [question.question_id for question in first.parts[0].questions]
    second_ids = [question.question_id for question in second.parts[0].questions]
    repeat_ids = [question.question_id for question in repeat.parts[0].questions]
    assert first_ids == repeat_ids
    assert first_ids != second_ids


def test_topic_uuid_filters_question_bank_and_uses_topic_label_for_query() -> None:
    tools = FakeTopicFilterQuestionBankTools()
    planner = QuestionSetPlannerAgent(tools, part_counts={1: 1})
    topic_id = "98c563b1-7c26-5843-bb66-1333484f6468"

    plan = planner.plan(
        PlanRequest(
            mode="topic_practice",
            user_id="user_001",
            part=1,
            season_id="season_001",
            topic_ids=[topic_id],
            topic_labels=["App"],
            session_seed="session_topic",
        )
    )

    assert tools.last_topic_id == topic_id
    assert tools.queries
    assert topic_id not in tools.queries[0]
    assert "App" in tools.queries[0]
    assert plan.parts[0].questions[0].topic == "apps"


def test_extract_question_text_prefers_question_line() -> None:
    content = "Title line\nQuestion: What kind of public transport do you use?\n\nFollow-up questions:\n- Why?"

    assert extract_question_text(content) == "What kind of public transport do you use?"


class FakeQuestionBankTools:
    def search_questions(
        self,
        context: McpToolContext,
        *,
        query: str,
        active_season_id: str | None = None,
        part: int | None = None,
        top_k: int = 5,
        **_: object,
    ) -> SearchQuestionsResult:
        assert context.user_id == "user_001"
        assert context.scopes == ["question_bank:read"]
        assert set(context.allowed_tools) >= {"search_questions", "get_cue_card", "get_followup_templates"}
        assert active_season_id == "season_001"
        assert part == 1
        return SearchQuestionsResult(
            user_id=context.user_id,
            session_id=context.session_id,
            results=[
                make_search_item("q_city_1", "Question: Do you like parks in your city?"),
                make_search_item("q_city_1", "Question: Do you like parks in your city?"),
                make_search_item("q_city_2", "Question: Do you like the parks in your city?"),
                make_search_item("q_transport_1", "Question: What public transport do you usually use?"),
            ],
        )


class FakeDiverseQuestionBankTools:
    def search_questions(
        self,
        context: McpToolContext,
        *,
        query: str,
        active_season_id: str | None = None,
        part: int | None = None,
        top_k: int = 5,
        **_: object,
    ) -> SearchQuestionsResult:
        return SearchQuestionsResult(
            user_id=context.user_id,
            session_id=context.session_id,
            results=[
                make_search_item("q_music_1", "Question: What kind of music do you enjoy?"),
                make_search_item("q_books_1", "Question: What kinds of books do you read?"),
                make_search_item("q_food_1", "Question: What food do you usually cook?"),
                make_search_item("q_apps_1", "Question: What apps do you often use?"),
            ],
        )


class FakeTopicFilterQuestionBankTools:
    def __init__(self) -> None:
        self.last_topic_id: str | None = None
        self.queries: list[str] = []

    def search_questions(
        self,
        context: McpToolContext,
        *,
        query: str,
        active_season_id: str | None = None,
        part: int | None = None,
        topic_id: str | None = None,
        top_k: int = 5,
        **_: object,
    ) -> SearchQuestionsResult:
        self.last_topic_id = topic_id
        self.queries.append(query)
        assert active_season_id == "season_001"
        assert part == 1
        return SearchQuestionsResult(
            user_id=context.user_id,
            session_id=context.session_id,
            results=[make_search_item("q_app_1", "Question: What app do you use every day?", topic="apps")],
        )


def make_search_item(question_id: str, content: str, *, topic: str = "city") -> QuestionSearchItem:
    return QuestionSearchItem(
        question_id=question_id,
        part=1,
        topic=topic,
        season_id="season_001",
        title=f"Part 1 {topic}: {question_id}",
        content=content,
        score=0.91,
        source_ref=McpSourceRef(doc_id=question_id, chunk_id=f"chunk_{question_id}"),
    )
