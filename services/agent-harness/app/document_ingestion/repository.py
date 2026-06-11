from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

from app.document_ingestion.models import ArtifactRecord, Candidate, IngestionJob, RuntimePolicy, SourceFile, StepHandle
from app.rag.llamaindex_service import load_psycopg


class IngestionRepository(Protocol):
    def get_runtime_policy(self) -> RuntimePolicy: ...
    def claim_next_job(self, worker_id: str) -> IngestionJob | None: ...
    def mark_job_stage(self, job_id: str, stage: str, progress_pct: int, metadata: dict[str, Any] | None = None) -> None: ...
    def is_cancel_requested(self, job_id: str) -> bool: ...
    def start_step(self, job: IngestionJob, workflow_node: str, input_summary: str, input_payload: dict[str, Any] | None = None) -> StepHandle: ...
    def finish_step(
        self,
        step: StepHandle,
        *,
        status: str = "completed",
        output_summary: str | None = None,
        output_payload: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_type: str | None = None,
    ) -> None: ...
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
    ) -> None: ...
    def add_artifact(self, job: IngestionJob, artifact: ArtifactRecord, *, step_id: str | None = None) -> None: ...
    def replace_candidates(self, job: IngestionJob, candidates: list[Candidate]) -> list[Candidate]: ...
    def apply_completion_policy(self, job: IngestionJob, candidates: list[Candidate], classifier_label: str, classifier_confidence: float, metadata: dict[str, Any]) -> None: ...
    def fail_job(self, job: IngestionJob, error_code: str, message: str) -> None: ...
    def cancel_job(self, job: IngestionJob, reason: str = "cancel_requested") -> None: ...
    def heartbeat(self, job: IngestionJob) -> None: ...


class PostgresIngestionRepository:
    def __init__(self, database_url: str, *, chunk_max_chars: int = 1200, chunk_overlap_chars: int = 120) -> None:
        self.database_url = database_url
        self.chunk_max_chars = chunk_max_chars
        self.chunk_overlap_chars = chunk_overlap_chars
        self.psycopg, self.Jsonb = load_psycopg()

    def get_runtime_policy(self) -> RuntimePolicy:
        with self._connect() as conn:
            row = conn.execute(
                """
                select policy_value
                from agent_runtime_policies
                where policy_key = 'document_ingestion'
                """
            ).fetchone()
        if not row:
            return RuntimePolicy()
        payload = row["policy_value"] or {}
        return RuntimePolicy(
            max_concurrency=max(1, int(payload.get("max_concurrency") or 2)),
            paused=bool(payload.get("paused")),
        )

    def claim_next_job(self, worker_id: str) -> IngestionJob | None:
        run_id = f"run_doc_ingestion_{uuid4().hex}"
        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    select
                        j.id::text as job_id,
                        j.owner_user_id::text as owner_user_id,
                        j.requested_visibility,
                        j.requested_action,
                        j.status,
                        j.stage,
                        j.progress_pct,
                        j.priority,
                        j.metadata as job_metadata,
                        sf.id::text as source_file_id,
                        sf.owner_user_id::text as source_owner_user_id,
                        sf.visibility,
                        sf.upload_purpose,
                        sf.title,
                        sf.original_filename,
                        sf.extension,
                        sf.mime_type,
                        sf.size_bytes,
                        sf.checksum_sha256,
                        sf.storage_bucket,
                        sf.storage_key,
                        sf.metadata as source_metadata
                    from knowledge_ingestion_jobs j
                    join knowledge_source_files sf on sf.id = j.source_file_id
                    where j.status = 'queued'
                      and j.cancel_requested_at is null
                    order by j.priority desc, j.queued_at asc
                    for update skip locked
                    limit 1
                    """
                ).fetchone()
                if not row:
                    return None

                self._clear_previous_outputs(conn, row["job_id"])
                conn.execute(
                    """
                    insert into agent_runs
                        (id, user_id, status, metadata, run_kind, subject_type, subject_id, started_at)
                    values
                        (%s, %s::uuid, 'running', %s::jsonb, 'document_ingestion', 'knowledge_ingestion_job', %s, now())
                    """,
                    (
                        run_id,
                        row["owner_user_id"],
                        self._jsonb(
                            {
                                "worker_id": worker_id,
                                "job_id": row["job_id"],
                                "source_file_id": row["source_file_id"],
                                "requested_action": row["requested_action"],
                                "requested_visibility": row["requested_visibility"],
                            }
                        ),
                        row["job_id"],
                    ),
                )
                conn.execute(
                    """
                    update knowledge_ingestion_jobs
                    set status = 'running',
                        stage = 'agent_claimed',
                        progress_pct = greatest(progress_pct, 10),
                        run_id = %s,
                        started_at = coalesce(started_at, now()),
                        heartbeat_at = now(),
                        metadata = metadata || %s::jsonb
                    where id = %s::uuid
                    """,
                    (run_id, self._jsonb({"worker_id": worker_id, "claimed_at": datetime.now(UTC).isoformat()}), row["job_id"]),
                )

        source_file = SourceFile(
            id=row["source_file_id"],
            owner_user_id=row["source_owner_user_id"],
            visibility=row["visibility"],
            upload_purpose=row["upload_purpose"],
            title=row["title"],
            original_filename=row["original_filename"],
            extension=row["extension"],
            mime_type=row["mime_type"],
            size_bytes=int(row["size_bytes"]),
            checksum_sha256=row["checksum_sha256"],
            storage_bucket=row["storage_bucket"],
            storage_key=row["storage_key"],
            metadata=dict(row["source_metadata"] or {}),
        )
        return IngestionJob(
            id=row["job_id"],
            owner_user_id=row["owner_user_id"],
            requested_visibility=row["requested_visibility"],
            requested_action=row["requested_action"],
            status="running",
            stage="agent_claimed",
            progress_pct=max(10, int(row["progress_pct"] or 0)),
            priority=int(row["priority"] or 0),
            source_file=source_file,
            run_id=run_id,
            metadata=dict(row["job_metadata"] or {}),
        )

    def mark_job_stage(self, job_id: str, stage: str, progress_pct: int, metadata: dict[str, Any] | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                update knowledge_ingestion_jobs
                set stage = %s,
                    progress_pct = greatest(progress_pct, %s),
                    heartbeat_at = now(),
                    metadata = metadata || %s::jsonb
                where id = %s::uuid
                """,
                (stage, max(0, min(100, progress_pct)), self._jsonb(metadata or {}), job_id),
            )

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                select cancel_requested_at is not null or status = 'cancelled' as cancelled
                from knowledge_ingestion_jobs
                where id = %s::uuid
                """,
                (job_id,),
            ).fetchone()
        return bool(row and row["cancelled"])

    def start_step(self, job: IngestionJob, workflow_node: str, input_summary: str, input_payload: dict[str, Any] | None = None) -> StepHandle:
        started_at = datetime.now(UTC)
        with self._connect() as conn:
            row = conn.execute(
                """
                insert into agent_steps
                    (run_id, workflow_node, agent_name, prompt_version, model_name, execution_kind, status,
                     input_summary, input_payload, started_at)
                values
                    (%s, %s, 'DocumentIngestionAgent', 'document_ingestion.skills.v1', 'deterministic-skill-router',
                     'deterministic', 'running', %s, %s::jsonb, now())
                returning id::text
                """,
                (job.run_id, workflow_node, input_summary, self._jsonb(input_payload or {})),
            ).fetchone()
        return StepHandle(id=row["id"], started_at=started_at)

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
        latency_ms = max(0, int((datetime.now(UTC) - step.started_at).total_seconds() * 1000))
        with self._connect() as conn:
            conn.execute(
                """
                update agent_steps
                set status = %s,
                    output_summary = %s,
                    output_payload = %s::jsonb,
                    error_code = %s,
                    error_type = %s,
                    latency_ms = %s,
                    finished_at = now()
                where id = %s::uuid
                """,
                (status, output_summary, self._jsonb(output_payload or {}), error_code, error_type, latency_ms, step.id),
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
        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "select coalesce(max(event_index) + 1, 0) as next_index from agent_run_events where run_id = %s",
                    (job.run_id,),
                ).fetchone()
                conn.execute(
                    """
                    insert into agent_run_events
                        (run_id, step_id, event_index, event_type, title, summary, visibility, payload)
                    values
                        (%s, nullif(%s, '')::uuid, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (job.run_id, step_id or "", int(row["next_index"]), event_type, title, summary, visibility, self._jsonb(payload or {})),
                )

    def add_artifact(self, job: IngestionJob, artifact: ArtifactRecord, *, step_id: str | None = None) -> None:
        with self._connect() as conn:
            with conn.transaction():
                run_artifact_id = conn.execute(
                    """
                    insert into agent_run_artifacts
                        (run_id, step_id, artifact_kind, title, content_type, storage_bucket, storage_key, size_bytes, inline_text, metadata)
                    values
                        (%s, nullif(%s, '')::uuid, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    returning id::text
                    """,
                    (
                        job.run_id,
                        step_id or "",
                        artifact.artifact_kind,
                        artifact.title,
                        artifact.content_type,
                        artifact.storage_bucket,
                        artifact.storage_key,
                        artifact.size_bytes,
                        artifact.inline_text,
                        self._jsonb(artifact.metadata),
                    ),
                ).fetchone()["id"]
                metadata = dict(artifact.metadata)
                metadata["agent_run_artifact_id"] = run_artifact_id
                conn.execute(
                    """
                    insert into knowledge_ingestion_artifacts
                        (job_id, run_id, artifact_kind, title, content_type, storage_bucket, storage_key, size_bytes, inline_text, metadata)
                    values
                        (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        job.id,
                        job.run_id,
                        artifact.artifact_kind,
                        artifact.title,
                        artifact.content_type,
                        artifact.storage_bucket,
                        artifact.storage_key,
                        artifact.size_bytes,
                        artifact.inline_text,
                        self._jsonb(metadata),
                    ),
                )

    def replace_candidates(self, job: IngestionJob, candidates: list[Candidate]) -> list[Candidate]:
        saved: list[Candidate] = []
        with self._connect() as conn:
            with conn.transaction():
                conn.execute("delete from knowledge_ingestion_candidates where job_id = %s::uuid", (job.id,))
                for candidate in candidates:
                    row = conn.execute(
                        """
                        insert into knowledge_ingestion_candidates
                            (job_id, candidate_kind, title, summary, content, candidate_status,
                             normalized_payload, materialization_plan, metadata)
                        values
                            (%s::uuid, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                        returning id::text
                        """,
                        (
                            job.id,
                            candidate.candidate_kind,
                            candidate.title,
                            candidate.summary,
                            candidate.content,
                            candidate.candidate_status,
                            self._jsonb(candidate.normalized_payload),
                            self._jsonb(candidate.materialization_plan),
                            self._jsonb(candidate.metadata),
                        ),
                    ).fetchone()
                    candidate.id = row["id"]
                    saved.append(candidate)
        return saved

    def apply_completion_policy(
        self,
        job: IngestionJob,
        candidates: list[Candidate],
        classifier_label: str,
        classifier_confidence: float,
        metadata: dict[str, Any],
    ) -> None:
        if self.is_cancel_requested(job.id):
            self.cancel_job(job)
            return

        has_background = any(candidate.candidate_kind == "background" for candidate in candidates)
        materialized_ids: list[str] = []
        with self._connect() as conn:
            with conn.transaction():
                if job.requested_visibility == "private":
                    for candidate in candidates:
                        if candidate.candidate_kind == "background":
                            continue
                        if candidate.id is None:
                            continue
                        self._materialize_private_candidate(conn, job, candidate)
                        materialized_ids.append(candidate.id)
                    if materialized_ids:
                        conn.execute(
                            """
                            update knowledge_ingestion_candidates
                            set candidate_status = 'materialized'
                            where id = any(%s::uuid[])
                            """,
                            (materialized_ids,),
                        )

                status = "awaiting_review" if job.requested_visibility == "public" else "completed"
                stage = "awaiting_review" if job.requested_visibility == "public" else "materialized"
                progress = 95 if job.requested_visibility == "public" else 100
                finished_at = "now()"
                materialized_at = "now()" if status == "completed" else None
                if job.requested_visibility == "private" and has_background:
                    status = "awaiting_user_confirmation"
                    stage = "awaiting_user_confirmation"
                    progress = 95
                    materialized_at = None

                final_metadata = {
                    **metadata,
                    "candidate_count": len(candidates),
                    "materialized_private_candidate_ids": materialized_ids,
                    "requires_admin_review": job.requested_visibility == "public",
                    "requires_user_confirmation": job.requested_visibility == "private" and has_background,
                }
                conn.execute(
                    f"""
                    update knowledge_ingestion_jobs
                    set status = %s,
                        stage = %s,
                        progress_pct = %s,
                        classifier_label = %s,
                        classifier_confidence = %s,
                        heartbeat_at = now(),
                        finished_at = {finished_at or 'null'},
                        materialized_at = {materialized_at or 'null'},
                        metadata = metadata || %s::jsonb
                    where id = %s::uuid
                    """,
                    (status, stage, progress, classifier_label, classifier_confidence, self._jsonb(final_metadata), job.id),
                )
                conn.execute(
                    "update agent_runs set status = 'completed', finished_at = now() where id = %s",
                    (job.run_id,),
                )

    def fail_job(self, job: IngestionJob, error_code: str, message: str) -> None:
        with self._connect() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    update knowledge_ingestion_jobs
                    set status = 'failed',
                        stage = 'failed',
                        progress_pct = least(progress_pct, 99),
                        error_code = %s,
                        error_message = %s,
                        heartbeat_at = now(),
                        finished_at = now(),
                        metadata = metadata || %s::jsonb
                    where id = %s::uuid
                    """,
                    (error_code, message[:800], self._jsonb({"failed_at": datetime.now(UTC).isoformat()}), job.id),
                )
                if job.run_id:
                    conn.execute("update agent_runs set status = 'failed', finished_at = now() where id = %s", (job.run_id,))

    def cancel_job(self, job: IngestionJob, reason: str = "cancel_requested") -> None:
        with self._connect() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    update knowledge_ingestion_jobs
                    set status = 'cancelled',
                        stage = 'cancelled',
                        heartbeat_at = now(),
                        finished_at = coalesce(finished_at, now()),
                        metadata = metadata || %s::jsonb
                    where id = %s::uuid
                    """,
                    (self._jsonb({"cancel_reason": reason, "cancelled_at": datetime.now(UTC).isoformat()}), job.id),
                )
                if job.run_id:
                    conn.execute("update agent_runs set status = 'cancelled', finished_at = now() where id = %s", (job.run_id,))

    def heartbeat(self, job: IngestionJob) -> None:
        with self._connect() as conn:
            conn.execute("update knowledge_ingestion_jobs set heartbeat_at = now() where id = %s::uuid", (job.id,))

    def _materialize_private_candidate(self, conn: Any, job: IngestionJob, candidate: Candidate) -> None:
        doc_type = "question_bank" if candidate.candidate_kind == "question" else "topic_knowledge"
        metadata = {
            "doc_type": doc_type,
            "title": candidate.title,
            "status": "active",
            "source": "document_ingestion",
            "job_id": job.id,
            "candidate_id": candidate.id,
            "source_file_id": job.source_file.id,
            "requested_action": job.requested_action,
            **candidate.metadata,
        }
        row = conn.execute(
            """
            insert into knowledge_docs (doc_type, owner_user_id, source_id, title, content_hash, metadata, status)
            values (%s::knowledge_doc_type, %s::uuid, %s::uuid, %s, %s, %s::jsonb, 'active'::content_status)
            returning id::text
            """,
            (doc_type, job.owner_user_id, job.source_file.id, candidate.title, hash_text(candidate.content), self._jsonb(metadata)),
        ).fetchone()
        chunks = split_text(candidate.content, self.chunk_max_chars, self.chunk_overlap_chars)
        for index, chunk in enumerate(chunks):
            chunk_metadata = {**metadata, "chunk_index": index}
            conn.execute(
                """
                insert into knowledge_chunks (doc_id, chunk_index, content, metadata, embedding, embedding_model, token_count)
                values (%s::uuid, %s, %s, %s::jsonb, null, null, %s)
                """,
                (row["id"], index, chunk, self._jsonb(chunk_metadata), estimate_token_count(chunk)),
            )

    def _clear_previous_outputs(self, conn: Any, job_id: str) -> None:
        conn.execute("delete from knowledge_ingestion_candidates where job_id = %s::uuid", (job_id,))
        conn.execute(
            """
            delete from knowledge_ingestion_artifacts
            where job_id = %s::uuid
              and artifact_kind <> 'original'
            """,
            (job_id,),
        )

    def _connect(self) -> Any:
        return self.psycopg.connect(self.database_url, row_factory=self.psycopg.rows.dict_row)

    def _jsonb(self, value: Any) -> Any:
        return self.Jsonb(value)


def split_text(content: str, max_chars: int, overlap_chars: int) -> list[str]:
    content = content.strip()
    if not content:
        return ["-"]
    if len(content) <= max_chars:
        return [content]
    chunks: list[str] = []
    start = 0
    while start < len(content):
        end = min(len(content), start + max_chars)
        cut = end
        if end < len(content):
            window = content[start:end]
            candidates = [window.rfind(marker) for marker in ("\n", "。", ".", "?", "!", ";", " ")]
            best = max(candidates)
            if best > max_chars // 2:
                cut = start + best + 1
        chunks.append(content[start:cut].strip())
        if cut >= len(content):
            break
        start = max(cut - overlap_chars, start + 1)
    return [chunk for chunk in chunks if chunk]


def estimate_token_count(content: str) -> int:
    return len(content.split())


def hash_text(value: str) -> str:
    digest = hashlib.sha256(value.strip().encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class TimedStep:
    def __init__(self, repository: IngestionRepository, job: IngestionJob, workflow_node: str, input_summary: str, input_payload: dict[str, Any] | None = None) -> None:
        self.repository = repository
        self.job = job
        self.workflow_node = workflow_node
        self.input_summary = input_summary
        self.input_payload = input_payload
        self.step: StepHandle | None = None
        self.started_perf = 0.0

    def __enter__(self) -> StepHandle:
        self.started_perf = perf_counter()
        self.step = self.repository.start_step(self.job, self.workflow_node, self.input_summary, self.input_payload)
        self.repository.add_event(
            self.job,
            "step.started",
            self.workflow_node,
            self.input_summary,
            {"workflow_node": self.workflow_node},
            step_id=self.step.id,
        )
        return self.step

    def finish(self, *, output_summary: str, output_payload: dict[str, Any] | None = None) -> None:
        if self.step is None:
            return
        payload = dict(output_payload or {})
        payload["latency_ms"] = max(0, int((perf_counter() - self.started_perf) * 1000))
        self.repository.finish_step(self.step, output_summary=output_summary, output_payload=payload)
        self.repository.add_event(
            self.job,
            "step.completed",
            self.workflow_node,
            output_summary,
            payload,
            step_id=self.step.id,
        )

    def fail(self, *, error_code: str, message: str) -> None:
        if self.step is None:
            return
        self.repository.finish_step(
            self.step,
            status="failed",
            output_summary=message[:240],
            output_payload={"error": message},
            error_code=error_code,
            error_type="runtime",
        )
        self.repository.add_event(
            self.job,
            "step.failed",
            self.workflow_node,
            message[:240],
            {"error_code": error_code, "message": message},
            step_id=self.step.id,
            visibility="details",
        )

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        if exc is not None:
            self.fail(error_code=exc.__class__.__name__, message=str(exc))
        return False


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
