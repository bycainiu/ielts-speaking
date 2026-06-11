export type MinimalAgentResponse = {
  run_id?: string;
  next_action?: string;
  events?: Array<{
    type?: string;
    payload?: Record<string, unknown> | null;
  }> | null;
  state?: Record<string, unknown> | null;
};

export type PersistableScoreReportPayload = {
  report_id?: string | null;
  version?: number;
  status: "ready";
  overall_band: number;
  confidence: number;
  disclaimer: string;
  model_run_id?: string | null;
  criteria: Record<string, Record<string, unknown>>;
  reviewer_notes: string[];
  next_practice_plan: Array<Record<string, unknown>>;
  feedback_items: Array<Record<string, unknown>>;
  reference_answers: Array<Record<string, unknown>>;
  raw_report: Record<string, unknown>;
};

export const IELTS_PRACTICE_DISCLAIMER = "AI 模拟评分仅用于练习参考，不代表 IELTS 官方成绩。";

const REQUIRED_CRITERIA = [
  "fluency_coherence",
  "lexical_resource",
  "grammatical_range_accuracy",
  "pronunciation",
] as const;

export function hasPersistableScoreReport(response: MinimalAgentResponse) {
  const state = asRecord(response.state);
  const report = asRecord(state?.score_report);
  if (!report) return false;
  if (numberFromUnknown(report.overall_band) === null) return false;
  const criteria = normalizeCriteriaForPersist(report.criteria);
  if (!REQUIRED_CRITERIA.every((key) => numberFromUnknown(criteria[key]?.band) !== null)) {
    return false;
  }
  if (numberFromUnknown(report.confidence) !== null) return true;
  return REQUIRED_CRITERIA.some((key) => numberFromUnknown(criteria[key]?.confidence) !== null);
}

export function scoreRetryMessage(response: MinimalAgentResponse) {
  const eventMessage = recoverableEventMessage(response);
  if (eventMessage) return eventMessage;

  const state = asRecord(response.state);
  if (state?.scoring_error === "no_scorable_answers") {
    return "没有可评分转写。本轮音频已保存，但 ASR 没有识别出回答；请重录、补充手动文本，或在复盘页查看已保存音频。";
  }

  if (response.next_action === "retry_current_node") {
    return "评分节点需要重试，但当前响应没有可保存的评分报告。请补充可评分回答后再提交。";
  }

  return "";
}

export function normalizeCriteriaForPersist(criteria: unknown): Record<string, Record<string, unknown>> {
  const source = asRecord(criteria);
  if (!source) return {};

  const normalized: Record<string, Record<string, unknown>> = {};
  for (const [key, value] of Object.entries(source)) {
    const objectValue = asRecord(value);
    if (objectValue) {
      normalized[key] = objectValue;
      continue;
    }
    const band = numberFromUnknown(value);
    if (band !== null) {
      normalized[key] = {
        band,
        confidence: 0.72,
        evidence: [],
        suggestions: [],
        raw_output: { source: "legacy_numeric_criterion" },
      };
    }
  }
  return normalized;
}

export function buildScoreReportPayload(response: MinimalAgentResponse): PersistableScoreReportPayload {
  const state = asRecord(response.state);
  const report = asRecord(state?.score_report);
  if (!report) {
    throw new Error("score_report_missing");
  }

  const criteria = normalizeCriteriaForPersist(report.criteria);
  if (!REQUIRED_CRITERIA.every((key) => criteria[key])) {
    throw new Error("score_report_criteria_missing");
  }

  const overallBand = numberFromUnknown(report.overall_band);
  let confidence = numberFromUnknown(report.confidence);
  if (confidence === null) {
    const confidences = REQUIRED_CRITERIA.map((key) => numberFromUnknown(criteria[key]?.confidence)).filter(
      (value): value is number => value !== null,
    );
    confidence = confidences.length ? confidences.reduce((sum, value) => sum + value, 0) / confidences.length : null;
  }
  if (overallBand === null || confidence === null) {
    throw new Error("score_report_band_missing");
  }

  const rawReport = asRecord(report.raw_report) ?? {};
  return {
    report_id: stringOrNull(report.report_id),
    version: numberFromUnknown(report.version) ?? 1,
    status: "ready",
    overall_band: overallBand,
    confidence,
    disclaimer: typeof report.disclaimer === "string" ? report.disclaimer : IELTS_PRACTICE_DISCLAIMER,
    model_run_id: stringOrNull(report.model_run_id) ?? response.run_id ?? null,
    criteria,
    reviewer_notes: stringArrayFromUnknown(report.reviewer_notes),
    next_practice_plan: recordArrayFromUnknown(report.next_practice_plan),
    feedback_items: recordArrayFromUnknown(state?.feedback_items),
    reference_answers: recordArrayFromUnknown(state?.reference_answers),
    raw_report: {
      ...rawReport,
      agent_run_id: response.run_id,
      feedback_summary: typeof state?.feedback_summary === "string" ? state.feedback_summary : undefined,
    },
  };
}

function recoverableEventMessage(response: MinimalAgentResponse) {
  for (const event of response.events ?? []) {
    if (event?.type !== "error.recoverable") continue;
    const payload = asRecord(event.payload);
    const message = normalizeText(payload?.message);
    if (message) return message;
  }
  return "";
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function recordArrayFromUnknown(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.map(asRecord).filter((item): item is Record<string, unknown> => Boolean(item));
}

function stringArrayFromUnknown(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

function numberFromUnknown(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function normalizeText(value: unknown) {
  if (typeof value !== "string") return "";
  return value.replace(/\s+/g, " ").trim();
}
