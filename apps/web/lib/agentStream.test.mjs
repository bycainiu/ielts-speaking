import assert from "node:assert/strict";
import test from "node:test";

import {
  formatUsage,
  latestAgentStreamSeq,
  mergeAgentStreamEvents,
  parseSseBuffer,
  summarizeStreamEvent,
} from "./agentStream.ts";

const baseEvent = {
  event_id: "evt_1",
  run_id: "run_1",
  session_id: "sess_1",
  kind: "message.delta",
  payload: {},
  visibility: "default",
  created_at: "2026-06-10T00:00:00Z",
};

test("agent stream events merge by event id and keep seq order", () => {
  const merged = mergeAgentStreamEvents(
    [{ ...baseEvent, seq: 2, event_id: "evt_2" }],
    [
      { ...baseEvent, seq: 1, event_id: "evt_1", content_delta: "hello" },
      { ...baseEvent, seq: 2, event_id: "evt_2", content_delta: "updated" },
    ],
  );

  assert.equal(merged.length, 2);
  assert.deepEqual(merged.map((event) => event.seq), [1, 2]);
  assert.equal(merged[1].content_delta, "updated");
  assert.equal(latestAgentStreamSeq(merged), 2);
});

test("agent stream parser reads complete sse frames and keeps remainder", () => {
  const parsed = parseSseBuffer(
    'id: 1\nevent: message.delta\ndata: {"seq":1,"event_id":"evt_1","run_id":"run_1","session_id":"sess_1","kind":"message.delta","payload":{},"visibility":"default","created_at":"2026-06-10T00:00:00Z"}\n\nid: 2\nevent:',
  );

  assert.equal(parsed.events.length, 1);
  assert.equal(parsed.events[0].seq, 1);
  assert.equal(parsed.remainder, "id: 2\nevent:");
});

test("agent stream summaries cover reasoning and usage", () => {
  assert.equal(
    summarizeStreamEvent({ ...baseEvent, seq: 1, kind: "reasoning.delta", reasoning_delta: "because evidence is thin" }),
    "because evidence is thin",
  );
  assert.equal(formatUsage({ input_tokens: 10, output_tokens: 5, total_tokens: 15, cache_read_input_tokens: 7 }), "15 tokens · cache read 7 · cache create 0");
});
