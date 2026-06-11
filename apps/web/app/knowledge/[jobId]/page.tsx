"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  Eye,
  FileJson,
  FileText,
  Loader2,
  RefreshCcw,
  RotateCcw,
  StopCircle,
  UserCheck,
} from "lucide-react";

import { AcademicShell, DetailDialog, EmptyState, InlineKpi, MonoBlock, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
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
  type KnowledgeArtifact,
  type KnowledgeCandidate,
  type KnowledgeImportJob,
} from "@/lib/knowledgeIngestion";
import { useAuthStore } from "@/store/authStore";

export default function KnowledgeImportDetailPage() {
  const router = useRouter();
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [job, setJob] = useState<KnowledgeImportJob | null>(null);
  const [selectedBackgroundIds, setSelectedBackgroundIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [artifactPreview, setArtifactPreview] = useState<KnowledgeArtifact | null>(null);
  const [candidatePreview, setCandidatePreview] = useState<KnowledgeCandidate | null>(null);

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
      if (!hasHydrated || !isAuthenticated || !jobId) return;
      if (!silent) setLoading(true);
      setError("");
      try {
        const response = await api.get<{ job: KnowledgeImportJob }>(`/knowledge/uploads/${jobId}`);
        setJob(response.data.job);
      } catch (err: unknown) {
        setError(apiErrorMessage(err, "导入详情加载失败。"));
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [hasHydrated, isAuthenticated, jobId],
  );

  useEffect(() => {
    void loadJob();
  }, [loadJob]);

  useEffect(() => {
    if (!job || isSettledJob(job.status)) return;
    const timer = window.setInterval(() => void loadJob(true), 2500);
    return () => window.clearInterval(timer);
  }, [job, loadJob]);

  const backgroundCandidates = useMemo(
    () => (job?.candidates ?? []).filter((candidate) => candidate.candidate_kind === "background" && candidate.candidate_status === "pending"),
    [job?.candidates],
  );

  useEffect(() => {
    if (backgroundCandidates.length === 0) return;
    setSelectedBackgroundIds((current) => {
      if (current.length > 0) return current.filter((id) => backgroundCandidates.some((candidate) => candidate.id === id));
      return backgroundCandidates.map((candidate) => candidate.id);
    });
  }, [backgroundCandidates]);

  const confirmBackground = async () => {
    if (!job) return;
    setActionLoading(true);
    setError("");
    setNotice("");
    try {
      const response = await api.post<{ job: KnowledgeImportJob }>(`/knowledge/uploads/${job.id}/confirm-background`, {
        candidate_ids: selectedBackgroundIds,
      });
      setJob(response.data.job);
      setNotice("背景候选已确认。");
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "背景候选确认失败。"));
    } finally {
      setActionLoading(false);
    }
  };

  const cancelJob = async () => {
    if (!job) return;
    setActionLoading(true);
    setError("");
    try {
      const response = await api.post<{ job: KnowledgeImportJob }>(`/knowledge/uploads/${job.id}/cancel`);
      setJob(response.data.job);
      setNotice("任务已取消。");
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "任务取消失败。"));
    } finally {
      setActionLoading(false);
    }
  };

  const retryJob = async () => {
    if (!job) return;
    setActionLoading(true);
    setError("");
    try {
      const response = await api.post<{ job: KnowledgeImportJob }>(`/knowledge/uploads/${job.id}/retry`);
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
      if (response.data.signed_url) {
        window.open(response.data.signed_url, "_blank", "noopener,noreferrer");
      }
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "产物预览失败。"));
    } finally {
      setActionLoading(false);
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  return (
    <AcademicShell activePath="/knowledge" userName={user?.display_name} userRole={user?.role} wide>
      <PageHeader
        eyebrow="Knowledge Import"
        title={job?.source_file.title || "Import Detail"}
        titleZh="导入详情"
        description={job ? `${job.source_file.original_filename} · ${formatBytes(job.source_file.size_bytes)} · ${shortId(job.id)}` : undefined}
        actions={
          <>
            <Button type="button" variant="soft" onClick={() => router.push("/knowledge")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              返回
            </Button>
            <Button type="button" variant="soft" onClick={() => void loadJob()} disabled={loading}>
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
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="min-w-0">
                <div className="flex flex-wrap gap-2">
                  <StatusBadge tone={statusTone(job.status)}>{job.status}</StatusBadge>
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
                <InlineKpi label="Queued" value={formatDateTime(job.queued_at)} />
                <InlineKpi label="Heartbeat" value={formatDateTime(job.heartbeat_at)} />
                <div className="flex flex-wrap gap-2 pt-2">
                  {canCancelJob(job.status) && (
                    <Button type="button" variant="dangerOutline" onClick={() => void cancelJob()} disabled={actionLoading}>
                      <StopCircle className="mr-2 h-4 w-4" />
                      取消
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

          {backgroundCandidates.length > 0 && (
            <Panel className="border-academic-accent/25 bg-academic-accent-soft">
              <SectionHeading icon={UserCheck} label="Background Confirmation" labelZh="背景确认" />
              <div className="grid max-h-[420px] gap-3 overflow-y-auto pr-1">
                {backgroundCandidates.map((candidate) => (
                  <label key={candidate.id} className="flex cursor-pointer items-start gap-3 rounded-lg border border-academic-accent/18 bg-white p-3">
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4 rounded border-slate-300 text-academic-accent"
                      checked={selectedBackgroundIds.includes(candidate.id)}
                      onChange={(event) => {
                        setSelectedBackgroundIds((current) =>
                          event.target.checked ? [...current, candidate.id] : current.filter((id) => id !== candidate.id),
                        );
                      }}
                    />
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-slate-900">{candidate.title}</span>
                      <span className="mt-1 block whitespace-pre-wrap break-words text-sm leading-6 text-slate-600">{candidate.content}</span>
                    </span>
                  </label>
                ))}
                <div>
                  <Button type="button" variant="teal" onClick={() => void confirmBackground()} disabled={actionLoading || selectedBackgroundIds.length === 0}>
                    <CheckCircle2 className="mr-2 h-4 w-4" />
                    确认选中背景
                  </Button>
                </div>
              </div>
            </Panel>
          )}

          <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
            <Panel className="overflow-hidden">
              <SectionHeading icon={ClipboardCheck} label="Candidates" labelZh="候选结果" />
              {(job.candidates ?? []).length === 0 ? (
                <EmptyState icon={ClipboardCheck} title="暂无候选" body="解析完成后会显示候选结果。" />
              ) : (
                <div className="grid max-h-[680px] gap-3 overflow-y-auto pr-1">
                  {(job.candidates ?? []).map((candidate) => (
                    <CandidateCard key={candidate.id} candidate={candidate} onOpen={() => setCandidatePreview(candidate)} />
                  ))}
                </div>
              )}
            </Panel>

            <div className="grid gap-5">
              <Panel>
                <SectionHeading icon={FileJson} label="Artifacts" labelZh="中间产物" />
                {(job.artifacts ?? []).length === 0 ? (
                  <EmptyState icon={FileJson} title="暂无产物" body="解析过程产物会显示在这里。" />
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
              <Panel>
                <SectionHeading icon={FileText} label="Run Events" labelZh="运行事件" />
                <RunEvents job={job} />
              </Panel>
            </div>
          </section>

          {artifactPreview && (
            <DetailDialog
              open={Boolean(artifactPreview)}
              title={artifactPreview.title}
              titleZh="产物预览"
              description={`${artifactPreview.artifact_kind} · ${formatBytes(artifactPreview.size_bytes)}`}
              onClose={() => setArtifactPreview(null)}
              className="max-w-5xl"
            >
              <MonoBlock className="max-h-[62vh]">{artifactPreview.inline_text || ""}</MonoBlock>
            </DetailDialog>
          )}

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
        </>
      ) : null}
    </AcademicShell>
  );
}

function CandidateCard({ candidate, onOpen }: { candidate: KnowledgeCandidate; onOpen: () => void }) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap gap-2">
            <StatusBadge tone={candidateTone(candidate.candidate_kind)}>{candidate.candidate_kind}</StatusBadge>
            <StatusBadge tone="slate">{candidate.candidate_status}</StatusBadge>
          </div>
          <h3 className="mt-3 break-words text-base font-semibold text-academic-navy">{candidate.title}</h3>
          {candidate.summary && <p className="mt-2 text-sm leading-6 text-slate-600">{candidate.summary}</p>}
        </div>
        <Button type="button" variant="soft" size="sm" onClick={onOpen}>
          <Eye className="mr-2 h-4 w-4" />
          详情
        </Button>
      </div>
      <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{truncateText(candidate.content, 360)}</p>
    </article>
  );
}

function RunEvents({ job }: { job: KnowledgeImportJob }) {
  const events = job.run?.events ?? [];
  const steps = job.run?.steps ?? [];
  if (events.length === 0 && steps.length === 0) {
    return <EmptyState icon={FileText} title="暂无事件" body="运行开始后会记录事件。" />;
  }
  return (
    <div className="grid max-h-[560px] gap-3 overflow-y-auto pr-1">
      {steps.map((step) => (
        <article key={step.id} className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={statusTone(step.status)}>{step.status}</StatusBadge>
            <span className="text-sm font-semibold text-slate-900">{step.workflow_node}</span>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-600">{step.output_summary || step.input_summary || "处理中"}</p>
          <p className="mt-1 text-xs text-slate-500">{formatDateTime(step.started_at)} · {step.latency_ms ?? 0}ms</p>
        </article>
      ))}
      {events.slice(-12).map((event) => (
        <article key={event.id} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone="blue">{event.event_type}</StatusBadge>
            <span className="text-sm font-semibold text-slate-900">{event.title || event.event_type}</span>
          </div>
          {event.summary && <p className="mt-2 text-sm leading-6 text-slate-600">{event.summary}</p>}
          <p className="mt-1 text-xs text-slate-500">{formatDateTime(event.created_at)}</p>
        </article>
      ))}
    </div>
  );
}

function truncateText(value: string, limit: number) {
  return value.length > limit ? `${value.slice(0, limit - 1)}...` : value;
}
