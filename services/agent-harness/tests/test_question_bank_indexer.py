from typing import Any

import pytest

from app.rag.ingestion.question_bank_indexer import (
    PostgresQuestionBankSource,
    QuestionBankIndexer,
    QuestionBankRecord,
    build_question_bank_select_sql,
    build_question_content,
    record_from_pg_row,
)
from app.rag.llamaindex_service import HashEmbeddingProvider, InMemoryKnowledgeStore, LlamaIndexKnowledgeService


ACTIVE_SEASON_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OLD_SEASON_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CITY_QUESTION_ID = "11111111-1111-1111-1111-111111111111"
FOOD_QUESTION_ID = "22222222-2222-2222-2222-222222222222"
ARCHIVED_QUESTION_ID = "33333333-3333-3333-3333-333333333333"
OLD_SEASON_QUESTION_ID = "44444444-4444-4444-4444-444444444444"
TOPIC_ID = "55555555-5555-5555-5555-555555555555"


def test_index_records_filters_active_season_and_returns_question_id() -> None:
    service = make_memory_service()
    indexer = QuestionBankIndexer(service)

    result = indexer.index_records(make_question_records(), active_season_id=ACTIVE_SEASON_ID)
    matches = indexer.search_questions(
        "public transport parks",
        active_season_id=ACTIVE_SEASON_ID,
        part=1,
        topic="city",
        top_k=1,
    )

    assert result.requested_count == 4
    assert result.indexed_count == 2
    assert result.skipped_count == 2
    assert result.chunk_count == 2
    assert set(result.doc_ids) == {CITY_QUESTION_ID, FOOD_QUESTION_ID}
    assert {item.reason for item in result.skipped_questions} == {"question_not_active", "season_not_selected"}
    assert matches[0].metadata["question_id"] == CITY_QUESTION_ID
    assert matches[0].metadata["season_id"] == ACTIVE_SEASON_ID
    assert matches[0].metadata["part"] == "1"
    assert matches[0].metadata["topic"] == "city"


def test_reindex_same_question_replaces_existing_chunks() -> None:
    service = make_memory_service(chunk_max_chars=36, chunk_overlap_chars=4)
    indexer = QuestionBankIndexer(service)
    question = QuestionBankRecord(
        question_id=CITY_QUESTION_ID,
        season_id=ACTIVE_SEASON_ID,
        part=1,
        text="Do you like buses in your city? " * 4,
        topic="city",
        source_type="original",
    )

    first_result = indexer.index_records([question], active_season_id=ACTIVE_SEASON_ID)
    updated = question.model_copy(update={"text": "Do you enjoy quiet metro stations near your home?"})
    second_result = indexer.index_records([updated], active_season_id=ACTIVE_SEASON_ID)
    matches = indexer.search_questions("quiet metro stations", active_season_id=ACTIVE_SEASON_ID, top_k=10)

    assert first_result.chunk_count > second_result.chunk_count
    assert second_result.indexed_count == 1
    assert matches
    assert {match.doc_id for match in matches} == {CITY_QUESTION_ID}
    assert len(matches) == second_result.chunk_count
    assert all("buses" not in match.content for match in matches)


def test_part_two_content_includes_cue_card_and_active_followups() -> None:
    record = QuestionBankRecord(
        question_id=FOOD_QUESTION_ID,
        season_id=ACTIVE_SEASON_ID,
        part=2,
        text="Describe a meal you enjoyed.",
        topic="food",
        source_type="authorized",
        cue_card={
            "cue_card_id": "66666666-6666-6666-6666-666666666666",
            "prompt": "Describe a meal you enjoyed with other people.",
            "bullet_points": ["what the meal was", "who you ate with", "why you remember it"],
        },
        followup_templates=[
            {"part": 3, "text": "Why do people like eating together?", "sort_order": 1, "review_status": "active"},
            {"part": 3, "text": "Archived follow-up", "sort_order": 2, "review_status": "archived"},
        ],
    )

    content = build_question_content(record)
    result = QuestionBankIndexer(make_memory_service()).index_records([record], active_season_id=ACTIVE_SEASON_ID)

    assert "Cue card: Describe a meal you enjoyed with other people." in content
    assert "- who you ate with" in content
    assert "Why do people like eating together?" in content
    assert "Archived follow-up" not in content
    assert result.indexed_count == 1


def test_sync_from_source_passes_active_season_filters() -> None:
    source = FakeQuestionBankSource(make_question_records())
    indexer = QuestionBankIndexer(make_memory_service())

    result = indexer.sync_from_source(source, active_season_id=ACTIVE_SEASON_ID, part=2, limit=25)
    matches = indexer.search_questions("restaurant cooking", active_season_id=ACTIVE_SEASON_ID, part=2)

    assert source.calls == [
        {
            "active_season_only": True,
            "season_id": ACTIVE_SEASON_ID,
            "part": 2,
            "limit": 25,
            "offset": 0,
        }
    ]
    assert result.indexed_count == 1
    assert matches[0].metadata["question_id"] == FOOD_QUESTION_ID


def test_postgres_source_builds_active_question_sql_and_records() -> None:
    sql, params = build_question_bank_select_sql(
        active_season_only=True,
        season_id=ACTIVE_SEASON_ID,
        part=2,
        limit=50,
        offset=10,
    )
    row = (
        FOOD_QUESTION_ID,
        ACTIVE_SEASON_ID,
        TOPIC_ID,
        2,
        "Describe a meal you enjoyed.",
        3,
        "authorized",
        "licensed",
        "active",
        '{"topic": "food"}',
        "food",
        "66666666-6666-6666-6666-666666666666",
        "Describe a meal you enjoyed with other people.",
        '["what the meal was","who you ate with"]',
        60,
        120,
        '[{"followup_id":"77777777-7777-7777-7777-777777777777","part":3,"text":"Why do people share meals?","sort_order":0,"review_status":"active"}]',
    )

    record = record_from_pg_row(row)

    assert "s.is_active = true" in sql
    assert "q.review_status = 'active'" in sql
    assert "q.season_id = %s::uuid" in sql
    assert "q.part = %s" in sql
    assert params == [ACTIVE_SEASON_ID, 2, 50, 10]
    assert record.question_id == FOOD_QUESTION_ID
    assert record.topic == "food"
    assert record.cue_card is not None
    assert record.cue_card.bullet_points == ["what the meal was", "who you ate with"]
    assert record.followup_templates[0].text == "Why do people share meals?"


def test_postgres_source_rejects_missing_database_url() -> None:
    with pytest.raises(ValueError, match="database_url is required"):
        PostgresQuestionBankSource("")


class FakeQuestionBankSource:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.calls: list[dict[str, Any]] = []

    def list_questions(
        self,
        *,
        active_season_only: bool = True,
        season_id: str | None = None,
        part: int | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "active_season_only": active_season_only,
                "season_id": season_id,
                "part": part,
                "limit": limit,
                "offset": offset,
            }
        )
        return self.records


def make_question_records() -> list[dict[str, Any]]:
    return [
        {
            "question_id": CITY_QUESTION_ID,
            "season_id": ACTIVE_SEASON_ID,
            "part": 1,
            "text": "Do you like public transport and parks in your city?",
            "topic": "city",
            "topic_id": TOPIC_ID,
            "source_type": "original",
            "review_status": "active",
        },
        {
            "question_id": FOOD_QUESTION_ID,
            "season_id": ACTIVE_SEASON_ID,
            "part": 2,
            "text": "Describe a restaurant where you enjoyed cooking and food.",
            "topic": "food",
            "source_type": "authorized",
            "review_status": "active",
            "difficulty": 3,
        },
        {
            "question_id": ARCHIVED_QUESTION_ID,
            "season_id": ACTIVE_SEASON_ID,
            "part": 1,
            "text": "Archived city question.",
            "topic": "city",
            "source_type": "original",
            "review_status": "archived",
        },
        {
            "question_id": OLD_SEASON_QUESTION_ID,
            "season_id": OLD_SEASON_ID,
            "part": 1,
            "text": "Old season city question.",
            "topic": "city",
            "source_type": "original",
            "review_status": "active",
        },
    ]


def make_memory_service(*, chunk_max_chars: int = 1200, chunk_overlap_chars: int = 120) -> LlamaIndexKnowledgeService:
    return LlamaIndexKnowledgeService(
        store=InMemoryKnowledgeStore(),
        embedding_provider=HashEmbeddingProvider(),
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_chars=chunk_overlap_chars,
    )
