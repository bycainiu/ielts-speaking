import assert from "node:assert/strict";
import test from "node:test";

import { collectPayloadHighlights, formatReadableValue, normalizePayload, summarizeReadablePayload } from "./traceReadable.ts";

test("normalizePayload parses JSON strings into objects", () => {
  assert.deepEqual(normalizePayload('{"text":"hello"}'), { text: "hello" });
});

test("collectPayloadHighlights extracts human-readable text fields", () => {
  const highlights = collectPayloadHighlights({
    prompt: "Write an IELTS follow-up question.",
    response: {
      text: "Why do you think that matters to young people?",
      reasoning: "The learner gave a very short answer.",
    },
  });

  assert.deepEqual(highlights, [
    { label: "Prompt", text: "Write an IELTS follow-up question." },
    { label: "Text", text: "Why do you think that matters to young people?" },
    { label: "Reasoning", text: "The learner gave a very short answer." },
  ]);
});

test("formatReadableValue compresses nested payloads for summaries", () => {
  const summary = formatReadableValue({
    text: "This is the visible text.",
    confidence: 0.92,
    metadata: { source: "tool" },
  });

  assert.match(summary, /text: This is the visible text\./i);
  assert.match(summary, /confidence: 0.92/i);
});

test("collectPayloadHighlights prefers nested question and cue-card content", () => {
  const highlights = collectPayloadHighlights({
    question_text: "Describe a book you recently read.",
    cue_card: {
      prompt: "You should say what it was about.",
      bullet_points: ["when you read it", "why you chose it"],
    },
    rationale: ["The learner needs a concrete part 2 prompt."],
  });

  assert.equal(highlights[0]?.label, "Question");
  assert.match(highlights[0]?.text ?? "", /Describe a book/i);
  assert.ok(highlights.some((item) => item.label === "Cue Card"));
  assert.ok(highlights.some((item) => item.label === "Bullet Points"));
});

test("collectPayloadHighlights unwraps JSON strings stored in text fields", () => {
  const highlights = collectPayloadHighlights({
    text: JSON.stringify({
      rationale: ["Part 1 已从 question-bank-mcp 规划题目。"],
      parts: [{ part: 1, questions: [{ text: "Do you work or study?" }] }],
    }),
  });

  assert.equal(highlights[0]?.label, "Rationale");
  assert.match(highlights[0]?.text ?? "", /question-bank-mcp/);
  assert.ok(highlights.some((item) => item.text.includes("Do you work or study?")));
  assert.ok(!highlights[0]?.text.startsWith("{"));
});

test("summarizeReadablePayload prefers readable payload text over raw json summary", () => {
  const summary = summarizeReadablePayload(
    '{"raw":"json"}',
    {
      events: [{ payload: { text: "Examiner: What kind of music do you enjoy?" } }],
      question_id: "q_001",
    },
  );

  assert.match(summary, /Examiner: What kind of music/i);
  assert.match(summary, /Question ID: q_001/i);
});

test("collectPayloadHighlights does not crash when payload contains empty string values", () => {
  // Regression: walkPayload("") → normalizePayload("") returns null → typeof null === "object" → Object.entries(null) throws
  assert.doesNotThrow(() => {
    collectPayloadHighlights({ key: "", nested: { deep: "" }, arr: ["", "hello"] });
  });
  assert.doesNotThrow(() => collectPayloadHighlights(""));
  assert.doesNotThrow(() => collectPayloadHighlights({ a: { b: { c: "" } } }));
});

test("summarizeReadablePayload ignores wrapped json summaries when payload has semantic highlights", () => {
  const summary = summarizeReadablePayload(
    '文本: {"fallback_used":false,"parts":[{"part":1}]}',
    {
      text: JSON.stringify({
        rationale: ["Part 1 已从 question-bank-mcp 规划题目。"],
        parts: [{ part: 1, questions: [{ text: "Do you work or study?" }] }],
      }),
    },
  );

  assert.match(summary, /Rationale: Part 1/);
  assert.doesNotMatch(summary, /fallback_used/);
});
