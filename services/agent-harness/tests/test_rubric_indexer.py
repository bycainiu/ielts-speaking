import pytest

from app.rag.ingestion.rubric_indexer import (
    RubricIndexer,
    RubricRecord,
    build_band_filter,
    build_rubric_content,
    build_rubric_document,
    stable_uuid,
)
from app.rag.llamaindex_service import HashEmbeddingProvider, InMemoryKnowledgeStore, LlamaIndexKnowledgeService


def test_index_and_search_rubric_by_criterion() -> None:
    indexer = RubricIndexer(make_memory_service())

    result = indexer.index_records(make_rubric_records())
    matches = indexer.search_rubric(
        "hesitation coherence but speech remains understandable",
        criterion="fluency_coherence",
        top_k=5,
    )

    assert result.requested_count == 5
    assert result.indexed_count == 4
    assert result.skipped_count == 1
    assert result.chunk_count == 4
    assert {match.metadata["criterion"] for match in matches} == {"fluency_coherence"}
    assert {match.metadata["rubric_id"] for match in matches} >= {"fc-band-6", "fc-band-7"}


def test_search_rubric_supports_band_range() -> None:
    indexer = RubricIndexer(make_memory_service())
    indexer.index_records(make_rubric_records())

    matches = indexer.search_rubric(
        "coherence hesitation flexible response",
        criterion="fluency_coherence",
        min_band=6,
        max_band=7,
        top_k=10,
    )

    assert {match.metadata["band"] for match in matches} == {"6", "6.5", "7"}
    assert all(match.metadata["criterion"] == "fluency_coherence" for match in matches)


def test_anchor_examples_are_referenceable_by_sample_id_and_policy_type() -> None:
    indexer = RubricIndexer(make_memory_service())
    indexer.index_records(make_rubric_records())

    matches = indexer.search_rubric(
        "anchor answer hesitation self correction",
        criterion="fluency_coherence",
        policy_types=["anchor_example"],
        anchor_sample_id="anchor-fc-6-a",
        top_k=3,
    )

    assert len(matches) == 1
    assert matches[0].metadata["policy_type"] == "anchor_example"
    assert matches[0].metadata["anchor_sample_id"] == "anchor-fc-6-a"
    assert matches[0].metadata["rubric_id"] == "anchor-fc-6-a"
    assert "Anchor sample ID: anchor-fc-6-a" in matches[0].content


def test_reindex_same_rubric_record_replaces_existing_chunks() -> None:
    service = make_memory_service(chunk_max_chars=42, chunk_overlap_chars=5)
    indexer = RubricIndexer(service)
    record = RubricRecord(
        rubric_id="fc-band-6",
        criterion="fluency_coherence",
        band="6",
        descriptor="Old descriptor about hesitation. " * 4,
        guidance="Old internal guidance.",
    )

    first_result = indexer.index_records([record])
    updated = record.model_copy(
        update={
            "descriptor": "New descriptor about coherence and steady speech.",
            "guidance": "New guidance for scoring.",
        }
    )
    second_result = indexer.index_records([updated])
    matches = indexer.search_rubric("steady speech coherence", criterion="fluency_coherence", bands=["6"], top_k=10)

    assert first_result.chunk_count > second_result.chunk_count
    assert second_result.indexed_count == 1
    assert matches
    assert {match.doc_id for match in matches} == {stable_uuid("fc-band-6")}
    assert all("Old descriptor" not in match.content for match in matches)


def test_build_band_filter_validates_ranges_and_deduplicates() -> None:
    assert build_band_filter(min_band=6, max_band=7) == ["6", "6.5", "7"]
    assert build_band_filter(bands=[6, "6.0", 6.5, 7]) == ["6", "6.5", "7"]

    with pytest.raises(ValueError, match="min_band must be <= max_band"):
        build_band_filter(min_band=7, max_band=6)

    with pytest.raises(ValueError, match="0.5 increments"):
        build_band_filter(bands=[6.25])


def test_rubric_document_uses_stable_uuid_and_content_for_internal_policy() -> None:
    record = RubricRecord(
        rubric_id="internal-pronunciation-policy-6",
        criterion="pronunciation",
        band=6.0,
        descriptor="Generally understandable with occasional strain.",
        policy_type="internal_policy",
        guidance="Do not penalize accent directly; focus on intelligibility, stress, rhythm, and chunking.",
        evidence=["listener can usually follow", "stress errors occasionally reduce clarity"],
    )

    document = build_rubric_document(record)
    content = build_rubric_content(record)

    assert document.doc_id == stable_uuid("internal-pronunciation-policy-6")
    assert document.metadata["band"] == "6"
    assert document.metadata["policy_type"] == "internal_policy"
    assert document.metadata["has_guidance"] is True
    assert "Do not penalize accent directly" in content
    assert "- listener can usually follow" in content


def make_rubric_records() -> list[dict[str, object]]:
    return [
        {
            "rubric_id": "fc-band-6",
            "criterion": "fluency_coherence",
            "band": "6",
            "descriptor": "Shows willingness to speak at length, with some hesitation, repetition, or self-correction.",
            "policy_type": "official_descriptor",
            "rubric_version": "ielts-speaking-rubric-v1",
        },
        {
            "rubric_id": "fc-band-6-5",
            "criterion": "fluency_coherence",
            "band": 6.5,
            "descriptor": "Sustains answers with generally clear coherence but still has noticeable hesitation.",
            "policy_type": "internal_policy",
            "guidance": "Use 6.5 when the answer is between Band 6 and Band 7 and evidence supports both sides.",
        },
        {
            "rubric_id": "fc-band-7",
            "criterion": "fluency_coherence",
            "band": "7",
            "descriptor": "Speaks at length without noticeable effort and develops ideas flexibly.",
            "policy_type": "official_descriptor",
        },
        {
            "rubric_id": "anchor-fc-6-a",
            "criterion": "fluency_coherence",
            "band": "6",
            "descriptor": "Anchor sample for Band 6 fluency and coherence.",
            "anchor_sample_id": "anchor-fc-6-a",
            "anchor_answer_excerpt": "I think, um, it was useful because I could, I could meet many people...",
            "anchor_score_rationale": "Frequent hesitation and repetition, but meaning remains clear.",
            "evidence": ["hesitation", "self-correction", "meaning remains clear"],
        },
        {
            "rubric_id": "draft-lexical-6",
            "criterion": "lexical_resource",
            "band": "6",
            "descriptor": "Draft lexical descriptor should not be indexed by default.",
            "status": "draft",
        },
    ]


def make_memory_service(*, chunk_max_chars: int = 1200, chunk_overlap_chars: int = 120) -> LlamaIndexKnowledgeService:
    return LlamaIndexKnowledgeService(
        store=InMemoryKnowledgeStore(),
        embedding_provider=HashEmbeddingProvider(),
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_chars=chunk_overlap_chars,
    )
