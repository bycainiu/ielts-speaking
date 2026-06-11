import type { ReactNode } from "react";

export type KnowledgeSourceFile = {
  id: string;
  owner_user_id: string;
  visibility: "private" | "public";
  upload_purpose: string;
  title: string;
  original_filename: string;
  extension: string;
  mime_type: string;
  size_bytes: number;
  checksum_sha256: string;
  storage_bucket: string;
  storage_key: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type KnowledgeCandidate = {
  id: string;
  job_id: string;
  candidate_kind: "question" | "knowledge" | "background";
  title: string;
  summary?: string | null;
  content: string;
  candidate_status: string;
  normalized_payload: Record<string, unknown>;
  materialization_plan: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type KnowledgeArtifact = {
  id: string;
  job_id: string;
  run_id?: string | null;
  artifact_kind: string;
  title: string;
  content_type: string;
  storage_bucket?: string | null;
  storage_key?: string | null;
  size_bytes?: number | null;
  inline_text?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type AgentRunEvent = {
  id: string;
  step_id?: string | null;
  event_index: number;
  event_type: string;
  title?: string | null;
  summary?: string | null;
  visibility: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AgentRunStep = {
  id: string;
  workflow_node: string;
  agent_name?: string | null;
  execution_kind?: string | null;
  status: string;
  input_summary?: string | null;
  output_summary?: string | null;
  input_payload?: unknown;
  output_payload?: unknown;
  latency_ms?: number | null;
  error_code?: string | null;
  started_at: string;
  finished_at?: string | null;
};

export type KnowledgeImportRun = {
  run_id: string;
  run_kind: string;
  subject_type?: string | null;
  subject_id?: string | null;
  status: string;
  started_at: string;
  finished_at?: string | null;
  steps: AgentRunStep[];
  events: AgentRunEvent[];
  artifacts: KnowledgeArtifact[];
};

export type KnowledgeImportJob = {
  id: string;
  owner_user_id: string;
  requested_visibility: "private" | "public";
  requested_action: string;
  status: string;
  stage: string;
  priority: number;
  progress_pct: number;
  classifier_label?: string | null;
  classifier_confidence?: number | null;
  run_id?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  queued_at: string;
  started_at?: string | null;
  heartbeat_at?: string | null;
  finished_at?: string | null;
  materialized_at?: string | null;
  updated_at: string;
  metadata: Record<string, unknown>;
  source_file: KnowledgeSourceFile;
  candidate_counts: Record<string, number>;
  candidates?: KnowledgeCandidate[];
  artifacts?: KnowledgeArtifact[];
  run?: KnowledgeImportRun | null;
};

export type RuntimePolicy = {
  policy_key: string;
  max_concurrency: number;
  paused: boolean;
  raw: Record<string, unknown>;
  updated_by?: string | null;
  updated_at: string;
};

export type ApiError = {
  response?: {
    data?: {
      message?: string;
    };
  };
  message?: string;
};

export function apiErrorMessage(error: unknown, fallback: string) {
  const apiError = error as ApiError;
  return apiError.response?.data?.message || apiError.message || fallback;
}

export function isSettledJob(status: string) {
  return ["awaiting_review", "awaiting_user_confirmation", "completed", "failed", "cancelled", "rejected"].includes(status);
}

export function canCancelJob(status: string) {
  return ["queued", "running"].includes(status);
}

export function canRetryJob(status: string) {
  return ["failed", "cancelled", "rejected"].includes(status);
}

export function statusTone(status: string): "sage" | "coral" | "red" | "slate" | "blue" | "gold" {
  if (status === "completed") return "sage";
  if (status === "running" || status === "queued") return "coral";
  if (status === "failed" || status === "rejected") return "red";
  if (status === "awaiting_review") return "gold";
  if (status === "awaiting_user_confirmation") return "blue";
  return "slate";
}

export function candidateTone(kind: string): "gold" | "teal" | "sage" {
  if (kind === "question") return "gold";
  if (kind === "background") return "teal";
  return "sage";
}

export function formatBytes(value?: number | null) {
  if (!value || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("zh-CN", { hour12: false });
}

export function shortId(value?: string | null) {
  if (!value) return "-";
  if (value.length <= 16) return value;
  return `${value.slice(0, 8)}...${value.slice(-6)}`;
}

export function asText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function candidateCounts(job: KnowledgeImportJob) {
  return {
    question: job.candidate_counts?.question ?? 0,
    knowledge: job.candidate_counts?.knowledge ?? 0,
    background: job.candidate_counts?.background ?? 0,
  };
}

export function actionLabel(action: string) {
  const labels: Record<string, string> = {
    auto: "自动识别",
    question_bank: "题库",
    knowledge: "知识",
    background: "背景",
    mixed: "混合",
  };
  return labels[action] || action;
}

export function visibilityLabel(visibility: string) {
  return visibility === "public" ? "公共待审核" : "私有";
}

export function renderOptional(value: ReactNode, fallback = "-") {
  return value || fallback;
}
