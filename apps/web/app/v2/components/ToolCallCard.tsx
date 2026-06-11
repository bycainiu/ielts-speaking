"use client";

import { Wrench } from "lucide-react";

import { MonoBlock, StatusBadge } from "@/components/academic";
import { formatPayload, summarizeReadablePayload } from "@/lib/traceReadable";
import { readableOrchestratorPayload, type OrchestratorStreamEvent } from "@/lib/orchestratorStream";

type ToolCallCardProps = {
  event: OrchestratorStreamEvent;
};

export function ToolCallCard({ event }: ToolCallCardProps) {
  const payload = event.payload;
  const status = typeof payload.status === "string" ? payload.status : event.kind === "agent.tool_result" ? "completed" : "running";
  const latency = typeof payload.latency_ms === "number" ? `${payload.latency_ms} ms` : null;
  const detail = summarizeReadablePayload(null, payload.arguments ?? payload.tool_arguments ?? payload.payload, "");

  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-900">
          <Wrench className="h-4 w-4 text-slate-500" />
          {readableOrchestratorPayload(event)}
        </div>
        <StatusBadge tone={status === "completed" ? "sage" : "gold"}>{status}</StatusBadge>
      </div>
      {latency ? <p className="mt-1 text-xs text-slate-500">{latency}</p> : null}
      {detail ? <p className="mt-2 text-xs leading-5 text-slate-600">{detail}</p> : null}
      {Object.keys(payload).length > 0 ? (
        <MonoBlock className="mt-2 max-h-32 overflow-auto text-xs">{formatPayload(payload)}</MonoBlock>
      ) : null}
    </div>
  );
}
