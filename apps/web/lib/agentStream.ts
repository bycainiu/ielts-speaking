export type AgentStreamEventKind =
  | "run.started"
  | "step.started"
  | "message.delta"
  | "reasoning.delta"
  | "tool.started"
  | "tool.delta"
  | "tool.completed"
  | "markdown.delta"
  | "question.requested"
  | "usage.updated"
  | "step.completed"
  | "run.completed"
  | "run.failed"
  | "run.cancelled"
  | "heartbeat"
  | "agent.activated"
  | "agent.thinking"
  | "agent.action"
  | "agent.tool_call"
  | "agent.tool_result"
  | "agent.message_sent"
  | "agent.message_received"
  | "agent.output"
  | "agent.deactivated"
  | "director.route_change"
  | "director.constraint_check";

export type AgentStreamVisibility = "default" | "admin" | "reasoning" | "hidden";

export type AgentUsageDetail = {
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  cache_creation_input_tokens?: number | null;
  cache_read_input_tokens?: number | null;
  estimated_cost_usd?: number | null;
};

export type AgentStreamEvent = {
  seq: number;
  event_id: string;
  run_id: string;
  session_id: string;
  step_id?: string | null;
  parent_id?: string | null;
  kind: AgentStreamEventKind;
  phase?: string | null;
  role?: string | null;
  content_delta?: string | null;
  reasoning_delta?: string | null;
  payload: Record<string, unknown>;
  usage?: AgentUsageDetail | null;
  visibility: AgentStreamVisibility;
  created_at: string;
};

export type AgentStreamStatus = "idle" | "loading" | "streaming" | "reconnecting" | "completed" | "failed";

export function mergeAgentStreamEvents(current: AgentStreamEvent[], incoming: AgentStreamEvent[]) {
  const byKey = new Map<string, AgentStreamEvent>();
  for (const event of current) {
    byKey.set(eventKey(event), event);
  }
  for (const event of incoming) {
    byKey.set(eventKey(event), event);
  }
  return Array.from(byKey.values()).sort((left, right) => left.seq - right.seq || left.created_at.localeCompare(right.created_at));
}

export function latestAgentStreamSeq(events: AgentStreamEvent[]) {
  return events.reduce((max, event) => Math.max(max, event.seq), 0);
}

export function isTerminalAgentStreamKind(kind: AgentStreamEventKind) {
  return kind === "run.completed" || kind === "run.failed" || kind === "run.cancelled";
}

export function parseSseBuffer(buffer: string) {
  const frames = buffer.split(/\r?\n\r?\n/);
  const remainder = frames.pop() ?? "";
  const events = frames.map(parseSseFrame).filter((event): event is AgentStreamEvent => Boolean(event));
  return { events, remainder };
}

export function summarizeStreamEvent(event: AgentStreamEvent) {
  if (event.kind === "message.delta") return event.content_delta || readablePayloadValue(event.payload, "text") || "Message update";
  if (event.kind === "reasoning.delta") return event.reasoning_delta || readablePayloadValue(event.payload, "reason") || "Reasoning update";
  if (event.kind === "question.requested") return readablePayloadValue(event.payload, "text") || "Question requested";
  if (event.kind === "tool.completed") return `${readablePayloadValue(event.payload, "tool_name") || "tool"} completed`;
  if (event.kind === "usage.updated") return formatUsage(event.usage);
  if (event.kind === "markdown.delta") return event.content_delta || event.phase || "Markdown update";
  return event.phase || event.kind;
}

export function formatUsage(usage?: AgentUsageDetail | null) {
  if (!usage) return "No usage";
  const total = usage.total_tokens ?? (usage.input_tokens ?? 0) + (usage.output_tokens ?? 0);
  const cacheRead = usage.cache_read_input_tokens ?? 0;
  const cacheCreate = usage.cache_creation_input_tokens ?? 0;
  return `${formatToken(total)} tokens · cache read ${formatToken(cacheRead)} · cache create ${formatToken(cacheCreate)}`;
}

function parseSseFrame(frame: string): AgentStreamEvent | null {
  const dataLines: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (!dataLines.length) return null;
  try {
    return JSON.parse(dataLines.join("\n")) as AgentStreamEvent;
  } catch {
    return null;
  }
}

function eventKey(event: AgentStreamEvent) {
  return event.event_id || `${event.run_id}:${event.seq}:${event.kind}`;
}

function readablePayloadValue(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

function formatToken(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(value);
}
