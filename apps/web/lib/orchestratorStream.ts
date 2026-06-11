import {
  type AgentStreamEvent,
  type AgentStreamEventKind,
  type AgentStreamStatus,
  formatUsage,
  isTerminalAgentStreamKind,
  latestAgentStreamSeq,
  mergeAgentStreamEvents,
  parseSseBuffer,
  summarizeStreamEvent,
} from "@/lib/agentStream";

export type OrchestratorStreamEventKind = AgentStreamEventKind;
export type OrchestratorStreamEvent = AgentStreamEvent;

export {
  type AgentStreamStatus,
  formatUsage,
  isTerminalAgentStreamKind,
  latestAgentStreamSeq,
  mergeAgentStreamEvents,
  parseSseBuffer,
  summarizeStreamEvent,
};

export function isOrchestratorThinkingKind(kind: OrchestratorStreamEventKind) {
  return kind === "agent.thinking" || kind === "reasoning.delta";
}

export function isOrchestratorToolKind(kind: OrchestratorStreamEventKind) {
  return kind === "agent.tool_call" || kind === "agent.tool_result" || kind === "tool.completed" || kind === "tool.started";
}

export function readableOrchestratorPayload(event: OrchestratorStreamEvent) {
  const payload = event.payload;
  const agent = typeof payload.agent === "string" ? payload.agent : typeof payload.agent_name === "string" ? payload.agent_name : "";
  const tool = typeof payload.tool === "string" ? payload.tool : typeof payload.tool_name === "string" ? payload.tool_name : "";
  if (event.kind === "agent.activated") return `${agent || "agent"} activated`;
  if (event.kind === "agent.deactivated") return `${agent || "agent"} deactivated`;
  if (event.kind === "agent.tool_call") return `${agent || "agent"} → ${tool || "tool"}`;
  if (event.kind === "agent.tool_result") return `${tool || "tool"} result`;
  if (event.kind === "agent.message_sent" || event.kind === "agent.message_received") {
    const messageType = typeof payload.type === "string" ? payload.type : event.kind;
    const target = typeof payload.target === "string" ? payload.target : typeof payload.source === "string" ? payload.source : "";
    return `${messageType}${target ? ` · ${target}` : ""}`;
  }
  if (event.kind === "director.route_change") return `route → ${String(payload.route ?? payload.target ?? "next")}`;
  return summarizeStreamEvent(event);
}

export function collectReasoningText(events: OrchestratorStreamEvent[]) {
  return events
    .filter((event) => isOrchestratorThinkingKind(event.kind))
    .map((event) => event.reasoning_delta || event.content_delta || readableOrchestratorPayload(event))
    .join("");
}
