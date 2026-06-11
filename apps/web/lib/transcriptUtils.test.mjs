import assert from "node:assert/strict";
import test from "node:test";

import {
  choosePreferredTranscript,
  isSyntheticServiceTranscript,
  isSyntheticTranscriptText,
  selectReviewTranscript,
} from "./transcriptUtils.ts";

test("mock transcript text is treated as synthetic", () => {
  assert.equal(isSyntheticTranscriptText("Mock IELTS speaking transcript for audio asset abc-123."), true);
  assert.equal(
    isSyntheticTranscriptText("I recorded my IELTS speaking answer, but automatic transcription was unavailable during this browser test."),
    true,
  );
  assert.equal(isSyntheticTranscriptText("I usually wear blue clothes because they feel calm."), false);
});

test("service transcript metadata can mark synthetic fallback payloads", () => {
  assert.equal(
    isSyntheticServiceTranscript({
      asr_text: "I usually wear blue clothes because they feel calm.",
      provider: "mimo_asr",
      metadata: { fallback: true },
    }),
    true,
  );
  assert.equal(
    isSyntheticServiceTranscript({
      asr_text: "I usually wear blue clothes because they feel calm.",
      provider: "mimo_asr",
      metadata: { mock: false },
    }),
    false,
  );
});
test("preferred transcript keeps real server ASR when available", () => {
  const selected = choosePreferredTranscript({
    serviceTranscript: {
      asr_text: "I usually wear blue and white clothes because they are simple.",
      provider: "mimo_asr",
      metadata: { mock: false },
    },
    browserTranscript: "browser transcript should not win here",
  });

  assert.deepEqual(selected, {
    transcript: "I usually wear blue and white clothes because they are simple.",
    source: "service",
    reason: null,
  });
});

test("preferred transcript falls back to browser STT when service payload is synthetic", () => {
  const selected = choosePreferredTranscript({
    serviceTranscript: {
      asr_text: "Mock IELTS speaking transcript for audio asset abc-123.",
      provider: "fallback_mock_asr",
      metadata: { fallback: true },
    },
    browserTranscript: "I usually wear dark colours because they are easy to match.",
  });

  assert.deepEqual(selected, {
    transcript: "I usually wear dark colours because they are easy to match.",
    source: "browser",
    reason: "service_synthetic",
  });
});

test("review transcript never shows synthetic placeholder text", () => {
  assert.equal(
    selectReviewTranscript({
      correctedTranscript: null,
      answerText: "Mock IELTS speaking transcript for audio asset abc-123.",
      asrTranscript: "Mock IELTS speaking transcript for audio asset abc-123.",
      asrProvider: "fallback_mock_asr",
    }),
    "",
  );

  assert.equal(
    selectReviewTranscript({
      correctedTranscript: null,
      answerText: "stale answer text",
      asrTranscript: "I like wearing black clothes because they look formal.",
      asrProvider: "browser_speech_recognition",
    }),
    "I like wearing black clothes because they look formal.",
  );
});
