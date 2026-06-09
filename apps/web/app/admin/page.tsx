"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  ArrowLeft,
  BarChart3,
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
  Layers3,
  Loader2,
  MessageSquareText,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  XCircle,
} from "lucide-react";
import { useRouter } from "next/navigation";

import { AcademicShell, EmptyState, MetricCard, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { agentApi, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";

type AdminStatus = "healthy" | "attention" | "blocked" | "unknown";
type ContentStatus = "draft" | "reviewing" | "active" | "archived";

type ApiError = {
  response?: {
    data?: {
      message?: string;
      detail?: string | { message?: string };
    };
    status?: number;
  };
};

type RequestResult<T> = { ok: true; data: T } | { ok: false; message: string };

type SummaryItem = {
  content_type: string;
  status: string;
  count: number;
};

type PromptVersion = {
  id: string;
  agent_name: string;
  purpose: string;
  version: string;
  content_hash: string;
  metadata: Record<string, unknown>;
  active: boolean;
  created_at: string;
};

type ReportUserFeedback = {
  id: string;
  report_id: string;
  session_id: string;
  user_id: string;
  target_type: string;
  target_id?: string | null;
  vote: "up" | "down" | string;
  comment?: string | null;
  created_at: string;
};

type VoiceClonePolicy = {
  enabled: boolean;
  version: string;
  requires_explicit_consent: boolean;
  updated_by?: string | null;
  updated_at: string;
};

type LatencyStats = {
  count: number;
  avg_ms: number;
  p95_ms: number;
};

type ObservabilitySummary = {
  run_count: number;
  completed_count: number;
  failed_count: number;
  cancelled_count: number;
  error_rate: number;
  latency: LatencyStats;
  tool_call_count: number;
  tool_success_rate: number;
  structured_output_total: number;
  structured_output_valid_count: number;
  structured_output_validity_rate: number;
  recent_runs: {
    run_id: string;
    session_id: string;
    mode?: string | null;
    status: string;
    latency_ms?: number | null;
    started_at: string;
  }[];
};

type AnchorDatasetAudit = {
  sample_count: number;
  covered_bands: number[];
  source_compliance_values: string[];
  passed: boolean;
  findings: string[];
};

type AnchorSamplesResponse = {
  audit: AnchorDatasetAudit;
  calibration_anchor_count: number;
  note: string;
};

type ServiceHealth = {
  key: string;
  label: string;
  labelZh: string;
  status: AdminStatus;
  detail: string;
  latencyMs?: number;
};

type ModuleCardConfig = {
  title: string;
  titleZh: string;
  description: string;
  href: string;
  icon: LucideIcon;
  status: AdminStatus;
  statusLabel: string;
  metricLabel: string;
  metricValue: string;
};

const statusOptions: ContentStatus[] = ["draft", "reviewing", "active", "archived"];

const statusMeta: Record<ContentStatus, { label: string; labelZh: string; bar: string; text: string }> = {
  draft: { label: "Draft", labelZh: "草稿", bar: "bg-[#5B8DEF]", text: "text-blue-700" },
  reviewing: { label: "In Review", labelZh: "评审中", bar: "bg-[#F2B84B]", text: "text-[#8A6F1D]" },
  active: { label: "Active", labelZh: "已启用", bar: "bg-[#69B58A]", text: "text-[#3E7056]" },
  archived: { label: "Archived", labelZh: "已归档", bar: "bg-slate-300", text: "text-slate-500" },
};

const contentTypeConfig = [
  { key: "question", label: "Questions", labelZh: "题目", href: "/admin/questions" },
  { key: "knowledge_doc", label: "Knowledge", labelZh: "文档", href: "/admin/knowledge" },
  { key: "reference_answer", label: "Reference Answers", labelZh: "参考答案", href: "/admin/review" },
];

const unknownHealth: ServiceHealth[] = [
  { key: "api-go", label: "api-go", labelZh: "业务 API", status: "unknown", detail: "Waiting for refresh" },
  { key: "agent-harness", label: "agent-harness", labelZh: "Agent 后端", status: "unknown", detail: "Waiting for refresh" },
  { key: "speech-assessment", label: "speech-assessment", labelZh: "语音评估", status: "unknown", detail: "Waiting for refresh" },
  { key: "postgres", label: "postgres", labelZh: "数据库", status: "unknown", detail: "Readyz is not exposed through the web gateway" },
  { key: "redis", label: "redis", labelZh: "缓存", status: "unknown", detail: "Readyz is not exposed through the web gateway" },
  { key: "minio", label: "minio", labelZh: "对象存储", status: "unknown", detail: "Readyz is not exposed through the web gateway" },
];

export default function AdminConsolePage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [summary, setSummary] = useState<SummaryItem[]>([]);
  const [promptVersions, setPromptVersions] = useState<PromptVersion[]>([]);
  const [feedback, setFeedback] = useState<ReportUserFeedback[]>([]);
  const [voicePolicy, setVoicePolicy] = useState<VoiceClonePolicy | null>(null);
  const [observability, setObservability] = useState<ObservabilitySummary | null>(null);
  const [anchorAudit, setAnchorAudit] = useState<AnchorDatasetAudit | null>(null);
  const [systemHealth, setSystemHealth] = useState<ServiceHealth[]>(unknownHealth);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const canAdmin = user?.role === "operator" || user?.role === "admin";

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/login");
    }
  }, [hasHydrated, isAuthenticated, router]);

  useEffect(() => {
    if (hasHydrated && isAuthenticated && !user) {
      fetchUser();
    }
  }, [fetchUser, hasHydrated, isAuthenticated, user]);

  const loadAdminConsole = useCallback(
    async (silent = false) => {
      if (!hasHydrated || !isAuthenticated || !canAdmin) return;
      if (silent) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError("");
      setNotice("");

      const [
        summaryResult,
        promptResult,
        feedbackResult,
        policyResult,
        observabilityResult,
        anchorResult,
        apiHealth,
        agentHealth,
        speechHealth,
      ] = await Promise.all([
        safeRequest(api.get<{ summary: SummaryItem[] }>("/admin/content-review/summary")),
        safeRequest(api.get<{ versions: PromptVersion[] }>("/admin/prompts/versions?active=true&limit=40")),
        safeRequest(api.get<{ feedback: ReportUserFeedback[] }>("/reports/feedback/export?limit=20")),
        safeRequest(api.get<{ policy: VoiceClonePolicy }>("/admin/compliance/voice-clone-policy")),
        safeRequest(agentApi.get<ObservabilitySummary>("/agent/observability/summary", { params: { limit: "20" } })),
        safeRequest(agentApi.get<AnchorSamplesResponse>("/agent/calibration/anchor-samples", { params: { include_samples: "false" } })),
        checkServiceHealth({
          key: "api-go",
          label: "api-go",
          labelZh: "业务 API",
          request: () => api.get<{ name: string; version: string }>("/version"),
          detail: (response) => `${response.data.name} ${response.data.version}`,
        }),
        checkServiceHealth({
          key: "agent-harness",
          label: "agent-harness",
          labelZh: "Agent 后端",
          request: () => agentApi.get<{ service: string; env: string }>("/healthz"),
          detail: (response) => `${response.data.service} ${response.data.env}`,
        }),
        checkServiceHealth({
          key: "speech-assessment",
          label: "speech-assessment",
          labelZh: "语音评估",
          request: async () => {
            const response = await fetch("/speech-assessment/healthz", { cache: "no-store" });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return (await response.json()) as { status?: string; service?: string; provider?: string };
          },
          detail: (response) => `${response.service ?? "speech-assessment"} ${response.status ?? "ok"}`,
        }),
      ]);

      if (summaryResult.ok) setSummary(summaryResult.data.data.summary ?? []);
      if (promptResult.ok) setPromptVersions(promptResult.data.data.versions ?? []);
      if (feedbackResult.ok) setFeedback(feedbackResult.data.data.feedback ?? []);
      if (policyResult.ok) setVoicePolicy(policyResult.data.data.policy ?? null);
      if (observabilityResult.ok) setObservability(observabilityResult.data.data);
      if (anchorResult.ok) setAnchorAudit(anchorResult.data.data.audit ?? null);

      const readinessStatus: AdminStatus = apiHealth.status === "healthy" ? "unknown" : apiHealth.status;
      setSystemHealth([
        apiHealth,
        agentHealth,
        speechHealth,
        {
          key: "postgres",
          label: "postgres",
          labelZh: "数据库",
          status: readinessStatus,
          detail: readinessStatus === "unknown" ? "Use api-go /readyz for direct readiness" : "API surface is unavailable",
        },
        {
          key: "redis",
          label: "redis",
          labelZh: "缓存",
          status: readinessStatus,
          detail: readinessStatus === "unknown" ? "Use api-go /readyz for direct readiness" : "API surface is unavailable",
        },
        {
          key: "minio",
          label: "minio",
          labelZh: "对象存储",
          status: readinessStatus,
          detail: readinessStatus === "unknown" ? "Use api-go /readyz for direct readiness" : "API surface is unavailable",
        },
      ]);

      const coreFailures = [
        summaryResult.ok ? "" : `Content summary: ${summaryResult.message}`,
        promptResult.ok ? "" : `Prompt versions: ${promptResult.message}`,
        feedbackResult.ok ? "" : `Feedback export: ${feedbackResult.message}`,
        policyResult.ok ? "" : `Voice clone policy: ${policyResult.message}`,
      ].filter(Boolean);
      const optionalFailures = [
        observabilityResult.ok ? "" : "Agent observability",
        anchorResult.ok ? "" : "Calibration anchors",
        agentHealth.status === "healthy" ? "" : "Agent health",
        speechHealth.status === "healthy" ? "" : "Speech health",
      ].filter(Boolean);

      setError(coreFailures.join(" | "));
      setNotice(optionalFailures.length > 0 ? "部分 AI 运行或健康信号暂不可用，已按降级状态展示。" : "");
      setLastUpdated(new Date());
      setLoading(false);
      setRefreshing(false);
    },
    [canAdmin, hasHydrated, isAuthenticated],
  );

  useEffect(() => {
    loadAdminConsole();
  }, [loadAdminConsole]);

  const contentRows = useMemo(() => {
    return contentTypeConfig.map((config) => {
      const counts = statusOptions.reduce(
        (acc, status) => {
          acc[status] = summary
            .filter((item) => item.content_type === config.key && item.status === status)
            .reduce((total, item) => total + item.count, 0);
          return acc;
        },
        { draft: 0, reviewing: 0, active: 0, archived: 0 } as Record<ContentStatus, number>,
      );
      const total = statusOptions.reduce((sum, status) => sum + counts[status], 0);
      return { ...config, counts, total, pending: counts.draft + counts.reviewing };
    });
  }, [summary]);

  const rowByType = useMemo(() => {
    return new Map(contentRows.map((row) => [row.key, row]));
  }, [contentRows]);

  const totalPendingContent = contentRows.reduce((sum, row) => sum + row.pending, 0);
  const totalContentItems = contentRows.reduce((sum, row) => sum + row.total, 0);

  const feedbackStats = useMemo(() => {
    const positive = feedback.filter((item) => item.vote === "up").length;
    const negative = feedback.filter((item) => item.vote === "down").length;
    const needsReview = feedback.filter((item) => item.vote === "down" || Boolean(item.comment?.trim())).length;
    return { positive, negative, needsReview };
  }, [feedback]);

  const moduleCards = useMemo<ModuleCardConfig[]>(() => {
    const questionRow = rowByType.get("question");
    const knowledgeRow = rowByType.get("knowledge_doc");
    const referenceRow = rowByType.get("reference_answer");
    const observabilityStatus = observability
      ? observability.error_rate > 0.05 || observability.structured_output_validity_rate < 0.95
        ? "attention"
        : "healthy"
      : "unknown";
    const calibrationStatus = anchorAudit ? (anchorAudit.passed ? "healthy" : "attention") : "unknown";

    return [
      {
        title: "Question Bank",
        titleZh: "题库管理",
        description: "Manage seasons, topics and question publishing.",
        href: "/admin/questions",
        icon: BookOpenCheck,
        status: (questionRow?.pending ?? 0) > 0 ? "attention" : "healthy",
        statusLabel: (questionRow?.pending ?? 0) > 0 ? "Pending review" : "Healthy",
        metricLabel: "Pending Changes",
        metricValue: String(questionRow?.pending ?? 0),
      },
      {
        title: "Knowledge Base",
        titleZh: "知识库",
        description: "Manage topic material, rubric chunks and indexing.",
        href: "/admin/knowledge",
        icon: Database,
        status: (knowledgeRow?.pending ?? 0) > 0 ? "attention" : "healthy",
        statusLabel: (knowledgeRow?.pending ?? 0) > 0 ? "Pending review" : "Healthy",
        metricLabel: "Pending Docs",
        metricValue: String(knowledgeRow?.pending ?? 0),
      },
      {
        title: "Prompt Versions",
        titleZh: "提示词版本",
        description: "Inspect active prompt metadata and redacted hashes.",
        href: "/admin/prompts",
        icon: Sparkles,
        status: promptVersions.length > 0 ? "healthy" : "unknown",
        statusLabel: promptVersions.length > 0 ? "Healthy" : "No active data",
        metricLabel: "Active Versions",
        metricValue: String(promptVersions.length),
      },
      {
        title: "Review Board",
        titleZh: "评审队列",
        description: "Review reference answers, user feedback and policy.",
        href: "/admin/review",
        icon: ShieldCheck,
        status: (referenceRow?.pending ?? 0) + feedbackStats.needsReview > 0 ? "attention" : "healthy",
        statusLabel: (referenceRow?.pending ?? 0) + feedbackStats.needsReview > 0 ? "Attention" : "Healthy",
        metricLabel: "Pending Items",
        metricValue: String((referenceRow?.pending ?? 0) + feedbackStats.needsReview),
      },
      {
        title: "Agent Observability",
        titleZh: "智能体观测",
        description: "Monitor runs, latency, tool calls and trace health.",
        href: "/admin/observability",
        icon: Activity,
        status: observabilityStatus,
        statusLabel: statusLabel(observabilityStatus),
        metricLabel: "Recent Runs",
        metricValue: String(observability?.run_count ?? 0),
      },
      {
        title: "Scoring Calibration",
        titleZh: "评分校准",
        description: "Audit anchor samples and run speech quality gates.",
        href: "/admin/calibration",
        icon: BarChart3,
        status: calibrationStatus,
        statusLabel: statusLabel(calibrationStatus),
        metricLabel: "Anchor Samples",
        metricValue: String(anchorAudit?.sample_count ?? 0),
      },
    ];
  }, [anchorAudit, feedbackStats.needsReview, observability, promptVersions.length, rowByType]);

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/admin" userName={user?.display_name} userRole={user?.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">
          <SectionHeading icon={ShieldCheck} label="Access denied" labelZh="权限不足" />
          <h1 className="font-serif text-3xl text-[#0B132B]">Admin Console</h1>
          <p className="mt-2 text-sm leading-6">This workspace is available to operator and admin accounts.</p>
          <Button type="button" variant="soft" className="mt-5" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Practice / 练习
          </Button>
        </Panel>
      </AcademicShell>
    );
  }

  return (
    <AcademicShell activePath="/admin" userName={user?.display_name} userRole={user?.role}>
      <PageHeader
        eyebrow="Operations"
        title="Admin Console"
        titleZh="运营后台"
        description="Content, AI operations, compliance and quality gates for IELTS Speaking Agent Studio."
        actions={
          <>
            <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Practice / 练习
            </Button>
            <Button type="button" variant="gold" onClick={() => loadAdminConsole(true)} disabled={refreshing}>
              <RefreshCcw className={cn("mr-2 h-4 w-4", refreshing && "animate-spin")} />
              Refresh
            </Button>
          </>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm leading-6 text-red-700">{error}</Panel>}
      {notice && !error && <Panel className="border-[#E9DFC6] bg-[#F7F4EA] text-sm leading-6 text-[#8A6F1D]">{notice}</Panel>}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Layers3} label="Content Queue" value={formatNumber(totalPendingContent)} helper={`${formatNumber(totalContentItems)} total content items`} tone="gold" />
        <MetricCard icon={Sparkles} label="Active Prompts" value={formatNumber(promptVersions.length)} helper="Prompt bodies remain redacted" tone="teal" />
        <MetricCard icon={BrainCircuit} label="Agent Error Rate" value={formatPercent(observability?.error_rate ?? 0)} helper={`${observability?.run_count ?? 0} recent runs`} tone="sage" />
        <MetricCard icon={BarChart3} label="Anchor Coverage" value={formatNumber(anchorAudit?.sample_count ?? 0)} helper={anchorAudit?.passed ? "Coverage audit passed" : "Coverage audit pending"} tone="light" />
      </div>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        {moduleCards.map((item) => (
          <ModuleCard key={item.href} item={item} onOpen={() => router.push(item.href)} />
        ))}
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.95fr_0.85fr]">
        <Panel>
          <SectionHeading
            icon={Layers3}
            label="Content Queue"
            labelZh="内容队列"
            action={<span className="text-xs text-slate-500">{lastUpdated ? `Updated ${formatTime(lastUpdated)}` : "Not refreshed"}</span>}
          />
          <div className="mb-4 flex flex-wrap gap-3">
            {statusOptions.map((status) => (
              <span key={status} className="inline-flex items-center gap-2 text-xs text-slate-500">
                <span className={cn("h-2.5 w-2.5 rounded-full", statusMeta[status].bar)} />
                {statusMeta[status].label}
                <span className="text-slate-400">{statusMeta[status].labelZh}</span>
              </span>
            ))}
          </div>
          {loading ? (
            <LoadingBlock label="Loading content queue..." />
          ) : contentRows.every((row) => row.total === 0) ? (
            <EmptyState icon={FileText} title="No content summary" body="Content review summary is empty. 当前暂无内容队列统计。" />
          ) : (
            <div className="space-y-4">
              {contentRows.map((row) => (
                <button
                  key={row.key}
                  type="button"
                  onClick={() => router.push(row.href)}
                  className="w-full cursor-pointer rounded-lg border border-slate-200 bg-slate-50 p-3 text-left transition-colors hover:border-[#D4AF37]/50 hover:bg-[#F7F4EA]"
                >
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <span className="text-sm font-semibold text-slate-900">
                      {row.label}
                      <span className="ml-2 text-xs font-medium text-slate-400">{row.labelZh}</span>
                    </span>
                    <span className="text-sm font-semibold text-slate-700">{formatNumber(row.total)}</span>
                  </div>
                  <div className="flex h-3 overflow-hidden rounded-full bg-white">
                    {statusOptions.map((status) => {
                      const value = row.counts[status];
                      const width = row.total > 0 ? (value / row.total) * 100 : 0;
                      return <span key={status} className={statusMeta[status].bar} style={{ width: `${width}%` }} />;
                    })}
                  </div>
                  <div className="mt-2 grid grid-cols-4 gap-2 text-[11px]">
                    {statusOptions.map((status) => (
                      <span key={status} className={cn("truncate", statusMeta[status].text)}>
                        {row.counts[status]} {statusMeta[status].label}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          )}
        </Panel>

        <Panel>
          <SectionHeading icon={Activity} label="System Health" labelZh="系统健康" />
          <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-semibold text-slate-900">Operational surface</span>
              <StatusBadge tone={overallHealthTone(systemHealth)}>{overallHealthLabel(systemHealth)}</StatusBadge>
            </div>
            <p className="mt-1 text-xs leading-5 text-slate-500">Direct dependency readiness requires api-go /readyz outside the current web rewrite.</p>
          </div>
          <div className="space-y-3">
            {systemHealth.map((item) => (
              <HealthRow key={item.key} item={item} />
            ))}
          </div>
        </Panel>

        <Panel>
          <SectionHeading icon={MessageSquareText} label="Recent Feedback" labelZh="近期反馈" />
          <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-1">
            <FeedbackStat icon={ThumbsUp} label="Positive" labelZh="积极" value={feedbackStats.positive} tone="sage" />
            <FeedbackStat icon={ThumbsDown} label="Negative" labelZh="消极" value={feedbackStats.negative} tone="red" />
            <FeedbackStat icon={Clock3} label="Needs Review" labelZh="人工复核" value={feedbackStats.needsReview} tone="coral" />
          </div>
          <div className="mt-4 space-y-3">
            {feedback.slice(0, 4).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => router.push("/admin/review")}
                className="w-full cursor-pointer rounded-lg border border-slate-200 bg-slate-50 p-3 text-left transition-colors hover:border-[#D4AF37]/50 hover:bg-[#F7F4EA]"
              >
                <div className="flex items-center justify-between gap-2">
                  <StatusBadge tone={item.vote === "up" ? "sage" : "coral"}>{item.vote === "up" ? "Positive" : "Needs review"}</StatusBadge>
                  <span className="text-xs text-slate-400">{formatDate(item.created_at)}</span>
                </div>
                <p className="mt-2 line-clamp-2 text-sm leading-5 text-slate-700">{item.comment || `${item.target_type} feedback without comment`}</p>
                <p className="mt-2 truncate font-mono text-[11px] text-slate-400">{shortId(item.report_id)} / {shortId(item.session_id)}</p>
              </button>
            ))}
            {feedback.length === 0 && !loading && (
              <EmptyState icon={MessageSquareText} title="No recent feedback" body="No exported report feedback is available yet. 暂无近期报告反馈。" />
            )}
          </div>
        </Panel>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <ComplianceCard
          icon={ShieldCheck}
          title="Recording Consent"
          titleZh="录音同意"
          status="healthy"
          statusText="Required"
          body="Recording consent is collected before practice audio is processed."
          action="Open profile"
          onOpen={() => router.push("/background")}
        />
        <ComplianceCard
          icon={Database}
          title="Data Deletion"
          titleZh="数据删除"
          status="healthy"
          statusText="Enabled"
          body="Privacy controls can request deletion of reports, recordings and profile data."
          action="Open profile"
          onOpen={() => router.push("/background")}
        />
        <ComplianceCard
          icon={voicePolicy?.enabled ? XCircle : CheckCircle2}
          title="Voice Clone"
          titleZh="语音克隆"
          status={voicePolicy?.enabled ? "blocked" : "healthy"}
          statusText={voicePolicy?.enabled ? "Enabled" : "Disabled"}
          body={voicePolicy?.requires_explicit_consent ? "Explicit consent is required by policy." : "Policy loaded from compliance settings."}
          action="Open policy"
          onOpen={() => router.push("/admin/review")}
        />
        <ComplianceCard
          icon={Sparkles}
          title="Prompt Redaction"
          titleZh="提示词脱敏"
          status={promptVersions.length > 0 ? "healthy" : "unknown"}
          statusText={promptVersions.length > 0 ? "Active" : "Pending"}
          body="Prompt admin exposes metadata and content hashes without full prompt bodies."
          action="Open prompts"
          onOpen={() => router.push("/admin/prompts")}
        />
      </section>
    </AcademicShell>
  );
}

function ModuleCard({ item, onOpen }: { item: ModuleCardConfig; onOpen: () => void }) {
  const Icon = item.icon;
  return (
    <article className="flex min-h-[260px] flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-[#EEF4FF] text-[#4F6FEF]">
          <Icon className="h-5 w-5" />
        </span>
        <StatusBadge tone={statusTone(item.status)}>{item.statusLabel}</StatusBadge>
      </div>
      <h2 className="mt-4 text-sm font-semibold text-[#0B132B]">{item.title}</h2>
      <p className="text-xs font-medium text-[#4F6FEF]">{item.titleZh}</p>
      <p className="mt-3 min-h-[54px] text-xs leading-5 text-slate-500">{item.description}</p>
      <div className="mt-auto">
        <p className="text-[11px] uppercase tracking-wide text-slate-400">{item.metricLabel}</p>
        <p className="mt-1 text-xl font-semibold text-slate-950">{item.metricValue}</p>
        <Button type="button" variant="soft" size="sm" className="mt-4 w-full" onClick={onOpen}>
          Open / 打开
        </Button>
      </div>
    </article>
  );
}

function HealthRow({ item }: { item: ServiceHealth }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
      <div className="flex min-w-0 items-center gap-3">
        <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", healthDotClass(item.status))} />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-900">{item.label}</p>
          <p className="truncate text-xs text-slate-500">{item.labelZh}</p>
        </div>
      </div>
      <div className="min-w-0 text-right">
        <p className="truncate text-xs font-semibold text-slate-700">{statusLabel(item.status)}</p>
        <p className="max-w-[180px] truncate text-[11px] text-slate-400">
          {item.latencyMs !== undefined ? `${item.latencyMs} ms` : item.detail}
        </p>
      </div>
    </div>
  );
}

function FeedbackStat({ icon: Icon, label, labelZh, value, tone }: { icon: LucideIcon; label: string; labelZh: string; value: number; tone: "sage" | "coral" | "red" }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2 text-xs font-semibold text-slate-500">
          <Icon className={cn("h-4 w-4 shrink-0", tone === "sage" && "text-[#4F8A6B]", tone === "coral" && "text-[#E76F51]", tone === "red" && "text-red-500")} />
          <span className="truncate">{label}</span>
        </span>
        <StatusBadge tone={tone}>{labelZh}</StatusBadge>
      </div>
      <p className="mt-2 text-2xl font-semibold text-slate-950">{formatNumber(value)}</p>
    </div>
  );
}

function ComplianceCard({
  icon: Icon,
  title,
  titleZh,
  status,
  statusText,
  body,
  action,
  onOpen,
}: {
  icon: LucideIcon;
  title: string;
  titleZh: string;
  status: AdminStatus;
  statusText: string;
  body: string;
  action: string;
  onOpen: () => void;
}) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <span className={cn("flex h-10 w-10 items-center justify-center rounded-lg", statusIconSurface(status))}>
          <Icon className="h-5 w-5" />
        </span>
        <StatusBadge tone={statusTone(status)}>{statusText}</StatusBadge>
      </div>
      <h2 className="mt-4 text-sm font-semibold text-[#0B132B]">{title}</h2>
      <p className="text-xs font-medium text-slate-400">{titleZh}</p>
      <p className="mt-3 min-h-[58px] text-xs leading-5 text-slate-500">{body}</p>
      <Button type="button" variant="soft" size="sm" className="mt-4 w-full" onClick={onOpen}>
        {action}
      </Button>
    </article>
  );
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center text-sm text-slate-600">
      <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#D4AF37]" />
      {label}
    </div>
  );
}

async function safeRequest<T>(request: Promise<T>): Promise<RequestResult<T>> {
  try {
    return { ok: true, data: await request };
  } catch (err: unknown) {
    return { ok: false, message: errorMessage(err) };
  }
}

async function checkServiceHealth<T>({
  key,
  label,
  labelZh,
  request,
  detail,
}: {
  key: string;
  label: string;
  labelZh: string;
  request: () => Promise<T>;
  detail: (response: T) => string;
}): Promise<ServiceHealth> {
  const started = performance.now();
  const result = await safeRequest(request());
  const latencyMs = Math.max(1, Math.round(performance.now() - started));
  if (!result.ok) {
    return { key, label, labelZh, status: "blocked", detail: result.message, latencyMs };
  }
  return { key, label, labelZh, status: "healthy", detail: detail(result.data), latencyMs };
}

function errorMessage(err: unknown) {
  const apiError = err as ApiError;
  const detail = apiError.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;
  if (apiError.response?.data?.message) return apiError.response.data.message;
  if (apiError.response?.status) return `HTTP ${apiError.response.status}`;
  if (err instanceof Error) return err.message;
  return "Service unavailable";
}

function statusTone(status: AdminStatus): "sage" | "coral" | "red" | "slate" {
  if (status === "healthy") return "sage";
  if (status === "attention") return "coral";
  if (status === "blocked") return "red";
  return "slate";
}

function healthDotClass(status: AdminStatus) {
  if (status === "healthy") return "bg-[#4F8A6B]";
  if (status === "attention") return "bg-[#E76F51]";
  if (status === "blocked") return "bg-red-500";
  return "bg-slate-300";
}

function statusIconSurface(status: AdminStatus) {
  if (status === "healthy") return "bg-[#EEF7F2] text-[#4F8A6B]";
  if (status === "attention") return "bg-[#FFF3EC] text-[#E76F51]";
  if (status === "blocked") return "bg-red-50 text-red-600";
  return "bg-slate-100 text-slate-500";
}

function statusLabel(status: AdminStatus) {
  if (status === "healthy") return "Healthy";
  if (status === "attention") return "Attention";
  if (status === "blocked") return "Blocked";
  return "Not checked";
}

function overallHealthTone(items: ServiceHealth[]): "sage" | "coral" | "red" | "slate" {
  if (items.some((item) => item.status === "blocked")) return "red";
  if (items.some((item) => item.status === "attention")) return "coral";
  if (items.some((item) => item.status === "unknown")) return "slate";
  return "sage";
}

function overallHealthLabel(items: ServiceHealth[]) {
  if (items.some((item) => item.status === "blocked")) return "Degraded";
  if (items.some((item) => item.status === "attention")) return "Attention";
  if (items.some((item) => item.status === "unknown")) return "Partial";
  return "Healthy";
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function formatTime(value: Date) {
  return value.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function shortId(value: string) {
  if (!value) return "n/a";
  return value.length <= 12 ? value : `${value.slice(0, 8)}...`;
}
