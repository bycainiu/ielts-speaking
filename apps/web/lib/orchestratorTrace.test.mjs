import assert from "node:assert/strict";
import test from "node:test";

function labelStreamKind(kind) {
  const labels = {
    "director.route_change": "Director route",
    "agent.message_sent": "Agent message sent",
    "agent.thinking": "Agent reasoning",
  };
  return labels[kind] ?? kind;
}

function buildOrchestratorTraceTimeline(events, messages, toolIterations) {
  const items = [];
  let order = 0;
  for (const event of events.filter((item) => item.kind !== "heartbeat")) {
    items.push({
      id: event.event_id,
      order: order++,
      kind: event.kind === "director.route_change" ? "route" : "stream",
      title: labelStreamKind(event.kind),
      route: event.payload?.route,
      reasoningText: event.reasoning_delta,
      agent: event.payload?.agent || event.phase,
      targetAgent: event.payload?.target,
      createdAt: event.created_at,
    });
  }
  for (const message of messages) {
    items.push({
      id: `message-${message.message_id}`,
      order: order++,
      kind: "agent_message",
      title: message.message_type,
      targetAgent: message.target_agent,
      createdAt: message.created_at,
    });
  }
  for (const iteration of toolIterations) {
    items.push({
      id: `tool-${iteration.agent_name}-${iteration.iteration}`,
      order: order++,
      kind: "tool_iteration",
      title: iteration.tool_name ? `Tool · ${iteration.tool_name}` : "LLM iteration",
      toolName: iteration.tool_name,
      createdAt: iteration.created_at,
    });
    if (iteration.llm_request_messages?.length) {
      items.push({
        id: `llm-${iteration.agent_name}-${iteration.iteration}`,
        order: order++,
        kind: "llm_messages",
        title: "LLM request messages",
        agent: iteration.agent_name,
      });
    }
  }
  return items.sort((left, right) => {
    const leftTime = Date.parse(left.createdAt ?? "") || left.order;
    const rightTime = Date.parse(right.createdAt ?? "") || right.order;
    return leftTime - rightTime || left.order - right.order;
  });
}

test("buildOrchestratorTraceTimeline merges stream, messages, and tool iterations chronologically", () => {
  const timeline = buildOrchestratorTraceTimeline(
    [
      {
        event_id: "evt-1",
        kind: "director.route_change",
        phase: "exam_director",
        payload: { agent: "exam_director", target: "live_examiner", route: "deliver_question", part: 2 },
        created_at: "2026-06-10T10:00:01.000Z",
      },
      {
        event_id: "evt-2",
        kind: "agent.thinking",
        phase: "question_strategist",
        reasoning_delta: "Need a place topic with cue card.",
        payload: {},
        created_at: "2026-06-10T10:00:02.000Z",
      },
    ],
    [
      {
        message_id: "msg-1",
        source_agent: "exam_director",
        target_agent: "live_examiner",
        message_type: "task.deliver_question",
        payload: { part: 2 },
        created_at: "2026-06-10T10:00:01.500Z",
      },
    ],
    [
      {
        agent_name: "question_strategist",
        iteration: 1,
        llm_request_messages: [{ role: "user", content: "Plan questions" }],
        tool_name: "search_questions",
        created_at: "2026-06-10T10:00:03.000Z",
      },
    ],
  );

  assert.ok(timeline.length >= 4);
  assert.equal(labelStreamKind("director.route_change"), "Director route");
  assert.ok(timeline.some((item) => item.kind === "route" && item.route === "deliver_question"));
  assert.ok(timeline.some((item) => item.kind === "agent_message" && item.targetAgent === "live_examiner"));
  assert.ok(timeline.some((item) => item.kind === "tool_iteration" && item.toolName === "search_questions"));
  assert.ok(timeline.some((item) => item.kind === "llm_messages" && item.agent === "question_strategist"));
});
