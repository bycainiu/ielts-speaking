"use client";

import {
  Bot,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Cpu,
  Database,
  Lock,
  MessageSquareText,
  ShieldCheck,
  Wrench,
  XCircle,
} from "lucide-react";

import { Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { collectPayloadHighlights, formatReadableValue, hasPayload, normalizePayload, summarizeReadablePayload } from "@/lib/traceReadable";
import {
  countTraceSemantics,
  formatCallModel,
  formatCallProvider,
  formatExecutionKind,
  formatPayloadOrigin,
  formatStepModel,
  formatTraceCallTitle,
  formatTraceTokens,
  hasCapturedLlmCalls,
  isCapturedLlmCall,
} from "@/lib/traceSemantics";
import { cn } from "@/lib/utils";

import type { AgentRunTrace, ReviewConversationItem, TraceLlmCall, TraceMessage, TraceStep, TraceToolCall } from "./types";

type AgentTone = "gold" | "teal" | "sage" | "coral" | "blue" | "slate";

const agentToneClasses: Record<
  AgentTone,
  {
    avatar: string;
    marker: string;
    rail: string;
    surface: string;
    label: string;
  }
> = {
  gold: {
    avatar: "border-academic-score/35 bg-academic-score-soft text-amber-800",
    marker: "border-academic-score bg-academic-score-soft text-amber-800",
    rail: "bg-academic-score",
    surface: "border-academic-score/30 bg-[#FFFDF6]",
    label: "text-amber-800",
  },
  teal: {
    avatar: "border-academic-accent/25 bg-academic-accent-soft text-blue-800",
    marker: "border-academic-accent bg-academic-accent-soft text-blue-800",
    rail: "bg-academic-accent",
    surface: "border-academic-accent/20 bg-[#F8FCFE]",
    label: "text-blue-800",
  },
  sage: {
    avatar: "border-emerald-600/25 bg-academic-success-soft text-emerald-800",
    marker: "border-emerald-600 bg-academic-success-soft text-emerald-800",
    rail: "bg-emerald-600",
    surface: "border-emerald-600/20 bg-[#FAFFFC]",
    label: "text-emerald-800",
  },
  coral: {
    avatar: "border-orange-500/25 bg-[#FFF0EA] text-orange-700",
    marker: "border-orange-500 bg-[#FFF0EA] text-orange-700",
    rail: "bg-orange-500",
    surface: "border-orange-500/20 bg-[#FFF9F6]",
    label: "text-orange-700",
  },
  blue: {
    avatar: "border-blue-200 bg-blue-50 text-blue-700",
    marker: "border-blue-300 bg-blue-50 text-blue-700",
    rail: "bg-blue-500",
    surface: "border-blue-200 bg-blue-50/45",
    label: "text-blue-700",
  },
  slate: {
    avatar: "border-slate-200 bg-slate-100 text-slate-700",
    marker: "border-slate-300 bg-white text-slate-700",
    rail: "bg-slate-300",
    surface: "border-slate-200 bg-white",
    label: "text-slate-700",
  },
};

export function AgentTracePanel({
  item,
  trace,
  canAdmin,
  loading = false,
}: {
  item?: ReviewConversationItem;
  trace?: AgentRunTrace | null;
  canAdmin: boolean;
  loading?: boolean;
}) {
  const steps = trace?.steps ?? [];
  const { capturedLlmCount, derivedCallCount, toolCallCount } = countTraceSemantics(steps);

  return (
    <Panel className="h-fit lg:sticky lg:top-4">
      <SectionHeading
        icon={BrainCircuit}
        label="Behind the answer"
        labelZh="后台轨迹"
        action={<StatusBadge tone="gold">Turn {(item?.turnIndex ?? 0) + 1}</StatusBadge>}
      />

      {!trace ? (
        <TraceUnavailableSummary item={item} loading={loading} canAdmin={canAdmin} />
      ) : (
        <>
          <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs font-semibold text-blue-800">Agent run path</p>
                <p className="mt-1 text-[11px] text-slate-500">
                  {steps.length} steps · {capturedLlmCount} 真实 LLM 请求 · {derivedCallCount} 派生/确定性记 · {toolCallCount} 工具调用 · {trace.status}
                </p>
              </div>
              <StatusBadge tone={trace.status === "failed" ? "red" : trace.status === "running" ? "coral" : "sage"}>Trace loaded</StatusBadge>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-slate-600">
              {pathLabels(steps).map((label, index) => (
                <span key={`${label}-${index}`} className="inline-flex items-center gap-2">
                  <span className="max-w-[150px] truncate rounded-md border border-slate-200 bg-white px-2 py-1">{label}</span>
                  {index < Math.min(pathLabels(steps).length, 7) - 1 && <span className="text-slate-300">→</span>}
                </span>
              ))}
              {steps.length === 0 && <span className="rounded-md border border-slate-200 bg-white px-2 py-1">Trace 暂无 step</span>}
            </div>
          </div>

          <div className="relative grid gap-3">
            <div className="absolute bottom-6 left-5 top-6 w-px bg-slate-200" />
            {steps.map((step, index) => (
              <TraceStepCard key={step.step_id} index={index + 1} step={step} canAdmin={canAdmin} />
            ))}
          </div>

          <div className="mt-4 rounded-lg border border-slate-200 bg-white p-3">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
              <Lock className="h-4 w-4 text-academic-accent" />
              管理员详情：脱敏输入输出
            </div>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              {canAdmin
                ? "Expand a node to inspect captured redacted inputs, outputs, messages, and tool parameters. Derived records are labeled explicitly."
                : "Learner view shows only the summary needed for review."}
            </p>
          </div>
        </>
      )}
    </Panel>
  );
}

function TraceUnavailableSummary({
  item,
  loading,
  canAdmin,
}: {
  item?: ReviewConversationItem;
  loading: boolean;
  canAdmin: boolean;
}) {
  return (
    <div className="grid gap-3">
      {loading ? (
        <p className="rounded-md bg-academic-score-soft px-3 py-2 text-xs text-amber-800">正在加载管理员 Trace...</p>
      ) : (
        <div className="rounded-lg border border-academic-score/30 bg-academic-score-soft p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-amber-800">真实调用轨迹不可用.</p>
            <StatusBadge tone="gold">No provider trace</StatusBadge>
          </div>
          <p className="mt-2 text-xs leading-5 text-[#7A6220]">
            Agent Harness 没有返回这个 run 的 trace。历史 run 可能已从内存 TraceStore 淘汰或服务重启后丢失；这里不会把复盘摘要伪装成 LLM 请求、模型消息、token、latency 或工具调用。
          </p>
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
          <MessageSquareText className="h-4 w-4 text-academic-accent" />
          当前轮次复盘摘要
        </div>
        <div className="mt-3 grid gap-2">
          <DetailLine label="Part / Turn" value={`Part ${item?.part ?? "-"} · Turn ${(item?.turnIndex ?? 0) + 1}`} />
          <DetailLine label="Question" value={truncateText(item?.questionText || "未保存题目文本", 140)} />
          <DetailLine label="Answer" value={truncateText(item?.answerText || "未保存回答文本", 140)} />
          {item?.agentRunId ? <DetailLine label="Run ID" value={item.agentRunId} /> : null}
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
          <Lock className="h-4 w-4 text-academic-accent" />
          管理员详情：真实 Trace 边界
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-500">
          {canAdmin ? "Admin details are available when expanded." : "Learner view shows review summary only."}
        </p>
      </div>
    </div>
  );
}

function TraceStepCard({ step, index, canAdmin }: { step: TraceStep; index: number; canAdmin: boolean }) {
  const tone = agentToneFor(step, index);
  const toneClass = agentToneClasses[tone];
  const title = step.agent_name || step.workflow_node;
  const llmCalls = step.llm_calls ?? [];
  const hasRealLlm = hasCapturedLlmCalls(step);

  return (
    <article className={cn("relative ml-10 rounded-lg border p-3 shadow-sm", toneClass.surface)}>
      <span
        className={cn(
          "absolute -left-10 top-4 z-10 flex h-9 w-9 items-center justify-center rounded-full border text-xs font-semibold shadow-sm",
          toneClass.marker,
        )}
      >
        {index}
      </span>

      <div className="flex min-w-0 gap-3">
        <AgentAvatar label={title} tone={tone} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="break-words text-sm font-semibold text-academic-navy">{title}</p>
              <p className="mt-1 break-all font-mono text-[11px] text-slate-500">{step.workflow_node}</p>
            </div>
            <StatusBadge tone={statusTone(step.status)}>
              {step.status === "completed" ? <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> : step.status === "failed" ? <XCircle className="mr-1 h-3.5 w-3.5" /> : null}
              {step.status}
            </StatusBadge>
          </div>

          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <TraceMeta icon={Cpu} label="kind" value={formatExecutionKind(step.execution_kind || "deterministic")} />
            <TraceMeta icon={Cpu} label="model" value={formatStepModel(step)} />
            <TraceMeta icon={BrainCircuit} label="prompt/version" value={step.prompt_version || "Unavailable"} />
            <TraceMeta icon={Clock3} label="latency" value={formatLatency(step.latency_ms)} />
            <TraceMeta label="tokens" value={formatTraceTokens(step.input_tokens, step.output_tokens, { realLlmOnly: hasRealLlm })} />
          </div>

          <MessageBlock label="Input" tone="input" value={summarizeReadablePayload(step.input_summary, step.input_payload ?? step.input_detail, payloadPreviewText(step.input_payload ?? step.input_detail) || "暂无输入摘要")} />
          <MessageBlock label="Message" tone="output" value={summarizeReadablePayload(step.output_summary, step.output_payload ?? step.scoring_result, "暂无输出摘要")} />
          <PayloadHighlights title="可读输入" payload={step.input_payload ?? step.input_detail} emptyLabel="当前未提取到更直观的输入文本" />
          <PayloadHighlights title="可读输出" payload={step.output_payload ?? step.scoring_result} emptyLabel="当前未提取到更直观的输出文本" />

          {llmCalls.length > 0 && <LlmCallList calls={llmCalls} />}
          {step.tool_calls?.length > 0 && <ToolCallList tools={step.tool_calls} canAdmin={canAdmin} />}

          {(step.retrieved_chunks?.length ?? 0) > 0 && (
            <div className="mt-3 rounded-md border border-slate-200 bg-white/80 px-3 py-2">
              <p className="inline-flex items-center gap-2 text-xs font-semibold text-slate-700">
                <Database className="h-3.5 w-3.5 text-academic-accent" />
                Sources / 来源
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {(step.retrieved_chunks ?? []).slice(0, 4).map((chunk, chunkIndex) => (
                  <StatusBadge key={chunkIndex} tone="teal">
                    {sourceLabel(chunk)}
                  </StatusBadge>
                ))}
              </div>
            </div>
          )}

          {canAdmin && (
            <details className="mt-3 rounded-md border border-slate-200 bg-white/90">
              <summary className="flex cursor-pointer items-center justify-between gap-3 px-3 py-2 text-xs font-semibold text-slate-700">
                <span className="inline-flex items-center gap-2">
                  <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
                  展开本次 Agent input
                </span>
                <span className={cn("h-1.5 w-1.5 rounded-full", toneClass.rail)} />
              </summary>
              <div className="grid gap-3 border-t border-slate-200 p-3">
                <DetailLine label="Workflow" value={step.workflow_node} />
                <DetailLine label="Part / Question" value={`Part ${step.part ?? "-"} · ${shortValue(step.question_id)}`} />
                <ReadablePayload title="Input detail" value={step.input_payload ?? step.input_detail ?? step.input_summary} />
                <TraceMessages messages={step.messages} />
                {llmCalls.length > 0 && <LlmCallList calls={llmCalls} />}
                <ReadablePayload title="Output detail" value={step.output_payload ?? step.scoring_result ?? step.output_summary} />
              </div>
            </details>
          )}
        </div>
      </div>
    </article>
  );
}

function AgentAvatar({ label, tone }: { label: string; tone: AgentTone }) {
  return (
    <span
      className={cn(
        "hidden h-10 w-10 shrink-0 items-center justify-center rounded-full border text-xs font-bold shadow-sm sm:flex",
        agentToneClasses[tone].avatar,
      )}
      title={label}
    >
      {initials(label)}
    </span>
  );
}

function TraceMeta({
  icon: Icon = MessageSquareText,
  label,
  value,
}: {
  icon?: typeof MessageSquareText;
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-2">
      <span className="flex min-w-0 items-center gap-1.5 text-[11px] font-medium uppercase text-slate-500">
        <Icon className="h-3.5 w-3.5 shrink-0 text-academic-accent" />
        <span className="truncate">{label}</span>
      </span>
      <span className="min-w-0 max-w-[60%] truncate text-right text-xs font-semibold text-slate-800" title={value}>
        {value}
      </span>
    </div>
  );
}

function MessageBlock({ label, tone, value }: { label: string; tone: "input" | "output"; value?: string | null }) {
  if (!value) return null;
  return (
    <div
      className={cn(
        "mt-3 rounded-md border px-3 py-2",
        tone === "input" ? "border-academic-accent/15 bg-white/80" : "border-emerald-600/20 bg-white",
      )}
    >
      <p className="text-[11px] font-semibold uppercase text-slate-500">{label}</p>
      <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-slate-700">{value}</p>
    </div>
  );
}

function ToolCallList({ tools, canAdmin }: { tools: TraceToolCall[]; canAdmin: boolean }) {
  return (
    <div className="mt-3 grid gap-2">
      {tools.map((tool, toolIndex) => (
        <ToolCallCard key={`${tool.tool_name}-${toolIndex}`} tool={tool} index={toolIndex + 1} canAdmin={canAdmin} />
      ))}
    </div>
  );
}

function LlmCallList({ calls }: { calls: TraceLlmCall[] }) {
  return (
    <div className="mt-3 grid gap-2">
      {calls.map((call, index) => (
        <LlmCallCard key={call.llm_call_id || `${call.call_name}-${index}`} call={call} index={index + 1} />
      ))}
    </div>
  );
}

function LlmCallCard({ call, index }: { call: TraceLlmCall; index: number }) {
  const isRealLlm = isCapturedLlmCall(call);
  const inputLabel = isRealLlm ? "请求内容摘要" : "派生输入摘要";
  const outputLabel = isRealLlm ? "模型输出摘要" : "派生输出摘要";
  const inputTitle = isRealLlm ? "请求文本片段" : "派生输入片段";
  const outputTitle = isRealLlm ? "响应文本片段" : "派生输出片段";
  return (
    <div className={cn("rounded-md border px-3 py-2", isRealLlm ? "border-academic-score/30 bg-[#FFFDF6]" : "border-slate-200 bg-white")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={cn("inline-flex min-w-0 items-center gap-2 text-xs font-semibold", isRealLlm ? "text-amber-800" : "text-slate-700")}>
          <Bot className="h-3.5 w-3.5 shrink-0" />
          <span className={cn("rounded-sm px-1.5 py-0.5 font-mono text-[10px]", isRealLlm ? "bg-[#FFF3C3] text-amber-800" : "bg-slate-100 text-slate-600")}>{index}</span>
          <span className="truncate">{formatTraceCallTitle(call)} · {call.call_name}</span>
        </span>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={call.status === "completed" ? "sage" : call.status === "failed" ? "red" : "coral"}>{call.status}</StatusBadge>
          <StatusBadge tone={isRealLlm ? "gold" : "teal"}>{formatExecutionKind(call.execution_kind || "deterministic")}</StatusBadge>
          {call.payload_origin ? <StatusBadge tone="slate">{formatPayloadOrigin(call.payload_origin)}</StatusBadge> : null}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500">
        <span>{formatCallProvider(call)}</span>
        <span>{formatCallModel(call)}</span>
        <span>latency: {formatLatency(call.latency_ms)}</span>
        <span>tokens: {formatTraceTokens(call.input_tokens, call.output_tokens, { realLlmOnly: isRealLlm })}</span>
      </div>
      <MessageBlock label={inputLabel} tone="input" value={summarizeReadablePayload(call.input_summary, call.request_payload, payloadPreviewText(call.request_payload) || "暂无输入摘要")} />
      <MessageBlock label={outputLabel} tone="output" value={summarizeReadablePayload(call.output_summary, call.response_payload, payloadPreviewText(call.response_payload) || "暂无输出摘要")} />
      <PayloadHighlights title={inputTitle} payload={call.request_payload} emptyLabel="当前未提取到输入文本" />
      <PayloadHighlights title={outputTitle} payload={call.response_payload} emptyLabel="当前未提取到输出文本" />
      <details className="mt-2 rounded-md border border-slate-200 bg-slate-50">
        <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-slate-700">{isRealLlm ? "完整脱敏 LLM 请求/响应" : "完整脱敏派生记录"}</summary>
        <div className="grid gap-2 border-t border-slate-200 p-3">
          <ReadablePayload title={isRealLlm ? "Request / 请求" : "Derived Input / 派生输入"} value={call.request_payload} emptyLabel="当前未保存输入内容" />
          <ReadablePayload title={isRealLlm ? "Response / 响应" : "Derived Output / 派生输出"} value={call.response_payload} emptyLabel="当前未保存输出内容" />
        </div>
      </details>
    </div>
  );
}

function ToolCallCard({ tool, index, canAdmin }: { tool: TraceToolCall; index: number; canAdmin: boolean }) {
  const status = tool.status === "completed" ? "sage" : "red";
  const toolInput = toolInputValue(tool);
  const toolOutput = toolOutputValue(tool);

  return (
    <div className="rounded-md border border-academic-accent/20 bg-white px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex min-w-0 items-center gap-2 text-xs font-semibold text-blue-800">
          <Wrench className="h-3.5 w-3.5 shrink-0" />
          <span className="rounded-sm bg-academic-accent-soft px-1.5 py-0.5 font-mono text-[10px] text-blue-800">{index}</span>
          <span className="truncate">{tool.tool_name}</span>
        </span>
        <StatusBadge tone={status}>{tool.status}</StatusBadge>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500">
        <span>scope: {tool.scope || "Unavailable"}</span>
        <span>latency: {formatLatency(tool.latency_ms)}</span>
        {tool.error_code && <span className="text-red-600">error: {tool.error_code}</span>}
      </div>
      <PayloadHighlights title="工具参数片段" payload={toolInput} emptyLabel="当前未提取到更直观的参数内容" />
      <PayloadHighlights title="工具输出片段" payload={toolOutput} emptyLabel="当前未提取到更直观的输出内容" />

      {canAdmin && (
        <details className="mt-2 rounded-md border border-slate-200 bg-slate-50">
          <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-slate-700">工具参数 / 返回</summary>
          <div className="grid gap-2 border-t border-slate-200 p-3">
            <ReadablePayload title="工具参数" value={toolInput} emptyLabel="当前审计记录未保存更细的工具参数" />
            <ReadablePayload title="工具返回" value={toolOutput} emptyLabel="当前审计记录未保存工具返回内容" />
          </div>
        </details>
      )}
    </div>
  );
}

function ReadablePayload({
  title,
  value,
  emptyLabel = "暂无可展示的脱敏详情",
}: {
  title: string;
  value: unknown;
  emptyLabel?: string;
}) {
  const normalized = normalizePayload(value);

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
      <p className="text-[11px] font-semibold uppercase text-slate-500">{title}</p>
      {!hasPayload(normalized) ? (
        <p className="mt-1 text-xs leading-5 text-slate-500">{emptyLabel}</p>
      ) : typeof normalized === "string" || typeof normalized === "number" || typeof normalized === "boolean" ? (
        <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-slate-700">{String(normalized)}</p>
      ) : Array.isArray(normalized) ? (
        <div className="mt-2 grid gap-1.5">
          {normalized.slice(0, 8).map((item, index) => (
            <p key={index} className="rounded-sm bg-white px-2 py-1 text-xs leading-5 text-slate-700">
              {index + 1}. {formatReadableValue(item)}
            </p>
          ))}
          {normalized.length > 8 && <p className="text-[11px] text-slate-500">还有 {normalized.length - 8} 项已折叠.</p>}
        </div>
      ) : (
        <dl className="mt-2 grid gap-2">
          {Object.entries(normalized as Record<string, unknown>)
            .slice(0, 12)
            .map(([key, payloadValue]) => (
              <div key={key} className="grid gap-1 rounded-sm bg-white px-2 py-1.5">
                <dt className="font-mono text-[11px] text-slate-500">{key}</dt>
                <dd className="break-words text-xs leading-5 text-slate-700">{formatReadableValue(payloadValue)}</dd>
              </div>
            ))}
        </dl>
      )}
    </div>
  );
}

function TraceMessages({ messages }: { messages?: TraceMessage[] | null }) {
  if (!messages?.length) return null;
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
      <p className="text-[11px] font-semibold uppercase text-slate-500">Trace messages</p>
      <div className="mt-2 grid gap-2">
        {messages.slice(0, 6).map((message, index) => (
          <div key={index} className="rounded-sm bg-white px-2 py-1.5">
            <p className="text-[11px] font-semibold text-blue-800">{message.role || message.type || `message ${index + 1}`}</p>
            <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-slate-700">{summarizeReadablePayload(null, message.content, message.content || "empty message")}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function PayloadHighlights({
  title,
  payload,
  emptyLabel,
}: {
  title: string;
  payload: unknown;
  emptyLabel: string;
}) {
  if (!hasPayload(payload)) return null;
  const highlights = collectPayloadHighlights(payload);
  return (
    <div className="mt-3 rounded-md border border-slate-200 bg-white/90 px-3 py-2">
      <p className="text-[11px] font-semibold uppercase text-slate-500">{title}</p>
      {highlights.length === 0 ? (
        <p className="mt-1 text-xs leading-5 text-slate-500">{emptyLabel}</p>
      ) : (
        <div className="mt-2 grid gap-2">
          {highlights.map((item) => (
            <div key={`${title}-${item.label}-${item.text.slice(0, 24)}`} className="rounded-sm border border-slate-200 bg-slate-50 px-2 py-1.5">
              <p className="text-[11px] font-semibold text-blue-800">{item.label}</p>
              <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-slate-700">{item.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DetailLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
      <span className="shrink-0 font-semibold text-slate-500">{label}</span>
      <span className="min-w-0 break-words text-right font-medium text-slate-800">{value}</span>
    </div>
  );
}

function pathLabels(steps: TraceStep[]) {
  const labels = steps.map((step) => step.agent_name || step.workflow_node).filter(Boolean);
  return labels.slice(0, 7);
}

function agentToneFor(step: TraceStep, index: number): AgentTone {
  const name = `${step.agent_name ?? ""} ${step.workflow_node}`.toLowerCase();
  if (name.includes("question") || name.includes("planner")) return "sage";
  if (name.includes("examiner")) return "gold";
  if (name.includes("asr") || name.includes("speech") || name.includes("audio")) return "teal";
  if (name.includes("follow")) return "blue";
  if (name.includes("score") || name.includes("review") || name.includes("feedback") || name.includes("coach")) return "coral";
  return (["slate", "teal", "sage", "gold"] as AgentTone[])[index % 4];
}

function initials(label: string) {
  const words = label
    .replace(/Agent$/i, "")
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean);
  if (words.length === 0) return "AI";
  return words
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
}

function statusTone(status: TraceStep["status"]): "sage" | "coral" | "red" | "slate" {
  if (status === "completed") return "sage";
  if (status === "failed") return "red";
  if (status === "running") return "coral";
  return "slate";
}

function sourceLabel(chunk: Record<string, unknown>) {
  const source = typeof chunk.source === "string" ? chunk.source : "knowledge";
  const questionId = typeof chunk.question_id === "string" ? chunk.question_id.slice(0, 8) : "";
  const score = typeof chunk.score === "number" ? ` ${Math.round(chunk.score * 100)}%` : "";
  return `${source}${questionId ? ` ${questionId}` : ""}${score}`;
}

function toolInputValue(tool: TraceToolCall) {
  return tool.input_payload ?? tool.arguments ?? tool.parameters ?? tool.request ?? tool.input_summary ?? (tool.scope ? `scope=${tool.scope}` : null);
}

function toolOutputValue(tool: TraceToolCall) {
  return tool.output_payload ?? tool.response ?? tool.result_summary ?? tool.output_summary ?? tool.error_code ?? null;
}

function readablePayloadTitle(value: unknown) {
  const normalized = normalizePayload(value);
  if (!hasPayload(normalized)) return null;
  return "展开可查看结构化 input detail";
}

function payloadPreviewText(value: unknown) {
  const firstHighlight = collectPayloadHighlights(value, 1)[0];
  if (firstHighlight?.text) return firstHighlight.text;
  return readablePayloadTitle(value);
}

function formatLatency(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${value}ms`;
}

function shortValue(value?: string | null) {
  if (!value) return "-";
  return value.length > 14 ? `${value.slice(0, 14)}...` : value;
}

function truncateText(value: string, limit: number) {
  return value.length > limit ? `${value.slice(0, limit - 1)}...` : value;
}
