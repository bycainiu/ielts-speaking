from typing import Any

import pytest

from app.rag.ingestion.user_profile_indexer import (
    PostgresUserProfileSource,
    UserProfileFactRecord,
    UserProfileIndexer,
    build_user_fact_content,
    build_user_profile_select_sql,
    record_from_pg_row,
    stable_fact_doc_id,
)
from app.rag.llamaindex_service import HashEmbeddingProvider, InMemoryKnowledgeStore, LlamaIndexKnowledgeService


USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_USER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
QUESTIONNAIRE_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
HOBBY_FACT_ID = "11111111-1111-1111-1111-111111111111"
WORK_FACT_ID = "22222222-2222-2222-2222-222222222222"
PRIVATE_FACT_ID = "33333333-3333-3333-3333-333333333333"
GOAL_FACT_ID = "44444444-4444-4444-4444-444444444444"
GRAMMAR_FACT_ID = "55555555-5555-5555-5555-555555555555"


def test_index_records_filters_excluded_private_and_searches_by_topic() -> None:
    indexer = UserProfileIndexer(make_memory_service())

    result = indexer.index_records(make_profile_records(), user_id=USER_ID, replace_user_index=True)
    matches = indexer.search_user_facts(
        "cooking meals at home",
        user_id=USER_ID,
        topic="hobbies",
        allowed_usage=["question_personalization"],
    )

    assert result.requested_count == 4
    assert result.indexed_count == 1
    assert result.skipped_count == 3
    assert result.deleted_count == 0
    assert {item.reason for item in result.skipped_facts} == {"fact_excluded", "fact_private", "user_not_selected"}
    assert matches[0].metadata["fact_id"] == HOBBY_FACT_ID
    assert matches[0].metadata["owner_user_id"] == USER_ID
    assert matches[0].metadata["topic"] == "hobbies"
    assert matches[0].metadata["allowed_usage"] == ["question_personalization", "feedback_personalization"]


def test_user_update_replace_user_index_removes_old_facts() -> None:
    service = make_memory_service()
    indexer = UserProfileIndexer(service)
    indexer.index_records(
        [
            {
                "fact_id": HOBBY_FACT_ID,
                "user_id": USER_ID,
                "questionnaire_id": QUESTIONNAIRE_ID,
                "topic": "hobbies",
                "fact_key": "hobby",
                "fact_value": "The learner enjoys cooking Italian meals at home.",
                "allowed_usage": ["question_personalization"],
            }
        ],
        user_id=USER_ID,
        replace_user_index=True,
    )

    result = indexer.index_records(
        [
            {
                "fact_id": GOAL_FACT_ID,
                "user_id": USER_ID,
                "questionnaire_id": QUESTIONNAIRE_ID,
                "topic": "goals",
                "fact_key": "target_band",
                "fact_value": "The learner wants to reach Band 7 in three months.",
                "allowed_usage": ["feedback_personalization", "scoring_context"],
            }
        ],
        user_id=USER_ID,
        replace_user_index=True,
    )
    old_matches = indexer.search_user_facts("Italian cooking", user_id=USER_ID, topic="hobbies")
    new_matches = indexer.search_user_facts("Band 7 three months", user_id=USER_ID, topic="goals")

    assert result.deleted_count == 1
    assert old_matches == []
    assert new_matches[0].metadata["fact_id"] == GOAL_FACT_ID


def test_allowed_usage_filter_keeps_scoring_context_separate() -> None:
    indexer = UserProfileIndexer(make_memory_service())
    indexer.index_records(
        [
            {
                "fact_id": HOBBY_FACT_ID,
                "user_id": USER_ID,
                "questionnaire_id": QUESTIONNAIRE_ID,
                "topic": "hobbies",
                "fact_key": "hobby",
                "fact_value": "The learner enjoys cooking at home.",
                "allowed_usage": ["question_personalization"],
            },
            {
                "fact_id": GRAMMAR_FACT_ID,
                "user_id": USER_ID,
                "questionnaire_id": QUESTIONNAIRE_ID,
                "topic": "learning_history",
                "fact_key": "grammar_weakness",
                "fact_value": "The learner often misses past tense endings.",
                "allowed_usage": ["scoring_context", "feedback_personalization"],
            },
        ],
        user_id=USER_ID,
        replace_user_index=True,
    )

    matches = indexer.search_user_facts(
        "past tense endings",
        user_id=USER_ID,
        allowed_usage=["scoring_context"],
    )

    assert [match.metadata["fact_id"] for match in matches] == [GRAMMAR_FACT_ID]
    assert matches[0].metadata["allowed_usage"] == ["scoring_context", "feedback_personalization"]


def test_sync_from_source_fetches_all_latest_facts_and_replaces() -> None:
    source = FakeUserProfileSource(make_profile_records())
    indexer = UserProfileIndexer(make_memory_service())

    result = indexer.sync_from_source(source, user_id=USER_ID, topic="hobbies", limit=25)
    matches = indexer.search_user_facts("cooking", user_id=USER_ID, topic="hobbies")

    assert source.calls == [
        {
            "user_id": USER_ID,
            "include_excluded": True,
            "include_private": True,
            "topic": "hobbies",
            "allowed_usage": None,
            "limit": 25,
            "offset": 0,
        }
    ]
    assert result.indexed_count == 1
    assert matches[0].metadata["fact_id"] == HOBBY_FACT_ID


def test_postgres_source_builds_latest_fact_sql_and_records() -> None:
    sql, params = build_user_profile_select_sql(
        user_id=USER_ID,
        include_excluded=False,
        include_private=False,
        topic="hobbies",
        allowed_usage=["question_personalization"],
        limit=50,
        offset=10,
    )
    row = (
        HOBBY_FACT_ID,
        USER_ID,
        QUESTIONNAIRE_ID,
        "hobbies",
        "hobby",
        "The learner enjoys cooking at home.",
        "normal",
        '["question_personalization","feedback_personalization"]',
        False,
    )

    record = record_from_pg_row(row)

    assert "latest_questionnaire" in sql
    assert "bf.is_excluded = false" in sql
    assert "bf.privacy_level <> 'private'" in sql
    assert "bf.topic = %s" in sql
    assert "bf.allowed_usage && %s::text[]" in sql
    assert params == [USER_ID, USER_ID, "hobbies", ["question_personalization"], 50, 10]
    assert record.fact_id == HOBBY_FACT_ID
    assert record.user_id == USER_ID
    assert record.allowed_usage == ["question_personalization", "feedback_personalization"]
    assert record.is_excluded is False


def test_private_fact_can_be_indexed_only_when_explicitly_allowed() -> None:
    indexer = UserProfileIndexer(make_memory_service())
    private_record = {
        "fact_id": PRIVATE_FACT_ID,
        "user_id": USER_ID,
        "questionnaire_id": QUESTIONNAIRE_ID,
        "topic": "finance",
        "fact_key": "salary",
        "fact_value": "The learner's salary is private.",
        "privacy_level": "private",
        "allowed_usage": ["feedback_personalization"],
    }

    default_result = indexer.index_records([private_record], user_id=USER_ID, replace_user_index=True)
    explicit_result = indexer.index_records(
        [private_record],
        user_id=USER_ID,
        include_private=True,
        replace_user_index=True,
    )
    default_search = indexer.search_user_facts("salary", user_id=USER_ID, include_private=False)
    explicit_search = indexer.search_user_facts("salary", user_id=USER_ID, include_private=True)

    assert default_result.indexed_count == 0
    assert default_result.skipped_facts[0].reason == "fact_private"
    assert explicit_result.indexed_count == 1
    assert default_search == []
    assert explicit_search[0].metadata["privacy_level"] == "private"


def test_build_user_fact_document_uses_stable_doc_id_and_hashes_value() -> None:
    record = UserProfileFactRecord(
        fact_id=HOBBY_FACT_ID,
        user_id=USER_ID,
        questionnaire_id=QUESTIONNAIRE_ID,
        topic="hobbies",
        fact_key="hobby",
        fact_value="The learner enjoys cooking at home.",
        allowed_usage=["question_personalization"],
    )

    document = index_document(record)
    content = build_user_fact_content(record)

    assert document.doc_id == stable_fact_doc_id(record)
    assert document.owner_user_id == USER_ID
    assert document.metadata["fact_value_hash"]
    assert "Fact value: The learner enjoys cooking at home." in content


def test_postgres_source_rejects_missing_database_url() -> None:
    with pytest.raises(ValueError, match="database_url is required"):
        PostgresUserProfileSource("")


class FakeUserProfileSource:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.calls: list[dict[str, Any]] = []

    def list_user_facts(
        self,
        user_id: str,
        *,
        include_excluded: bool = True,
        include_private: bool = True,
        topic: str | None = None,
        allowed_usage: list[str] | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "user_id": user_id,
                "include_excluded": include_excluded,
                "include_private": include_private,
                "topic": topic,
                "allowed_usage": allowed_usage,
                "limit": limit,
                "offset": offset,
            }
        )
        return self.records


def make_profile_records() -> list[dict[str, Any]]:
    return [
        {
            "fact_id": HOBBY_FACT_ID,
            "user_id": USER_ID,
            "questionnaire_id": QUESTIONNAIRE_ID,
            "topic": "hobbies",
            "fact_key": "hobby",
            "fact_value": "The learner enjoys cooking meals at home.",
            "privacy_level": "normal",
            "allowed_usage": ["question_personalization", "feedback_personalization"],
        },
        {
            "fact_id": WORK_FACT_ID,
            "user_id": USER_ID,
            "questionnaire_id": QUESTIONNAIRE_ID,
            "topic": "work",
            "fact_key": "workplace",
            "fact_value": "The learner works at a bank.",
            "privacy_level": "sensitive",
            "allowed_usage": ["question_personalization"],
            "is_excluded": True,
        },
        {
            "fact_id": PRIVATE_FACT_ID,
            "user_id": USER_ID,
            "questionnaire_id": QUESTIONNAIRE_ID,
            "topic": "finance",
            "fact_key": "salary",
            "fact_value": "The learner's salary is private.",
            "privacy_level": "private",
            "allowed_usage": ["feedback_personalization"],
        },
        {
            "fact_id": GOAL_FACT_ID,
            "user_id": OTHER_USER_ID,
            "questionnaire_id": QUESTIONNAIRE_ID,
            "topic": "goals",
            "fact_key": "target_band",
            "fact_value": "Another user wants Band 8.",
            "allowed_usage": ["feedback_personalization"],
        },
    ]


def index_document(record: UserProfileFactRecord):
    from app.rag.ingestion.user_profile_indexer import build_user_fact_document

    return build_user_fact_document(record)


def make_memory_service(*, chunk_max_chars: int = 1200, chunk_overlap_chars: int = 120) -> LlamaIndexKnowledgeService:
    return LlamaIndexKnowledgeService(
        store=InMemoryKnowledgeStore(),
        embedding_provider=HashEmbeddingProvider(),
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_chars=chunk_overlap_chars,
    )
