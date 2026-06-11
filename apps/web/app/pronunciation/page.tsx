"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  Loader2,
  Mic2,
  Play,
  RefreshCcw,
  ShieldCheck,
  Square,
  Volume2,
  Waves,
} from "lucide-react";

import { AcademicShell, EmptyState, InlineKpi, PageHeader, Panel, SectionHeading, StatusBadge, Waveform } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { audioFileExtension, useAudioRecorder } from "@/hooks/useAudioRecorder";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

type WordFeedback = {
  target_index: number;
  target_word: string;
  spoken_word?: string | null;
  gop_score: number;
  accuracy: number;
  timing: string;
  stress: string;
  status: "matched" | "substituted" | "missing";
  note: string;
};

type PhonemeFeedback = {
  target_index: number;
  word: string;
  phoneme: string;
  gop_score: number;
  accuracy: number;
  status: "acceptable" | "needs_review" | "missing";
  note: string;
};

type DrillResponse = {
  drill_id: string;
  provider: string;
  model: string;
  target_text: string;
  transcript?: string | null;
  confidence: number;
  alignment: {
    target_word_count: number;
    spoken_word_count: number;
    aligned_word_count: number;
    missing_word_count: number;
    substituted_word_count: number;
    alignment_confidence: number;
  };
  word_feedback: WordFeedback[];
  phoneme_feedback: PhonemeFeedback[];
  warnings?: string[];
};

type ApiError = {
  response?: {
    data?: {
      message?: string;
    };
  };
};

const speechAssessmentBase = process.env.NEXT_PUBLIC_SPEECH_ASSESSMENT_URL || "/speech-assessment";

const drillTexts = [
  "Technology has changed the way people communicate in everyday life.",
  "I prefer learning languages through real conversations and regular feedback.",
  "Public transport can make a city more convenient and environmentally friendly.",
];

export default function PronunciationPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const { isRecording, startRecording, stopRecording } = useAudioRecorder();
  const [targetText, setTargetText] = useState(drillTexts[0]);
  const [selectedWordIndex, setSelectedWordIndex] = useState(0);
  const [recordingConsentAccepted, setRecordingConsentAccepted] = useState(false);
  const [consentLoading, setConsentLoading] = useState(true);
  const [consentSaving, setConsentSaving] = useState(false);
  const [assessing, setAssessing] = useState(false);
  const [result, setResult] = useState<DrillResponse | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const recordingStartedAtRef = useRef<number | null>(null);

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/login");
    }
  }, [hasHydrated, isAuthenticated, router]);

  useEffect(() => {
    if (hasHydrated && isAuthenticated && !user) {
      fetchUser();
    }
  }, [fetchUser, hasHydrated, isAuthenticated, user]);

  useEffect(() => {
    if (!hasHydrated || !isAuthenticated) return;
    let cancelled = false;
    async function loadConsent() {
      setConsentLoading(true);
      try {
        const response = await api.get("/privacy/consents?consent_type=recording");
        if (!cancelled) {
          setRecordingConsentAccepted(Boolean(response.data.latest?.accepted));
        }
      } catch {
        if (!cancelled) setRecordingConsentAccepted(false);
      } finally {
        if (!cancelled) setConsentLoading(false);
      }
    }
    loadConsent();
    return () => {
      cancelled = true;
    };
  }, [hasHydrated, isAuthenticated]);

  const words = useMemo(() => tokenize(targetText), [targetText]);
  const selectedWord = result?.word_feedback.find((item) => item.target_index === selectedWordIndex);
  const selectedPhonemes = result?.phoneme_feedback.filter((item) => item.target_index === selectedWordIndex) ?? [];

  const acceptRecordingConsent = async () => {
    setConsentSaving(true);
    setError("");
    try {
      await api.post("/privacy/consents", {
        consent_type: "recording",
        version: "recording_consent.v1",
        accepted: true,
        metadata: {
          surface: "pronunciation_drill",
        },
      });
      setRecordingConsentAccepted(true);
      setNotice("Recording consent saved.");
    } catch {
      setError("Recording consent could not be saved.");
    } finally {
      setConsentSaving(false);
    }
  };

  const playModelAudio = () => {
    if (typeof window === "undefined" || !window.speechSynthesis) {
      setError("Browser speech synthesis is not available.");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(targetText);
    utterance.lang = "en-US";
    utterance.rate = 0.92;
    window.speechSynthesis.speak(utterance);
  };

  const startDrillRecording = async () => {
    if (!recordingConsentAccepted) {
      setError("Recording consent is required before drill recording.");
      return;
    }
    setResult(null);
    setError("");
    setNotice("");
    recordingStartedAtRef.current = Date.now();
    try {
      await startRecording();
    } catch {
      recordingStartedAtRef.current = null;
      setError("Microphone recording is not available in this browser. Check permission, HTTPS/localhost access, or try another supported browser.");
    }
  };

  const stopAndAssess = async () => {
    setAssessing(true);
    setError("");
    setNotice("");
    const startedAt = recordingStartedAtRef.current;
    const durationMs = Math.max(1000, startedAt ? Date.now() - startedAt : 1000);
    recordingStartedAtRef.current = null;

    try {
      const audioBlob = await stopRecording();
      if (audioBlob.size <= 0) {
        throw new Error("empty_recording");
      }

      const sessionResponse = await api.post("/sessions", {
        mode: "part_practice",
        target_part: 1,
        state: {
          setup_surface: "pronunciation_drill",
          target_text: targetText,
          ui_locale_hint: "en-CN",
        },
      });
      const sessionId = sessionResponse.data.session.id;
      await api.post(`/sessions/${sessionId}/start`);
      const turnResponse = await api.post(`/sessions/${sessionId}/turns`, {
        part: 1,
        speaker: "user",
        status: "recording",
        question_text: targetText,
        metadata: {
          source: "pronunciation_drill",
        },
      });
      const turnId = turnResponse.data.turn.id;

      const formData = new FormData();
      formData.append("file", audioBlob, `pronunciation-drill.${audioFileExtension(audioBlob.type)}`);
      formData.append("duration_ms", String(durationMs));
      formData.append("kind", "user_recording");
      formData.append("session_id", sessionId);
      formData.append("turn_id", turnId);

      const uploadResponse = await api.post("/audio/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const audioId = uploadResponse.data.audio_asset.id;

      const response = await fetch(`${speechAssessmentBase}/speech/pronunciation-drill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audio_asset_id: audioId,
          target_text: targetText,
          transcript: targetText,
          duration_ms: durationMs,
          metadata: {
            surface: "web_pronunciation_drill",
            user_id: user?.id,
          },
        }),
      });
      if (!response.ok) {
        throw new Error(`speech_assessment_${response.status}`);
      }
      const payload = (await response.json()) as DrillResponse;
      setResult(payload);
      setSelectedWordIndex(0);
      setNotice("Pronunciation evidence generated. This is not an official IELTS band score.");
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Pronunciation drill could not be assessed.");
    } finally {
      setAssessing(false);
    }
  };

  const resetDrill = () => {
    setResult(null);
    setError("");
    setNotice("");
    setSelectedWordIndex(0);
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  return (
    <AcademicShell activePath="/pronunciation" userName={user?.display_name || user?.email} userRole={user?.role}>
      <PageHeader
        eyebrow="Evidence-only Drill"
        title="Pronunciation Drill"
        titleZh="发音专项训练"
        description="Fixed-text read-aloud practice with word-level and phoneme-level evidence. It is separated from mock-exam scoring."
        actions={
          <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Dashboard
          </Button>
        }
      />

      {!consentLoading && !recordingConsentAccepted && (
        <Panel className="border-[#D4AF37]/35 bg-[#FFF8DF]">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex gap-3">
              <ShieldCheck className="mt-1 h-5 w-5 text-[#8A6F1D]" />
              <div>
                <h2 className="text-sm font-semibold text-slate-950">Recording Consent 褰曢煶鎺堟潈</h2>
                <p className="mt-1 text-sm leading-6 text-slate-600">
                  Drill audio is uploaded for pronunciation evidence and replay-related processing. You can delete recordings from History.
                </p>
              </div>
            </div>
            <Button type="button" variant="gold" onClick={acceptRecordingConsent} disabled={consentSaving}>
              {consentSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldCheck className="mr-2 h-4 w-4" />}
              I consent
            </Button>
          </div>
        </Panel>
      )}

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}
      {notice && <Panel className="border-[#3A7CA5]/20 bg-[#EAF5FA] text-sm text-[#2F6384]">{notice}</Panel>}

      <section className="grid gap-5 xl:grid-cols-[minmax(0,0.95fr)_minmax(320px,0.8fr)_minmax(330px,0.9fr)]">
        <Panel>
          <SectionHeading icon={Volume2} label="Drill Script" labelZh="跟读文本" />
          <label htmlFor="drill-text" className="grid min-w-0 gap-2 text-sm font-medium text-slate-700">
            <span>Preset sentence 预设句子</span>
            <select
              id="drill-text"
              value={targetText}
              onChange={(event) => {
                setTargetText(event.target.value);
                resetDrill();
              }}
              className="h-11 w-full min-w-0 max-w-full rounded-md border border-slate-200 bg-white px-3 text-sm outline-none transition-colors focus:border-[#D4AF37]"
            >
              {drillTexts.map((text) => (
                <option key={text} value={text}>
                  {text}
                </option>
              ))}
            </select>
          </label>

          <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="flex flex-wrap gap-2">
              {words.map((word, index) => {
                const feedback = result?.word_feedback.find((item) => item.target_index === index);
                return (
                  <button
                    key={`${word}-${index}`}
                    type="button"
                    onClick={() => setSelectedWordIndex(index)}
                    className={`cursor-pointer rounded-md border px-2 py-1 text-sm font-medium transition-colors ${
                      selectedWordIndex === index
                        ? "border-[#D4AF37] bg-[#FFF8DF] text-[#0B132B]"
                        : feedback
                          ? wordToneClass(feedback)
                          : "border-slate-200 bg-white text-slate-700 hover:border-[#D4AF37]/50"
                    }`}
                  >
                    {word}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-5 grid gap-3">
            <InlineKpi icon={ShieldCheck} label="Policy" value="Practice evidence only" />
            <InlineKpi icon={CheckCircle2} label="Mode" value="pronunciation_drill" />
            <InlineKpi icon={Waves} label="Provider" value={result?.provider || "deterministic_mfa_kaldi_gop"} />
          </div>
        </Panel>

        <Panel tone="dark">
          <SectionHeading icon={Mic2} label="Record Studio" labelZh="录音工作台" />
          <div className="flex min-h-[440px] flex-col items-center justify-center text-center">
            <div className="flex h-24 w-24 items-center justify-center rounded-full border border-[#D4AF37]/35 bg-white/10 text-[#D4AF37]">
              <Mic2 className="h-10 w-10" />
            </div>
            <p className="mt-5 text-sm leading-6 text-slate-300">
              Listen once, record the sentence, then review word and phoneme evidence.
            </p>
            <Waveform active={isRecording} className="mt-6 justify-center" />

            <div className="mt-6 flex flex-wrap justify-center gap-2">
              <Button type="button" variant="soft" onClick={playModelAudio}>
                <Play className="mr-2 h-4 w-4" />
                Model audio
              </Button>
              {isRecording ? (
                <Button type="button" variant="destructive" size="lg" onClick={stopAndAssess} disabled={assessing}>
                  {assessing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Square className="mr-2 h-4 w-4" />}
                  Stop & assess
                </Button>
              ) : (
                <Button type="button" variant="gold" size="lg" onClick={startDrillRecording} disabled={assessing}>
                  <Mic2 className="mr-2 h-4 w-4" />
                  Record
                </Button>
              )}
              <Button type="button" variant="soft" onClick={resetDrill}>
                <RefreshCcw className="mr-2 h-4 w-4" />
                Retry
              </Button>
            </div>
          </div>
        </Panel>

        <Panel>
          <SectionHeading icon={Waves} label="Pronunciation Evidence" labelZh="发音证据" />
          {result ? (
            <div className="grid gap-4">
              <div className="grid grid-cols-3 gap-3">
                <Metric label="Confidence" value={formatPercent(result.confidence)} />
                <Metric label="Aligned" value={`${result.alignment.aligned_word_count}/${result.alignment.target_word_count}`} />
                <Metric label="Missing" value={String(result.alignment.missing_word_count)} />
              </div>

              {selectedWord ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-lg font-semibold text-slate-950">{selectedWord.target_word}</h2>
                    <StatusBadge tone={selectedWord.status === "matched" ? "sage" : selectedWord.status === "missing" ? "red" : "coral"}>
                      {selectedWord.status}
                    </StatusBadge>
                  </div>
                  <div className="mt-3 grid gap-2 text-sm text-slate-600">
                    <InlineKpi label="Accuracy" value={formatPercent(selectedWord.accuracy)} />
                    <InlineKpi label="GOP score" value={formatPercent(selectedWord.gop_score)} />
                    <InlineKpi label="Timing" value={selectedWord.timing} />
                    <InlineKpi label="Stress" value={selectedWord.stress} />
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{selectedWord.note}</p>
                </div>
              ) : null}

              <div>
                <p className="mb-2 text-sm font-semibold text-slate-700">Phoneme detail 音素细节</p>
                {selectedPhonemes.length > 0 ? (
                  <div className="grid gap-2">
                    {selectedPhonemes.map((item, index) => (
                      <div key={`${item.word}-${item.phoneme}-${index}`} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
                        <span className="font-mono text-sm text-slate-700">{item.phoneme}</span>
                        <StatusBadge tone={item.status === "acceptable" ? "sage" : item.status === "missing" ? "red" : "coral"}>
                          {formatPercent(item.accuracy)}
                        </StatusBadge>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                    Select a word with phoneme evidence.
                  </p>
                )}
              </div>
            </div>
          ) : (
            <EmptyState
              icon={Mic2}
              title="Record a drill first"
              body="Word heatmap, phoneme detail, timing and stress feedback will appear after assessment."
            />
          )}
        </Panel>
      </section>
    </AcademicShell>
  );
}

function tokenize(text: string) {
  return text
    .split(/\s+/)
    .map((word) => word.replace(/(^[^\w']+|[^\w']+$)/g, ""))
    .filter(Boolean);
}

function wordToneClass(feedback: WordFeedback) {
  if (feedback.status === "missing" || feedback.accuracy < 0.58) {
    return "border-[#E76F51]/30 bg-[#E76F51]/10 text-[#B8533C]";
  }
  if (feedback.status === "substituted" || feedback.accuracy < 0.76) {
    return "border-[#D4AF37]/35 bg-[#FFF8DF] text-[#8A6F1D]";
  }
  return "border-[#4F8A6B]/25 bg-[#4F8A6B]/10 text-[#3E7056]";
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-950">{value}</p>
    </div>
  );
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}
