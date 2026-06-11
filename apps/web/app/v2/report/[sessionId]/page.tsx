"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, BrainCircuit, Download, Eye, FileText, History, Lock, RefreshCw, ShieldCheck, type LucideIcon } from "lucide-react";

import { AcademicShell, DetailDialog, EmptyState, InlineKpi, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { AgentTracePanel } from "@/components/review/AgentTracePanel";
import { ConversationReplay } from "@/components/review/ConversationReplay";
import { CriterionEvidenceCards } from "@/components/review/CriterionEvidenceCards";
import { ReferenceAnswerDock } from "@/components/review/ReferenceAnswerDock";
import { ReviewTimeline } from "@/components/review/ReviewTimeline";
import {
  type AgentRunTrace,
  type ReportEvidence,
  type ReviewConversationItem,
  type ReviewSessionPart,
  type ReviewTurn,
  type ScoreReport,
} from "@/components/review/types";
import { Button } from "@/components/ui/button";
import { agentApi, api, orchestratorApi } from "@/lib/api";
import { selectReviewTranscript } from "@/lib/transcriptUtils";
import { useAuthStore } from "@/store/authStore";

type SessionResponse = {
  session: {
    id: string;
    user_id?: string;
    mode: string;
    status: string;
    parts?: ReviewSessionPart[];
    turns?: ReviewTurn[];
    created_at?: string;
    completed_at?: string | null;
  };
};

type ReportResponse = {
  report: ScoreReport;
};

type ApiError = {
  response?: {
    data?: {
      message?: string;
    };
  };
};

export default function ReportPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const canAdmin = user?.role === "operator" || user?.role === "admin";

  const [session, setSession] = useState<SessionResponse["session"] | null>(null);
  const [report, setReport] = useState<ScoreReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [traceLoading, setTraceLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(null);
  const [tracesByRunId, setTracesByRunId] = useState<Record<string, AgentRunTrace>>({});
  const [traceDialogOpen, setTraceDialogOpen] = useState(false);

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

  useEffect(() => {
    if (!hasHydrated || !isAuthenticated || !user) return;
    let cancelled = false;

    async function loadReview() {
      setLoading(true);
      setError("");
      setNotice("");
      try {
        const sessionPath = canAdmin ? `/admin/sessions/${sessionId}` : `/sessions/${sessionId}`;
        const reportPath = canAdmin ? `/admin/sessions/${sessionId}/report` : `/sessions/${sessionId}/report`;
        const sessionResponse = await api.get<SessionResponse>(sessionPath);
        if (!cancelled) {
          setSession(sessionResponse.data.session);
        }

        try {
          const reportResponse = await api.get<ReportResponse>(reportPath);
          if (!cancelled) {
            setReport(reportResponse.data.report);
          }
        } catch {
          if (!cancelled) {
            setReport(null);
            setNotice("评分报告尚未生成，仍可查看已保存的问答、转写和音频。");
          }
        }
      } catch (err: unknown) {
        const apiError = err as ApiError;
        if (!cancelled) {
          setError(apiError.response?.data?.message || "会话复盘加载失败。");
          setSession(null);
          setReport(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadReview();
    return () => {
      cancelled = true;
    };
  }, [canAdmin, hasHydrated, isAuthenticated, sessionId, user]);

  const conversationItems = useMemo(() => buildConversationItems(session, report), [session, report]);
  const selectedItem = conversationItems.find((item) => item.id === selectedTurnId) ?? conversationItems[0];
  const runIds = useMemo(() => collectRunIds(conversationItems, report), [conversationItems, report]);

  useEffect(() => {
    if (!selectedTurnId && conversationItems[0]) {
      setSelectedTurnId(conversationItems[0].id);
    }
  }, [conversationItems, selectedTurnId]);

  useEffect(() => {
    if (!canAdmin || runIds.length === 0) {
      setTracesByRunId({});
      return;
    }
    let cancelled = false;

    async function loadTraces() {
      setTraceLoading(true);
      const next: Record<string, AgentRunTrace> = {};
      await Promise.allSettled(
        runIds.map(async (runId) => {
          const response = await orchestratorApi.get<AgentRunTrace>(`/agent/runs/${encodeURIComponent(runId)}/trace`);
          next[runId] = response.data;
        }),
      );
      if (!cancelled) {
        setTracesByRunId(next);
        setTraceLoading(false);
      }
    }

    loadTraces();
    return () => {
      cancelled = true;
    };
  }, [canAdmin, runIds]);

  const selectedTrace = selectedItem?.agentRunId ? tracesByRunId[selectedItem.agentRunId] : undefined;
  const traceCoverage = runIds.length ? Object.keys(tracesByRunId).length / runIds.length : 0;

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  return (
    <AcademicShell activePath="/history" userName={user?.display_name || user?.email} userRole={user?.role} wide>
      <PageHeader
        eyebrow="Session Review"
        title="Session Review"
        titleZh="增强复盘"
        description="对照每一轮考试问答、原音频、语音指标、评分证据和背后的 Agent/工具调用轨迹。"
        actions={
          <>
            <Button type="button" variant="soft" onClick={() => router.push("/history")}>
              <History className="mr-2 h-4 w-4" />
              History
            </Button>
            <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Practice
            </Button>
            <Button type="button" variant="soft" onClick={() => window.print()}>
              <Download className="mr-2 h-4 w-4" />
              Export
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap gap-2">
        <KpiChip icon={FileText} label={session?.mode || "full_exam"} />
        <KpiChip label="Overall Band" value={formatBand(report?.overall_band)} tone="gold" />
        <KpiChip label="Confidence" value={formatPercent(report?.confidence)} tone="teal" />
        <KpiChip label="Turns" value={String(conversationItems.length)} />
        <KpiChip label="Trace complete" value={canAdmin ? `${Math.round(traceCoverage * 100)}%` : "Redacted"} tone="sage" />
        <KpiChip label="Report version" value={report?.version ? String(report.version) : "-"} />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge tone="gold">Learner view</StatusBadge>
        <StatusBadge tone={canAdmin ? "teal" : "slate"}>
          <Lock className="mr-1 h-3.5 w-3.5" />
          Admin trace {canAdmin ? "enabled" : "locked"}
        </StatusBadge>
        <StatusBadge tone="blue">
          <ShieldCheck className="mr-1 h-3.5 w-3.5" />
          Redacted trace enabled
        </StatusBadge>
      </div>

      {loading && (
        <Panel className="flex min-h-64 items-center justify-center">
          <RefreshCw className="mr-2 h-5 w-5 animate-spin text-academic-score" />
          <span className="text-sm text-slate-600">正在加载增强复盘...</span>
        </Panel>
      )}

      {error && !loading && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}
      {notice && !loading && <Panel className="border-academic-score/30 bg-academic-score-soft text-sm text-amber-800">{notice}</Panel>}

      {session && !loading && (
        <>
          {conversationItems.length === 0 ? (
            <EmptyState icon={FileText} title="暂无会话轮次" body="这次考试还没有保存任何问答轮次。" />
          ) : (
            <section className="grid gap-4 xl:grid-cols-[220px_minmax(0,1fr)_320px]">
              <ReviewTimeline items={conversationItems} selectedId={selectedItem?.id} report={report} onSelect={setSelectedTurnId} />
              <ConversationReplay items={conversationItems} selectedId={selectedItem?.id} onSelect={setSelectedTurnId} />
              <TraceSummaryPanel
                item={selectedItem}
                trace={selectedTrace}
                canAdmin={canAdmin}
                loading={traceLoading}
                onOpen={() => setTraceDialogOpen(true)}
              />
            </section>
          )}

          {report?.criteria?.length ? (
            <CriterionEvidenceCards criteria={report.criteria} items={conversationItems} />
          ) : (
            <Panel>
              <EmptyState icon={FileText} title="暂无评分维度" body="报告生成后会显示 Fluency、Lexical、Grammar、Pronunciation 四维证据。" />
            </Panel>
          )}

          <ReferenceAnswerDock referenceAnswers={report?.reference_answers ?? []} selectedItem={selectedItem} />

          <p className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs leading-relaxed text-slate-500">
            {report?.disclaimer ?? "AI scoring is for practice reference only, not official IELTS results."}
          </p>

          <DetailDialog
            open={traceDialogOpen}
            title="Agent Trace"
            titleZh="调用详情"
            description={selectedItem?.agentRunId ? `Turn ${(selectedItem.turnIndex ?? 0) + 1} · Run ${selectedItem.agentRunId}` : "当前轮次没有可关联的 Agent run。"}
            onClose={() => setTraceDialogOpen(false)}
            className="max-w-6xl"
          >
            <AgentTracePanel item={selectedItem} trace={selectedTrace} canAdmin={canAdmin} loading={traceLoading} />
          </DetailDialog>
        </>
      )}
    </AcademicShell>
  );
}

function TraceSummaryPanel({
  item,
  trace,
  canAdmin,
  loading,
  onOpen,
}: {
  item?: ReviewConversationItem;
  trace?: AgentRunTrace | null;
  canAdmin: boolean;
  loading: boolean;
  onOpen: () => void;
}) {
  return (
    <Panel className="h-fit lg:sticky lg:top-4">
      <SectionHeading
        icon={BrainCircuit}
        label="Trace Summary"
        labelZh="后台轨迹"
        action={<StatusBadge tone={canAdmin ? "teal" : "slate"}>{canAdmin ? "Admin" : "Redacted"}</StatusBadge>}
      />
      <div className="grid gap-3">
        <InlineKpi label="Turn" value={item ? `Part ${item.part} · Turn ${item.turnIndex + 1}` : "-"} />
        <InlineKpi label="Run" value={item?.agentRunId || "未关联"} />
        <InlineKpi label="Steps" value={trace ? String(trace.steps.length) : loading ? "加载中" : "不可用"} />
        <InlineKpi label="Status" value={trace?.status || (loading ? "loading" : "no trace")} />
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs leading-6 text-slate-600">
          完整 Agent step、真实 LLM 请求、工具参数和脱敏 payload 已移入详情窗口，主页面只保留当前轮次定位信息。
        </div>
        <Button type="button" variant="teal" onClick={onOpen} disabled={loading && !trace}>
          <Eye className="mr-2 h-4 w-4" />
          打开详情
        </Button>
      </div>
    </Panel>
  );
}

function KpiChip({
  icon: Icon,
  label,
  value,
  tone = "slate",
}: {
  icon?: LucideIcon;
  label: string;
  value?: string;
  tone?: "gold" | "teal" | "sage" | "slate";
}) {
  const tones = {
    gold: "border-academic-score/30 bg-academic-score-soft text-amber-800",
    teal: "border-academic-accent/25 bg-academic-accent-soft text-blue-800",
    sage: "border-emerald-600/25 bg-academic-success-soft text-emerald-800",
    slate: "border-slate-200 bg-white text-slate-600",
  };
  return (
    <div className={`inline-flex min-h-10 items-center gap-2 rounded-md border px-3 text-sm shadow-sm ${tones[tone]}`}>
      {Icon && <Icon className="h-4 w-4" />}
      <span>{label}</span>
      {value && <span className="font-semibold text-academic-navy">{value}</span>}
    </div>
  );
}

function buildConversationItems(session: SessionResponse["session"] | null, report: ScoreReport | null): ReviewConversationItem[] {
  if (!session?.turns?.length) return [];
  const partById = new Map((session.parts ?? []).map((part) => [part.id, part.part]));
  const evidenceByTurn = evidenceByTurnId(report);
  const referenceByTurn = new Map((report?.reference_answers ?? []).filter((item) => item.turn_id).map((item) => [item.turn_id as string, item]));

  return [...session.turns]
    .sort((a, b) => a.turn_index - b.turn_index)
    .filter((turn) => turn.question_text || turn.answer_text || (turn.audio_assets?.length ?? 0) > 0)
    .map((turn) => {
      const latestAsr = latestItem(turn.asr_results);
      const latestMetrics = latestItem(turn.speech_metrics);
      const part = partById.get(turn.part_id ?? "") ?? numberFromMetadata(turn.metadata, "part") ?? inferPart(turn.turn_index);
      const questionId = turn.question_id || stringFromMetadata(turn.metadata, "agent_question_id") || stringFromMetadata(turn.metadata, "question_id");
      const agentRunId = turn.agent_run_id || stringFromMetadata(turn.metadata, "agent_run_id");
      const answerText = selectReviewTranscript({
        correctedTranscript: latestAsr?.corrected_transcript,
        answerText: turn.answer_text,
        asrTranscript: latestAsr?.transcript,
        asrProvider: latestAsr?.provider,
      });
      return {
        id: turn.id,
        turnIndex: turn.turn_index,
        part,
        questionId,
        questionText: turn.question_text,
        answerText,
        agentRunId,
        metadata: turn.metadata,
        examinerAudio: firstAsset(turn, "examiner_tts"),
        userAudio: firstAsset(turn, "user_recording"),
        asr: latestAsr,
        metrics: latestMetrics,
        evidence: evidenceByTurn.get(turn.id) ?? [],
        referenceAnswer: referenceByTurn.get(turn.id),
        status: turn.status,
      };
    });
}

function evidenceByTurnId(report: ScoreReport | null) {
  const grouped = new Map<string, Array<ReportEvidence & { criterion: string }>>();
  for (const criterion of report?.criteria ?? []) {
    for (const item of criterion.evidence ?? []) {
      if (!item.turn_id) continue;
      grouped.set(item.turn_id, [...(grouped.get(item.turn_id) ?? []), { ...item, criterion: criterion.criterion }]);
    }
  }
  return grouped;
}

function firstAsset(turn: ReviewTurn, kind: string) {
  return (turn.audio_assets ?? []).find((asset) => asset.kind === kind);
}

function latestItem<T extends { created_at?: string }>(items?: T[]) {
  if (!items?.length) return undefined;
  return [...items].sort((a, b) => Date.parse(b.created_at ?? "") - Date.parse(a.created_at ?? ""))[0];
}

function collectRunIds(items: ReviewConversationItem[], report: ScoreReport | null) {
  const ids = new Set<string>();
  for (const item of items) {
    if (item.agentRunId) ids.add(item.agentRunId);
  }
  if (report?.model_run_id) ids.add(report.model_run_id);
  const rawRunId = typeof report?.raw_report?.agent_run_id === "string" ? report.raw_report.agent_run_id : undefined;
  if (rawRunId) ids.add(rawRunId);
  return Array.from(ids);
}

function numberFromMetadata(metadata: Record<string, unknown> | null | undefined, key: string) {
  const value = metadata?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function stringFromMetadata(metadata: Record<string, unknown> | null | undefined, key: string) {
  const value = metadata?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function inferPart(turnIndex: number) {
  if (turnIndex <= 1) return 1;
  if (turnIndex === 2) return 2;
  return 3;
}

function formatBand(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(1);
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}
