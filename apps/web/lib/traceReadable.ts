export type PayloadHighlight = {
  label: string;
  text: string;
};

const interestingKeys = new Set([
  "text",
  "content",
  "prompt",
  "prompt_text",
  "reasoning",
  "thinking",
  "message",
  "messages",
  "instruction",
  "query",
  "filters",
  "part",
  "topic",
  "question_id",
  "question_text",
  "answer_text",
  "suggested_question",
  "transcript",
  "corrected_transcript",
  "summary",
  "reason",
  "rationale",
  "feedback",
  "body",
  "question",
  "questions",
  "cue_card",
  "bullet_points",
  "style_tags",
  "events",
]);

export function normalizePayload(value: unknown): unknown {
  if (typeof value !== "string") return value;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    try {
      return JSON.parse(trimmed) as unknown;
    } catch {
      return trimmed;
    }
  }
  return trimmed;
}

export function hasPayload(value: unknown) {
  const normalized = normalizePayload(value);
  if (normalized === null || normalized === undefined) return false;
  if (typeof normalized === "string") return normalized.trim().length > 0;
  if (Array.isArray(normalized)) return normalized.length > 0;
  if (typeof normalized === "object") return Object.keys(normalized as Record<string, unknown>).length > 0;
  return true;
}

export function formatPayload(value: unknown) {
  const normalized = normalizePayload(value);
  if (normalized === null || normalized === undefined) return "null";
  if (typeof normalized === "string") return normalized;
  try {
    return JSON.stringify(normalized, null, 2);
  } catch {
    return String(normalized);
  }
}

export function samePayload(left: unknown, right: unknown) {
  return formatPayload(left) === formatPayload(right);
}

export function formatReadableValue(value: unknown, limit = 240): string {
  const normalized = normalizePayload(value);
  if (normalized === null || normalized === undefined) return "-";
  if (typeof normalized === "string") return truncate(normalized, limit);
  if (typeof normalized === "number" || typeof normalized === "boolean") return String(normalized);
  if (Array.isArray(normalized)) {
    if (normalized.length === 0) return "empty list";
    return normalized.slice(0, 4).map((item) => formatReadableValue(item, 120)).join(" · ");
  }
  const entries = Object.entries(normalized as Record<string, unknown>).slice(0, 5);
  if (entries.length === 0) return "empty object";
  return entries.map(([key, item]) => `${key}: ${formatReadableValue(item, 120)}`).join(" · ");
}

export function collectPayloadHighlights(value: unknown, maxItems = 6): PayloadHighlight[] {
  const normalized = normalizePayload(value);
  const found = new Map<string, string>();
  collectStructuredHighlights(normalized, found, maxItems);
  walkPayload(normalized, [], found, maxItems);
  return Array.from(found.entries()).map(([label, text]) => ({ label, text }));
}

export function summarizeReadablePayload(summary: unknown, payload?: unknown, fallback = "无摘要") {
  const summaryHighlights = collectPayloadHighlights(summary, 2);
  const payloadHighlights = collectPayloadHighlights(payload, 3);

  if (summaryHighlights.length > 0 && !looksLikeWrappedJson(summaryHighlights)) {
    return summaryHighlights.map((item) => `${item.label}: ${item.text}`).join("\n");
  }

  if (payloadHighlights.length > 0) {
    return payloadHighlights.map((item) => `${item.label}: ${item.text}`).join("\n");
  }

  if (summaryHighlights.length > 0) {
    return summaryHighlights.map((item) => `${item.label}: ${item.text}`).join("\n");
  }

  if (hasPayload(summary)) {
    return formatReadableValue(summary, 420);
  }
  if (hasPayload(payload)) {
    return formatReadableValue(payload, 420);
  }
  return fallback;
}

function looksLikeWrappedJson(highlights: PayloadHighlight[]) {
  return highlights.some((item) => {
    const text = item.text.trim();
    return text.startsWith("{") || text.startsWith("[") || text.includes('"{') || text.includes('":') || text.includes('\\"');
  });
}

function collectStructuredHighlights(value: unknown, found: Map<string, string>, maxItems: number) {
  if (found.size >= maxItems || value === null || value === undefined) return;
  const normalized = normalizePayload(value);
  if (!normalized || typeof normalized !== "object") return;
  if (Array.isArray(normalized)) return;

  const record = normalized as Record<string, unknown>;
  pushHighlight(found, "Question", record.question_text ?? record.question, maxItems);
  pushHighlight(found, "Topic", record.topic, maxItems);
  pushHighlight(found, "Query", record.query, maxItems);
  pushHighlight(found, "Question ID", record.question_id, maxItems);
  pushHighlight(found, "Part", record.part, maxItems);
  pushHighlight(found, "Style Tags", record.style_tags, maxItems);
  pushHighlight(found, "Reasoning", record.reasoning, maxItems);
  pushHighlight(found, "Rationale", record.rationale, maxItems);
  pushHighlight(found, "Feedback", record.feedback, maxItems);
  collectNestedTextPayload(record.text, found, maxItems);
  if (found.size < maxItems) {
    pushHighlight(found, "Text", record.text, maxItems);
  }

  if (found.size < maxItems && Array.isArray(record.questions)) {
    const questionTexts = record.questions
      .map((item) => normalizePayload(item))
      .map((item) => {
        if (typeof item === "string") return item;
        if (typeof item === "object" && item && !Array.isArray(item)) {
          return typeof (item as Record<string, unknown>).text === "string" ? (item as Record<string, unknown>).text as string : "";
        }
        return "";
      })
      .filter(Boolean)
      .slice(0, 3)
      .join("\n");
    pushHighlight(found, "Questions", questionTexts, maxItems);
  }

  if (found.size < maxItems && typeof record.cue_card === "object" && record.cue_card && !Array.isArray(record.cue_card)) {
    const cueCard = record.cue_card as Record<string, unknown>;
    pushHighlight(found, "Cue Card", cueCard.prompt, maxItems);
    pushHighlight(found, "Bullet Points", cueCard.bullet_points, maxItems);
  }

  if (found.size < maxItems && Array.isArray(record.events)) {
    const texts = record.events
      .map((item) => normalizePayload(item))
      .map((item) => {
        if (typeof item !== "object" || !item || Array.isArray(item)) return "";
        const payload = (item as Record<string, unknown>).payload;
        if (typeof payload !== "object" || !payload || Array.isArray(payload)) return "";
        return typeof (payload as Record<string, unknown>).text === "string" ? (payload as Record<string, unknown>).text as string : "";
      })
      .filter(Boolean)
      .slice(0, 3)
      .join("\n");
    pushHighlight(found, "Events", texts, maxItems);
  }
}

function collectNestedTextPayload(value: unknown, found: Map<string, string>, maxItems: number) {
  if (found.size >= maxItems || typeof value !== "string") return;
  const nested = normalizePayload(value);
  if (!nested || typeof nested !== "object") return;
  collectStructuredHighlights(nested, found, maxItems);
  walkPayload(nested, ["text"], found, maxItems);
}

function pushHighlight(found: Map<string, string>, label: string, value: unknown, maxItems: number) {
  if (found.size >= maxItems || found.has(label)) return;
  if (!hasPayload(value)) return;
  const text = formatReadableValue(value, 600);
  if (!text || text === "-") return;
  found.set(label, text);
}

function walkPayload(
  value: unknown,
  path: string[],
  found: Map<string, string>,
  maxItems: number,
  depth = 0,
) {
  if (found.size >= maxItems || depth > 4 || value === null || value === undefined) return;
  const normalized = normalizePayload(value);

  // normalizePayload("") returns null; typeof null === "object" would cause Object.entries(null) to throw
  if (normalized === null || normalized === undefined) return;

  if (typeof normalized === "string") {
    const text = normalized.trim();
    if (!text) return;
    const key = path[path.length - 1];
    if (path.length === 0 || interestingKeys.has(key)) {
      const label = humanizePath(path);
      if (!found.has(label)) found.set(label, truncate(text, 600));
    }
    return;
  }

  if (typeof normalized === "number" || typeof normalized === "boolean") {
    const key = path[path.length - 1];
    if (interestingKeys.has(key)) {
      const label = humanizePath(path);
      if (!found.has(label)) found.set(label, String(normalized));
    }
    return;
  }

  if (Array.isArray(normalized)) {
    if (isMessageList(normalized)) {
      normalized.slice(0, maxItems).forEach((item, index) => {
        const record = item as Record<string, unknown>;
        const role = typeof record.role === "string" ? record.role : `message ${index + 1}`;
        const content = typeof record.content === "string" ? record.content : formatReadableValue(record.content, 320);
        if (content && found.size < maxItems) {
          found.set(`${role} text`, truncate(content, 600));
        }
      });
      return;
    }

    normalized.slice(0, 5).forEach((item, index) => {
      walkPayload(item, [...path, String(index)], found, maxItems, depth + 1);
    });
    return;
  }

  if (typeof normalized === "object") {
    Object.entries(normalized as Record<string, unknown>).forEach(([key, item]) => {
      if (found.size >= maxItems) return;
      walkPayload(item, [...path, key], found, maxItems, depth + 1);
    });
  }
}

function isMessageList(value: unknown[]) {
  return value.every((item) => typeof item === "object" && item !== null && ("content" in (item as Record<string, unknown>) || "role" in (item as Record<string, unknown>)));
}

function humanizePath(path: string[]) {
  if (path.length === 0) return "文本";
  const visible = path.filter((item) => !/^\d+$/.test(item));
  const key = visible[visible.length - 1] || path[path.length - 1];
  return key
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function truncate(value: string, limit: number) {
  return value.length > limit ? `${value.slice(0, limit - 1)}...` : value;
}
