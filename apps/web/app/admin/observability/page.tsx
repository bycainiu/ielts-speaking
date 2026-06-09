"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Ban,
  Clock3,
  Database,
  Filter,
  Loader2,
  RefreshCcw,
  Search,
  ShieldCheck,
  Waypoints,
} from "lucide-react";

import { AcademicShell, EmptyState, InlineKpi, MetricCard, MonoBlock, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { agentApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";

type ApiError = {
  response?: {
    data?: {
      message?: string;
    };
  };
};

type LatencyStats = {
  count: number;
  avg_ms: number;
  p50_ms: number;
  p95_ms: number;
  min_ms: number;
  max_ms: number;
};

type ObservabilityRun = {
  run_id: string;
  session_id: string;
  mode?: string | null;
  status: "running" | "completed" | "failed" | "cancelled";
  latency_ms?: number | null;
  step_count: number;
  error_code?: string | null;
  started_at: string;
  finished_at?: string | null;
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
  input_token_count: number;
  output_token_count: number;
  estimated_model_cost_usd: number;
  errors_by_code: Record<string, number>;
  recent_runs: ObservabilityRun[];
};

type ObservabilityAlert = {
  alert_id: string;
  severity: "warning" | "critical";
  metric: string;
  message: string;
  threshold: number;
  actual: number;
  runbook: string;
};

type TraceToolCall = {
  tool_name: string;
  scope?: string | null;
  status: "completed" | "failed";
  latency_ms: number;
  error_code?: string | null;
};

type TraceStep = {
  step_id: string;
  workflow_node: string;
  part?: number | null;
  question_id?: string | null;
  agent_name?: string | null;
  prompt_version?: string | null;
  model_name?: string | null;
  status: "running" | "completed" | "failed";
  input_tokens?: number | null;
  output_tokens?: number | null;
  retrieved_chunks?: Record<string, unknown>[];
  structured_output_validity?: boolean | null;
  scoring_result?: Record<string, unknown> | null;
  latency_ms?: number | null;
  error_code?: string | null;
  error_type?: string | null;
  started_at: string;
  finished_at?: string | null;
  tool_calls: TraceToolCall[];
};

type AgentRunTrace = {
  run_id: string;
  session_id: string;
  user_id_hash?: string | null;
  mode?: string | null;
  part?: number | null;
  question_id?: string | null;
  status: "running" | "completed" | "failed" | "cancelled";
  started_at: string;
  finished_at?: string | null;
  steps: TraceStep[];
};

const modes = ["", "full_exam", "part_practice", "topic_practice"];

export default function ObservabilityAdminPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [sessionId, setSessionId] = useState("");
  const [runId, setRunId] = useState("");
  const [mode, setMode] = useState("");
  const [summary, setSummary] = useState<ObservabilitySummary | null>(null);
  const [alerts, setAlerts] = useState<ObservabilityAlert[]>([]);
  const [trace, setTrace] = useState<AgentRunTrace | null>(null);
  const [selectedStepId, setSelectedStepId] = useState("");
  const [loading, setLoading] = useState(true);
  const [traceLoading, setTraceLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
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

  const filterParams = useCallback(() => {
    const params: Record<string, string> = { limit: "100" };
    if (sessionId.trim()) params.session_id = sessionId.trim();
    if (runId.trim()) params.run_id = runId.trim();
    if (mode) params.mode = mode;
    return params;
  }, [mode, runId, sessionId]);

  const loadObservability = useCallback(async () => {
    if (!hasHydrated || !isAuthenticated || !canAdmin) return;
    setLoading(true);
    setError("");
    try {
      const params = filterParams();
      const [summaryResponse, alertsResponse] = await Promise.all([
        agentApi.get<ObservabilitySummary>("/agent/observability/summary", { params }),
        agentApi.get<ObservabilityAlert[]>("/agent/observability/alerts", { params }),
      ]);
      setSummary(summaryResponse.data);
      setAlerts(alertsResponse.data ?? []);
      const nextRunId = runId.trim() || summaryResponse.data.recent_runs[0]?.run_id || "";
      if (nextRunId) {
        await loadTrace(nextRunId);
      } else {
        setTrace(null);
      }
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Observability data could not be loaded.");
      setSummary(null);
      setAlerts([]);
      setTrace(null);
    } finally {
      setLoading(false);
    }
  }, [canAdmin, filterParams, hasHydrated, isAuthenticated, runId]);

  useEffect(() => {
    loadObservability();
  }, [loadObservability]);

  const loadTrace = async (targetRunId: string) => {
    setTraceLoading(true);
    setSelectedStepId("");
    try {
      const response = await agentApi.get<AgentRunTrace>(`/agent/runs/${encodeURIComponent(targetRunId)}/trace`);
      setTrace(response.data);
      setRunId(targetRunId);
      setSelectedStepId(response.data.steps[0]?.step_id || "");
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Trace detail could not be loaded.");
    } finally {
      setTraceLoading(false);
    }
  };

  const createProbeRun = async () => {
    setActionLoading(true);
    setError("");
    setNotice("");
    try {
      const session = `web_obs_${Date.now()}`;
      const response = await agentApi.post<{ run_id: string }>(`/agent/sessions/${session}/plan`, {
        mode: "full_exam",
        user_id: user?.id || user?.email || "operator",
      });
      setSessionId(session);
      setRunId(response.data.run_id);
      setNotice("Probe run created.");
      await loadObservability();
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Probe run could not be created.");
    } finally {
      setActionLoading(false);
    }
  };

  const cancelRun = async () => {
    const targetRunId = trace?.run_id || runId.trim();
    if (!targetRunId) return;
    setActionLoading(true);
    setError("");
    setNotice("");
    try {
      await agentApi.post(`/agent/runs/${encodeURIComponent(targetRunId)}/cancel`);
      setNotice("Run cancelled.");
      await loadObservability();
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Run could not be cancelled.");
    } finally {
      setActionLoading(false);
    }
  };

  const selectedStep = useMemo(() => {
    if (!trace?.steps.length) return null;
    return trace.steps.find((step) => step.step_id === selectedStepId) ?? trace.steps[0];
  }, [selectedStepId, trace]);

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/admin/observability" userName={user?.display_name} userRole={user?.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">
          <SectionHeading icon={ShieldCheck} label="Access denied" labelZh="权限不足" />
          <h1 className="font-serif text-3xl text-[#0B132B]">Agent Observability</h1>
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
    <AcademicShell activePath="/admin/observability" userName={user?.display_name} userRole={user?.role}>
      <PageHeader
        eyebrow="AI Operations"
        title="Agent Observability"
        titleZh="Agent 观测"
        description="Trace, workflow events, tool calls and recovery signals."
        actions={
          <>
            <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Practice
            </Button>
            <Button type="button" variant="teal" onClick={loadObservability} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
              Refresh
            </Button>
          </>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}
      {notice && <Panel className="border-[#4F8A6B]/25 bg-[#EEF7F2] text-sm text-[#3E7056]">{notice}</Panel>}

      <Panel>
        <SectionHeading icon={Filter} label="Filters" labelZh="筛选" />
        <div className="grid gap-3 lg:grid-cols-[1fr_1fr_180px_auto_auto]">
          <InputField label="Session ID" value={sessionId} onChange={setSessionId} />
          <InputField label="Run ID" value={runId} onChange={setRunId} />
          <label className="grid gap-2 text-sm text-slate-700">
            <span className="font-medium">Mode</span>
            <select value={mode} onChange={(event) => setMode(event.target.value)} className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-[#D4AF37]">
              {modes.map((item) => (
                <option key={item || "all"} value={item}>
                  {item || "all"}
                </option>
              ))}
            </select>
          </label>
          <Button type="button" variant="soft" className="self-end" onClick={loadObservability} disabled={loading}>
            <Search className="mr-2 h-4 w-4" />
            Search
          </Button>
          <Button type="button" variant="gold" className="self-end" onClick={createProbeRun} disabled={actionLoading}>
            {actionLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Activity className="mr-2 h-4 w-4" />}
            Probe
          </Button>
        </div>
      </Panel>

      <section className="grid gap-4 md:grid-cols-4">
        <MetricCard icon={Clock3} label="P95 Latency" value={`${summary?.latency.p95_ms ?? 0}ms`} helper="agent run p95" tone="teal" />
        <MetricCard icon={Waypoints} label="Tool Success" value={formatPercent(summary?.tool_success_rate ?? 1)} helper={`${summary?.tool_call_count ?? 0} tool calls`} tone="sage" />
        <MetricCard icon={ShieldCheck} label="Structured Validity" value={formatPercent(summary?.structured_output_validity_rate ?? 1)} helper={`${summary?.structured_output_valid_count ?? 0}/${summary?.structured_output_total ?? 0} outputs`} tone="gold" />
        <MetricCard icon={Database} label="Model Cost" value={formatUsd(summary?.estimated_model_cost_usd ?? 0)} helper={`${(summary?.input_token_count ?? 0) + (summary?.output_token_count ?? 0)} est. tokens`} />
      </section>

      <section className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
        <Panel className="min-h-[520px]">
          <SectionHeading icon={Activity} label="Runs" labelZh="运行" />
          {loading ? (
            <LoadingBlock label="Loading runs..." />
          ) : summary?.recent_runs.length ? (
            <div className="grid gap-2">
              {summary.recent_runs.map((item) => (
                <button
                  key={item.run_id}
                  type="button"
                  onClick={() => loadTrace(item.run_id)}
                  className={cn(
                    "grid cursor-pointer gap-2 rounded-lg border p-3 text-left transition-colors",
                    trace?.run_id === item.run_id ? "border-[#D4AF37] bg-[#FFF8DF]" : "border-slate-200 bg-white hover:border-[#D4AF37]/50",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <StatusBadge tone={statusTone(item.status)}>{item.status}</StatusBadge>
                    <span className="text-xs text-slate-500">{item.latency_ms ?? 0}ms</span>
                  </div>
                  <span className="break-all font-mono text-xs text-slate-700">{item.run_id}</span>
                  <span className="truncate text-xs text-slate-500">{item.session_id}</span>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState icon={Activity} title="No runs" body="Create a probe run or adjust filters." />
          )}
        </Panel>

        <Panel className="min-h-[520px]">
          <SectionHeading
            icon={Waypoints}
            label="Trace Timeline"
            labelZh="调用链"
            action={
              <Button type="button" variant="soft" size="sm" onClick={cancelRun} disabled={actionLoading || !trace}>
                {actionLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Ban className="mr-2 h-4 w-4" />}
                Cancel
              </Button>
            }
          />
          {traceLoading ? (
            <LoadingBlock label="Loading trace..." />
          ) : trace ? (
            <div className="grid gap-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone={statusTone(trace.status)}>{trace.status}</StatusBadge>
                  <StatusBadge tone="teal">{trace.mode || "mode unknown"}</StatusBadge>
                  <StatusBadge tone="slate">{trace.steps.length} steps</StatusBadge>
                </div>
                <p className="mt-2 break-all font-mono text-xs text-slate-600">{trace.run_id}</p>
              </div>
              <div className="grid gap-2">
                {trace.steps.map((step) => (
                  <button
                    key={step.step_id}
                    type="button"
                    onClick={() => setSelectedStepId(step.step_id)}
                    className={cn(
                      "grid cursor-pointer gap-2 rounded-lg border p-3 text-left transition-colors",
                      selectedStep?.step_id === step.step_id ? "border-[#D4AF37] bg-[#FFF8DF]" : "border-slate-200 bg-white hover:border-[#D4AF37]/50",
                    )}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold text-slate-900">{step.workflow_node}</span>
                      <StatusBadge tone={statusTone(step.status)}>{step.status}</StatusBadge>
                    </div>
                    <div className="grid gap-2 text-xs text-slate-500 sm:grid-cols-3">
                      <span>{step.agent_name || "-"}</span>
                      <span>{step.model_name || "-"}</span>
                      <span>{step.latency_ms ?? 0}ms</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState icon={Waypoints} title="No trace selected" body="Select a run to inspect its workflow steps." />
          )}
        </Panel>

        <div className="grid gap-5">
          <Panel>
            <SectionHeading icon={AlertTriangle} label="Alerts" labelZh="告警" />
            {alerts.length ? (
              <div className="grid gap-2">
                {alerts.map((item) => (
                  <article key={item.alert_id} className="rounded-lg border border-slate-200 bg-white p-3">
                    <div className="flex items-center justify-between gap-2">
                      <StatusBadge tone={item.severity === "critical" ? "red" : "coral"}>{item.severity}</StatusBadge>
                      <span className="text-xs text-slate-500">{item.metric}</span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-700">{item.message}</p>
                    <p className="mt-2 text-xs text-slate-500">actual {item.actual} · threshold {item.threshold}</p>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState icon={AlertTriangle} title="No active alerts" body="Current filters do not produce release-blocking observability alerts." />
            )}
          </Panel>

          <Panel>
            <SectionHeading icon={Database} label="Step Detail" labelZh="节点详情" />
            {selectedStep ? (
              <div className="grid gap-3">
                <InlineKpi label="Prompt" value={selectedStep.prompt_version || "-"} />
                <InlineKpi label="Tokens" value={`${selectedStep.input_tokens ?? 0} in / ${selectedStep.output_tokens ?? 0} out`} />
                <InlineKpi label="Structured" value={selectedStep.structured_output_validity === false ? "invalid" : "valid"} />
                <InlineKpi label="Tools" value={String(selectedStep.tool_calls.length)} />
                <MonoBlock>{JSON.stringify(stepDetailPayload(selectedStep), null, 2)}</MonoBlock>
              </div>
            ) : (
              <EmptyState icon={Database} title="No step detail" body="Select a trace step to inspect payload metadata." />
            )}
          </Panel>
        </div>
      </section>
    </AcademicShell>
  );
}

function InputField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 min-w-0 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-[#D4AF37]"
      />
    </label>
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

function statusTone(status: string): "sage" | "coral" | "red" | "slate" {
  if (status === "completed") return "sage";
  if (status === "failed") return "red";
  if (status === "running") return "coral";
  return "slate";
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function formatUsd(value: number) {
  if (value <= 0) return "$0.0000";
  return `$${value.toFixed(4)}`;
}

function stepDetailPayload(step: TraceStep) {
  return {
    workflow_node: step.workflow_node,
    part: step.part,
    question_id: step.question_id,
    agent_name: step.agent_name,
    model_name: step.model_name,
    prompt_version: step.prompt_version,
    latency_ms: step.latency_ms,
    retrieved_chunks: step.retrieved_chunks ?? [],
    scoring_result: step.scoring_result,
    error_code: step.error_code,
    error_type: step.error_type,
    tool_calls: step.tool_calls,
  };
}
