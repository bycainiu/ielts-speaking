from typing import Any

import pytest

from app.core.config import Settings
from app.rag.llamaindex_service import (
    HashEmbeddingProvider,
    InMemoryKnowledgeStore,
    KnowledgeDocument,
    KnowledgeServiceError,
    LlamaIndexKnowledgeService,
    PgVectorKnowledgeStore,
    build_pgvector_filter_sql,
    split_text,
    vector_literal,
)
from app.rag.chunk_schema import KnowledgeMetadataError


class FakeJsonb:
    def __init__(self, value):
        self.value = value


def test_ingest_and_retrieve_top_k_with_metadata_filter() -> None:
    service = make_memory_service()
    result = service.ingest_documents(
        [
            KnowledgeDocument(
                doc_id="doc_city_p1",
                doc_type="question_bank",
                title="City Part 1",
                content="Hometown city parks and public transport question.",
                metadata={"season_id": "2026-q2", "part": "1", "topic": "city", "source_type": "original"},
                source_id="question_001",
            ),
            KnowledgeDocument(
                doc_id="doc_food_p1",
                doc_type="question_bank",
                title="Food Part 1",
                content="Cooking meals and favorite restaurant question.",
                metadata={"season_id": "2026-q2", "part": "1", "topic": "food", "source_type": "original"},
                source_id="question_002",
            ),
        ]
    )

    matches = service.retrieve(
        "city transport",
        top_k=1,
        filters={"doc_type": "question_bank", "season_id": "2026-q2", "part": "1"},
    )

    assert len(result) == 2
    assert matches[0].doc_id == "doc_city_p1"
    assert matches[0].metadata["topic"] == "city"
    assert 0 <= matches[0].score <= 1


def test_question_bank_metadata_is_required_and_normalized() -> None:
    service = make_memory_service()
    service.ingest_documents(
        [
            KnowledgeDocument(
                doc_id="doc_question_schema",
                doc_type="question_bank",
                title="Part 2 Object",
                content="Describe an object that is important to you.",
                metadata={
                    "season": "2026-q2",
                    "part": 2,
                    "topic": "objects",
                    "source_type": "authorized",
                    "question_id": "question_123",
                },
            )
        ]
    )

    matches = service.retrieve("important object", filters={"doc_type": "question_bank", "part": "2"})

    assert matches[0].metadata["part"] == "2"
    assert matches[0].metadata["season_id"] == "2026-q2"
    assert matches[0].metadata["source_type"] == "authorized"


def test_question_bank_metadata_rejects_missing_filter_fields() -> None:
    service = make_memory_service()

    with pytest.raises(KnowledgeMetadataError, match="question_bank metadata invalid"):
        service.ingest_documents(
            [
                KnowledgeDocument(
                    doc_id="doc_invalid_question",
                    doc_type="question_bank",
                    title="Invalid Question",
                    content="What do you do on weekends?",
                    metadata={"season_id": "2026-q2", "part": "1", "topic": "weekends"},
                )
            ]
        )


def test_rubric_metadata_normalizes_band_and_requires_descriptor() -> None:
    service = make_memory_service()
    service.ingest_documents(
        [
            KnowledgeDocument(
                doc_id="doc_rubric_schema",
                doc_type="rubric",
                title="Lexical 6",
                content="Band 6 lexical resource descriptor.",
                metadata={
                    "criterion": "lexical_resource",
                    "band": 6.0,
                    "descriptor": "Uses enough vocabulary to discuss topics clearly.",
                },
            )
        ]
    )

    matches = service.retrieve("vocabulary topics", filters={"doc_type": "rubric", "band": "6"})

    assert matches[0].metadata["criterion"] == "lexical_resource"
    assert matches[0].metadata["band"] == "6"

    with pytest.raises(KnowledgeMetadataError, match="rubric metadata invalid"):
        service.ingest_documents(
            [
                KnowledgeDocument(
                    doc_id="doc_invalid_rubric",
                    doc_type="rubric",
                    title="Invalid Rubric",
                    content="Missing descriptor.",
                    metadata={"criterion": "lexical_resource", "band": "6"},
                )
            ]
        )


def test_user_profile_metadata_supports_allowed_usage_filter() -> None:
    service = make_memory_service()
    service.ingest_documents(
        [
            KnowledgeDocument(
                doc_id="doc_user_scoring",
                doc_type="user_profile",
                title="Grammar weakness",
                content="The learner often misses past tense endings.",
                metadata={
                    "privacy_level": "normal",
                    "allowed_usage": ["scoring_context", "feedback_personalization"],
                    "topic": "learning_history",
                    "fact_key": "grammar_weakness",
                },
                owner_user_id="user_123",
            ),
            KnowledgeDocument(
                doc_id="doc_user_question",
                doc_type="user_profile",
                title="Hobby",
                content="The learner enjoys cooking at home.",
                metadata={
                    "privacy_level": "normal",
                    "allowed_usage": ["question_personalization"],
                    "topic": "hobbies",
                    "fact_key": "hobby",
                },
                owner_user_id="user_123",
            ),
        ]
    )

    matches = service.retrieve(
        "past tense grammar",
        filters={"doc_type": "user_profile", "allowed_usage": ["scoring_context"]},
    )

    assert [match.doc_id for match in matches] == ["doc_user_scoring"]
    assert matches[0].metadata["allowed_usage"] == ["scoring_context", "feedback_personalization"]


def test_retrieve_respects_list_filter_and_active_status() -> None:
    service = make_memory_service()
    service.ingest_documents(
        [
            KnowledgeDocument(
                doc_id="doc_active",
                doc_type="rubric",
                title="Fluency 6",
                content="Band six fluency has some hesitation but remains understandable.",
                metadata={
                    "criterion": "fluency_coherence",
                    "band": "6",
                    "descriptor": "Some hesitation but speech remains understandable.",
                },
            ),
            KnowledgeDocument(
                doc_id="doc_archived",
                doc_type="rubric",
                title="Archived Fluency",
                content="Archived fluency descriptor should not be returned.",
                metadata={
                    "criterion": "fluency_coherence",
                    "band": "6",
                    "descriptor": "Archived descriptor.",
                },
                status="archived",
            ),
        ]
    )

    matches = service.retrieve("fluency hesitation", filters={"criterion": ["fluency_coherence", "lexical_resource"]})

    assert [match.doc_id for match in matches] == ["doc_active"]


def test_reingest_replaces_existing_document_chunks() -> None:
    service = make_memory_service(chunk_max_chars=24, chunk_overlap_chars=4)
    service.ingest_documents(
        [
            KnowledgeDocument(
                doc_id="doc_update",
                doc_type="topic_knowledge",
                title="Old Topic",
                content="old topic text about bicycles " * 3,
                metadata={"topic": "transport"},
            )
        ]
    )
    first_count = len(service.retrieve("bicycles", top_k=10))

    service.ingest_documents(
        [
            KnowledgeDocument(
                doc_id="doc_update",
                doc_type="topic_knowledge",
                title="New Topic",
                content="new topic text about trains and stations",
                metadata={"topic": "transport"},
            )
        ]
    )
    matches = service.retrieve("trains stations", top_k=10)

    assert first_count > 1
    assert all(match.doc_id == "doc_update" for match in matches)
    assert all("old topic" not in match.content for match in matches)


def test_split_text_uses_overlap() -> None:
    chunks = split_text("abcdefghijklmnopqrstuvwxyz", max_chars=10, overlap_chars=3)

    assert chunks == ["abcdefghij", "hijklmnopq", "opqrstuvwx", "vwxyz"]


def test_from_settings_memory_backend_describe() -> None:
    service = LlamaIndexKnowledgeService.from_settings(make_settings())

    description = service.describe()

    assert description["backend"] == "memory"
    assert description["embedding_dimension"] == 1536
    assert description["chunk_max_chars"] == 1200


def test_pgvector_backend_requires_database_url() -> None:
    settings = make_settings(KNOWLEDGE_STORE_BACKEND="pgvector", KNOWLEDGE_DATABASE_URL="")

    with pytest.raises(RuntimeError):
        settings.validate_runtime()

    with pytest.raises(KnowledgeServiceError):
        PgVectorKnowledgeStore("")


def test_pgvector_helpers_build_vector_and_filter_sql() -> None:
    vector = vector_literal([0.1, -0.2, 0.0])
    where_sql, params = build_pgvector_filter_sql(
        {"doc_type": "rubric", "criterion": "fluency_coherence", "band": ["6", "7"]},
        FakeJsonb,
    )

    assert vector == "[0.10000000,-0.20000000,0.00000000]"
    assert "kd.doc_type" in where_sql
    assert "kc.metadata @>" in where_sql
    assert "any" in where_sql
    assert "?|" in where_sql
    assert params[0] == "rubric"
    assert params[1].value == {"criterion": "fluency_coherence"}
    assert params[2] == "band"
    assert params[3] == ["6", "7"]


def test_hash_embedding_is_deterministic_and_normalized() -> None:
    provider = HashEmbeddingProvider(dimension=16)
    first = provider.embed("city city transport")
    second = provider.embed("city city transport")

    assert first == second
    assert pytest.approx(sum(value * value for value in first), rel=1e-6) == 1.0


def make_memory_service(*, chunk_max_chars: int = 1200, chunk_overlap_chars: int = 120) -> LlamaIndexKnowledgeService:
    return LlamaIndexKnowledgeService(
        store=InMemoryKnowledgeStore(),
        embedding_provider=HashEmbeddingProvider(),
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_chars=chunk_overlap_chars,
    )


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "APP_ENV": "local",
        "MIMO_API_KEY": "test-key",
        "MIMO_BASE_URL": "https://mimo.local/v1",
        "MIMO_DEFAULT_MODEL": "mimo-v2.5-pro",
        "MIMO_API_FORMAT": "openai",
        "MIMO_TIMEOUT_SECONDS": 3.0,
        "MIMO_MAX_RETRIES": 0,
        "MIMO_MODEL_ROUTES_JSON": "{}",
        "LANGFUSE_ENABLED": False,
        "KNOWLEDGE_STORE_BACKEND": "memory",
        "KNOWLEDGE_DATABASE_URL": "postgres://ielts:ielts@postgres:5432/ielts_speaking?sslmode=disable",
        "KNOWLEDGE_EMBEDDING_DIMENSION": 1536,
    }
    values.update(overrides)
    return Settings(**values)
