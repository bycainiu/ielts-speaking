"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Bot,
  BrainCircuit,
  Clock3,
  Database,
  Eye,
  FileText,
  Filter,
  Layers3,
  Loader2,
  RefreshCcw,
  ScrollText,
  Search,
  ShieldCheck,
  UserRound,
  Waypoints,
} from "lucide-react";
import { useRouter } from "next/navigation";

import { AcademicShell, DetailDialog, EmptyState, InlineKpi, MetricCard, MonoBlock, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { useAdminSessionContexts } from "@/hooks/useAdminSessionContexts";
import { useAdminUserContexts } from "@/hooks/useAdminUserContexts";
import {
  displayQuestionBankLabel,
  formatModeLabel,
  displaySessionMeta,
  displaySessionTitle,
  displayUserMeta,
  displayUserName,
  shortId,
} from "@/lib/adminSessionContext";
import type { AgentRunTrace, TraceLlmCall, TraceToolCall } from "@/components/review/types";
import { Button } from "@/components/ui/button";
import { agentApi, api } from "@/lib/api";
import { collectPayloadHighlights, formatPayload, hasPayload, summarizeReadablePayload } from "@/lib/traceReadable";
import {
  formatCallModel,
  formatCallProvider,
  formatExecutionKind,
  formatPayloadOrigin,
  formatStepModel,
  formatTraceCallTitle,
  formatTraceTokens,
  hasCapturedLlmCalls,
  isCapturedLlmCall,
} from "@/lib/traceSemantics";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";

type ApiError = {
  response?: {
    data?: {
      message?: string;
      detail?: string;
    };
  };
};

type AgentAuditSessionSummary = {
  session_id: string;
  user_id_hash?: string | null;
  mode?: string | null;
  status: string;
  started_at: string;
  last_event_at: string;
  run_count: number;
  event_count: number;
  completed_run_count: number;
  failed_run_count: number;
  current_part?: number | null;
  latest_question_id?: string | null;
  completed_parts: number[];
  recent_event_types: string[];
  agent_names: string[];
};

type AgentSessionEvent = {
  type: string;
  session_id: string;
  run_id: string;
  payload: Record<string, unknown>;
  created_at: string;
};

type AgentAuditRunSummary = {
  run_id: string;
  session_id: string;
  mode?: string | null;
  part?: number | null;
  question_id?: string | null;
  status: "running" | "completed" | "failed" | "cancelled";
  latency_ms?: number | null;
  step_count: number;
  error_code?: string | null;
  started_at: string;
  finished_at?: string | null;
};

type AgentAuditSessionDetail = AgentAuditSessionSummary & {
  event_type_counts: Record<string, number>;
  events: AgentSessionEvent[];
  runs: AgentAuditRunSummary[];
  traces: AgentRunTrace[];
};

type AdminAuditLog = {
  id: string;
  actor_user_id?: string | null;
  actor_role: string;
  action: string;
  resource: string;
  method: string;
  path: string;
  status_code: number;
  metadata: Record<string, unknown>;
  created_at: string;
};

const modeOptions = ["", "full_exam", "part_practice", "topic_practice"];
const sessionStatusOptions = ["", "completed", "failed", "scoring", "session_completed", "cancelled"];
const logResourceOptions = ["", "audit_logs", "question_bank", "knowledge_base", "prompt_versions", "content_review"];
const statusClassOptions = ["0", "2", "4", "5"];

export default function AdminAuditPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [sessionId, setSessionId] = useState("");
  const [mode, setMode] = useState("");
  const [sessionStatus, setSessionStatus] = useState("");
  const [logResource, setLogResource] = useState("");
  const [statusClass, setStatusClass] = useState("0");
  const [searchText, setSearchText] = useState("");
  const [sessions, setSessions] = useState<AgentAuditSessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [sessionDetail, setSessionDetail] = useState<AgentAuditSessionDetail | null>(null);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedStepId, setSelectedStepId] = useState("");
  const [auditLogs, setAuditLogs] = useState<AdminAuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [stepDetailOpen, setStepDetailOpen] = useState(false);
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

  const loadSessionDetail = useCallback(async (targetSessionId: string) => {
    if (!targetSessionId) {
      setSessionDetail(null);
      setSelectedRunId("");
      setSelectedStepId("");
      return;
    }
    setSelectedSessionId(targetSessionId);
    setDetailLoading(true);
    setError("");
    try {
      const response = await agentApi.get<AgentAuditSessionDetail>(`/agent/audit/sessions/${encodeURIComponent(targetSessionId)}`, {
        params: { limit: "500" },
      });
      setSessionDetail(response.data);
      setSelectedSessionId(targetSessionId);
      setSelectedRunId((current) => current && response.data.runs.some((item) => item.run_id === current) ? current : (response.data.runs[0]?.run_id ?? ""));
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "审计详情加载失败.");
      setSessionDetail(null);
      setSelectedRunId("");
      setSelectedStepId("");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const loadAuditConsole = useCallback(async () => {
    if (!hasHydrated || !isAuthenticated || !canAdmin) return;
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const sessionParams: Record<string, string> = { limit: "40" };
      const logParams: Record<string, string> = { limit: "40" };
      if (sessionId.trim()) sessionParams.session_id = sessionId.trim();
      if (mode) sessionParams.mode = mode;
      if (sessionStatus) sessionParams.status = sessionStatus;
      if (logResource) logParams.resource = logResource;
      if (statusClass !== "0") logParams.status_class = statusClass;
      if (searchText.trim()) logParams.q = searchText.trim();

      const [sessionResponse, logResponse] = await Promise.all([
        agentApi.get<AgentAuditSessionSummary[]>("/agent/audit/sessions", { params: sessionParams }),
        api.get<{ logs: AdminAuditLog[] }>("/admin/audit/logs", { params: logParams }),
      ]);

      const nextSessions = sessionResponse.data ?? [];
      setSessions(nextSessions);
      setAuditLogs(logResponse.data.logs ?? []);

      const nextSessionId =
        (sessionId.trim() && nextSessions.find((item) => item.session_id === sessionId.trim())?.session_id) ||
        (selectedSessionId && nextSessions.find((item) => item.session_id === selectedSessionId)?.session_id) ||
        nextSessions[0]?.session_id ||
        "";

      if (nextSessionId) {
        await loadSessionDetail(nextSessionId);
      } else {
        setSelectedSessionId("");
        setSessionDetail(null);
        setSelectedRunId("");
        setSelectedStepId("");
        setNotice("当前筛选条件下没有可用的会话审计数据.");
      }
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "审计后台数据加载失败.");
      setSessions([]);
      setAuditLogs([]);
      setSessionDetail(null);
      setSelectedRunId("");
      setSelectedStepId("");
    } finally {
      setLoading(false);
    }
  }, [canAdmin, hasHydrated, isAuthenticated, loadSessionDetail, logResource, mode, searchText, selectedSessionId, sessionId, sessionStatus, statusClass]);

  useEffect(() => {
    loadAuditConsole();
  }, [loadAuditConsole]);

  const tracesByRunId = useMemo(() => new Map((sessionDetail?.traces ?? []).map((trace) => [trace.run_id, trace])), [sessionDetail?.traces]);
  const sessionIds = useMemo(
    () =>
      Array.from(
        new Set(
          sessions
            .map((item) => item.session_id?.trim())
            .filter(Boolean) as string[],
        ),
      ),
    [sessions],
  );
  const { contextMap } = useAdminSessionContexts(sessionIds, hasHydrated && isAuthenticated && canAdmin);
  const userHashes = useMemo(
    () =>
      Array.from(
        new Set(
          [
            ...sessions.map((item) => item.user_id_hash?.trim()),
            sessionDetail?.user_id_hash?.trim(),
          ].filter(Boolean) as string[],
        ),
      ),
    [sessionDetail?.user_id_hash, sessions],
  );
  const { contextMap: userContextMap } = useAdminUserContexts(userHashes, hasHydrated && isAuthenticated && canAdmin);
  const selectedSessionContext = selectedSessionId ? contextMap[selectedSessionId] ?? null : null;
  const selectedUserContext = sessionDetail?.user_id_hash ? userContextMap[sessionDetail.user_id_hash] ?? null : null;
  const selectedTrace = useMemo(() => {
    if (!sessionDetail?.traces.length) return null;
    return tracesByRunId.get(selectedRunId) ?? tracesByRunId.get(sessionDetail.runs[0]?.run_id ?? "") ?? sessionDetail.traces[sessionDetail.traces.length - 1];
  }, [selectedRunId, sessionDetail, tracesByRunId]);

  useEffect(() => {
    if (!selectedTrace) {
      setSelectedStepId("");
      return;
    }
    const valid = selectedTrace.steps.some((step) => step.step_id === selectedStepId);
    if (!valid) {
      setSelectedStepId(selectedTrace.steps[0]?.step_id ?? "");
    }
  }, [selectedStepId, selectedTrace]);

  const selectedStep = useMemo(() => {
    if (!selectedTrace?.steps.length) return null;
    return selectedTrace.steps.find((step) => step.step_id === selectedStepId) ?? selectedTrace.steps[0];
  }, [selectedStepId, selectedTrace]);

  const totalEvents = sessions.reduce((sum, item) => sum + item.event_count, 0);
  const totalRuns = sessions.reduce((sum, item) => sum + item.run_count, 0);
  const riskySessions = sessions.filter((item) => item.failed_run_count > 0 || item.status === "failed").length;
  const failedLogs = auditLogs.filter((item) => item.status_code >= 400).length;

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/admin/audit" userName={user?.display_name} userRole={user?.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">
          <SectionHeading icon={ShieldCheck} label="Access denied" labelZh="权限不足" />
          <h1 className="font-serif text-3xl text-academic-navy">Audit Console</h1>
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
    <AcademicShell activePath="/admin/audit" userName={user?.display_name} userRole={user?.role} wide>
      <PageHeader
        eyebrow="Compliance & Ops"
        title="Audit Console"
        titleZh="日志审计"
        description="面向管理员的完整审计后台，统一查看用户事件流、Agent 分层调用链、工具执行细节与后台操作留痕."
        actions={
          <>
            <Button type="button" variant="soft" onClick={() => router.push("/admin/observability")}>
              <Waypoints className="mr-2 h-4 w-4" />
              Observability
            </Button>
            <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Practice
            </Button>
            <Button type="button" variant="gold" onClick={loadAuditConsole} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
              Refresh
            </Button>
          </>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm leading-6 text-red-700">{error}</Panel>}
      {notice && !error && <Panel className="border-academic-paper-border bg-academic-paper text-sm leading-6 text-amber-800">{notice}</Panel>}

      <Panel>
        <SectionHeading icon={Filter} label="Filters" labelZh="筛选条件" />
        <div className="grid gap-3 xl:grid-cols-[1.2fr_180px_180px_180px_180px_1fr_auto]">
          <InputField label="Session ID" value={sessionId} onChange={setSessionId} placeholder="sess_..." />
          <SelectField label="Mode" value={mode} options={modeOptions} onChange={setMode} />
          <SelectField label="Session Status" value={sessionStatus} options={sessionStatusOptions} onChange={setSessionStatus} />
          <SelectField label="Log Resource" value={logResource} options={logResourceOptions} onChange={setLogResource} />
          <SelectField
            label="HTTP Class"
            value={statusClass}
            options={statusClassOptions}
            labels={{ "0": "all", "2": "2xx", "4": "4xx", "5": "5xx" }}
            onChange={setStatusClass}
          />
          <InputField label="Search Log" value={searchText} onChange={setSearchText} placeholder="action / path / metadata" />
          <Button type="button" variant="soft" className="self-end" onClick={loadAuditConsole} disabled={loading}>
            <Search className="mr-2 h-4 w-4" />
            Search
          </Button>
        </div>
      </Panel>

      <section className="grid gap-4 md:grid-cols-4">
        <MetricCard icon={Layers3} label="Audited Sessions" value={String(sessions.length)} helper={`${totalRuns} runs in current window`} tone="gold" />
        <MetricCard icon={ScrollText} label="Session Events" value={String(totalEvents)} helper="AG-UI 完整时间线事件数" tone="teal" />
        <MetricCard icon={AlertTriangle} label="Risky Sessions" value={String(riskySessions)} helper="存在失败 run 或 fatal 信号" tone="sage" />
        <MetricCard icon={ShieldCheck} label="Admin Logs" value={String(auditLogs.length)} helper={`${failedLogs} logs are 4xx/5xx`} />
      </section>

      <section className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
        <Panel className="min-h-[580px] overflow-hidden">
          <SectionHeading icon={Layers3} label="Sessions" labelZh="审计会话" />
          {loading ? (
            <LoadingBlock label="Loading sessions..." />
          ) : sessions.length === 0 ? (
            <EmptyState icon={Layers3} title="No audited sessions" body="暂无审计会话。" />
          ) : (
            <div className="grid max-h-[560px] gap-2 overflow-y-auto pr-1">
              {sessions.map((item) => {
                const sessionContext = contextMap[item.session_id] ?? null;
                const userContext = item.user_id_hash ? userContextMap[item.user_id_hash] ?? null : null;
                return (
                  <button
                    key={item.session_id}
                    type="button"
                    onClick={() => void loadSessionDetail(item.session_id)}
                    className={cn(
                      "grid cursor-pointer gap-2 rounded-lg border p-3 text-left transition-colors",
                      selectedSessionId === item.session_id ? "border-academic-score bg-academic-score-soft" : "border-slate-200 bg-white hover:border-academic-score/50",
                    )}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <StatusBadge tone={statusTone(item.status)}>{item.status}</StatusBadge>
                      <span className="text-xs text-slate-500">{formatTime(item.last_event_at)}</span>
                    </div>
                    <span className="break-words text-sm font-semibold text-slate-900">{displaySessionTitle(sessionContext, item.session_id)}</span>
                    <div className="grid gap-1 text-[11px] text-slate-500">
                      <span>{displayUserName(sessionContext ?? userContext) || item.user_id_hash || "Unavailable"}{displayUserMeta(sessionContext ?? userContext) ? ` · ${displayUserMeta(sessionContext ?? userContext)}` : ""}</span>
                      <span>{displaySessionMeta(sessionContext) || formatModeLabel(item.mode) || "mode unknown"} · {item.run_count} runs · {item.event_count} events</span>
                      <span>part {item.current_part ?? "-"} · completed {item.completed_parts.join(", ") || "-"}</span>
                      <span className="font-mono text-[10px] text-slate-400">session {shortId(item.session_id)}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </Panel>

        <Panel className="min-h-[580px] overflow-hidden">
          <SectionHeading
            icon={UserRound}
            label="Event Flow"
            labelZh="完整事件"
            action={sessionDetail ? <StatusBadge tone="teal">{sessionDetail.event_count} events</StatusBadge> : null}
          />
          {detailLoading ? (
            <LoadingBlock label="Loading event flow..." />
          ) : !sessionDetail ? (
            <EmptyState icon={UserRound} title="No session selected" body="请选择一个会话。" />
          ) : sessionDetail.events.length === 0 ? (
            <EmptyState icon={UserRound} title="No events" body="暂无事件。" />
          ) : (
            <div className="relative grid max-h-[560px] gap-3 overflow-y-auto pr-1">
              <div className="absolute bottom-4 left-5 top-4 w-px bg-slate-200" />
              {sessionDetail.events.map((event, index) => (
                <EventFlowCard key={`${event.run_id}-${event.type}-${event.created_at}-${index}`} event={event} selectedRunId={selectedRunId} />
              ))}
            </div>
          )}
        </Panel>

        <Panel className="min-h-[580px] overflow-hidden">
          <SectionHeading icon={FileText} label="Admin Logs" labelZh="后台留痕" />
          {loading ? (
            <LoadingBlock label="Loading admin logs..." />
          ) : auditLogs.length === 0 ? (
            <EmptyState icon={FileText} title="No admin logs" body="暂无管理日志。" />
          ) : (
            <div className="grid max-h-[560px] gap-3 overflow-y-auto pr-1">
              {auditLogs.map((item) => (
                <article key={item.id} className="rounded-lg border border-slate-200 bg-white p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone={httpTone(item.status_code)}>{item.status_code}</StatusBadge>
                      <StatusBadge tone="slate">{item.actor_role}</StatusBadge>
                      <StatusBadge tone="blue">{item.method}</StatusBadge>
                    </div>
                    <span className="text-xs text-slate-500">{formatTime(item.created_at)}</span>
                  </div>
                  <p className="mt-2 text-sm font-semibold text-slate-900">{item.resource}</p>
                  <p className="mt-1 break-all text-xs text-slate-600">{item.action}</p>
                  <p className="mt-1 break-all font-mono text-[11px] text-slate-400">{item.path}</p>
                  <details className="mt-2 rounded-md border border-slate-200 bg-slate-50">
                    <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-slate-700">Metadata</summary>
                    <div className="border-t border-slate-200 p-3">
                      <MonoBlock className="max-h-40">{JSON.stringify(item.metadata, null, 2)}</MonoBlock>
                    </div>
                  </details>
                </article>
              ))}
            </div>
          )}
        </Panel>
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Panel>
          <SectionHeading
            icon={BrainCircuit}
            label="Agent Hierarchy"
            labelZh="Agent 分层调用"
            action={selectedTrace ? <StatusBadge tone={statusTone(selectedTrace.status)}>{selectedTrace.status}</StatusBadge> : null}
          />
          {detailLoading ? (
            <LoadingBlock label="Loading traces..." />
          ) : !sessionDetail ? (
            <EmptyState icon={BrainCircuit} title="No trace context" body="暂无 Trace 上下文。" />
          ) : sessionDetail.runs.length === 0 ? (
            <EmptyState icon={BrainCircuit} title="No runs" body="暂无运行记录。" />
          ) : (
            <div className="grid gap-4">
              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                {sessionDetail.runs.map((run) => (
                  <button
                    key={run.run_id}
                    type="button"
                    onClick={() => setSelectedRunId(run.run_id)}
                    className={cn(
                      "grid cursor-pointer gap-2 rounded-lg border p-3 text-left transition-colors",
                      selectedRunId === run.run_id ? "border-academic-score bg-academic-score-soft" : "border-slate-200 bg-slate-50 hover:border-academic-score/50 hover:bg-white",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <StatusBadge tone={statusTone(run.status)}>{run.status}</StatusBadge>
                      <span className="text-xs text-slate-500">{run.latency_ms ?? 0}ms</span>
                    </div>
                    <span className="break-all font-mono text-xs text-slate-700">{run.run_id}</span>
                    <span className="text-[11px] text-slate-500">{run.step_count} steps · part {run.part ?? "-"}</span>
                  </button>
                ))}
              </div>

              {selectedTrace ? (
                <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
                  <div className="grid max-h-[560px] gap-2 overflow-y-auto pr-1">
                    {selectedTrace.steps.map((step) => (
                      <button
                        key={step.step_id}
                        type="button"
                        onClick={() => setSelectedStepId(step.step_id)}
                        className={cn(
                          "grid cursor-pointer gap-2 rounded-lg border p-3 text-left transition-colors",
                          selectedStep?.step_id === step.step_id ? "border-academic-score bg-academic-score-soft" : "border-slate-200 bg-white hover:border-academic-score/50",
                        )}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-semibold text-slate-900">{step.agent_name || step.workflow_node}</span>
                          <StatusBadge tone={statusTone(step.status)}>{step.status}</StatusBadge>
                        </div>
                        <div className="grid gap-2 text-xs text-slate-500 sm:grid-cols-3">
                          <span>{step.workflow_node}</span>
                          <span>{formatStepModel(step)}</span>
                          <span>{step.tool_calls.length} tools</span>
                        </div>
                      </button>
                    ))}
                  </div>

                  <Panel className="h-fit border-slate-200 bg-slate-50 xl:sticky xl:top-4">
                    <SectionHeading icon={Database} label="Step Snapshot" labelZh="调用快照" />
                    {selectedStep ? (
                      <div className="grid gap-3">
                        <InlineKpi label="Workflow" value={selectedStep.workflow_node} />
                        <InlineKpi label="Prompt" value={selectedStep.prompt_version || "-"} />
                        <InlineKpi label="Tokens" value={formatTraceTokens(selectedStep.input_tokens, selectedStep.output_tokens, { realLlmOnly: hasCapturedLlmCalls(selectedStep) })} />
                        <InlineKpi label="Latency" value={formatLatency(selectedStep.latency_ms)} />
                        <InlineKpi label="Tools" value={String(selectedStep.tool_calls.length)} />
                        <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs leading-6 text-slate-600">
                          输入、输出、messages、真实 LLM 与工具调用已收进详情窗口，避免审计页被单个 step 的 payload 拉长。
                        </div>
                        <Button type="button" variant="teal" onClick={() => setStepDetailOpen(true)}>
                          <Eye className="mr-2 h-4 w-4" />
                          打开调用明细
                        </Button>
                      </div>
                    ) : (
                      <EmptyState icon={Database} title="No step selected" body="请选择一个 step。" />
                    )}
                  </Panel>
                </div>
              ) : (
                <EmptyState icon={BrainCircuit} title="No selected trace" body="暂无选中的 Trace。" />
              )}
            </div>
          )}
        </Panel>

        <div className="grid gap-5">
          <Panel>
            <SectionHeading icon={Activity} label="Session Facts" labelZh="会话画像" />
            {sessionDetail ? (
              <div className="grid gap-3">
                <InlineKpi label="Mode" value={sessionDetail.mode || "-"} />
                <InlineKpi label="User" value={displayUserName(selectedSessionContext ?? selectedUserContext) || sessionDetail.user_id_hash || "-"} />
                <InlineKpi label="User Meta" value={displayUserMeta(selectedSessionContext ?? selectedUserContext) || sessionDetail.user_id_hash || "-"} />
                <InlineKpi label="Question Bank" value={displayQuestionBankLabel(selectedSessionContext)} />
                <InlineKpi label="Current Part" value={String(sessionDetail.current_part ?? "-")} />
                <InlineKpi label="Latest Question" value={sessionDetail.latest_question_id || "-"} />
                <InlineKpi label="Completed Parts" value={sessionDetail.completed_parts.join(", ") || "-"} />
                <InlineKpi label="Agents" value={sessionDetail.agent_names.join(", ") || "-"} />
              </div>
            ) : (
              <EmptyState icon={Activity} title="No session facts" body="暂无会话事实。" />
            )}
          </Panel>

          <Panel>
            <SectionHeading icon={Clock3} label="Event Counts" labelZh="事件分布" />
            {sessionDetail && Object.keys(sessionDetail.event_type_counts).length > 0 ? (
              <div className="grid gap-2">
                {Object.entries(sessionDetail.event_type_counts).map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <span className="min-w-0 truncate text-xs font-medium text-slate-600">{type}</span>
                    <StatusBadge tone="slate">{count}</StatusBadge>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState icon={Clock3} title="No event stats" body="暂无事件统计。" />
            )}
          </Panel>

          <Panel>
            <SectionHeading icon={Bot} label="Recent Signals" labelZh="近期信号" />
            {sessionDetail?.recent_event_types.length ? (
              <div className="flex flex-wrap gap-2">
                {sessionDetail.recent_event_types.map((item, index) => (
                  <StatusBadge key={`${item}-${index}`} tone="gold">{item}</StatusBadge>
                ))}
              </div>
            ) : (
              <EmptyState icon={Bot} title="No recent signals" body="暂无近期信号。" />
            )}
          </Panel>
        </div>
      </section>

      <DetailDialog
        open={stepDetailOpen && Boolean(selectedStep)}
        title={selectedStep?.agent_name || selectedStep?.workflow_node || "Trace Detail"}
        titleZh="调用明细"
        description={selectedTrace ? `${shortRunId(selectedTrace.run_id)} · ${selectedStep?.step_id || ""}` : undefined}
        onClose={() => setStepDetailOpen(false)}
        className="max-w-6xl"
      >
        {selectedStep ? (
          <div className="grid gap-4">
            <div className="grid gap-3 md:grid-cols-4">
              <InlineKpi label="Workflow" value={selectedStep.workflow_node} />
              <InlineKpi label="Prompt" value={selectedStep.prompt_version || "-"} />
              <InlineKpi label="Tokens" value={formatTraceTokens(selectedStep.input_tokens, selectedStep.output_tokens, { realLlmOnly: hasCapturedLlmCalls(selectedStep) })} />
              <InlineKpi label="Latency" value={formatLatency(selectedStep.latency_ms)} />
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              <ReadableBlock title="Input" value={selectedStep.input_payload ?? selectedStep.input_detail ?? selectedStep.input_summary} />
              <ReadableBlock title="Output" value={selectedStep.output_payload ?? selectedStep.scoring_result ?? selectedStep.output_summary} />
            </div>
            <ReadableBlock title="Messages" value={selectedStep.messages ?? []} />
            <LlmCallsBlock calls={selectedStep.llm_calls ?? []} />
            <ToolCallsBlock calls={selectedStep.tool_calls ?? []} />
          </div>
        ) : null}
      </DetailDialog>
    </AcademicShell>
  );
}

function InputField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-11 min-w-0 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-academic-score"
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  labels,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  labels?: Record<string, string>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-academic-score">
        {options.map((item) => (
          <option key={item || "all"} value={item}>
            {labels?.[item] || item || "all"}
          </option>
        ))}
      </select>
    </label>
  );
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center text-sm text-slate-600">
      <Loader2 className="mr-2 h-5 w-5 animate-spin text-academic-score" />
      {label}
    </div>
  );
}

function EventFlowCard({ event, selectedRunId }: { event: AgentSessionEvent; selectedRunId: string }) {
  const meta = eventMeta(event.type);
  const Icon = meta.icon;
  const payload = event.payload ?? {};
  const isActiveRun = selectedRunId && event.run_id === selectedRunId;
  return (
    <article
      className={cn(
        "relative ml-10 rounded-lg border p-3 shadow-sm",
        meta.surface,
        isActiveRun && "border-academic-score ring-1 ring-academic-score/30",
      )}
    >
      <span className={cn("absolute -left-10 top-4 z-10 flex h-9 w-9 items-center justify-center rounded-full border text-xs shadow-sm", meta.badge)}>
        <Icon className="h-4 w-4" />
      </span>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-900">{eventHeadline(event)}</p>
          <p className="mt-1 break-all font-mono text-[11px] text-slate-500">{event.type}</p>
        </div>
        <div className="text-right">
          <StatusBadge tone={meta.tone}>{shortRunId(event.run_id)}</StatusBadge>
          <p className="mt-1 text-[11px] text-slate-500">{formatTime(event.created_at)}</p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-500">
        {payload.part ? <span>part {String(payload.part)}</span> : null}
        {typeof payload.question_id === "string" ? <span>question {truncate(payload.question_id, 18)}</span> : null}
      </div>
      <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-5 text-slate-700">{eventBody(event)}</p>
      <details className="mt-2 rounded-md border border-slate-200 bg-white/80">
        <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-slate-700">Payload 详情</summary>
        <div className="border-t border-slate-200 p-3">
          <ReadableBlock title="Payload" value={event.payload} />
        </div>
      </details>
    </article>
  );
}

function ReadableBlock({ title, value }: { title: string; value: unknown }) {
  const highlights = collectPayloadHighlights(value);
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{summarizeReadablePayload(null, value, "当前未提取到更直观的文本片段.")}</p>
      {highlights.length > 0 ? (
        <div className="mt-2 grid gap-2">
          {highlights.map((item) => (
            <div key={`${title}-${item.label}-${item.text.slice(0, 24)}`} className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2">
              <p className="text-[11px] font-semibold text-blue-800">{item.label}</p>
              <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{item.text}</p>
            </div>
          ))}
        </div>
      ) : null}
      {hasPayload(value) ? (
        <details className="mt-2 rounded-md border border-slate-200 bg-slate-50">
          <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-slate-700">完整脱敏结构</summary>
          <div className="border-t border-slate-200 p-3">
            <MonoBlock className="max-h-44">{formatPayload(value ?? null)}</MonoBlock>
          </div>
        </details>
      ) : null}
    </div>
  );
}

function LlmCallsBlock({ calls }: { calls: TraceLlmCall[] }) {
  if (!calls.length) return null;
  return (
    <section className="grid gap-2 rounded-lg border border-academic-score/25 bg-[#FFFDF6] p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-800">调用记录（真实 LLM / 派生）</p>
      {calls.map((call, index) => {
        const isRealLlm = isCapturedLlmCall(call);
        return (
          <article key={call.llm_call_id || `${call.call_name}-${index}`} className={cn("rounded-lg border bg-white p-3", isRealLlm ? "border-academic-score/25" : "border-slate-200")}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="break-words text-sm font-semibold text-slate-900">{formatTraceCallTitle(call)} · {call.call_name || `调用 ${index + 1}`}</p>
                <p className="mt-1 text-[11px] text-slate-500">
                  {[call.agent_name, formatCallProvider(call), formatCallModel(call), call.prompt_version].filter(Boolean).join(" · ") || "调用上下文未提供"}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <StatusBadge tone={statusTone(call.status)}>{call.status}</StatusBadge>
                <StatusBadge tone={isRealLlm ? "gold" : "teal"}>{formatExecutionKind(call.execution_kind || "deterministic")}</StatusBadge>
                <StatusBadge tone="slate">{formatPayloadOrigin(call.payload_origin)}</StatusBadge>
              </div>
            </div>
            <div className="mt-3 grid gap-3">
              <CallPayloadBlock title={isRealLlm ? "请求输入" : "派生输入"} value={call.request_payload ?? call.input_summary} emptyLabel="当前未保存输入内容" />
              <CallPayloadBlock title={isRealLlm ? "模型输出" : "派生输出"} value={call.response_payload ?? call.output_summary} emptyLabel="当前未保存输出内容" />
            </div>
          </article>
        );
      })}
    </section>
  );
}

function ToolCallsBlock({ calls }: { calls: TraceToolCall[] }) {
  if (!calls.length) return null;
  return (
    <section className="grid gap-2 rounded-lg border border-emerald-600/25 bg-[#FAFFFC] p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-800">工具调用</p>
      {calls.map((tool, index) => {
        const requestBody = tool.arguments ?? tool.parameters ?? tool.input_payload ?? tool.request ?? tool.input_summary;
        const responseBody = tool.output_payload ?? tool.response ?? tool.result_summary ?? tool.output_summary;
        return (
          <article key={`${tool.tool_name}-${index}`} className="rounded-lg border border-emerald-600/20 bg-white p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="break-words text-sm font-semibold text-slate-900">{tool.tool_name || `工具 ${index + 1}`}</p>
                <p className="mt-1 text-[11px] text-slate-500">{tool.scope || "Unavailable"}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <StatusBadge tone={tool.status === "completed" ? "sage" : "red"}>{tool.status}</StatusBadge>
                <StatusBadge tone="gold">{formatLatency(tool.latency_ms)}</StatusBadge>
              </div>
            </div>
            {tool.error_code ? <p className="mt-2 break-words text-xs text-red-600">{tool.error_code}</p> : null}
            <div className="mt-3 grid gap-3">
              <CallPayloadBlock title="工具参数" value={requestBody} emptyLabel="当前审计记录未保存工具参数" />
              <CallPayloadBlock title="工具返回" value={responseBody} emptyLabel="当前审计记录未保存工具返回" />
            </div>
          </article>
        );
      })}
    </section>
  );
}

function CallPayloadBlock({
  title,
  value,
  emptyLabel,
}: {
  title: string;
  value: unknown;
  emptyLabel: string;
}) {
  const highlights = collectPayloadHighlights(value, 4);
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{summarizeReadablePayload(null, value, emptyLabel)}</p>
      {highlights.length > 0 ? (
        <div className="mt-2 grid gap-2">
          {highlights.map((item) => (
            <div key={`${title}-${item.label}-${item.text.slice(0, 24)}`} className="rounded-md border border-slate-200 bg-white px-2.5 py-2">
              <p className="text-[11px] font-semibold text-blue-800">{item.label}</p>
              <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{item.text}</p>
            </div>
          ))}
        </div>
      ) : null}
      {hasPayload(value) ? (
        <details className="mt-2 rounded-md border border-slate-200 bg-white">
          <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-slate-700">完整脱敏结构</summary>
          <div className="border-t border-slate-200 p-3">
            <MonoBlock className="max-h-40">{formatPayload(value)}</MonoBlock>
          </div>
        </details>
      ) : null}
    </div>
  );
}

function eventMeta(type: string): { tone: "gold" | "teal" | "sage" | "coral" | "red" | "blue"; icon: LucideIcon; surface: string; badge: string } {
  if (type.startsWith("user.")) {
    return {
      tone: "teal",
      icon: UserRound,
      surface: "border-academic-accent/20 bg-[#F8FCFE]",
      badge: "border-academic-accent/30 bg-academic-accent-soft text-blue-800",
    };
  }
  if (type.startsWith("examiner.")) {
    return {
      tone: "gold",
      icon: Bot,
      surface: "border-academic-score/25 bg-[#FFFDF6]",
      badge: "border-academic-score/35 bg-academic-score-soft text-amber-800",
    };
  }
  if (type.startsWith("asr.") || type.startsWith("timer.")) {
    return {
      tone: "blue",
      icon: Clock3,
      surface: "border-blue-200 bg-blue-50/50",
      badge: "border-blue-200 bg-blue-50 text-blue-700",
    };
  }
  if (type.startsWith("agent.") || type.startsWith("scoring.")) {
    return {
      tone: "sage",
      icon: BrainCircuit,
      surface: "border-emerald-600/20 bg-[#FAFFFC]",
      badge: "border-emerald-600/30 bg-academic-success-soft text-emerald-800",
    };
  }
  if (type.startsWith("error.")) {
    return {
      tone: "red",
      icon: AlertTriangle,
      surface: "border-red-200 bg-red-50",
      badge: "border-red-200 bg-white text-red-600",
    };
  }
  return {
    tone: "coral",
    icon: Activity,
    surface: "border-orange-500/20 bg-[#FFF9F6]",
    badge: "border-orange-500/30 bg-[#FFF0EA] text-orange-700",
  };
}

function eventHeadline(event: AgentSessionEvent) {
  const payload = event.payload ?? {};
  if (event.type === "examiner.message") return String(payload.text || "Examiner message");
  if (event.type === "asr.final") return "ASR final transcript";
  if (event.type === "agent.followup_planned") return `Follow-up ${String(payload.decision || "planned")}`;
  if (event.type === "report.ready") return `Score report ready · ${String(payload.overall_band ?? "-")}`;
  if (event.type === "session.started") return `Session started · ${String(payload.mode || "unknown")}`;
  if (event.type === "part.started") return `Part ${String(payload.part || "-")} started`;
  if (event.type === "part.completed") return `Part ${String(payload.part || "-")} completed`;
  if (event.type === "scoring.dimension_completed") return `${String(payload.criterion || "criterion")} scored`;
  if (event.type === "error.recoverable" || event.type === "error.fatal") return String(payload.message || event.type);
  return event.type;
}

function eventBody(event: AgentSessionEvent) {
  const payload = event.payload ?? {};
  if (event.type === "asr.final") return truncate(String(payload.text || "No transcript"), 180);
  if (event.type === "agent.followup_planned") return `${String(payload.reason || "No reason")} · confidence ${String(payload.confidence ?? "-")}`;
  if (event.type === "report.ready") return `overall ${String(payload.overall_band ?? "-")} · confidence ${String(payload.confidence ?? "-")} · feedback ${String(payload.feedback_count ?? 0)}`;
  if (event.type === "error.recoverable" || event.type === "error.fatal") return String(payload.message || "No message");
  if (typeof payload.text === "string") return truncate(payload.text, 180);
  return summarizeReadablePayload(null, payload, truncate(JSON.stringify(payload), 180));
}

function statusTone(status: string): "sage" | "coral" | "red" | "slate" {
  if (status === "completed") return "sage";
  if (status === "failed") return "red";
  if (status === "running" || status === "scoring" || status === "session_completed") return "coral";
  return "slate";
}

function httpTone(statusCode: number): "sage" | "coral" | "red" | "slate" {
  if (statusCode >= 500) return "red";
  if (statusCode >= 400) return "coral";
  if (statusCode >= 200 && statusCode < 400) return "sage";
  return "slate";
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatLatency(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${value}ms`;
}

function shortRunId(value: string) {
  return value.length > 14 ? `${value.slice(0, 12)}...` : value;
}

function truncate(value: string, limit: number) {
  return value.length > limit ? `${value.slice(0, limit - 1)}...` : value;
}
