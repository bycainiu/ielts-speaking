"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  Eye,
  FileJson,
  FileText,
  GitBranch,
  Loader2,
  RefreshCcw,
  RotateCcw,
  ShieldCheck,
  StopCircle,
  XCircle,
} from "lucide-react";

import { AcademicShell, DetailDialog, EmptyState, InlineKpi, MonoBlock, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { authenticatedFetch } from "@/lib/authSession";
import { api } from "@/lib/api";
import {
  actionLabel,
  apiErrorMessage,
  asText,
  canCancelJob,
  canRetryJob,
  candidateTone,
  formatBytes,
  formatDateTime,
  isSettledJob,
  shortId,
  statusTone,
  visibilityLabel,
  type AgentRunEvent,
  type AgentRunStep,
  type KnowledgeArtifact,
  type KnowledgeCandidate,
  type KnowledgeImportJob,
} from "@/lib/knowledgeIngestion";
import { useAuthStore } from "@/store/authStore";

type StreamEvent = {
  event: string;
  data: unknown;
};

type DetailViewerState = {
  title: string;
  subtitle?: string;
  payload: unknown;
};

export default function AdminKnowledgeImportDetailPage() {
  const router = useRouter();
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;
  const { user, accessToken, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [job, setJob] = useState<KnowledgeImportJob | null>(null);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([]);
  const [reviewNotes, setReviewNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [artifactPreview, setArtifactPreview] = useState<KnowledgeArtifact | null>(null);
  const [candidatePreview, setCandidatePreview] = useState<KnowledgeCandidate | null>(null);
  const [detailViewer, setDetailViewer] = useState<DetailViewerState | null>(null);

  const canAdmin = user?.role === "operator" || user?.role === "admin";

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/login");
    }
  }, [hasHydrated, isAuthenticated, router]);

  useEffect(() => {
    if (hasHydrated && isAuthenticated && !user) {
      void fetchUser();
    }
  }, [fetchUser, hasHydrated, isAuthenticated, user]);

  const loadJob = useCallback(
    async (silent = false) => {
      if (!hasHydrated || !isAuthenticated || !canAdmin || !jobId) return;
      if (!silent) setLoading(true);
      setError("");
      try {
        const response = await api.get<{ job: KnowledgeImportJob }>(`/admin/knowledge/imports/${jobId}`);
        setJob(response.data.job);
      } catch (err: unknown) {
        setError(apiErrorMessage(err, "导入任务加载失败。"));
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [canAdmin, hasHydrated, isAuthenticated, jobId],
  );

  useEffect(() => {
    void loadJob();
  }, [loadJob]);

  useEffect(() => {
    if (!job?.id || !accessToken || !canAdmin || isSettledJob(job.status)) return;
    const streamJobId = job.id;
    const controller = new AbortController();
    let closed = false;

    async function streamJob() {
      setStreaming(true);
      try {
        const response = await authenticatedFetch(`/api/admin/knowledge/imports/${encodeURIComponent(streamJobId)}/stream`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok || !response.body) return;
        for await (const event of readSseEvents(response.body)) {
          if (closed) break;
          if (event.event === "snapshot") {
            const payload = event.data as { job?: KnowledgeImportJob };
            if (payload.job) setJob(payload.job);
          }
          if (event.event === "done") break;
        }
      } catch {
        if (!controller.signal.aborted) {
          void loadJob(true);
        }
      } finally {
        if (!closed) setStreaming(false);
      }
    }

    void streamJob();
    return () => {
      closed = true;
      controller.abort();
    };
  }, [accessToken, canAdmin, job?.id, job?.status, loadJob]);

  const candidates = useMemo(() => job?.candidates ?? [], [job?.candidates]);
  useEffect(() => {
    if (candidates.length === 0) return;
    setSelectedCandidateIds((current) => {
      if (current.length > 0) return current.filter((id) => candidates.some((candidate) => candidate.id === id));
      return candidates.map((candidate) => candidate.id);
    });
  }, [candidates]);

  const canReview = job?.requested_visibility === "public" && job.status === "awaiting_review";
  const sortedEvents = useMemo(() => [...(job?.run?.events ?? [])].sort((left, right) => left.event_index - right.event_index), [job?.run?.events]);
  const sortedSteps = useMemo(() => [...(job?.run?.steps ?? [])].sort((left, right) => new Date(left.started_at).getTime() - new Date(right.started_at).getTime()), [job?.run?.steps]);

  const reviewJob = async (decision: "approve" | "reject") => {
    if (!job) return;
    setActionLoading(true);
    setError("");
    setNotice("");
    try {
      const response = await api.post<{ job: KnowledgeImportJob }>(`/admin/knowledge/imports/${job.id}/review`, {
        decision,
        candidate_ids: selectedCandidateIds,
        notes: reviewNotes,
      });
      setJob(response.data.job);
      setNotice(decision === "approve" ? "导入候选已发布。" : "导入候选已拒绝。");
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "审核操作失败。"));
    } finally {
      setActionLoading(false);
    }
  };

  const cancelJob = async () => {
    if (!job) return;
    setActionLoading(true);
    setError("");
    try {
      const response = await api.post<{ job: KnowledgeImportJob }>(`/admin/knowledge/imports/${job.id}/cancel`);
      setJob(response.data.job);
      setNotice("任务已终止。");
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "任务终止失败。"));
    } finally {
      setActionLoading(false);
    }
  };

  const retryJob = async () => {
    if (!job) return;
    setActionLoading(true);
    setError("");
    try {
      const response = await api.post<{ job: KnowledgeImportJob }>(`/admin/knowledge/imports/${job.id}/retry`);
      setJob(response.data.job);
      setNotice("任务已重新排队。");
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "任务重试失败。"));
    } finally {
      setActionLoading(false);
    }
  };

  const openArtifact = async (artifact: KnowledgeArtifact) => {
    if (artifact.inline_text) {
      setArtifactPreview(artifact);
      return;
    }
    if (!job) return;
    setActionLoading(true);
    setError("");
    try {
      const response = await api.get<{ signed_url?: string }>(`/knowledge/uploads/${job.id}/artifacts/${artifact.id}/preview`);
      if (response.data.signed_url) window.open(response.data.signed_url, "_blank", "noopener,noreferrer");
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "产物预览失败。"));
    } finally {
      setActionLoading(false);
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/admin/knowledge/imports" userName={user?.display_name} userRole={user?.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">
          <SectionHeading icon={ShieldCheck} label="Access denied" labelZh="权限不足" />
          <h1 className="font-serif text-3xl text-academic-navy">Import Detail</h1>
          <p className="mt-2 text-sm leading-6">该工作台仅对 operator / admin 角色开放。</p>
        </Panel>
      </AcademicShell>
    );
  }

  return (
    <AcademicShell activePath="/admin/knowledge/imports" userName={user?.display_name} userRole={user?.role} wide>
      <PageHeader
        eyebrow="Document Ingestion Run"
        title={job?.source_file.title || "Import Detail"}
        titleZh="运行观察"
        description={job ? `${job.source_file.original_filename} · ${formatBytes(job.source_file.size_bytes)} · ${shortId(job.id)}` : undefined}
        actions={
          <>
            <Button type="button" variant="soft" onClick={() => router.push("/admin/knowledge/imports")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              队列
            </Button>
            <Button type="button" variant="teal" onClick={() => void loadJob()} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
              刷新
            </Button>
          </>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}
      {notice && <Panel className="border-emerald-600/25 bg-academic-success-soft text-sm text-emerald-800">{notice}</Panel>}

      {loading && !job ? (
        <Panel>
          <div className="flex min-h-52 items-center justify-center text-sm text-slate-600">
            <Loader2 className="mr-2 h-5 w-5 animate-spin text-academic-score" />
            加载中...
          </div>
        </Panel>
      ) : job ? (
        <>
          <Panel>
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
              <div className="min-w-0">
                <div className="flex flex-wrap gap-2">
                  <StatusBadge tone={statusTone(job.status)}>{job.status}</StatusBadge>
                  <StatusBadge tone={streaming ? "coral" : "slate"}>{streaming ? "streaming" : "snapshot"}</StatusBadge>
                  <StatusBadge tone="teal">{visibilityLabel(job.requested_visibility)}</StatusBadge>
                  <StatusBadge tone="gold">{actionLabel(job.requested_action)}</StatusBadge>
                  {job.classifier_label && <StatusBadge tone="blue">{job.classifier_label}</StatusBadge>}
                </div>
                <div className="mt-5 h-2.5 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-academic-accent" style={{ width: `${Math.max(3, job.progress_pct)}%` }} />
                </div>
                <p className="mt-2 text-sm text-slate-600">
                  {job.stage} · {job.progress_pct}% · updated {formatDateTime(job.updated_at)}
                </p>
                {job.error_message && <p className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{job.error_message}</p>}
              </div>
              <div className="grid gap-2">
                <InlineKpi label="Run" value={shortId(job.run_id)} />
                <InlineKpi label="Owner" value={shortId(job.owner_user_id)} />
                <InlineKpi label="Heartbeat" value={formatDateTime(job.heartbeat_at)} />
                <div className="flex flex-wrap gap-2 pt-2">
                  {canCancelJob(job.status) && (
                    <Button type="button" variant="dangerOutline" onClick={() => void cancelJob()} disabled={actionLoading}>
                      <StopCircle className="mr-2 h-4 w-4" />
                      终止
                    </Button>
                  )}
                  {canRetryJob(job.status) && (
                    <Button type="button" variant="soft" onClick={() => void retryJob()} disabled={actionLoading}>
                      <RotateCcw className="mr-2 h-4 w-4" />
                      重试
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </Panel>

          {canReview && (
            <Panel className="border-academic-score/30 bg-academic-score-soft">
              <SectionHeading icon={ShieldCheck} label="Review" labelZh="审核发布" />
              <div className="grid gap-3">
                <textarea
                  value={reviewNotes}
                  onChange={(event) => setReviewNotes(event.target.value)}
                  className="min-h-24 rounded-md border border-academic-score/30 bg-white px-3 py-2 text-sm outline-none focus:border-academic-score"
                />
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="teal" onClick={() => void reviewJob("approve")} disabled={actionLoading || selectedCandidateIds.length === 0}>
                    <CheckCircle2 className="mr-2 h-4 w-4" />
                    批准发布
                  </Button>
                  <Button type="button" variant="dangerOutline" onClick={() => void reviewJob("reject")} disabled={actionLoading || selectedCandidateIds.length === 0}>
                    <XCircle className="mr-2 h-4 w-4" />
                    拒绝
                  </Button>
                </div>
              </div>
            </Panel>
          )}

          <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_440px]">
            <div className="grid gap-5">
              <Panel>
                <SectionHeading icon={GitBranch} label="Process" labelZh="处理过程" />
                <ProcessTimeline
                  steps={sortedSteps}
                  events={sortedEvents}
                  onOpenDetail={(title, payload, subtitle) => setDetailViewer({ title, payload, subtitle })}
                />
              </Panel>
              <Panel className="overflow-hidden">
                <SectionHeading icon={ShieldCheck} label="Candidates" labelZh="候选结果" />
                {candidates.length === 0 ? (
                  <EmptyState icon={ShieldCheck} title="暂无候选" body="解析完成后会显示候选。" />
                ) : (
                  <div className="grid max-h-[680px] gap-3 overflow-y-auto pr-1">
                    {candidates.map((candidate) => (
                      <label key={candidate.id} className="grid cursor-pointer gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm lg:grid-cols-[auto_minmax(0,1fr)]">
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4 rounded border-slate-300 text-academic-accent"
                          checked={selectedCandidateIds.includes(candidate.id)}
                          onChange={(event) =>
                            setSelectedCandidateIds((current) =>
                              event.target.checked ? [...current, candidate.id] : current.filter((id) => id !== candidate.id),
                            )
                          }
                        />
                        <CandidateReviewCard candidate={candidate} onOpen={() => setCandidatePreview(candidate)} />
                      </label>
                    ))}
                  </div>
                )}
              </Panel>
            </div>

            <div className="grid gap-5 content-start">
              <Panel>
                <SectionHeading icon={FileJson} label="Artifacts" labelZh="中间产物" />
                {(job.artifacts ?? []).length === 0 ? (
                  <EmptyState icon={FileJson} title="暂无产物" body="解析产物会显示在这里。" />
                ) : (
                  <div className="grid max-h-[360px] gap-2 overflow-y-auto pr-1">
                    {(job.artifacts ?? []).map((artifact) => (
                      <button
                        key={artifact.id}
                        type="button"
                        onClick={() => void openArtifact(artifact)}
                        className="flex min-w-0 cursor-pointer items-start justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-3 text-left transition-colors hover:border-academic-score/60 hover:bg-[#FFFDF5]"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-semibold text-slate-900">{artifact.title}</span>
                          <span className="mt-1 block text-xs text-slate-500">{artifact.artifact_kind} · {formatBytes(artifact.size_bytes)}</span>
                        </span>
                        <Eye className="h-4 w-4 shrink-0 text-academic-accent" />
                      </button>
                    ))}
                  </div>
                )}
              </Panel>
            </div>
          </section>

          <DetailDialog
            open={Boolean(artifactPreview)}
            title={artifactPreview?.title || "Artifact Preview"}
            titleZh="产物预览"
            description={artifactPreview ? `${artifactPreview.artifact_kind} · ${formatBytes(artifactPreview.size_bytes)}` : undefined}
            onClose={() => setArtifactPreview(null)}
            className="max-w-5xl"
          >
            {artifactPreview ? <MonoBlock className="max-h-[62vh]">{artifactPreview.inline_text || ""}</MonoBlock> : null}
          </DetailDialog>

          <DetailDialog
            open={Boolean(candidatePreview)}
            title={candidatePreview?.title || "Candidate Detail"}
            titleZh="候选详情"
            description={candidatePreview ? `${candidatePreview.candidate_kind} · ${candidatePreview.candidate_status}` : undefined}
            onClose={() => setCandidatePreview(null)}
            className="max-w-5xl"
          >
            {candidatePreview ? (
              <div className="grid gap-4">
                <div className="flex flex-wrap gap-2">
                  <StatusBadge tone={candidateTone(candidatePreview.candidate_kind)}>{candidatePreview.candidate_kind}</StatusBadge>
                  <StatusBadge tone="slate">{candidatePreview.candidate_status}</StatusBadge>
                </div>
                {candidatePreview.summary && <p className="text-sm leading-6 text-slate-600">{candidatePreview.summary}</p>}
                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <p className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{candidatePreview.content}</p>
                </div>
                <MonoBlock className="max-h-[46vh]">{asText(candidatePreview.normalized_payload)}</MonoBlock>
              </div>
            ) : null}
          </DetailDialog>

          <DetailDialog
            open={Boolean(detailViewer)}
            title={detailViewer?.title || "Payload Detail"}
            titleZh="结构详情"
            description={detailViewer?.subtitle}
            onClose={() => setDetailViewer(null)}
            className="max-w-5xl"
          >
            {detailViewer ? <MonoBlock className="max-h-[62vh]">{asText(detailViewer.payload)}</MonoBlock> : null}
          </DetailDialog>
        </>
      ) : null}
    </AcademicShell>
  );
}

function CandidateReviewCard({ candidate, onOpen }: { candidate: KnowledgeCandidate; onOpen: () => void }) {
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          <StatusBadge tone={candidateTone(candidate.candidate_kind)}>{candidate.candidate_kind}</StatusBadge>
          <StatusBadge tone="slate">{candidate.candidate_status}</StatusBadge>
        </div>
        <Button type="button" variant="soft" size="sm" onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onOpen();
        }}>
          <Eye className="mr-2 h-4 w-4" />
          详情
        </Button>
      </div>
      <h3 className="mt-3 break-words text-base font-semibold text-academic-navy">{candidate.title}</h3>
      {candidate.summary && <p className="mt-2 text-sm leading-6 text-slate-600">{candidate.summary}</p>}
      <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{truncateText(candidate.content, 360)}</p>
    </div>
  );
}

function ProcessTimeline({
  steps,
  events,
  onOpenDetail,
}: {
  steps: AgentRunStep[];
  events: AgentRunEvent[];
  onOpenDetail: (title: string, payload: unknown, subtitle?: string) => void;
}) {
  if (steps.length === 0 && events.length === 0) {
    return <EmptyState icon={FileText} title="暂无运行记录" body="任务开始后会显示步骤和事件。" />;
  }
  return (
    <div className="grid max-h-[620px] gap-3 overflow-y-auto pr-1">
      {steps.map((step) => (
        <article key={step.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={statusTone(step.status)}>{step.status}</StatusBadge>
            <StatusBadge tone="teal">{step.execution_kind || "deterministic"}</StatusBadge>
            <span className="text-sm font-semibold text-slate-900">{step.workflow_node}</span>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-600">{step.output_summary || step.input_summary || "处理中"}</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <InlineKpi label="Agent" value={step.agent_name || "-"} />
            <InlineKpi label="Latency" value={`${step.latency_ms ?? 0}ms`} />
            <InlineKpi label="Started" value={formatDateTime(step.started_at)} />
          </div>
          <Button
            type="button"
            variant="soft"
            size="sm"
            className="mt-3"
            onClick={() => onOpenDetail(`输入 / 输出 · ${step.workflow_node}`, { input: step.input_payload, output: step.output_payload }, step.id)}
          >
            <Eye className="mr-2 h-4 w-4" />
            查看输入输出
          </Button>
        </article>
      ))}
      {events.map((event) => (
        <article key={event.id} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone="blue">{event.event_type}</StatusBadge>
            <span className="text-sm font-semibold text-slate-900">{event.title || event.event_type}</span>
          </div>
          {event.summary && <p className="mt-2 text-sm leading-6 text-slate-600">{event.summary}</p>}
          <p className="mt-1 text-xs text-slate-500">{formatDateTime(event.created_at)}</p>
          {event.visibility === "details" && (
            <Button
              type="button"
              variant="soft"
              size="sm"
              className="mt-2"
              onClick={() => onOpenDetail(`事件载荷 · ${event.event_type}`, event.payload, event.id)}
            >
              <Eye className="mr-2 h-4 w-4" />
              查看载荷
            </Button>
          )}
        </article>
      ))}
    </div>
  );
}

function truncateText(value: string, limit: number) {
  return value.length > limit ? `${value.slice(0, limit - 1)}...` : value;
}

async function* readSseEvents(stream: ReadableStream<Uint8Array>): AsyncGenerator<StreamEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseSseEvent(rawEvent);
        if (parsed) yield parsed;
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseEvent(raw: string): StreamEvent | null {
  let event = "message";
  const data: string[] = [];
  raw.split(/\r?\n/).forEach((line) => {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  });
  if (data.length === 0) return null;
  const text = data.join("\n");
  try {
    return { event, data: JSON.parse(text) };
  } catch {
    return { event, data: text };
  }
}
