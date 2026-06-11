from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


JobStatus = Literal[
    "queued",
    "running",
    "awaiting_review",
    "awaiting_user_confirmation",
    "completed",
    "failed",
    "cancelled",
    "rejected",
]
CandidateKind = Literal["question", "knowledge", "background"]
CandidateStatus = Literal["pending", "approved", "rejected", "confirmed", "materialized"]
ArtifactKind = Literal[
    "original",
    "extracted_text",
    "normalized_text",
    "command_output",
    "preview",
    "candidate_export",
    "materialization_simulation",
]


@dataclass(slots=True)
class SourceFile:
    id: str
    owner_user_id: str
    visibility: str
    upload_purpose: str
    title: str
    original_filename: str
    extension: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    storage_bucket: str
    storage_key: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IngestionJob:
    id: str
    owner_user_id: str
    requested_visibility: str
    requested_action: str
    status: JobStatus
    stage: str
    progress_pct: int
    priority: int
    source_file: SourceFile
    run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimePolicy:
    max_concurrency: int = 2
    paused: bool = False


@dataclass(slots=True)
class ExtractedDocument:
    text: str
    parser_name: str
    command_log: str
    page_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Candidate:
    candidate_kind: CandidateKind
    title: str
    content: str
    summary: str | None = None
    normalized_payload: dict[str, Any] = field(default_factory=dict)
    materialization_plan: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    candidate_status: CandidateStatus = "pending"
    id: str | None = None


@dataclass(slots=True)
class ExtractionResult:
    classifier_label: str
    classifier_confidence: float
    candidates: list[Candidate]
    skills_used: list[str] = field(default_factory=list)
    normalized_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ArtifactRecord:
    artifact_kind: ArtifactKind
    title: str
    content_type: str
    inline_text: str | None = None
    storage_bucket: str | None = None
    storage_key: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StepHandle:
    id: str
    started_at: datetime
