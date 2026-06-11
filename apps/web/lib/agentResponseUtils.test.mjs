import assert from "node:assert/strict";
import test from "node:test";

import { buildScoreReportPayload, hasPersistableScoreReport, scoreRetryMessage } from "./agentResponseUtils.ts";

test("score response without score_report is not persistable", () => {
  const response = {
    next_action: "retry_current_node",
    events: [
      {
        type: "error.recoverable",
        payload: {
          message: "没有可评分回答，请先提交至少一轮 ASR 转写。",
          retry_node: "scoring_workflow",
        },
      },
    ],
    state: {
      scoring_error: "no_scorable_answers",
    },
  };

  assert.equal(hasPersistableScoreReport(response), false);
  assert.equal(scoreRetryMessage(response), "没有可评分回答，请先提交至少一轮 ASR 转写。");
});

test("legacy numeric criteria can be normalized for persistence", () => {
  const payload = buildScoreReportPayload({
    run_id: "run_123",
    next_action: "finish_session",
    state: {
      score_report: {
        overall_band: 5.5,
        criteria: {
          fluency_coherence: 5.5,
          lexical_resource: 5.5,
          grammatical_range_accuracy: 5.5,
          pronunciation: 5.5,
        },
      },
    },
  });
  assert.equal(payload.overall_band, 5.5);
  assert.equal(payload.criteria.fluency_coherence.band, 5.5);
  assert.equal(hasPersistableScoreReport({
    next_action: "finish_session",
    state: {
      score_report: {
        overall_band: 5.5,
        criteria: {
          fluency_coherence: 5.5,
          lexical_resource: 5.5,
          grammatical_range_accuracy: 5.5,
          pronunciation: 5.5,
        },
      },
    },
  }), true);
});
