"use client";

import { useMemo, useState } from "react";
import { BrainCircuit, ChevronDown, ChevronUp, Loader2, Radio } from "lucide-react";

import { Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { OrchestratorRunTimeline } from "@/app/v2/components/OrchestratorRunTimeline";
import { Button } from "@/components/ui/button";
import {
  collectReasoningText,
  isOrchestratorToolKind,
  type AgentStreamStatus,
  type OrchestratorStreamEvent,
} from "@/lib/orchestratorStream";
import { cn } from "@/lib/utils";

import { ToolCallCard } from "./ToolCallCard";

type AgentThinkingPanelProps = {
  events: OrchestratorStreamEvent[];
  status: AgentStreamStatus;
  error?: string;
  onReconnect?: () => void;
  className?: string;
};

export function AgentThinkingPanel({ events, status, error, onReconnect, className }: AgentThinkingPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const visibleEvents = useMemo(() => events.filter((event) => event.kind !== "heartbeat"), [events]);
  const reasoningText = useMemo(() => collectReasoningText(visibleEvents), [visibleEvents]);
  const toolEvents = useMemo(() => visibleEvents.filter((event) => isOrchestratorToolKind(event.kind)), [visibleEvents]);
  const routeEvents = useMemo(() => visibleEvents.filter((event) => event.kind === "director.route_change"), [visibleEvents]);
  const messageEvents = useMemo(
    () => visibleEvents.filter((event) => event.kind === "agent.message_sent" || event.kind === "agent.message_received"),
    [visibleEvents],
  );

  return (
    <Panel className={cn("border-slate-200 bg-white/95", className)}>
      <div className="flex items-start justify-between gap-3">
        <SectionHeading icon={BrainCircuit} label="Agent Orchestration" labelZh="多 Agent 编排" />
        <div className="flex items-center gap-2">
          <StatusBadge tone={status === "streaming" ? "sage" : status === "failed" ? "coral" : "slate"}>
            {status === "loading" || status === "reconnecting" ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Radio className="mr-1 h-3 w-3" />}
            {status}
          </StatusBadge>
          <Button type="button" variant="ghost" size="icon" onClick={() => setExpanded((value) => !value)} aria-label={expanded ? "Collapse panel" : "Expand panel"}>
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="mt-4 space-y-4">
          {error ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
              {onReconnect ? (
                <Button type="button" variant="link" className="ml-2 h-auto p-0 text-rose-700" onClick={onReconnect}>
                  Reconnect
                </Button>
              ) : null}
            </div>
          ) : null}

          {routeEvents.length > 0 ? (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Routing</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {routeEvents.map((event) => {
                  const target = typeof event.payload.target === "string" ? event.payload.target : "next";
                  const route = typeof event.payload.route === "string" ? event.payload.route : event.kind;
                  return (
                    <StatusBadge key={event.event_id || `${event.seq}:${event.kind}`} tone="teal">
                      {target}:{route}
                    </StatusBadge>
                  );
                })}
              </div>
            </div>
          ) : null}

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Reasoning</p>
            <div className="mt-2 max-h-40 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-700">
              {reasoningText || "Waiting for agent reasoning..."}
            </div>
          </div>

          {toolEvents.length > 0 ? (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Tool Calls</p>
              {toolEvents.map((event) => (
                <ToolCallCard key={event.event_id || `${event.seq}:${event.kind}`} event={event} />
              ))}
            </div>
          ) : null}

          {visibleEvents.length > 0 ? (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Event Trace</p>
              <OrchestratorRunTimeline
                events={visibleEvents}
                messages={messageEvents.map((event) => messageEventToRecord(event))}
                toolIterations={[]}
                compact
                hideHeader
                className="mt-2"
              />
            </div>
          ) : null}
        </div>
      )}
    </Panel>
  );
}

function messageEventToRecord(event: OrchestratorStreamEvent) {
  const payload = event.payload;
  const nestedPayload =
    payload.payload && typeof payload.payload === "object" && !Array.isArray(payload.payload)
      ? (payload.payload as Record<string, unknown>)
      : payload;
  return {
    message_id: typeof payload.message_id === "string" ? payload.message_id : event.event_id,
    source_agent:
      (typeof payload.agent === "string" && payload.agent) ||
      (typeof payload.source === "string" && payload.source) ||
      event.phase ||
      "orchestrator",
    target_agent: typeof payload.target === "string" ? payload.target : "exam_director",
    message_type: typeof payload.type === "string" ? payload.type : event.kind,
    payload: nestedPayload,
    created_at: event.created_at,
  };
}
