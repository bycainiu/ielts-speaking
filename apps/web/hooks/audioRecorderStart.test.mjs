import assert from "node:assert/strict";
import test from "node:test";

import { shouldResetActiveStream, waitForAudioTrackReady, waitForMicrophoneStream } from "./audioRecorderStart.ts";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

test("慢授权超过软超时后仍可继续成功返回流", async () => {
  const stream = { id: "slow-stream" };
  let slowNoticeCount = 0;
  const currentGeneration = 1;

  const result = await waitForMicrophoneStream({
    requestStream: async () => {
      await sleep(20);
      return stream;
    },
    attemptGeneration: 1,
    getCurrentGeneration: () => currentGeneration,
    onSlow: () => {
      slowNoticeCount += 1;
    },
    slowTimeoutMs: 5,
  });

  assert.equal(result, stream);
  assert.equal(currentGeneration, 1);
  assert.equal(slowNoticeCount, 1);
});

test("旧请求晚到时会取消该流并抛出 recording_cancelled", async () => {
  const stream = { id: "late-stream" };
  let currentGeneration = 1;
  let cancelledStream = null;

  const pending = waitForMicrophoneStream({
    requestStream: async () => {
      await sleep(20);
      return stream;
    },
    attemptGeneration: 1,
    getCurrentGeneration: () => currentGeneration,
    onCancelledStream: (lateStream) => {
      cancelledStream = lateStream;
    },
    slowTimeoutMs: 50,
  });

  await sleep(5);
  currentGeneration = 2;

  await assert.rejects(pending, (err) => err instanceof Error && err.message === "recording_cancelled");
  assert.equal(cancelledStream, stream);
});

test("仅当前尝试或同一条流才允许清空 active stream", () => {
  const currentStream = { id: "current" };
  const oldStream = { id: "old" };

  assert.equal(shouldResetActiveStream(currentStream, currentStream, false), true);
  assert.equal(shouldResetActiveStream(currentStream, oldStream, false), false);
  assert.equal(shouldResetActiveStream(currentStream, oldStream, true), true);
  assert.equal(shouldResetActiveStream(null, oldStream, false), false);
});

test("音轨 unmute 后再视为真正 ready", async () => {
  const listeners = new Map();
  const track = {
    muted: true,
    readyState: "live",
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    removeEventListener(type) {
      listeners.delete(type);
    },
  };
  const stream = {
    getAudioTracks() {
      return [track];
    },
  };

  const pending = waitForAudioTrackReady(stream, { timeoutMs: 100, pollIntervalMs: 5 });
  await sleep(20);
  track.muted = false;
  listeners.get("unmute")?.();
  await pending;
  assert.equal(track.muted, false);
});

test("音轨长期未 ready 时按超时继续，不会卡死", async () => {
  const track = {
    muted: true,
    readyState: "live",
    addEventListener() {},
    removeEventListener() {},
  };
  const stream = {
    getAudioTracks() {
      return [track];
    },
  };

  const startedAt = Date.now();
  await waitForAudioTrackReady(stream, { timeoutMs: 30, pollIntervalMs: 5 });
  assert.ok(Date.now() - startedAt >= 20);
});
