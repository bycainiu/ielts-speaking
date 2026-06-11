"use client";

import { useMemo, useState } from "react";
import { Braces, ChevronDown, ChevronUp, GitBranch, MessageSquareText } from "lucide-react";

import { MonoBlock, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { formatPayload, summarizeReadablePayload } from "@/lib/traceReadable";
import {
  buildOrchestratorTraceTimeline,
  extractTraceAgent,
  isDetailRichTraceItem,
  labelStreamKind,
  type OrchestratorAgentMessage,
  type OrchestratorToolIteration,
  type OrchestratorTraceItem,
} from "@/lib/orchestratorTrace";
import { type OrchestratorStreamEvent } from "@/lib/orchestratorStream";
import { cn } from "@/lib/utils";

type OrchestratorRunTimelineProps = {
  events: OrchestratorStreamEvent[];
  messages: OrchestratorAgentMessage[];
  toolIterations: OrchestratorToolIteration[];
  compact?: boolean;
  hideHeader?: boolean;
  className?: string;
};

export function OrchestratorRunTimeline({
  events,
  messages,
  toolIterations,
  compact = false,
  hideHeader = false,
  className,
}: OrchestratorRunTimelineProps) {
  const timeline = useMemo(
    () => buildOrchestratorTraceTimeline(events, messages, toolIterations),
    [events, messages, toolIterations],
  );

  const content = (
    <div className="space-y-3">
      {timeline.length === 0 ? (
        <p className="text-sm text-slate-500">No orchestrator trace items yet.</p>
      ) : (
        timeline.map((item, index) => <TraceItemCard key={item.id} item={item} index={index + 1} compact={compact} />)
      )}
    </div>
  );

  if (hideHeader) {
    return <div className={className}>{content}</div>;
  }

  return (
    <Panel className={className}>
      <SectionHeading icon={GitBranch} label="Unified Trace" labelZh="统一时序 Trace" />
      {content}
    </Panel>
  );
}

function TraceItemCard({ item, index, compact }: { item: OrchestratorTraceItem; index: number; compact: boolean }) {
  const [expanded, setExpanded] = useState(!compact && index <= 3);
  const agent = extractTraceAgent(item);
  const rich = isDetailRichTraceItem(item);

  return (
    <article className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        className="flex w-full items-start justify-between gap-3 px-3 py-3 text-left"
        onClick={() => setExpanded((value) => !value)}
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[11px] text-slate-400">#{index}</span>
            <StatusBadge tone={toneForKind(item.kind)}>{item.kind}</StatusBadge>
            <span className="text-sm font-semibold text-slate-900">{item.title}</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {[agent, item.subtitle].filter(Boolean).join(" · ")}
            {item.route ? ` · route=${item.route}` : ""}
          </p>
          {!expanded && rich ? (
            <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-600">
              {previewText(item)}
            </p>
          ) : null}
        </div>
        {expanded ? <ChevronUp className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /> : <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />}
      </button>

      {expanded ? (
        <div className="space-y-3 border-t border-slate-100 px-3 py-3">
          {item.eventKind ? (
            <DetailBlock label="Event kind" value={labelStreamKind(item.eventKind)} />
          ) : null}
          {item.reasoningText ? <DetailBlock label="Reasoning" value={item.reasoningText} mono={false} /> : null}
          {item.userText ? <DetailBlock label="User message" value={item.userText} mono={false} /> : null}
          {item.assistantText ? <DetailBlock label="Assistant message" value={item.assistantText} mono={false} /> : null}
          {item.toolName ? <DetailBlock label="Tool" value={item.toolName} /> : null}
          {item.toolArguments ? (
            <JsonBlock title="Tool arguments / payload" value={item.toolArguments} />
          ) : null}
          {item.toolResult ? <JsonBlock title="Tool result" value={item.toolResult} /> : null}
          {item.usage ? <DetailBlock label="Usage" value={item.usage} /> : null}
          {item.payload && Object.keys(item.payload).length > 0 ? (
            <JsonBlock title="Raw payload" value={item.payload} />
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function DetailBlock({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={cn("mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700", mono && "font-mono text-xs")}>{value}</p>
    </div>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  const readable = summarizeReadablePayload(null, value, "");
  return (
    <div>
      <div className="mb-1 flex items-center gap-2">
        <Braces className="h-3.5 w-3.5 text-slate-500" />
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      </div>
      {readable ? <p className="mb-2 whitespace-pre-wrap break-words text-xs leading-5 text-slate-600">{readable}</p> : null}
      <MonoBlock className="max-h-56 overflow-auto text-xs">{formatPayload(value)}</MonoBlock>
    </div>
  );
}

function previewText(item: OrchestratorTraceItem) {
  return item.reasoningText || item.assistantText || item.userText || summarizeReadablePayload(null, item.toolArguments, item.title);
}

function toneForKind(kind: OrchestratorTraceItem["kind"]) {
  switch (kind) {
    case "route":
      return "gold" as const;
    case "agent_message":
      return "teal" as const;
    case "tool_iteration":
    case "llm_messages":
      return "blue" as const;
    default:
      return "slate" as const;
  }
}

export function OrchestratorRoutePath({ events }: { events: OrchestratorStreamEvent[] }) {
  const routes = useMemo(
    () =>
      events
        .filter((event) => event.kind === "director.route_change")
        .map((event) => {
          const payload = event.payload;
          const target = typeof payload.target === "string" ? payload.target : "next";
          const route = typeof payload.route === "string" ? payload.route : event.kind;
          return `${target}:${route}`;
        }),
    [events],
  );

  if (!routes.length) return null;

  return (
    <Panel>
      <SectionHeading icon={MessageSquareText} label="Director Routing" labelZh="Director 路由" />
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-700">
        <StatusBadge tone="gold">exam_director</StatusBadge>
        {routes.map((route, index) => (
          <span key={`${route}-${index}`} className="inline-flex items-center gap-2">
            <span>→</span>
            <StatusBadge tone="teal">{route}</StatusBadge>
          </span>
        ))}
      </div>
    </Panel>
  );
}
