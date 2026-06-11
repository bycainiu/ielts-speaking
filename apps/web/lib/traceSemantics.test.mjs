import assert from "node:assert/strict";
import test from "node:test";

import {
  countTraceSemantics,
  formatCallModel,
  formatCallProvider,
  formatStepModel,
  formatTraceCallTitle,
  isCapturedLlmCall,
} from "./traceSemantics.ts";

test("trace semantics only treats captured llm calls as real provider requests", () => {
  const derived = {
    execution_kind: "deterministic",
    payload_origin: "derived",
    provider: "deterministic",
    model_name: "deterministic-rule-engine",
  };
  const captured = {
    execution_kind: "llm",
    payload_origin: "captured",
    provider: "mimo",
    model_name: "mimo-v2.5-pro",
  };

  assert.equal(isCapturedLlmCall(derived), false);
  assert.equal(isCapturedLlmCall(captured), true);
  assert.equal(formatTraceCallTitle(derived), "确定性/派生记录");
  assert.equal(formatTraceCallTitle(captured), "真实 LLM 请求");
  assert.equal(formatCallProvider(derived), "确定性流程");
  assert.equal(formatCallModel(derived), "无模型调用");
  assert.equal(formatCallModel(captured), "mimo-v2.5-pro");
});

test("trace semantic counts do not inflate derived records into llm counts", () => {
  const counts = countTraceSemantics([
    {
      execution_kind: "deterministic",
      model_name: "mimo-v2.5-pro",
      llm_calls: [
        { execution_kind: "deterministic", payload_origin: "derived", model_name: "deterministic-rule-engine" },
        { execution_kind: "llm", payload_origin: "captured", model_name: "mimo-v2.5-pro" },
      ],
      tool_calls: [{ tool_name: "search_questions" }],
    },
  ]);

  assert.deepEqual(counts, { capturedLlmCount: 1, derivedCallCount: 1, toolCallCount: 1 });
  assert.equal(
    formatStepModel({
      execution_kind: "deterministic",
      model_name: "mimo-v2.5-pro",
      llm_calls: [{ execution_kind: "deterministic", payload_origin: "derived", model_name: "deterministic-rule-engine" }],
    }),
    "无模型调用",
  );
});
