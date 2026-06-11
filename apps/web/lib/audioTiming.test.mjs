import assert from "node:assert/strict";
import test from "node:test";

import {
  audioProgressPercent,
  finiteDurationMs,
  mediaSecondsToDurationMs,
  resolveAudioDurationMs,
} from "./audioTiming.ts";

test("媒体元数据的无限时长不会覆盖后端保存的录音时长", () => {
  assert.equal(mediaSecondsToDurationMs(Infinity), 0);
  assert.equal(resolveAudioDurationMs(Infinity, 28_000), 28_000);
  assert.equal(audioProgressPercent(7, resolveAudioDurationMs(Infinity, 28_000)), 25);
});

test("音频进度计算会钳制异常值和结束边界", () => {
  assert.equal(finiteDurationMs(NaN), 0);
  assert.equal(finiteDurationMs(0), 0);
  assert.equal(audioProgressPercent(10, 20_000), 50);
  assert.equal(audioProgressPercent(30, 20_000), 100);
  assert.equal(audioProgressPercent(-1, 20_000), 0);
});
