import pytest

from app.mcp.question_bank_mcp import QuestionBankMcpTools
from app.mcp.security import McpAuthorizationError, McpToolContext
from app.rag.ingestion.question_bank_indexer import QuestionBankIndexer, QuestionBankRecord
from app.rag.llamaindex_service import (
    HashEmbeddingProvider,
    InMemoryKnowledgeStore,
    KnowledgeSearchResult,
    LlamaIndexKnowledgeService,
)


ACTIVE_SEASON_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CITY_QUESTION_ID = "11111111-1111-1111-1111-111111111111"
FOOD_QUESTION_ID = "22222222-2222-2222-2222-222222222222"
VALID_PART3_QUESTION_ID = "33333333-3333-3333-3333-333333333333"
PLACEHOLDER_PART3_QUESTION_ID = "44444444-4444-4444-4444-444444444444"


def test_search_questions_requires_scope_and_returns_source_refs() -> None:
    tools = make_tools()
    context = McpToolContext(
        user_id="user_1",
        session_id="sess_1",
        scopes=["question_bank:read"],
        allowed_tools=["search_questions"],
    )

    result = tools.search_questions(
        context,
        query="public transport",
        active_season_id=ACTIVE_SEASON_ID,
        part=1,
        topic="city",
        top_k=1,
    )

    assert result.user_id == "user_1"
    assert result.session_id == "sess_1"
    assert result.results[0].question_id == CITY_QUESTION_ID
    assert result.results[0].part == 1
    assert result.results[0].source_ref.doc_id == CITY_QUESTION_ID
    assert result.results[0].source_ref.chunk_id


def test_question_bank_tool_rejects_missing_scope() -> None:
    tools = make_tools()
    context = McpToolContext(user_id="user_1", session_id="sess_1", scopes=[])

    with pytest.raises(McpAuthorizationError, match="missing required scope"):
        tools.search_questions(context, query="city")


def test_question_bank_tool_rejects_disallowed_tool() -> None:
    tools = make_tools()
    context = McpToolContext(
        user_id="user_1",
        session_id="sess_1",
        scopes=["question_bank:read"],
        allowed_tools=["search_questions"],
    )

    with pytest.raises(McpAuthorizationError, match="tool is not allowed"):
        tools.get_cue_card(context, question_id=FOOD_QUESTION_ID)


def test_get_cue_card_returns_structured_part_two_metadata() -> None:
    tools = make_tools()
    context = read_context(allowed_tools=["get_cue_card"])

    cue_card = tools.get_cue_card(context, question_id=FOOD_QUESTION_ID)

    assert cue_card is not None
    assert cue_card.question_id == FOOD_QUESTION_ID
    assert cue_card.cue_card_id == "66666666-6666-6666-6666-666666666666"
    assert cue_card.prompt == "Describe a meal you enjoyed with other people."
    assert cue_card.bullet_points == ["what the meal was", "who you ate with", "why you remember it"]
    assert cue_card.preparation_seconds == 60
    assert cue_card.speaking_seconds == 120
    assert cue_card.source_ref.doc_id == FOOD_QUESTION_ID


def test_get_cue_card_returns_none_for_non_cue_card_question() -> None:
    tools = make_tools()
    context = read_context(allowed_tools=["get_cue_card"])

    assert tools.get_cue_card(context, question_id=CITY_QUESTION_ID) is None


def test_get_followup_templates_filters_by_part_and_ignores_archived_items() -> None:
    tools = make_tools()
    context = read_context(allowed_tools=["get_followup_templates"])

    result = tools.get_followup_templates(context, question_id=FOOD_QUESTION_ID, part=3)

    assert [item.text for item in result.followups] == [
        "Why do people like eating together?",
        "Do restaurants change family life?",
    ]
    assert all(item.part == 3 for item in result.followups)
    assert all(item.source_ref.doc_id == FOOD_QUESTION_ID for item in result.followups)


def test_search_questions_skips_placeholder_question_records() -> None:
    tools = QuestionBankMcpTools(FakeSearchIndexer())
    context = read_context(allowed_tools=["search_questions"])

    result = tools.search_questions(
        context,
        query="travel",
        active_season_id=ACTIVE_SEASON_ID,
        part=3,
        top_k=5,
    )

    assert [item.question_id for item in result.results] == [VALID_PART3_QUESTION_ID]
    assert all("待补充" not in item.content for item in result.results)


def make_tools() -> QuestionBankMcpTools:
    indexer = QuestionBankIndexer(make_memory_service())
    indexer.index_records(make_question_records(), active_season_id=ACTIVE_SEASON_ID)
    return QuestionBankMcpTools(indexer)


def make_memory_service() -> LlamaIndexKnowledgeService:
    return LlamaIndexKnowledgeService(
        store=InMemoryKnowledgeStore(),
        embedding_provider=HashEmbeddingProvider(),
        chunk_max_chars=1200,
        chunk_overlap_chars=120,
    )


def read_context(*, allowed_tools: list[str]) -> McpToolContext:
    return McpToolContext(
        user_id="user_1",
        session_id="sess_1",
        scopes=["question_bank:read"],
        allowed_tools=allowed_tools,
    )


def make_question_records() -> list[QuestionBankRecord]:
    return [
        QuestionBankRecord(
            question_id=CITY_QUESTION_ID,
            season_id=ACTIVE_SEASON_ID,
            part=1,
            text="Do you like public transport and parks in your city?",
            topic="city",
            source_type="original",
            review_status="active",
        ),
        QuestionBankRecord(
            question_id=FOOD_QUESTION_ID,
            season_id=ACTIVE_SEASON_ID,
            part=2,
            text="Describe a restaurant where you enjoyed cooking and food.",
            topic="food",
            source_type="authorized",
            review_status="active",
            cue_card={
                "cue_card_id": "66666666-6666-6666-6666-666666666666",
                "prompt": "Describe a meal you enjoyed with other people.",
                "bullet_points": ["what the meal was", "who you ate with", "why you remember it"],
                "preparation_seconds": 60,
                "speaking_seconds": 120,
            },
            followup_templates=[
                {
                    "followup_id": "77777777-7777-7777-7777-777777777777",
                    "part": 3,
                    "text": "Why do people like eating together?",
                    "sort_order": 1,
                    "review_status": "active",
                },
                {
                    "followup_id": "88888888-8888-8888-8888-888888888888",
                    "part": 3,
                    "text": "Archived follow-up",
                    "sort_order": 2,
                    "review_status": "archived",
                },
                {
                    "followup_id": "99999999-9999-9999-9999-999999999999",
                    "part": 3,
                    "text": "Do restaurants change family life?",
                    "sort_order": 3,
                    "review_status": "active",
                },
            ],
        ),
        QuestionBankRecord(
            question_id=VALID_PART3_QUESTION_ID,
            season_id=ACTIVE_SEASON_ID,
            part=3,
            text="Why do some families eat together less often now?",
            topic="food",
            source_type="authorized",
            review_status="active",
        ),
        QuestionBankRecord(
            question_id=PLACEHOLDER_PART3_QUESTION_ID,
            season_id=ACTIVE_SEASON_ID,
            part=3,
            text="待补充",
            topic="food",
            source_type="authorized",
            review_status="active",
        ),
    ]


class FakeSearchIndexer:
    def search_questions(self, *args: object, **kwargs: object) -> list[KnowledgeSearchResult]:
        return [
            KnowledgeSearchResult(
                chunk_id="chunk_valid",
                doc_id=VALID_PART3_QUESTION_ID,
                doc_type="question_bank",
                title="Part 3 travel: valid",
                content="Question: Why do some people enjoy travelling alone?",
                metadata={
                    "question_id": VALID_PART3_QUESTION_ID,
                    "part": "3",
                    "topic": "travel",
                    "season_id": ACTIVE_SEASON_ID,
                },
                score=0.92,
            ),
            KnowledgeSearchResult(
                chunk_id="chunk_placeholder",
                doc_id=PLACEHOLDER_PART3_QUESTION_ID,
                doc_type="question_bank",
                title="Part 3 travel: placeholder",
                content="Question: 待补充",
                metadata={
                    "question_id": PLACEHOLDER_PART3_QUESTION_ID,
                    "part": "3",
                    "topic": "travel",
                    "season_id": ACTIVE_SEASON_ID,
                },
                score=0.99,
            ),
        ]
