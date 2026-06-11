from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.document_ingestion.extractor import DocumentSkillRouter, extract_document
from app.document_ingestion.models import ArtifactRecord, Candidate, IngestionJob, RuntimePolicy, SourceFile, StepHandle
from app.document_ingestion.storage import InMemoryDocumentObjectStore
from app.document_ingestion.supervisor import DocumentIngestionSupervisor


def make_job(*, visibility: str = "private", action: str = "mixed") -> IngestionJob:
    source = SourceFile(
        id="22222222-2222-2222-2222-222222222222",
        owner_user_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        visibility=visibility,
        upload_purpose=action,
        title="IELTS Notes",
        original_filename="notes.md",
        extension=".md",
        mime_type="text/markdown",
        size_bytes=128,
        checksum_sha256="sha256:test",
        storage_bucket="bucket",
        storage_key="knowledge/user/notes.md",
    )
    return IngestionJob(
        id="11111111-1111-1111-1111-111111111111",
        owner_user_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        requested_visibility=visibility,
        requested_action=action,
        status="queued",
        stage="queued",
        progress_pct=5,
        priority=0,
        source_file=source,
    )


class FakeRepository:
    def __init__(self, job: IngestionJob, *, cancelled: bool = False) -> None:
        self.job = job
        self.cancelled = cancelled
        self.claimed = False
        self.stages: list[tuple[str, int]] = []
        self.events: list[tuple[str, str]] = []
        self.artifacts: list[ArtifactRecord] = []
        self.candidates: list[Candidate] = []
        self.completed = False
        self.failed = False
        self.cancelled_job = False
        self.steps: dict[str, dict[str, Any]] = {}

    def get_runtime_policy(self) -> RuntimePolicy:
        return RuntimePolicy(max_concurrency=2, paused=False)

    def claim_next_job(self, worker_id: str) -> IngestionJob | None:
        if self.claimed:
            return None
        self.claimed = True
        self.job.run_id = "run_doc_ingestion_test"
        self.job.status = "running"
        return self.job

    def mark_job_stage(self, job_id: str, stage: str, progress_pct: int, metadata: dict[str, Any] | None = None) -> None:
        self.stages.append((stage, progress_pct))

    def is_cancel_requested(self, job_id: str) -> bool:
        return self.cancelled

    def start_step(self, job: IngestionJob, workflow_node: str, input_summary: str, input_payload: dict[str, Any] | None = None) -> StepHandle:
        step_id = f"step-{len(self.steps) + 1}"
        self.steps[step_id] = {
            "workflow_node": workflow_node,
            "input_summary": input_summary,
            "input_payload": input_payload or {},
            "status": "running",
        }
        return StepHandle(id=step_id, started_at=datetime.now(UTC))

    def finish_step(
        self,
        step: StepHandle,
        *,
        status: str = "completed",
        output_summary: str | None = None,
        output_payload: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_type: str | None = None,
    ) -> None:
        self.steps[step.id].update(
            {
                "status": status,
                "output_summary": output_summary,
                "output_payload": output_payload or {},
                "error_code": error_code,
                "error_type": error_type,
            }
        )

    def add_event(
        self,
        job: IngestionJob,
        event_type: str,
        title: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        *,
        step_id: str | None = None,
        visibility: str = "default",
    ) -> None:
        self.events.append((event_type, title))

    def add_artifact(self, job: IngestionJob, artifact: ArtifactRecord, *, step_id: str | None = None) -> None:
        self.artifacts.append(artifact)

    def replace_candidates(self, job: IngestionJob, candidates: list[Candidate]) -> list[Candidate]:
        for index, candidate in enumerate(candidates, start=1):
            candidate.id = f"candidate-{index}"
        self.candidates = list(candidates)
        return self.candidates

    def apply_completion_policy(self, job: IngestionJob, candidates: list[Candidate], classifier_label: str, classifier_confidence: float, metadata: dict[str, Any]) -> None:
        self.completed = True
        self.job.status = "completed"
        self.job.stage = "materialized"

    def fail_job(self, job: IngestionJob, error_code: str, message: str) -> None:
        self.failed = True

    def cancel_job(self, job: IngestionJob, reason: str = "cancel_requested") -> None:
        self.cancelled_job = True

    def heartbeat(self, job: IngestionJob) -> None:
        pass


def test_document_skill_router_extracts_question_knowledge_and_background() -> None:
    job = make_job()
    content = b"""# Speaking practice
Part 1
What do you do in your free time?

Describe a city you enjoyed visiting
- where it is
- why you went there

Target band: 7.5
Occupation: software engineer

Useful answer material: I often connect the topic to concrete examples and short stories.
"""
    document = extract_document(content, filename="notes.md", extension=".md", mime_type="text/markdown")
    result = DocumentSkillRouter().extract(job, document)

    kinds = {candidate.candidate_kind for candidate in result.candidates}
    assert {"question", "knowledge", "background"}.issubset(kinds)
    assert result.classifier_label in {"question_bank", "topic_knowledge", "user_profile"}
    assert "question_extractor" in result.skills_used
    assert any(candidate.normalized_payload.get("fact_key") == "target_band" for candidate in result.candidates)


def test_supervisor_processes_one_job_and_records_artifacts() -> None:
    job = make_job()
    object_store = InMemoryDocumentObjectStore(
        {
            ("bucket", "knowledge/user/notes.md"): b"""# IELTS notes
What kind of music do you like?
Occupation: product manager

Topic material: Music helps me relax after a long day and gives me examples for Part 1 answers.
"""
        }
    )
    repository = FakeRepository(job)
    supervisor = DocumentIngestionSupervisor(
        enabled=True,
        repository=repository,
        object_store=object_store,
        poll_interval_seconds=0.25,
        worker_id="test-worker",
    )

    processed = asyncio.run(supervisor.process_next())

    assert processed is True
    assert repository.completed is True
    assert repository.failed is False
    assert ("file_fetch", 18) in repository.stages
    assert ("text_extract", 35) in repository.stages
    assert ("candidate_extract", 65) in repository.stages
    assert {candidate.candidate_kind for candidate in repository.candidates} >= {"question", "background"}
    assert {"extracted_text", "normalized_text", "candidate_export", "preview"}.issubset(
        {artifact.artifact_kind for artifact in repository.artifacts}
    )
    assert ("run.completed", "文档解析完成") in repository.events


def test_supervisor_honors_cancel_request_before_processing_file() -> None:
    job = make_job()
    object_store = InMemoryDocumentObjectStore({("bucket", "knowledge/user/notes.md"): b"What do you study?"})
    repository = FakeRepository(job, cancelled=True)
    supervisor = DocumentIngestionSupervisor(
        enabled=True,
        repository=repository,
        object_store=object_store,
        poll_interval_seconds=0.25,
        worker_id="test-worker",
    )

    processed = asyncio.run(supervisor.process_next())

    assert processed is True
    assert repository.cancelled_job is True
    assert repository.completed is False
    assert repository.candidates == []
