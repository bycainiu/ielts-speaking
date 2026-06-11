from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.document_ingestion.extractor import DocumentParseError, DocumentSkillRouter, candidates_to_json, extract_document
from app.document_ingestion.models import ArtifactRecord, Candidate, ExtractionResult, IngestionJob
from app.document_ingestion.repository import IngestionRepository, PostgresIngestionRepository, TimedStep
from app.document_ingestion.storage import MinioDocumentObjectStore, ObjectStorageError, artifact_key


logger = logging.getLogger("agent_harness.document_ingestion")


class DocumentIngestionCancelled(RuntimeError):
    pass


class DocumentIngestionSupervisor:
    def __init__(
        self,
        *,
        enabled: bool,
        repository: IngestionRepository | None,
        object_store: Any | None,
        poll_interval_seconds: float = 2.0,
        worker_id: str | None = None,
        max_inline_artifact_chars: int = 16000,
        skill_router: DocumentSkillRouter | None = None,
    ) -> None:
        self.enabled = enabled
        self.repository = repository
        self.object_store = object_store
        self.poll_interval_seconds = max(0.25, poll_interval_seconds)
        self.worker_id = worker_id or f"document-ingestion-{uuid4().hex[:10]}"
        self.max_inline_artifact_chars = max(2000, max_inline_artifact_chars)
        self.skill_router = skill_router or DocumentSkillRouter()
        self._loop_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._active_tasks: set[asyncio.Task[None]] = set()

    def describe(self) -> dict[str, Any]:
        policy = None
        if self.repository is not None:
            try:
                policy = asdict(self.repository.get_runtime_policy())
            except Exception as exc:  # pragma: no cover - healthz 不能因为 DB 短暂失败整体不可用
                policy = {"error": exc.__class__.__name__, "message": str(exc)}
        return {
            "enabled": self.enabled,
            "ready": self.enabled and self.repository is not None and self.object_store is not None,
            "worker_id": self.worker_id,
            "active_runs": len(self._active_tasks),
            "poll_interval_seconds": self.poll_interval_seconds,
            "policy": policy,
        }

    async def start(self) -> None:
        if not self.enabled or self.repository is None or self.object_store is None:
            logger.info("document_ingestion_supervisor_disabled", extra={"worker_id": self.worker_id})
            return
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stop_event.clear()
        self._loop_task = asyncio.create_task(self._run_loop(), name="document-ingestion-supervisor")
        logger.info("document_ingestion_supervisor_started", extra={"worker_id": self.worker_id})

    async def stop(self) -> None:
        self._stop_event.set()
        if self._loop_task is not None:
            await self._loop_task
        if self._active_tasks:
            await asyncio.gather(*list(self._active_tasks), return_exceptions=True)

    async def process_next(self) -> bool:
        if self.repository is None or self.object_store is None:
            return False
        policy = await asyncio.to_thread(self.repository.get_runtime_policy)
        if policy.paused:
            return False
        job = await asyncio.to_thread(self.repository.claim_next_job, self.worker_id)
        if job is None:
            return False
        await self._process_job(job)
        return True

    async def _run_loop(self) -> None:
        assert self.repository is not None
        while not self._stop_event.is_set():
            self._active_tasks = {task for task in self._active_tasks if not task.done()}
            try:
                policy = await asyncio.to_thread(self.repository.get_runtime_policy)
                if not policy.paused:
                    capacity = max(0, policy.max_concurrency - len(self._active_tasks))
                    for _ in range(capacity):
                        job = await asyncio.to_thread(self.repository.claim_next_job, self.worker_id)
                        if job is None:
                            break
                        task = asyncio.create_task(self._process_job(job), name=f"document-ingestion-{job.id}")
                        task.add_done_callback(self._log_task_exception)
                        self._active_tasks.add(task)
            except Exception:
                logger.exception("document_ingestion_dispatch_failed", extra={"worker_id": self.worker_id})
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                continue

    def _log_task_exception(self, task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except Exception:
            logger.exception("document_ingestion_task_failed", extra={"worker_id": self.worker_id})

    async def _process_job(self, job: IngestionJob) -> None:
        assert self.repository is not None
        assert self.object_store is not None
        try:
            self.repository.add_event(
                job,
                "run.started",
                "文档解析开始",
                f"开始处理 {job.source_file.original_filename}",
                {
                    "job_id": job.id,
                    "source_file_id": job.source_file.id,
                    "skills_entry": "app/document_ingestion/skills/SKILL.md",
                },
            )
            await self._raise_if_cancelled(job)

            content = await self._download_original(job)
            await self._raise_if_cancelled(job)

            document = await self._extract_text(job, content)
            await self._raise_if_cancelled(job)

            result = await self._extract_candidates(job, document)
            await self._raise_if_cancelled(job)

            saved = await asyncio.to_thread(self.repository.replace_candidates, job, result.candidates)
            await self._publish_result_artifacts(job, result, saved)
            await self._raise_if_cancelled(job)

            await asyncio.to_thread(
                self.repository.apply_completion_policy,
                job,
                saved,
                result.classifier_label,
                result.classifier_confidence,
                {"skills_used": result.skills_used, "extractor_metadata": result.metadata},
            )
            self.repository.add_event(
                job,
                "run.completed",
                "文档解析完成",
                f"生成 {len(saved)} 个候选，分类为 {result.classifier_label}",
                {
                    "candidate_count": len(saved),
                    "classifier_label": result.classifier_label,
                    "classifier_confidence": result.classifier_confidence,
                },
            )
        except DocumentIngestionCancelled as exc:
            self.repository.cancel_job(job, str(exc))
            self.repository.add_event(job, "run.cancelled", "文档解析已取消", str(exc), {"reason": str(exc)})
        except (DocumentParseError, ObjectStorageError) as exc:
            self.repository.fail_job(job, exc.__class__.__name__, str(exc))
            self.repository.add_event(job, "run.failed", "文档解析失败", str(exc), {"error_code": exc.__class__.__name__}, visibility="details")
        except Exception as exc:
            self.repository.fail_job(job, exc.__class__.__name__, str(exc))
            self.repository.add_event(job, "run.failed", "文档解析异常", str(exc), {"error_code": exc.__class__.__name__}, visibility="details")
            raise

    async def _download_original(self, job: IngestionJob) -> bytes:
        assert self.repository is not None
        assert self.object_store is not None
        self.repository.mark_job_stage(job.id, "file_fetch", 18)
        context = TimedStep(
            self.repository,
            job,
            "file_fetch",
            f"从对象存储读取 {job.source_file.original_filename}",
            {"bucket": job.source_file.storage_bucket, "key": job.source_file.storage_key, "size_bytes": job.source_file.size_bytes},
        )
        with context as step:
            content = await asyncio.to_thread(self.object_store.get_bytes, job.source_file.storage_bucket, job.source_file.storage_key)
            self.repository.add_artifact(
                job,
                ArtifactRecord(
                    artifact_kind="command_output",
                    title="对象存储读取日志",
                    content_type="text/plain",
                    inline_text=f"downloaded {len(content)} bytes from {job.source_file.storage_bucket}/{job.source_file.storage_key}",
                    size_bytes=len(content),
                    metadata={"stage": "file_fetch"},
                ),
                step_id=step.id,
            )
            context.finish(
                output_summary=f"读取 {len(content)} 字节",
                output_payload={"byte_size": len(content), "checksum_sha256": job.source_file.checksum_sha256},
            )
            return content

    async def _extract_text(self, job: IngestionJob, content: bytes):
        assert self.repository is not None
        self.repository.mark_job_stage(job.id, "text_extract", 35)
        context = TimedStep(
            self.repository,
            job,
            "text_extract",
            "抽取文档文本",
            {
                "filename": job.source_file.original_filename,
                "extension": job.source_file.extension,
                "mime_type": job.source_file.mime_type,
            },
        )
        with context as step:
            document = await asyncio.to_thread(
                extract_document,
                content,
                filename=job.source_file.original_filename,
                extension=job.source_file.extension,
                mime_type=job.source_file.mime_type,
            )
            await self._store_text_artifact(
                job,
                "extracted_text",
                "抽取文本",
                document.text,
                {"parser": document.parser_name, "page_count": document.page_count},
                step_id=step.id,
            )
            self.repository.add_artifact(
                job,
                ArtifactRecord(
                    artifact_kind="command_output",
                    title="解析命令输出",
                    content_type="text/plain",
                    inline_text=document.command_log,
                    metadata={"stage": "text_extract", "parser": document.parser_name},
                ),
                step_id=step.id,
            )
            context.finish(
                output_summary=f"{document.parser_name} 抽取 {len(document.text)} 个字符",
                output_payload={"parser": document.parser_name, "char_count": len(document.text), "page_count": document.page_count},
            )
            return document

    async def _extract_candidates(self, job: IngestionJob, document: Any) -> ExtractionResult:
        assert self.repository is not None
        self.repository.mark_job_stage(job.id, "candidate_extract", 65)
        context = TimedStep(
            self.repository,
            job,
            "candidate_extract",
            "运行文档导入技能路由",
            {"requested_action": job.requested_action, "requested_visibility": job.requested_visibility},
        )
        with context as step:
            result = await asyncio.to_thread(self.skill_router.extract, job, document)
            await self._store_text_artifact(
                job,
                "normalized_text",
                "规范化文本",
                result.normalized_text,
                {"skills_used": result.skills_used},
                step_id=step.id,
            )
            context.finish(
                output_summary=f"识别 {len(result.candidates)} 个候选",
                output_payload={
                    "classifier_label": result.classifier_label,
                    "classifier_confidence": result.classifier_confidence,
                    "skills_used": result.skills_used,
                    "candidate_kinds": candidate_counts(result.candidates),
                },
            )
            return result

    async def _publish_result_artifacts(self, job: IngestionJob, result: ExtractionResult, saved: list[Candidate]) -> None:
        assert self.repository is not None
        self.repository.mark_job_stage(job.id, "candidate_write", 82)
        context = TimedStep(
            self.repository,
            job,
            "candidate_write",
            "保存候选结果与预览产物",
            {"candidate_count": len(saved)},
        )
        with context as step:
            payload = candidates_to_json(saved)
            await self._store_text_artifact(
                job,
                "candidate_export",
                "候选结果 JSON",
                payload,
                {
                    "classifier_label": result.classifier_label,
                    "classifier_confidence": result.classifier_confidence,
                    "candidate_count": len(saved),
                },
                step_id=step.id,
                extension=".json",
                content_type="application/json",
            )
            preview = build_preview(saved)
            self.repository.add_artifact(
                job,
                ArtifactRecord(
                    artifact_kind="preview",
                    title="候选结果预览",
                    content_type="text/markdown",
                    inline_text=preview,
                    metadata={"candidate_count": len(saved), "candidate_kinds": candidate_counts(saved)},
                ),
                step_id=step.id,
            )
            context.finish(output_summary="候选结果已保存", output_payload={"candidate_count": len(saved), "preview_chars": len(preview)})

    async def _store_text_artifact(
        self,
        job: IngestionJob,
        artifact_kind: str,
        title: str,
        text: str,
        metadata: dict[str, Any],
        *,
        step_id: str,
        extension: str = ".txt",
        content_type: str = "text/plain",
    ) -> None:
        assert self.repository is not None
        assert self.object_store is not None
        encoded = text.encode("utf-8")
        if len(text) <= self.max_inline_artifact_chars:
            self.repository.add_artifact(
                job,
                ArtifactRecord(
                    artifact_kind=artifact_kind,  # type: ignore[arg-type]
                    title=title,
                    content_type=content_type,
                    inline_text=text,
                    size_bytes=len(encoded),
                    metadata=metadata,
                ),
                step_id=step_id,
            )
            return
        key = artifact_key(job.id, title, extension)
        await asyncio.to_thread(self.object_store.put_bytes, job.source_file.storage_bucket, key, encoded, content_type)
        self.repository.add_artifact(
            job,
            ArtifactRecord(
                artifact_kind=artifact_kind,  # type: ignore[arg-type]
                title=title,
                content_type=content_type,
                storage_bucket=job.source_file.storage_bucket,
                storage_key=key,
                size_bytes=len(encoded),
                inline_text=text[: self.max_inline_artifact_chars],
                metadata={**metadata, "truncated_inline_preview": True},
            ),
            step_id=step_id,
        )

    async def _raise_if_cancelled(self, job: IngestionJob) -> None:
        assert self.repository is not None
        cancelled = await asyncio.to_thread(self.repository.is_cancel_requested, job.id)
        if cancelled:
            raise DocumentIngestionCancelled("cancel_requested")


def build_document_ingestion_supervisor(settings: Settings) -> DocumentIngestionSupervisor:
    if not settings.document_ingestion_enabled or not settings.knowledge_database_url:
        return DocumentIngestionSupervisor(
            enabled=False,
            repository=None,
            object_store=None,
            poll_interval_seconds=settings.document_ingestion_poll_interval_seconds,
            worker_id=settings.document_ingestion_worker_id,
        )

    repository = PostgresIngestionRepository(
        settings.knowledge_database_url,
        chunk_max_chars=settings.knowledge_chunk_max_chars,
        chunk_overlap_chars=settings.knowledge_chunk_overlap_chars,
    )
    object_store = MinioDocumentObjectStore(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
    )
    return DocumentIngestionSupervisor(
        enabled=True,
        repository=repository,
        object_store=object_store,
        poll_interval_seconds=settings.document_ingestion_poll_interval_seconds,
        worker_id=settings.document_ingestion_worker_id,
        max_inline_artifact_chars=settings.document_ingestion_max_inline_artifact_chars,
    )


def candidate_counts(candidates: list[Candidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.candidate_kind] = counts.get(candidate.candidate_kind, 0) + 1
    return counts


def build_preview(candidates: list[Candidate]) -> str:
    lines = ["# 候选结果预览", ""]
    for index, candidate in enumerate(candidates[:12], start=1):
        lines.append(f"## {index}. {candidate.title}")
        lines.append(f"- 类型：{candidate.candidate_kind}")
        if candidate.summary:
            lines.append(f"- 摘要：{candidate.summary}")
        lines.append("")
        lines.append(candidate.content[:600])
        lines.append("")
    if len(candidates) > 12:
        lines.append(f"还有 {len(candidates) - 12} 个候选未在预览中展示。")
    return "\n".join(lines).strip() + "\n"
