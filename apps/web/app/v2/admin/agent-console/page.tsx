"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2, RefreshCcw, ScrollText, Search, ShieldCheck, TerminalSquare } from "lucide-react";

import { AcademicShell, EmptyState, InlineKpi, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { AgentTimeline } from "@/app/v2/components/AgentTimeline";
import { OrchestratorRoutePath, OrchestratorRunTimeline } from "@/app/v2/components/OrchestratorRunTimeline";
import { Button } from "@/components/ui/button";
import { useOrchestratorStream } from "@/hooks/useOrchestratorStream";
import { orchestratorApi } from "@/lib/api";
import type { OrchestratorAgentMessage, OrchestratorToolIteration } from "@/lib/orchestratorTrace";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";

type TraceStatus = "running" | "completed" | "failed" | "cancelled";

type OrchestratorRun = {
  run_id: string;
  session_id: string;
  workflow_node: string;
  status: TraceStatus;
  latency_ms?: number;
  message_count?: number;
  stream_event_count?: number;
  error_code?: string | null;
  started_at: string;
  finished_at?: string | null;
};

type AgentMessageRecord = OrchestratorAgentMessage;

const statusFilters = ["", "running", "completed", "failed", "cancelled"] as const;

export default function V2AgentConsolePage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [runs, setRuns] = useState<OrchestratorRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [statusFilter, setStatusFilter] = useState<(typeof statusFilters)[number]>("");
  const [messages, setMessages] = useState<AgentMessageRecord[]>([]);
  const [toolIterations, setToolIterations] = useState<OrchestratorToolIteration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const canAdmin = user?.role === "operator" || user?.role === "admin";
  const stream = useOrchestratorStream(selectedRunId, { enabled: Boolean(selectedRunId && canAdmin) });
  const selectedRun = useMemo(() => runs.find((run) => run.run_id === selectedRunId) ?? null, [runs, selectedRunId]);
  const visibleEvents = useMemo(() => stream.events.filter((event) => event.kind !== "heartbeat"), [stream.events]);

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) router.push("/login");
  }, [hasHydrated, isAuthenticated, router]);

  useEffect(() => {
    if (hasHydrated && isAuthenticated && !user) void fetchUser();
  }, [fetchUser, hasHydrated, isAuthenticated, user]);

  const loadRuns = useCallback(async () => {
    if (!hasHydrated || !isAuthenticated || !canAdmin) return;
    setLoading(true);
    setError("");
    try {
      const response = await orchestratorApi.get<OrchestratorRun[]>("/agent/runs", { params: { limit: 100 } });
      const nextRuns = (response.data ?? []).filter((run) => !statusFilter || run.status === statusFilter);
      setRuns(nextRuns);
      setSelectedRunId((current) => current || nextRuns[0]?.run_id || "");
    } catch {
      setError("Request failed.");
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, [canAdmin, hasHydrated, isAuthenticated, statusFilter]);

  const loadRunDetails = useCallback(async (runId: string) => {
    if (!runId || !canAdmin) return;
    try {
      const [messagesResponse, toolIterationsResponse] = await Promise.all([
        orchestratorApi.get<AgentMessageRecord[]>(`/agent/runs/${encodeURIComponent(runId)}/messages`),
        orchestratorApi.get<OrchestratorToolIteration[]>(`/agent/runs/${encodeURIComponent(runId)}/tool-iterations`),
      ]);
      setMessages(messagesResponse.data ?? []);
      setToolIterations(toolIterationsResponse.data ?? []);
    } catch {
      setMessages([]);
      setToolIterations([]);
    }
  }, [canAdmin]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  useEffect(() => {
    if (selectedRunId) void loadRunDetails(selectedRunId);
  }, [loadRunDetails, selectedRunId]);

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/v2/admin/agent-console" userName={user?.display_name} userRole={user?.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">
          <SectionHeading icon={ShieldCheck} label="Access denied" labelZh="权限不足" />
          <p className="mt-2 text-sm leading-6">当前账号无权访问 V2 Agent 控制台。</p>
          <Button type="button" variant="soft" className="mt-5" onClick={() => router.push("/v2/practice/setup/full")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            返回 V2 练习
          </Button>
        </Panel>
      </AcademicShell>
    );
  }

  return (
    <AcademicShell activePath="/v2/admin/agent-console" userName={user?.display_name} userRole={user?.role} wide>
      <PageHeader
        eyebrow="V2 Orchestrator"
        title="Agent Console"
        titleZh="Agent 控制台"
        description="Inspect orchestrator runs, SSE events, agent lanes, messages, and LLM/tool iterations."
        actions={
          <>
            <Button type="button" variant="soft" onClick={() => router.push("/admin/observability")}>
              <ScrollText className="mr-2 h-4 w-4" />
              V1 Observability
            </Button>
            <Button type="button" variant="teal" onClick={() => void loadRuns()} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
              Refresh
            </Button>
          </>
        }
      />

      {error ? <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel> : null}
      {stream.error ? <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{stream.error}</Panel> : null}

      <section className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
        <Panel className="min-h-[720px] overflow-hidden">
          <SectionHeading icon={Search} label="Runs" labelZh="运行选择" />
          <label className="grid gap-2 text-sm text-slate-700">
            <span className="font-medium">Status</span>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as (typeof statusFilters)[number])}
              className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-academic-score"
            >
              {statusFilters.map((item) => (
                <option key={item || "all"} value={item}>
                  {item || "all"}
                </option>
              ))}
            </select>
          </label>
          <div className="mt-4 grid max-h-[620px] gap-2 overflow-y-auto pr-1">
            {loading ? (
              <div className="flex items-center justify-center py-10 text-sm text-slate-500">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Loading runs...
              </div>
            ) : runs.length ? (
              runs.map((run) => (
                <button
                  key={run.run_id}
                  type="button"
                  onClick={() => setSelectedRunId(run.run_id)}
                  className={cn(
                    "cursor-pointer rounded-lg border p-3 text-left transition-colors",
                    selectedRunId === run.run_id ? "border-academic-score bg-academic-score-soft" : "border-slate-200 bg-white hover:border-academic-accent/40 hover:bg-academic-accent-soft",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <StatusBadge tone={run.status === "completed" ? "sage" : run.status === "failed" ? "coral" : "gold"}>{run.status}</StatusBadge>
                    <span className="font-mono text-[11px] text-slate-400">{run.workflow_node}</span>
                  </div>
                  <p className="mt-2 break-all font-mono text-xs font-semibold text-slate-800">{run.run_id}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <StatusBadge tone="teal">{run.message_count ?? 0} msgs</StatusBadge>
                    <StatusBadge tone="blue">{run.stream_event_count ?? 0} events</StatusBadge>
                  </div>
                </button>
              ))
            ) : (
              <EmptyState icon={TerminalSquare} title="暂无运行" body="当前筛选条件下没有可用的 V2 run。" />
            )}
          </div>
        </Panel>

        <div className="grid gap-5">
          {selectedRun ? (
            <Panel>
              <SectionHeading icon={ShieldCheck} label="Selected Run" labelZh="当前 Run" />
              <div className="grid gap-2 md:grid-cols-2">
                <InlineKpi label="Session" value={selectedRun.session_id} />
                <InlineKpi label="Workflow" value={selectedRun.workflow_node} />
                <InlineKpi label="Latency" value={`${selectedRun.latency_ms ?? 0} ms`} />
                <InlineKpi label="Stream" value={stream.status} />
              </div>
            </Panel>
          ) : null}
          <OrchestratorRoutePath events={visibleEvents} />
          <OrchestratorRunTimeline events={visibleEvents} messages={messages} toolIterations={toolIterations} />
          <AgentTimeline events={visibleEvents} />
        </div>
      </section>
    </AcademicShell>
  );
}
