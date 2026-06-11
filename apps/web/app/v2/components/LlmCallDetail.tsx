"use client";

import { Braces } from "lucide-react";

import { MonoBlock, Panel, SectionHeading } from "@/components/academic";
import { formatUsage, type OrchestratorStreamEvent } from "@/lib/orchestratorStream";

type LlmCallDetailProps = {
  events: OrchestratorStreamEvent[];
};

export function LlmCallDetail({ events }: LlmCallDetailProps) {
  const llmEvents = events.filter((event) => event.kind === "agent.thinking" || event.kind === "usage.updated" || event.kind === "agent.tool_call");

  return (
    <Panel>
      <SectionHeading icon={Braces} label="LLM / Tool Detail" labelZh="LLM 调用详情" />
      <div className="space-y-3">
        {llmEvents.length === 0 ? <p className="text-sm text-slate-500">No LLM iterations captured for this run.</p> : null}
        {llmEvents.map((event) => (
          <div key={event.event_id || `${event.seq}:${event.kind}`} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="flex items-center justify-between gap-2 text-sm font-medium text-slate-900">
              <span>{event.kind}</span>
              <span className="text-xs text-slate-500">{event.phase || "orchestrator"}</span>
            </div>
            {event.reasoning_delta || event.content_delta ? (
              <p className="mt-2 text-sm leading-6 text-slate-700">{event.reasoning_delta || event.content_delta}</p>
            ) : null}
            {event.usage ? <p className="mt-2 text-xs text-slate-500">{formatUsage(event.usage)}</p> : null}
            {Object.keys(event.payload).length > 0 ? (
              <MonoBlock className="mt-2 max-h-40 overflow-auto text-xs">{JSON.stringify(event.payload, null, 2)}</MonoBlock>
            ) : null}
          </div>
        ))}
      </div>
    </Panel>
  );
}
