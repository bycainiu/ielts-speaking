export type TraceExecutionKind = "llm" | "deterministic" | "tool" | string;

export type TraceCallLike = {
  execution_kind?: TraceExecutionKind | null;
  payload_origin?: "captured" | "derived" | string | null;
  provider?: string | null;
  model_name?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
};

export type TraceStepLike = {
  execution_kind?: TraceExecutionKind | null;
  model_name?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  llm_calls?: TraceCallLike[] | null;
  tool_calls?: unknown[] | null;
};

export function isCapturedLlmCall(call?: TraceCallLike | null) {
  return call?.execution_kind === "llm" && call.payload_origin === "captured";
}

export function isDerivedTraceCall(call?: TraceCallLike | null) {
  return Boolean(call) && !isCapturedLlmCall(call);
}

export function countTraceSemantics(steps?: TraceStepLike[] | null) {
  const normalizedSteps = Array.isArray(steps) ? steps : [];
  let capturedLlmCount = 0;
  let derivedCallCount = 0;
  let toolCallCount = 0;

  for (const step of normalizedSteps) {
    const calls = Array.isArray(step.llm_calls) ? step.llm_calls : [];
    capturedLlmCount += calls.filter(isCapturedLlmCall).length;
    derivedCallCount += calls.filter(isDerivedTraceCall).length;
    toolCallCount += Array.isArray(step.tool_calls) ? step.tool_calls.length : 0;
  }

  return { capturedLlmCount, derivedCallCount, toolCallCount };
}

export function hasCapturedLlmCalls(step?: TraceStepLike | null) {
  return Boolean(step?.llm_calls?.some(isCapturedLlmCall));
}

export function formatPayloadOrigin(value?: string | null) {
  if (value === "captured") return "真实捕获";
  if (value === "derived") return "派生记录";
  return value || "来源未知";
}

export function formatExecutionKind(value?: string | null) {
  if (value === "llm") return "LLM";
  if (value === "tool") return "工具";
  if (value === "deterministic") return "确定性流程";
  return value || "执行类型未知";
}

export function formatTraceCallTitle(call: TraceCallLike) {
  if (isCapturedLlmCall(call)) return "真实 LLM 请求";
  if (call.execution_kind === "tool") return "工具派生记录";
  return "确定性/派生记录";
}

export function formatCallProvider(call: TraceCallLike) {
  if (isCapturedLlmCall(call)) return cleanLabel(call.provider) || "provider 未捕获";
  if (call.execution_kind === "tool") return "工具执行";
  return "确定性流程";
}

export function formatCallModel(call: TraceCallLike) {
  if (isCapturedLlmCall(call)) return cleanLabel(call.model_name) || "模型未捕获";
  if (call.execution_kind === "llm") return cleanLabel(call.model_name) || "模型未捕获";
  return "无模型调用";
}

export function formatStepModel(step: TraceStepLike) {
  const captured = step.llm_calls?.find(isCapturedLlmCall);
  if (captured) return formatCallModel(captured);
  if (step.execution_kind === "llm") return cleanLabel(step.model_name) || "模型未捕获";
  return "无模型调用";
}

export function formatTraceTokens(input?: number | null, output?: number | null, options?: { realLlmOnly?: boolean }) {
  if (options?.realLlmOnly === false) return "--";
  if (!input && !output) return "--";
  return `${input ?? 0} in / ${output ?? 0} out`;
}

function cleanLabel(value?: string | null) {
  const normalized = value?.trim();
  if (!normalized || normalized === "redacted" || normalized === "deterministic-rule-engine" || normalized === "model-call") {
    return "";
  }
  return normalized;
}
