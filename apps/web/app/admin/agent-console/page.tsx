"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import {
  ArrowLeft,
  Bot,
  Braces,
  BrainCircuit,
  Clock3,
  Database,
  Loader2,
  Radio,
  RefreshCcw,
  ScrollText,
  Search,
  ShieldCheck,
  TerminalSquare,
  Wrench,
} from "lucide-react";

import { AcademicShell, DetailDialog, EmptyState, InlineKpi, MonoBlock, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { useAgentRunStream } from "@/hooks/useAgentRunStream";
import { agentApi } from "@/lib/api";
import { type AgentStreamEvent, formatUsage, summarizeStreamEvent } from "@/lib/agentStream";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";

type TraceStatus = "running" | "completed" | "failed" | "cancelled";

type AgentRun = {
  run_id: string;
  session_id: string;
  user_id_hash?: string | null;
  mode?: string | null;
  part?: number | null;
  question_id?: string | null;
  status: TraceStatus;
  latency_ms?: number | null;
  step_count: number;
  llm_call_count: number;
  tool_call_count: number;
  error_code?: string | null;
  started_at: string;
  finished_at?: string | null;
};

type PayloadViewerState = {
  title: string;
  payload: unknown;
};

const statusFilters = ["", "running", "completed", "failed", "cancelled"] as const;

export default function AgentConsolePage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [statusFilter, setStatusFilter] = useState<(typeof statusFilters)[number]>("running");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payloadViewer, setPayloadViewer] = useState<PayloadViewerState | null>(null);

  const canAdmin = user?.role === "operator" || user?.role === "admin";
  const stream = useAgentRunStream(selectedRunId, { enabled: Boolean(selectedRunId && canAdmin) });
  const selectedRun = useMemo(() => runs.find((run) => run.run_id === selectedRunId) ?? null, [runs, selectedRunId]);
  const visibleEvents = useMemo(() => stream.events.filter((event) => event.kind !== "heartbeat"), [stream.events]);
  const latestUsage = useMemo(() => [...visibleEvents].reverse().find((event) => event.usage)?.usage ?? null, [visibleEvents]);
  const reasoningEvents = useMemo(() => visibleEvents.filter((event) => event.kind === "reasoning.delta"), [visibleEvents]);

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

  const loadRuns = useCallback(async () => {
    if (!hasHydrated || !isAuthenticated || !canAdmin) return;
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = { limit: "100" };
      if (statusFilter) params.status = statusFilter;
      const response = await agentApi.get<AgentRun[]>("/agent/runs", { params });
      const nextRuns = response.data ?? [];
      setRuns(nextRuns);
      setSelectedRunId((current) => current || nextRuns[0]?.run_id || "");
    } catch {
      setError("Failed to load agent runs.");
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, [canAdmin, hasHydrated, isAuthenticated, statusFilter]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/admin/agent-console" userName={user?.display_name} userRole={user?.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">
          <SectionHeading icon={ShieldCheck} label="Access denied" labelZh="权限不足" />
          <h1 className="font-serif text-3xl text-academic-navy">Agent Console</h1>
          <p className="mt-2 text-sm leading-6">This console is only available to operator / admin roles.</p>
          <Button type="button" variant="soft" className="mt-5" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to practice
          </Button>
        </Panel>
      </AcademicShell>
    );
  }

  return (
    <AcademicShell activePath="/admin/agent-console" userName={user?.display_name} userRole={user?.role} wide>
      <PageHeader
        eyebrow="AI Operations"
        title="Agent Console"
        titleZh="Agent 控制台"
        description="Select any agent run to inspect messages, reasoning, tool calls, markdown, usage, and terminal events in real time."
        actions={
          <>
            <Button type="button" variant="soft" onClick={() => router.push("/admin/observability")}>
              <ScrollText className="mr-2 h-4 w-4" />
              Observability
            </Button>
            <Button type="button" variant="teal" onClick={loadRuns} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
              Refresh
            </Button>
          </>
        }
      />

      {error ? <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel> : null}
      {stream.error ? <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{stream.error}</Panel> : null}

      <section className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)_340px]">
        <Panel className="min-h-[720px] overflow-hidden">
          <SectionHeading icon={Search} label="Runs" labelZh="运行列表" />
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
              <LoadingBlock />
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
                    <StatusBadge tone={statusTone(run.status)}>{run.status}</StatusBadge>
                    <span className="font-mono text-[11px] text-slate-400">{formatTime(run.started_at)}</span>
                  </div>
                  <p className="mt-2 break-all font-mono text-xs font-semibold text-slate-800">{run.run_id}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <StatusBadge tone="teal">{run.mode || "mode"}</StatusBadge>
                    <StatusBadge tone="blue">{run.step_count} steps</StatusBadge>
                    <StatusBadge tone="slate">{run.tool_call_count} tools</StatusBadge>
                  </div>
                </button>
              ))
            ) : (
              <EmptyState icon={TerminalSquare} title="No runs" body="No agent runs match the current filter." />
            )}
          </div>
        </Panel>

        <Panel className="min-h-[720px] overflow-hidden p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge tone={stream.status === "streaming" ? "sage" : stream.status === "failed" ? "red" : "slate"}>
                  <Radio className="mr-1 h-3 w-3" />
                  {stream.status}
                </StatusBadge>
                {selectedRun ? <StatusBadge tone={statusTone(selectedRun.status)}>{selectedRun.status}</StatusBadge> : null}
              </div>
              <h2 className="mt-2 break-all font-mono text-sm font-semibold text-academic-navy">{selectedRunId || "No run selected"}</h2>
            </div>
            <Button type="button" variant="soft" size="sm" onClick={stream.reconnect} disabled={!selectedRunId}>
              <RefreshCcw className="mr-2 h-4 w-4" />
              Reconnect
            </Button>
          </div>

          <div className="max-h-[calc(100vh-13rem)] overflow-y-auto px-5 py-5">
            {selectedRunId ? (
              visibleEvents.length ? (
                <div className="grid gap-3">
                  {visibleEvents.map((event) => (
                    <TimelineEventCard key={event.event_id} event={event} onPayloadOpen={(payload) => setPayloadViewer({ title: `${event.kind} #${event.seq}`, payload })} />
                  ))}
                </div>
              ) : (
                <EmptyState icon={Radio} title="Waiting for events" body="This run has no stream events yet." />
              )
            ) : (
              <EmptyState icon={TerminalSquare} title="No runs" body="No agent runs match the current filter." />
            )}
          </div>
        </Panel>

        <div className="grid gap-5">
          <Panel>
            <SectionHeading icon={Clock3} label="Run Context" labelZh="运行上下文" />
            {selectedRun ? (
              <div className="grid gap-3">
                <InlineKpi label="Session" value={shortId(selectedRun.session_id)} />
                <InlineKpi label="Mode" value={selectedRun.mode || "-"} />
                <InlineKpi label="Question" value={selectedRun.question_id || "-"} />
                <InlineKpi label="Latency" value={formatDuration(selectedRun.latency_ms)} />
              </div>
            ) : (
              <EmptyState icon={Database} title="No context" body="Select a run to view session, question, and latency." />
            )}
          </Panel>

          <Panel>
            <SectionHeading icon={BrainCircuit} label="Reasoning" labelZh="推理过程" />
            {reasoningEvents.length ? (
              <div className="grid max-h-64 gap-2 overflow-y-auto pr-1">
                {reasoningEvents.slice(-6).reverse().map((event) => (
                  <details key={event.event_id} className="rounded-lg border border-academic-score/25 bg-academic-score-soft p-3">
                    <summary className="cursor-pointer text-sm font-semibold text-amber-800">#{event.seq} {event.phase || "reasoning"}</summary>
                    <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-5 text-slate-700">{event.reasoning_delta || "No reasoning text provided."}</p>
                  </details>
                ))}
              </div>
            ) : (
              <EmptyState icon={BrainCircuit} title="No reasoning fields" body="This workflow did not return reasoning or thinking deltas." />
            )}
          </Panel>

          <Panel>
            <SectionHeading icon={Braces} label="Usage" labelZh="用量" />
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-700">{formatUsage(latestUsage)}</div>
          </Panel>
        </div>
      </section>

      <DetailDialog
        open={Boolean(payloadViewer)}
        title={payloadViewer?.title || "Payload"}
        titleZh="载荷详情"
        onClose={() => setPayloadViewer(null)}
        className="max-w-6xl"
      >
        {payloadViewer ? <MonoBlock className="max-h-[62vh]">{formatPayload(payloadViewer.payload)}</MonoBlock> : null}
      </DetailDialog>
    </AcademicShell>
  );
}

function TimelineEventCard({ event, onPayloadOpen }: { event: AgentStreamEvent; onPayloadOpen: (payload: unknown) => void }) {
  const Icon = iconForKind(event.kind);
  return (
    <article className={cn("rounded-lg border bg-white p-4 shadow-sm", event.kind === "reasoning.delta" && "border-academic-score/35 bg-academic-score-soft", event.kind.includes("tool") && "border-academic-accent/25 bg-academic-accent-soft")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 rounded-md border border-slate-200 bg-white p-2 text-academic-accent">
            <Icon className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone={event.kind === "reasoning.delta" ? "gold" : event.kind.includes("tool") ? "teal" : "slate"}>{event.kind}</StatusBadge>
              {event.visibility !== "default" ? <StatusBadge tone="blue">{event.visibility}</StatusBadge> : null}
              <span className="font-mono text-[11px] text-slate-400">#{event.seq}</span>
            </div>
            <p className="mt-2 text-xs text-slate-500">{formatTime(event.created_at)} ? |  {event.phase || "phase"}</p>
          </div>
        </div>
        <Button type="button" variant="soft" size="sm" onClick={() => onPayloadOpen(event.payload)}>
          Payload
        </Button>
      </div>
      <div className="mt-3">
        {event.kind === "markdown.delta" ? (
          <MarkdownRenderer content={event.content_delta || summarizeStreamEvent(event)} />
        ) : event.kind === "reasoning.delta" ? (
          <ReasoningBlock event={event} />
        ) : event.kind.includes("tool") ? (
          <ToolCallBlock event={event} />
        ) : event.kind === "usage.updated" ? (
          <UsageBlock event={event} />
        ) : (
          <p className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{summarizeStreamEvent(event)}</p>
        )}
      </div>
    </article>
  );
}

function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none text-slate-700 prose-pre:bg-slate-950 prose-pre:text-slate-100">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

function ReasoningBlock({ event }: { event: AgentStreamEvent }) {
  return (
    <details className="rounded-lg border border-academic-score/25 bg-white/70 p-3" open={false}>
      <summary className="cursor-pointer text-sm font-semibold text-amber-800">Reasoning delta</summary>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{event.reasoning_delta || "No reasoning text provided."}</p>
    </details>
  );
}

function ToolCallBlock({ event }: { event: AgentStreamEvent }) {
  return (
    <div className="rounded-lg border border-academic-accent/20 bg-white/80 p-3">
      <div className="flex flex-wrap gap-2">
        <StatusBadge tone="teal">{String(event.payload.tool_name || event.phase || "tool")}</StatusBadge>
        {event.payload.status ? <StatusBadge tone={event.payload.status === "failed" ? "red" : "sage"}>{String(event.payload.status)}</StatusBadge> : null}
        {event.payload.latency_ms ? <StatusBadge tone="gold">{String(event.payload.latency_ms)}ms</StatusBadge> : null}
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-700">{summarizeStreamEvent(event)}</p>
    </div>
  );
}

function UsageBlock({ event }: { event: AgentStreamEvent }) {
  return <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-700">{formatUsage(event.usage)}</div>;
}

function LoadingBlock() {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
      <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
      Loading...
    </div>
  );
}

function iconForKind(kind: string) {
  if (kind.includes("tool")) return Wrench;
  if (kind === "reasoning.delta") return BrainCircuit;
  if (kind === "usage.updated") return Database;
  if (kind === "message.delta" || kind === "question.requested") return Bot;
  return TerminalSquare;
}

function statusTone(status: string) {
  if (status === "running") return "coral";
  if (status === "completed") return "sage";
  if (status === "failed") return "red";
  if (status === "cancelled") return "slate";
  return "slate";
}

function shortId(value?: string | null) {
  if (!value) return "-";
  return value.length <= 12 ? value : `${value.slice(0, 6)}...${value.slice(-4)}`;
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatDuration(value?: number | null) {
  if (value == null) return "-";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${value}ms`;
}

function formatPayload(payload: unknown) {
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}
