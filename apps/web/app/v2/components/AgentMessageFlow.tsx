"use client";

import { ArrowRightLeft } from "lucide-react";

import { Panel, SectionHeading } from "@/components/academic";

type AgentMessageRecord = {
  message_id: string;
  source_agent: string;
  target_agent: string;
  message_type: string;
  created_at?: string;
};

type AgentMessageFlowProps = {
  messages: AgentMessageRecord[];
};

export function AgentMessageFlow({ messages }: AgentMessageFlowProps) {
  return (
    <Panel>
      <SectionHeading icon={ArrowRightLeft} label="Agent Messages" labelZh="Agent 通信" />
      <div className="space-y-2">
        {messages.length === 0 ? <p className="text-sm text-slate-500">No inter-agent messages recorded.</p> : null}
        {messages.map((message) => (
          <div key={message.message_id} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
            <div className="flex flex-wrap items-center gap-2 text-slate-900">
              <span className="font-medium">{message.source_agent}</span>
              <span className="text-slate-400">→</span>
              <span className="font-medium">{message.target_agent}</span>
            </div>
            <p className="mt-1 text-xs text-slate-500">{message.message_type}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}
