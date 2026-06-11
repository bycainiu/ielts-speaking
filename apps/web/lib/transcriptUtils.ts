export type ServiceTranscriptCandidate = {
  asr_text?: string | null;
  provider?: string | null;
  model?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type ReviewTranscriptCandidate = {
  correctedTranscript?: string | null;
  answerText?: string | null;
  asrTranscript?: string | null;
  asrProvider?: string | null;
};

const MOCK_TRANSCRIPT_PATTERN = /^Mock IELTS speaking transcript for audio asset [0-9a-z-]+\.$/i;
const UNAVAILABLE_TRANSCRIPT_PATTERN = /^I recorded my IELTS speaking answer, but automatic transcription was unavailable during this browser test\.$/i;
const SYNTHETIC_PROVIDERS = new Set(["mock_asr", "fallback_mock_asr", "web_asr_fallback"]);

export function normalizeTranscriptText(text?: string | null) {
  if (typeof text !== "string") return "";
  return text.replace(/\s+/g, " ").trim();
}

export function isSyntheticTranscriptText(text?: string | null) {
  const normalized = normalizeTranscriptText(text);
  if (!normalized) return false;
  return MOCK_TRANSCRIPT_PATTERN.test(normalized) || UNAVAILABLE_TRANSCRIPT_PATTERN.test(normalized);
}

export function isSyntheticServiceTranscript(candidate?: ServiceTranscriptCandidate | null) {
  if (!candidate) return false;
  const provider = normalizeTranscriptText(candidate.provider).toLowerCase();
  if (provider && SYNTHETIC_PROVIDERS.has(provider)) {
    return true;
  }
  if (candidate.metadata?.mock === true || candidate.metadata?.fallback === true) {
    return true;
  }
  return isSyntheticTranscriptText(candidate.asr_text);
}

export function choosePreferredTranscript({
  serviceTranscript,
  browserTranscript,
}: {
  serviceTranscript?: ServiceTranscriptCandidate | null;
  browserTranscript?: string | null;
}) {
  const normalizedService = normalizeTranscriptText(serviceTranscript?.asr_text);
  if (normalizedService && !isSyntheticServiceTranscript(serviceTranscript)) {
    return {
      transcript: normalizedService,
      source: "service" as const,
      reason: null,
    };
  }

  const normalizedBrowser = normalizeTranscriptText(browserTranscript);
  if (normalizedBrowser) {
    return {
      transcript: normalizedBrowser,
      source: "browser" as const,
      reason: normalizedService ? "service_synthetic" : "service_unavailable",
    };
  }

  return {
    transcript: null,
    source: "none" as const,
    reason: normalizedService ? "service_synthetic" : "service_unavailable",
  };
}

export function selectReviewTranscript(candidate: ReviewTranscriptCandidate) {
  const correctedTranscript = normalizeTranscriptText(candidate.correctedTranscript);
  if (correctedTranscript && !isSyntheticTranscriptText(correctedTranscript)) {
    return correctedTranscript;
  }

  const asrTranscript = normalizeTranscriptText(candidate.asrTranscript);
  if (
    asrTranscript
    && !isSyntheticTranscriptText(asrTranscript)
    && !SYNTHETIC_PROVIDERS.has(normalizeTranscriptText(candidate.asrProvider).toLowerCase())
  ) {
    return asrTranscript;
  }

  const answerText = normalizeTranscriptText(candidate.answerText);
  if (answerText && !isSyntheticTranscriptText(answerText)) {
    return answerText;
  }

  return "";
}
