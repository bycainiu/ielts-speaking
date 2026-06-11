import {
  type AgentStreamEvent,
  type AgentStreamEventKind,
  formatUsage,
} from "./agentStream";

export type OrchestratorAgentMessage = {
  message_id: string;
  source_agent: string;
  target_agent: string;
  message_type: string;
  payload?: Record<string, unknown>;
  reply_to?: string | null;
  created_at?: string;
};

export type OrchestratorToolIteration = {
  agent_name: string;
  iteration: number;
  phase?: string | null;
  llm_request_messages?: Array<Record<string, unknown>> | null;
  llm_response_content?: string | null;
  llm_reasoning_text?: string | null;
  llm_tool_calls?: Array<Record<string, unknown>> | null;
  tool_name?: string | null;
  tool_arguments?: Record<string, unknown> | null;
  tool_result?: Record<string, unknown> | null;
  tool_status?: string | null;
  model_name?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  latency_ms?: number | null;
  created_at?: string;
};

export type OrchestratorTraceItemKind =
  | "stream"
  | "agent_message"
  | "tool_iteration"
  | "llm_messages"
  | "route";

export type OrchestratorTraceItem = {
  id: string;
  order: number;
  kind: OrchestratorTraceItemKind;
  title: string;
  subtitle?: string;
  agent?: string;
  targetAgent?: string;
  eventKind?: AgentStreamEventKind | string;
  reasoningText?: string;
  assistantText?: string;
  userText?: string;
  toolName?: string;
  toolArguments?: unknown;
  toolResult?: unknown;
  route?: string;
  payload?: Record<string, unknown>;
  usage?: string;
  createdAt?: string;
};

const streamKindLabels: Partial<Record<AgentStreamEventKind, string>> = {
  "run.started": "Run started",
  "run.completed": "Run completed",
  "run.failed": "Run failed",
  "agent.activated": "Agent activated",
  "agent.deactivated": "Agent deactivated",
  "agent.message_sent": "Agent message sent",
  "agent.message_received": "Agent message received",
  "agent.thinking": "Agent reasoning",
  "reasoning.delta": "Reasoning delta",
  "agent.tool_call": "Tool call",
  "agent.tool_result": "Tool result",
  "tool.started": "Tool started",
  "tool.completed": "Tool completed",
  "director.route_change": "Director route",
  "usage.updated": "Token usage",
};

export function buildOrchestratorTraceTimeline(
  events: AgentStreamEvent[],
  messages: OrchestratorAgentMessage[],
  toolIterations: OrchestratorToolIteration[],
): OrchestratorTraceItem[] {
  const items: OrchestratorTraceItem[] = [];
  let order = 0;

  for (const event of events.filter((item) => item.kind !== "heartbeat")) {
    items.push(streamEventToTraceItem(event, order));
    order += 1;
  }

  for (const message of messages) {
    items.push(agentMessageToTraceItem(message, order));
    order += 1;
  }

  for (const iteration of toolIterations) {
    items.push(toolIterationToTraceItem(iteration, order));
    order += 1;
    const llmMessages = iteration.llm_request_messages ?? [];
    if (llmMessages.length > 0) {
      items.push({
        id: `llm-messages-${iteration.agent_name}-${iteration.iteration}-${order}`,
        order,
        kind: "llm_messages",
        title: "LLM request messages",
        subtitle: `${iteration.agent_name} · iteration ${iteration.iteration}`,
        agent: iteration.agent_name,
        payload: { messages: llmMessages },
        reasoningText: iteration.llm_reasoning_text ?? undefined,
        assistantText: iteration.llm_response_content ?? undefined,
        createdAt: iteration.created_at,
      });
      order += 1;
    }
  }

  return items.sort(compareTraceItems);
}

export function labelStreamKind(kind: AgentStreamEventKind | string) {
  return streamKindLabels[kind as AgentStreamEventKind] ?? kind;
}

export function extractTraceAgent(item: OrchestratorTraceItem) {
  return item.agent || item.subtitle?.split("·")[0]?.trim() || "orchestrator";
}

function streamEventToTraceItem(event: AgentStreamEvent, order: number): OrchestratorTraceItem {
  const payload = event.payload;
  const agent =
    (typeof payload.agent === "string" && payload.agent) ||
    (typeof payload.agent_name === "string" && payload.agent_name) ||
    event.phase ||
    undefined;
  const target = typeof payload.target === "string" ? payload.target : undefined;
  const route = typeof payload.route === "string" ? payload.route : undefined;
  const toolName =
    (typeof payload.tool === "string" && payload.tool) ||
    (typeof payload.tool_name === "string" && payload.tool_name) ||
    undefined;

  return {
    id: event.event_id || `stream-${event.seq}-${event.kind}`,
    order,
    kind: event.kind === "director.route_change" ? "route" : "stream",
    title: labelStreamKind(event.kind),
    subtitle: [agent, target].filter(Boolean).join(" → ") || event.phase || undefined,
    agent,
    targetAgent: target,
    eventKind: event.kind,
    route,
    reasoningText: event.reasoning_delta || readString(payload, "reasoning") || readString(payload, "reasoning_text"),
    assistantText: event.content_delta || readString(payload, "content") || readString(payload, "text"),
    userText: readString(payload, "user_message") || readString(payload, "asr_text"),
    toolName,
    toolArguments: payload.arguments ?? payload.tool_arguments ?? payload.payload,
    toolResult: payload.result ?? payload.tool_result,
    payload,
    usage: event.usage ? formatUsage(event.usage) : undefined,
    createdAt: event.created_at,
  };
}

function agentMessageToTraceItem(message: OrchestratorAgentMessage, order: number): OrchestratorTraceItem {
  const payload = message.payload ?? {};
  return {
    id: `message-${message.message_id}`,
    order,
    kind: "agent_message",
    title: message.message_type,
    subtitle: `${message.source_agent} → ${message.target_agent}`,
    agent: message.source_agent,
    targetAgent: message.target_agent,
    userText: readString(payload, "asr_text") || readString(payload, "user_message"),
    assistantText: readString(payload, "text") || readString(payload, "followup_text"),
    toolArguments: payload,
    payload,
    createdAt: message.created_at,
  };
}

function toolIterationToTraceItem(iteration: OrchestratorToolIteration, order: number): OrchestratorTraceItem {
  return {
    id: `tool-${iteration.agent_name}-${iteration.iteration}-${order}`,
    order,
    kind: "tool_iteration",
    title: iteration.tool_name ? `Tool · ${iteration.tool_name}` : "LLM iteration",
    subtitle: `${iteration.agent_name} · iteration ${iteration.iteration}`,
    agent: iteration.agent_name,
    reasoningText: iteration.llm_reasoning_text ?? undefined,
    assistantText: iteration.llm_response_content ?? undefined,
    toolName: iteration.tool_name ?? undefined,
    toolArguments: iteration.tool_arguments ?? iteration.llm_tool_calls ?? undefined,
    toolResult: iteration.tool_result ?? undefined,
    payload: {
      phase: iteration.phase,
      tool_status: iteration.tool_status,
      model_name: iteration.model_name,
      latency_ms: iteration.latency_ms,
      input_tokens: iteration.input_tokens,
      output_tokens: iteration.output_tokens,
    },
    usage:
      iteration.input_tokens != null || iteration.output_tokens != null
        ? `${iteration.input_tokens ?? 0} in / ${iteration.output_tokens ?? 0} out`
        : undefined,
    createdAt: iteration.created_at,
  };
}

function compareTraceItems(left: OrchestratorTraceItem, right: OrchestratorTraceItem) {
  const leftTime = Date.parse(left.createdAt ?? "") || left.order;
  const rightTime = Date.parse(right.createdAt ?? "") || right.order;
  if (leftTime !== rightTime) return leftTime - rightTime;
  return left.order - right.order;
}

function readString(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : undefined;
}

export function isDetailRichTraceItem(item: OrchestratorTraceItem) {
  return Boolean(
    item.reasoningText ||
      item.assistantText ||
      item.userText ||
      item.toolName ||
      item.toolArguments ||
      item.toolResult ||
      (item.payload && Object.keys(item.payload).length > 0),
  );
}

export function isToolRelatedStreamKind(kind?: string) {
  if (!kind) return false;
  return kind === "agent.tool_call" || kind === "agent.tool_result" || kind === "tool.completed" || kind === "tool.started";
}
