import pytest

from app.mcp.rubric_mcp import RubricMcpTools
from app.mcp.security import McpAuthorizationError, McpToolContext
from app.rag.ingestion.rubric_indexer import RubricIndexer
from app.rag.llamaindex_service import HashEmbeddingProvider, InMemoryKnowledgeStore, LlamaIndexKnowledgeService


def test_retrieve_speaking_band_descriptor_returns_source_refs() -> None:
    tools = make_tools()
    context = read_context(allowed_tools=["retrieve_speaking_band_descriptor"])

    result = tools.retrieve_speaking_band_descriptor(
        context,
        query="hesitation coherence",
        criterion="fluency_coherence",
        min_band=6,
        max_band=6.5,
        top_k=5,
    )

    assert result.session_id == "sess_1"
    assert {item.band for item in result.descriptors} == {"6", "6.5"}
    assert {item.criterion for item in result.descriptors} == {"fluency_coherence"}
    assert all(item.source_ref.doc_id for item in result.descriptors)
    assert all(item.source_ref.chunk_id for item in result.descriptors)


def test_retrieve_speaking_band_descriptor_can_filter_policy_type() -> None:
    tools = make_tools()
    context = read_context(allowed_tools=["retrieve_speaking_band_descriptor"])

    result = tools.retrieve_speaking_band_descriptor(
        context,
        query="between band six and seven",
        criterion="fluency_coherence",
        bands=[6.5],
        policy_types=["internal_policy"],
    )

    assert [item.rubric_id for item in result.descriptors] == ["fc-band-6-5"]
    assert result.descriptors[0].policy_type == "internal_policy"


def test_get_anchor_samples_returns_only_anchor_examples() -> None:
    tools = make_tools()
    context = read_context(allowed_tools=["get_anchor_samples"])

    result = tools.get_anchor_samples(
        context,
        query="hesitation self correction",
        criterion="fluency_coherence",
        bands=[6],
        top_k=3,
    )

    assert [item.anchor_sample_id for item in result.anchors] == ["anchor-fc-6-a"]
    assert result.anchors[0].band == "6"
    assert "Anchor answer excerpt" in result.anchors[0].content
    assert result.anchors[0].source_ref.doc_id


def test_get_anchor_samples_can_filter_by_anchor_sample_id() -> None:
    tools = make_tools()
    context = read_context(allowed_tools=["get_anchor_samples"])

    result = tools.get_anchor_samples(context, anchor_sample_id="anchor-fc-6-a")

    assert len(result.anchors) == 1
    assert result.anchors[0].anchor_sample_id == "anchor-fc-6-a"


def test_rubric_mcp_rejects_missing_scope() -> None:
    tools = make_tools()
    context = McpToolContext(user_id="user_1", session_id="sess_1", scopes=[])

    with pytest.raises(McpAuthorizationError, match="missing required scope"):
        tools.retrieve_speaking_band_descriptor(context, query="fluency")


def test_rubric_mcp_rejects_disallowed_tool() -> None:
    tools = make_tools()
    context = read_context(allowed_tools=["get_anchor_samples"])

    with pytest.raises(McpAuthorizationError, match="tool is not allowed"):
        tools.retrieve_speaking_band_descriptor(context, query="fluency")


def make_tools() -> RubricMcpTools:
    indexer = RubricIndexer(make_memory_service())
    indexer.index_records(make_rubric_records())
    return RubricMcpTools(indexer)


def read_context(*, allowed_tools: list[str]) -> McpToolContext:
    return McpToolContext(
        user_id="user_1",
        session_id="sess_1",
        scopes=["rubric:read"],
        allowed_tools=allowed_tools,
    )


def make_memory_service() -> LlamaIndexKnowledgeService:
    return LlamaIndexKnowledgeService(
        store=InMemoryKnowledgeStore(),
        embedding_provider=HashEmbeddingProvider(),
        chunk_max_chars=1200,
        chunk_overlap_chars=120,
    )


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
            "guidance": "Use 6.5 when the answer is between Band 6 and Band 7.",
        },
        {
            "rubric_id": "lr-band-6",
            "criterion": "lexical_resource",
            "band": "6",
            "descriptor": "Uses enough vocabulary to discuss topics at length despite some inaccuracies.",
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
    ]
