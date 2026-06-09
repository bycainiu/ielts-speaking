from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.evals.common import EvalCaseResult, EvalSuiteReport, build_suite_report
from app.rag.llamaindex_service import (
    HashEmbeddingProvider,
    InMemoryKnowledgeStore,
    KnowledgeDocument,
    LlamaIndexKnowledgeService,
)


class RagEvalSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    query: str = Field(min_length=1)
    expected_doc_ids: list[str] = Field(min_length=1)
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=3, gt=0, le=10)
    min_precision: float = Field(default=0.34, ge=0, le=1)
    min_recall: float = Field(default=1.0, ge=0, le=1)


class RagEvalMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    retrieved_doc_ids: list[str] = Field(default_factory=list)
    missing_doc_ids: list[str] = Field(default_factory=list)


class RagasRagEvaluator:
    def __init__(self, knowledge_service: LlamaIndexKnowledgeService | None = None) -> None:
        self.knowledge_service = knowledge_service or build_default_knowledge_service()

    def run(self, samples: list[RagEvalSample] | None = None) -> EvalSuiteReport:
        results = [self.evaluate(sample) for sample in (samples or build_default_rag_eval_samples())]
        return build_suite_report(suite_name="ragas_rag_local", results=results, threshold=0.95)

    def evaluate(self, sample: RagEvalSample) -> EvalCaseResult:
        metrics = self.measure(sample)
        passed = metrics.precision >= sample.min_precision and metrics.recall >= sample.min_recall
        return EvalCaseResult(
            case_id=sample.sample_id,
            category="rag_retrieval",
            passed=passed,
            score=round((metrics.precision + metrics.recall) / 2, 4),
            reason=(
                f"precision={metrics.precision:.3f} recall={metrics.recall:.3f} "
                f"retrieved={','.join(metrics.retrieved_doc_ids)}"
            ),
            severity="high",
            metadata=metrics.model_dump(mode="json"),
        )

    def measure(self, sample: RagEvalSample) -> RagEvalMetrics:
        results = self.knowledge_service.retrieve(sample.query, top_k=sample.top_k, filters=sample.filters)
        retrieved_doc_ids: list[str] = []
        for item in results:
            if item.doc_id not in retrieved_doc_ids:
                retrieved_doc_ids.append(item.doc_id)
        expected = set(sample.expected_doc_ids)
        retrieved = set(retrieved_doc_ids)
        true_positive = len(expected & retrieved)
        precision = true_positive / len(retrieved) if retrieved else 0.0
        recall = true_positive / len(expected) if expected else 1.0
        return RagEvalMetrics(
            precision=round(precision, 4),
            recall=round(recall, 4),
            retrieved_doc_ids=retrieved_doc_ids,
            missing_doc_ids=sorted(expected - retrieved),
        )


def build_default_knowledge_service() -> LlamaIndexKnowledgeService:
    service = LlamaIndexKnowledgeService(
        store=InMemoryKnowledgeStore(),
        embedding_provider=HashEmbeddingProvider(dimension=128, model_name="hash-embedding-eval-v1"),
        chunk_max_chars=600,
        chunk_overlap_chars=60,
        backend="memory",
    )
    service.ingest_documents(default_knowledge_documents())
    return service


def default_knowledge_documents() -> list[KnowledgeDocument]:
    return [
        KnowledgeDocument(
            doc_id="eval_qbank_hometown",
            doc_type="question_bank",
            title="Part 1 hometown questions",
            content="IELTS Speaking Part 1 hometown city neighbourhood question bank. Where is your hometown? What do you like about your city?",
            metadata={
                "season_id": "2026-q2",
                "part": "1",
                "topic": "hometown",
                "source_type": "internal",
                "question_id": "eval_q_hometown",
            },
        ),
        KnowledgeDocument(
            doc_id="eval_qbank_public_place",
            doc_type="question_bank",
            title="Part 2 public place cue card",
            content="IELTS Speaking Part 2 cue card public place library park city. Describe a place in your city that you enjoy visiting.",
            metadata={
                "season_id": "2026-q2",
                "part": "2",
                "topic": "public_places",
                "source_type": "internal",
                "question_id": "eval_q_public_place",
            },
        ),
        KnowledgeDocument(
            doc_id="eval_qbank_technology",
            doc_type="question_bank",
            title="Part 3 technology discussion",
            content="IELTS Speaking Part 3 abstract discussion technology society education apps online learning future work.",
            metadata={
                "season_id": "2026-q2",
                "part": "3",
                "topic": "technology",
                "source_type": "internal",
                "question_id": "eval_q_technology",
            },
        ),
        KnowledgeDocument(
            doc_id="eval_rubric_fluency",
            doc_type="rubric",
            title="Fluency and coherence band descriptors",
            content="IELTS speaking rubric fluency coherence hesitation self-correction linking ideas Band 6 Band 7 descriptor.",
            metadata={
                "criterion": "fluency_coherence",
                "band": "6",
                "descriptor": "Fluency and coherence descriptor for hesitation and linking ideas.",
                "rubric_id": "eval_rubric_fluency",
                "rubric_version": "ielts-speaking-rubric-v1",
                "policy_type": "official_descriptor",
            },
        ),
        KnowledgeDocument(
            doc_id="eval_rubric_lexical",
            doc_type="rubric",
            title="Lexical resource band descriptors",
            content="IELTS speaking rubric lexical resource vocabulary topic words collocation paraphrase flexibility Band 6 Band 7.",
            metadata={
                "criterion": "lexical_resource",
                "band": "6",
                "descriptor": "Lexical resource descriptor for topic words, collocation, and paraphrase.",
                "rubric_id": "eval_rubric_lexical",
                "rubric_version": "ielts-speaking-rubric-v1",
                "policy_type": "official_descriptor",
            },
        ),
        KnowledgeDocument(
            doc_id="eval_rubric_pronunciation",
            doc_type="rubric",
            title="Pronunciation band descriptors",
            content="IELTS speaking rubric pronunciation intelligibility rhythm stress chunking accent does not directly reduce band.",
            metadata={
                "criterion": "pronunciation",
                "band": "6",
                "descriptor": "Pronunciation descriptor for intelligibility, rhythm, stress, and accent policy.",
                "rubric_id": "eval_rubric_pronunciation",
                "rubric_version": "ielts-speaking-rubric-v1",
                "policy_type": "official_descriptor",
            },
        ),
    ]


def build_default_rag_eval_samples() -> list[RagEvalSample]:
    return [
        RagEvalSample(
            sample_id="rag_qbank_hometown",
            query="Part 1 question about hometown city neighbourhood",
            expected_doc_ids=["eval_qbank_hometown"],
            filters={"doc_type": "question_bank", "part": 1},
        ),
        RagEvalSample(
            sample_id="rag_qbank_public_place",
            query="cue card describe a public place library park city",
            expected_doc_ids=["eval_qbank_public_place"],
            filters={"doc_type": "question_bank", "part": 2},
        ),
        RagEvalSample(
            sample_id="rag_qbank_technology",
            query="Part 3 technology society abstract discussion online education",
            expected_doc_ids=["eval_qbank_technology"],
            filters={"doc_type": "question_bank", "part": 3},
        ),
        RagEvalSample(
            sample_id="rag_rubric_fluency",
            query="fluency coherence hesitation self correction linking ideas band descriptor",
            expected_doc_ids=["eval_rubric_fluency"],
            filters={"doc_type": "rubric", "criterion": "fluency_coherence"},
        ),
        RagEvalSample(
            sample_id="rag_rubric_lexical",
            query="lexical resource vocabulary collocation paraphrase topic words",
            expected_doc_ids=["eval_rubric_lexical"],
            filters={"doc_type": "rubric", "criterion": "lexical_resource"},
        ),
        RagEvalSample(
            sample_id="rag_rubric_pronunciation",
            query="pronunciation intelligibility rhythm stress accent band descriptor",
            expected_doc_ids=["eval_rubric_pronunciation"],
            filters={"doc_type": "rubric", "criterion": "pronunciation"},
        ),
    ]
