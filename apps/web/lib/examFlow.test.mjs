import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_EXAM_FLOW_SETTINGS,
  clampPartTimingSeconds,
  examinerAudioFinishAction,
  normalizeExamFlowSettings,
  resolveTimerPlan,
} from "./examFlow.ts";

test("空 session state 使用默认设置：显示文案、自动停止、计时跟随后端策略", () => {
  for (const state of [null, undefined, {}, { unrelated: 1 }]) {
    const settings = normalizeExamFlowSettings(state);
    assert.deepEqual(settings, DEFAULT_EXAM_FLOW_SETTINGS);
  }
});

test("session state 中的流程设置会被解析并钳制在合法区间", () => {
  const settings = normalizeExamFlowSettings({
    show_question_text: false,
    auto_stop_recording: false,
    part_timing: {
      part1_answer_seconds: 200,
      part2_preparation_seconds: 0,
      part2_speaking_seconds: 30,
      part3_answer_seconds: "60",
    },
  });
  assert.equal(settings.showQuestionText, false);
  assert.equal(settings.autoStopRecording, false);
  assert.equal(settings.partTiming.part1AnswerSeconds, 90);
  assert.equal(settings.partTiming.part2PreparationSeconds, 0);
  assert.equal(settings.partTiming.part2SpeakingSeconds, 60);
  assert.equal(settings.partTiming.part3AnswerSeconds, 60);
});

test("非法的计时配置回退为 null（沿用后端计时策略）", () => {
  assert.equal(clampPartTimingSeconds("part1AnswerSeconds", "abc"), null);
  assert.equal(clampPartTimingSeconds("part1AnswerSeconds", NaN), null);
  assert.equal(clampPartTimingSeconds("part1AnswerSeconds", undefined), null);
  const settings = normalizeExamFlowSettings({ part_timing: { part1_answer_seconds: "abc" } });
  assert.equal(settings.partTiming.part1AnswerSeconds, null);
});

test("Part 2 默认进入思考阶段，倒计时为思考时间", () => {
  const plan = resolveTimerPlan(
    { part: 2, preparationSeconds: 60, speakingSeconds: 120, phase: "prepare_then_speak" },
    DEFAULT_EXAM_FLOW_SETTINGS,
  );
  assert.equal(plan.phase, "preparation");
  assert.equal(plan.countdownSeconds, 60);
  assert.equal(plan.speakingSeconds, 120);
});

test("Part 2 思考时间设为 0 时跳过思考阶段，直接进入作答倒计时", () => {
  const settings = normalizeExamFlowSettings({
    part_timing: { part2_preparation_seconds: 0, part2_speaking_seconds: 90 },
  });
  const plan = resolveTimerPlan(
    { part: 2, preparationSeconds: 60, speakingSeconds: 120, phase: "prepare_then_speak" },
    settings,
  );
  assert.equal(plan.phase, "speaking");
  assert.equal(plan.countdownSeconds, 90);
  assert.equal(plan.preparationSeconds, 0);
});

test("考前设置覆盖 Part 1 / Part 3 的作答用时", () => {
  const settings = normalizeExamFlowSettings({
    part_timing: { part1_answer_seconds: 45, part3_answer_seconds: 70 },
  });
  const part1 = resolveTimerPlan({ part: 1, speakingSeconds: 30 }, settings);
  assert.equal(part1.phase, "speaking");
  assert.equal(part1.countdownSeconds, 45);

  const part3 = resolveTimerPlan({ part: 3, speakingSeconds: 45 }, settings);
  assert.equal(part3.countdownSeconds, 70);
});

test("未配置覆盖时沿用后端事件中的计时策略", () => {
  const part1 = resolveTimerPlan({ part: 1, speakingSeconds: 30 }, DEFAULT_EXAM_FLOW_SETTINGS);
  assert.equal(part1.countdownSeconds, 30);
  const part2 = resolveTimerPlan(
    { part: 2, preparationSeconds: 45, speakingSeconds: 100 },
    DEFAULT_EXAM_FLOW_SETTINGS,
  );
  assert.equal(part2.phase, "preparation");
  assert.equal(part2.countdownSeconds, 45);
  assert.equal(part2.speakingSeconds, 100);
});

test("timer.started 的 purpose=preparation 也会进入思考阶段", () => {
  const plan = resolveTimerPlan(
    { part: 2, preparationSeconds: 60, speakingSeconds: 120, purpose: "preparation" },
    DEFAULT_EXAM_FLOW_SETTINGS,
  );
  assert.equal(plan.phase, "preparation");
});

test("首次读完 Part 1/3 题目后自动开始录音", () => {
  const action = examinerAudioFinishAction({
    sessionState: "examiner_speaking",
    questionPlaybackDone: false,
    timerPhase: "speaking",
  });
  assert.equal(action, "start_recording");
});

test("首次读完 Part 2 题目后进入思考倒计时而不是直接录音", () => {
  const action = examinerAudioFinishAction({
    sessionState: "examiner_speaking",
    questionPlaybackDone: false,
    timerPhase: "preparation",
  });
  assert.equal(action, "start_preparation");
});

test("Replay 已读过的题目不会触发录音或改变流程", () => {
  for (const sessionState of ["idle", "examiner_speaking", "user_preparing"]) {
    const action = examinerAudioFinishAction({
      sessionState,
      questionPlaybackDone: true,
      timerPhase: "speaking",
    });
    assert.equal(action, "none");
  }
});

test("状态已离开 examiner_speaking 时播放结束不推进流程", () => {
  for (const sessionState of ["user_speaking", "user_preparing", "processing", "idle"]) {
    const action = examinerAudioFinishAction({
      sessionState,
      questionPlaybackDone: false,
      timerPhase: "speaking",
    });
    assert.equal(action, "none");
  }
});
