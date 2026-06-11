"use client";

import { useMemo } from "react";
import { Clock3 } from "lucide-react";

import { Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { readableOrchestratorPayload, type OrchestratorStreamEvent } from "@/lib/orchestratorStream";

type AgentTimelineProps = {
  events: OrchestratorStreamEvent[];
};

const laneOrder = ["exam_director", "question_strategist", "live_examiner", "response_analyzer"];

export function AgentTimeline({ events }: AgentTimelineProps) {
  const lanes = useMemo(() => {
    const grouped = new Map<string, OrchestratorStreamEvent[]>();
    for (const event of events) {
      const agent = typeof event.payload.agent === "string" ? event.payload.agent : typeof event.payload.agent_name === "string" ? event.payload.agent_name : event.phase || "orchestrator";
      const items = grouped.get(agent) ?? [];
      items.push(event);
      grouped.set(agent, items);
    }
    return [...grouped.entries()].sort(([left], [right]) => laneOrder.indexOf(left) - laneOrder.indexOf(right));
  }, [events]);

  return (
    <Panel>
      <SectionHeading icon={Clock3} label="Agent Timeline" labelZh="泳道时间线" />
      <div className="space-y-4">
        {lanes.length === 0 ? <p className="text-sm text-slate-500">No orchestrator events yet.</p> : null}
        {lanes.map(([agent, laneEvents]) => (
          <div key={agent} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-slate-900">{agent}</p>
              <StatusBadge tone="teal">{laneEvents.length} events</StatusBadge>
            </div>
            <div className="space-y-2">
              {laneEvents.map((event) => (
                <div key={event.event_id || `${event.seq}:${event.kind}`} className="rounded-md border border-white bg-white px-3 py-2 text-sm text-slate-700">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{event.kind}</span>
                    <span className="text-xs text-slate-400">#{event.seq}</span>
                  </div>
                  <p className="mt-1 text-xs leading-5 text-slate-500">{readableOrchestratorPayload(event)}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
