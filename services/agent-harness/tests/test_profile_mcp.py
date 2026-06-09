import pytest

from app.mcp.profile_mcp import (
    PostgresProfilePrivacySource,
    ProfileMcpTools,
    build_privacy_exclusions_select_sql,
)
from app.mcp.security import McpAuthorizationError, McpToolContext
from app.rag.ingestion.user_profile_indexer import UserProfileIndexer
from app.rag.llamaindex_service import HashEmbeddingProvider, InMemoryKnowledgeStore, LlamaIndexKnowledgeService


USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_USER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
HOBBY_FACT_ID = "11111111-1111-1111-1111-111111111111"
GRAMMAR_FACT_ID = "22222222-2222-2222-2222-222222222222"
OTHER_FACT_ID = "33333333-3333-3333-3333-333333333333"


def test_get_user_background_summary_uses_context_user_scope() -> None:
    tools = make_tools()
    context = read_context(allowed_tools=["get_user_background_summary"])

    result = tools.get_user_background_summary(
        context,
        query="cooking at home",
        topic="hobbies",
        allowed_usage=["question_personalization"],
    )

    assert result.user_id == USER_ID
    assert result.session_id == "sess_1"
    assert [fact.fact_id for fact in result.facts] == [HOBBY_FACT_ID]
    assert "cooking meals at home" in result.summary_text
    assert result.facts[0].source_ref["doc_id"]


def test_get_user_background_summary_does_not_cross_user_boundary() -> None:
    tools = make_tools()
    context = read_context(allowed_tools=["get_user_background_summary"])

    result = tools.get_user_background_summary(context, query="Band 8 other user", top_k=5)

    assert all(fact.fact_id != OTHER_FACT_ID for fact in result.facts)
    assert "Another user" not in result.summary_text


def test_get_user_background_summary_filters_allowed_usage() -> None:
    tools = make_tools()
    context = read_context(allowed_tools=["get_user_background_summary"])

    result = tools.get_user_background_summary(
        context,
        query="past tense endings",
        allowed_usage=["scoring_context"],
    )

    assert [fact.fact_id for fact in result.facts] == [GRAMMAR_FACT_ID]
    assert result.facts[0].allowed_usage == ["scoring_context", "feedback_personalization"]


def test_profile_mcp_rejects_missing_scope() -> None:
    tools = make_tools()
    context = McpToolContext(user_id=USER_ID, session_id="sess_1", scopes=[])

    with pytest.raises(McpAuthorizationError, match="missing required scope"):
        tools.get_user_background_summary(context)


def test_profile_mcp_rejects_disallowed_tool() -> None:
    tools = make_tools()
    context = read_context(allowed_tools=["get_privacy_exclusions"])

    with pytest.raises(McpAuthorizationError, match="tool is not allowed"):
        tools.get_user_background_summary(context)


def test_get_privacy_exclusions_reads_context_user_only() -> None:
    source = FakePrivacySource({USER_ID: ["workplace", "salary", "salary"], OTHER_USER_ID: ["family"]})
    tools = make_tools(privacy_source=source)
    context = read_context(allowed_tools=["get_privacy_exclusions"])

    result = tools.get_privacy_exclusions(context)

    assert source.calls == [USER_ID]
    assert result.privacy_exclusions == ["workplace", "salary"]


def test_postgres_privacy_source_sql_targets_latest_questionnaire() -> None:
    sql, params = build_privacy_exclusions_select_sql(user_id=USER_ID)

    assert "from background_questionnaires" in sql
    assert "where user_id = %s::uuid" in sql
    assert "order by created_at desc" in sql
    assert "limit 1" in sql
    assert params == [USER_ID]


def test_postgres_privacy_source_rejects_missing_database_url() -> None:
    with pytest.raises(ValueError, match="database_url is required"):
        PostgresProfilePrivacySource("")


class FakePrivacySource:
    def __init__(self, values: dict[str, list[str]]) -> None:
        self.values = values
        self.calls: list[str] = []

    def get_privacy_exclusions(self, user_id: str) -> list[str]:
        self.calls.append(user_id)
        return self.values.get(user_id, [])


def make_tools(*, privacy_source=None) -> ProfileMcpTools:
    indexer = UserProfileIndexer(make_memory_service())
    indexer.index_records(make_profile_records(), user_id=USER_ID, replace_user_index=True)
    indexer.index_records(make_other_user_records(), user_id=OTHER_USER_ID, replace_user_index=True)
    return ProfileMcpTools(indexer, privacy_source=privacy_source)


def read_context(*, allowed_tools: list[str]) -> McpToolContext:
    return McpToolContext(
        user_id=USER_ID,
        session_id="sess_1",
        scopes=["profile:read"],
        allowed_tools=allowed_tools,
    )


def make_memory_service() -> LlamaIndexKnowledgeService:
    return LlamaIndexKnowledgeService(
        store=InMemoryKnowledgeStore(),
        embedding_provider=HashEmbeddingProvider(),
        chunk_max_chars=1200,
        chunk_overlap_chars=120,
    )


def make_profile_records() -> list[dict[str, object]]:
    return [
        {
            "fact_id": HOBBY_FACT_ID,
            "user_id": USER_ID,
            "topic": "hobbies",
            "fact_key": "hobby",
            "fact_value": "The learner enjoys cooking meals at home.",
            "privacy_level": "normal",
            "allowed_usage": ["question_personalization", "feedback_personalization"],
        },
        {
            "fact_id": GRAMMAR_FACT_ID,
            "user_id": USER_ID,
            "topic": "learning_history",
            "fact_key": "grammar_weakness",
            "fact_value": "The learner often misses past tense endings.",
            "privacy_level": "sensitive",
            "allowed_usage": ["scoring_context", "feedback_personalization"],
        },
    ]


def make_other_user_records() -> list[dict[str, object]]:
    return [
        {
            "fact_id": OTHER_FACT_ID,
            "user_id": OTHER_USER_ID,
            "topic": "goals",
            "fact_key": "target_band",
            "fact_value": "Another user wants Band 8.",
            "allowed_usage": ["feedback_personalization"],
        }
    ]
