"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  BrainCircuit,
  CheckCircle2,
  FileText,
  Loader2,
  Mic2,
  Play,
  Radio,
  RefreshCcw,
  ShieldCheck,
  Square,
  Timer as TimerIcon,
  UploadCloud,
  Wifi,
  WifiOff,
} from "lucide-react";

import { AcademicShell, InlineKpi, PageHeader, Panel, SectionHeading, StatusBadge, Waveform } from "@/components/academic";
import { AudioPlayer } from "@/components/AudioPlayer";
import { ExaminerAvatar } from "@/components/ExaminerAvatar";
import { RadarChart } from "@/components/RadarChart";
import { Timer } from "@/components/Timer";
import { Button } from "@/components/ui/button";
import { audioFileExtension, useAudioRecorder } from "@/hooks/useAudioRecorder";
import { type SessionEvent, useSessionSocket } from "@/hooks/useSessionSocket";
import { useVAD } from "@/hooks/useVAD";
import { agentApi, api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

type SessionState =
  | "connecting"
  | "idle"
  | "examiner_speaking"
  | "user_preparing"
  | "user_speaking"
  | "processing"
  | "completed";

type CueCard = {
  prompt: string;
  bullet_points?: string[];
  preparation_seconds?: number;
  speaking_seconds?: number;
};

type LiveEventPayload = {
  part?: number;
  title?: string;
  text?: string;
  question_id?: string;
  turn_id?: string;
  cue_card?: CueCard;
  practice_hints?: string[];
  topic_guidance?: {
    topic_label?: string;
    vocabulary?: string[];
    useful_expressions?: string[];
    feedback_focus?: string;
  };
  timer_policy?: {
    suggested_seconds?: number;
    preparation_seconds?: number;
    speaking_seconds?: number;
  };
  audio_id?: string;
  audio_asset_id?: string;
  manual_text?: string;
  duration_seconds?: number;
  suggested_seconds?: number;
  preparation_seconds?: number;
  speaking_seconds?: number;
  phase?: string;
  purpose?: string;
  completed_parts?: number[];
  confidence?: number;
  decision?: string;
  reason?: string;
  message?: string;
};

type SessionDetails = {
  id: string;
  mode: string;
  status: string;
  season_id?: string | null;
  target_part?: number | null;
  topic_id?: string | null;
  state?: Record<string, unknown> | null;
  turns?: Array<{
    id: string;
    speaker: string;
    question_text?: string | null;
    answer_text?: string | null;
  }>;
};

type ApiError = {
  response?: {
    status?: number;
    data?: {
      message?: string;
    };
  };
};

type PendingAudioUpload = {
  blob: Blob;
  durationMs: number;
  turnId: string | null;
  createdAt: number;
};

type AgentResponse = {
  run_id: string;
  events: SessionEvent[];
  state: Record<string, unknown>;
  next_action: "wait_for_user_answer" | "ask_next_question" | "score_session" | "finish_session" | "retry_current_node";
};

type AudioUploadResponse = {
  audio_asset: {
    id: string;
    mime_type?: string;
  };
};

type TranscribeAudioResponse = {
  audio_asset_id: string;
  asr_text: string;
  language?: string | null;
  confidence?: number | null;
  provider: string;
  model: string;
  duration_ms?: number | null;
  metadata?: Record<string, unknown>;
};

type ScoreReportPayload = {
  report_id?: string | null;
  version?: number;
  status: "ready";
  overall_band: number;
  confidence: number;
  disclaimer: string;
  model_run_id?: string | null;
  criteria: Record<string, Record<string, unknown>>;
  reviewer_notes: string[];
  next_practice_plan: Array<Record<string, unknown>>;
  feedback_items: Array<Record<string, unknown>>;
  reference_answers: Array<Record<string, unknown>>;
  raw_report: Record<string, unknown>;
};

const timeline = [
  { part: 1, label: "Part 1", labelZh: "日常问答", detail: "Daily topics", duration: "04:30" },
  { part: 2, label: "Part 2", labelZh: "话题卡", detail: "Cue card", duration: "03:00" },
  { part: 3, label: "Part 3", labelZh: "深入讨论", detail: "Deep discussion", duration: "04:30" },
];

const criteria = [
  { name: "Fluency", value: "--" },
  { name: "Lexical", value: "--" },
  { name: "Grammar", value: "--" },
  { name: "Pronunciation", value: "--" },
];

const MIN_RECORDING_MS = 1800;
const IELTS_DISCLAIMER = "AI 模拟评分仅用于练习参考，不代表 IELTS 官方成绩。";

export default function LiveSessionPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const { status: socketStatus, lastEvent, sendMessage, reconnect } = useSessionSocket(sessionId);
  const { isRecording, stream: recordingStream, startRecording, stopRecording } = useAudioRecorder();

  const [session, setSession] = useState<SessionDetails | null>(null);
  const [sessionState, setSessionState] = useState<SessionState>("connecting");
  const [currentPart, setCurrentPart] = useState(1);
  const [completedParts, setCompletedParts] = useState<number[]>([]);
  const [examinerText, setExaminerText] = useState("Connecting to the examiner...");
  const [examinerAudioId, setExaminerAudioId] = useState<string | null>(null);
  const [audioReplayKey, setAudioReplayKey] = useState(0);
  const [cueCard, setCueCard] = useState<CueCard | null>(null);
  const [practiceHints, setPracticeHints] = useState<string[]>([]);
  const [topicVocabulary, setTopicVocabulary] = useState<string[]>([]);
  const [suggestedSeconds, setSuggestedSeconds] = useState(0);
  const [asrText, setAsrText] = useState("");
  const [currentTurnId, setCurrentTurnId] = useState<string | null>(null);
  const [recordingConsentAccepted, setRecordingConsentAccepted] = useState(false);
  const [consentLoading, setConsentLoading] = useState(true);
  const [consentSaving, setConsentSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pendingUpload, setPendingUpload] = useState<PendingAudioUpload | null>(null);
  const [retryingUpload, setRetryingUpload] = useState(false);
  const [manualAnswerText, setManualAnswerText] = useState("");

  const recordingStartedAtRef = useRef<number | null>(null);
  const recordingStopDelayRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isStoppingRecordingRef = useRef(false);
  const speakingSecondsRef = useRef(0);
  const timerPhaseRef = useRef<"idle" | "preparation" | "speaking">("idle");
  const agentPlanStartedRef = useRef(false);
  const scoringInProgressRef = useRef(false);
  const agentStateRef = useRef<Record<string, unknown> | null>(null);
  const currentPartRef = useRef(1);
  const currentTurnIdRef = useRef<string | null>(null);
  const startAgentPlanRef = useRef<() => Promise<void>>(async () => undefined);
  const processUploadedAnswerRef = useRef<(audioId: string, audioBlob: Blob, durationMs: number, turnId: string) => Promise<void>>(async () => undefined);
  const activeStepIndex = Math.max(0, timeline.findIndex((item) => item.part === currentPart));
  const progressPercent = Math.min(100, Math.max(0, ((completedParts.length + (sessionState === "completed" ? 1 : 0)) / 4) * 100));
  const timerIsActive = sessionState === "user_preparing" || sessionState === "user_speaking";
  const vadMinimumBeforeSilenceMs = suggestedSeconds > 0 ? Math.max(MIN_RECORDING_MS, Math.round(suggestedSeconds * 1000 * 0.8)) : 12000;

  useEffect(() => {
    currentPartRef.current = currentPart;
  }, [currentPart]);

  useEffect(() => {
    currentTurnIdRef.current = currentTurnId;
  }, [currentTurnId]);

  useEffect(() => {
    return () => {
      if (recordingStopDelayRef.current) {
        clearTimeout(recordingStopDelayRef.current);
        recordingStopDelayRef.current = null;
      }
    };
  }, []);

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
    async function loadSessionContext() {
      try {
        const [sessionResponse, consentResponse] = await Promise.allSettled([
          api.get<{ session: SessionDetails }>(`/sessions/${sessionId}`),
          api.get("/privacy/consents?consent_type=recording"),
        ]);
        if (cancelled) return;
        if (sessionResponse.status === "fulfilled") {
          setSession(sessionResponse.value.data.session);
        }
        if (consentResponse.status === "fulfilled") {
          setRecordingConsentAccepted(Boolean(consentResponse.value.data.latest?.accepted));
        }
      } finally {
        if (!cancelled) {
          setConsentLoading(false);
        }
      }
    }

    loadSessionContext();
    return () => {
      cancelled = true;
    };
  }, [hasHydrated, isAuthenticated, sessionId]);

  useEffect(() => {
    if (socketStatus === "connected" && sessionState === "connecting") {
      setSessionState("idle");
    }
  }, [socketStatus, sessionState]);

  const uploadAnswerBlob = useCallback(
    async (audioBlob: Blob, durationMs: number, turnId: string | null) => {
      if (!turnId) {
        throw new Error("missing_turn_id");
      }
      const formData = new FormData();
      formData.append("file", audioBlob, `answer.${audioFileExtension(audioBlob.type)}`);
      formData.append("duration_ms", String(durationMs));
      formData.append("kind", "user_recording");
      formData.append("session_id", sessionId);
      formData.append("turn_id", turnId);

      const uploadResponse = await api.post<AudioUploadResponse>("/audio/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const audioId = uploadResponse.data.audio_asset.id;
      sendMessage("user.answer_committed", { audio_id: audioId, duration_ms: durationMs, turn_id: turnId });
      setPendingUpload(null);
      setManualAnswerText("");
      setNotice("Answer uploaded. ASR is processing...");
      await processUploadedAnswerRef.current(audioId, audioBlob, durationMs, turnId);
    },
    [sendMessage, sessionId],
  );

  const handleStopRecording = useCallback(async () => {
    if (!isRecording) return;
    if (isStoppingRecordingRef.current) return;

    const startedAt = recordingStartedAtRef.current;
    if (startedAt) {
      const elapsedMs = Date.now() - startedAt;
      const remainingMs = MIN_RECORDING_MS - elapsedMs;
      if (remainingMs > 0) {
        if (!recordingStopDelayRef.current) {
          recordingStopDelayRef.current = setTimeout(() => {
            recordingStopDelayRef.current = null;
            void handleStopRecording();
          }, remainingMs);
        }
        return;
      }
    }

    isStoppingRecordingRef.current = true;
    setSessionState("processing");
    setError("");
    const durationMs = Math.max(1000, startedAt ? Date.now() - startedAt : 1000);
    recordingStartedAtRef.current = null;
    if (recordingStopDelayRef.current) {
      clearTimeout(recordingStopDelayRef.current);
      recordingStopDelayRef.current = null;
    }

    let recordedAudioBlob: Blob | null = null;
    try {
      recordedAudioBlob = await stopRecording();
      const audioBlob = recordedAudioBlob;
      if (audioBlob.size <= 0) {
        throw new Error("empty_recording");
      }
      await uploadAnswerBlob(audioBlob, durationMs, currentTurnId);
    } catch (err: unknown) {
      const apiError = err as ApiError;
      if (err instanceof Error && err.message === "empty_recording") {
        setError("No audio was captured. Please start speaking again.");
      } else if (err instanceof Error && err.message === "missing_turn_id") {
        setError("The current question is not ready yet. Reconnect or wait for the examiner question to load.");
      } else if (err instanceof Error && err.message === "answer_processing_failed") {
        if (recordedAudioBlob && recordedAudioBlob.size > 0) {
          setPendingUpload({ blob: recordedAudioBlob, durationMs, turnId: currentTurnId, createdAt: Date.now() });
        }
        setError("Audio was captured, but ASR or next-question processing failed. Retry upload or continue with typed text.");
      } else {
        if (recordedAudioBlob && recordedAudioBlob.size > 0) {
          setPendingUpload({ blob: recordedAudioBlob, durationMs, turnId: currentTurnId, createdAt: Date.now() });
        }
        setError(apiError.response?.data?.message || "Audio upload failed. Keep this answer here and choose Retry upload or Continue without audio.");
        sendMessage("error.recoverable", {
          message: "audio_upload_failed",
          recovery_actions: ["retry_upload", "continue_without_audio"],
          turn_id: currentTurnId,
        });
      }
      setSessionState("idle");
    } finally {
      isStoppingRecordingRef.current = false;
    }
  }, [currentTurnId, isRecording, sendMessage, stopRecording, uploadAnswerBlob]);

  const retryPendingUpload = async () => {
    if (!pendingUpload) return;
    setRetryingUpload(true);
    setError("");
    setNotice("Retrying saved audio upload...");
    setSessionState("processing");
    try {
      await uploadAnswerBlob(pendingUpload.blob, pendingUpload.durationMs, pendingUpload.turnId);
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Retry upload failed. The local recording is still available.");
      setSessionState("idle");
    } finally {
      setRetryingUpload(false);
    }
  };

  const continueWithoutAudio = () => {
    const manualText = manualAnswerText.trim();
    if (!pendingUpload || !manualText) {
      setError("Type a short manual answer before continuing without audio.");
      return;
    }
    sendMessage("user.answer_committed", {
      audio_id: null,
      manual_text: manualText,
      duration_ms: pendingUpload.durationMs,
      turn_id: pendingUpload.turnId,
      recovery: "manual_text_fallback",
    });
    setAsrText(manualText);
    setPendingUpload(null);
    setManualAnswerText("");
    setError("");
    setNotice("Manual answer submitted without audio. Waiting for the next examiner turn.");
    setSessionState("processing");
    if (pendingUpload.turnId) {
      void processManualAnswer(pendingUpload.turnId, manualText, pendingUpload.durationMs);
    }
  };

  const applySessionEvent = useCallback((event: SessionEvent) => {
    const payload = event.payload as LiveEventPayload;
    if (payload.part) {
      currentPartRef.current = payload.part;
      setCurrentPart(payload.part);
    }
    if (payload.turn_id) {
      currentTurnIdRef.current = payload.turn_id;
      setCurrentTurnId(payload.turn_id);
    }

    switch (event.type) {
      case "session.started":
        setSessionState("idle");
        setCompletedParts([]);
        break;
      case "part.started":
        setSessionState("idle");
        setCueCard(null);
        setPracticeHints(Array.isArray(payload.practice_hints) ? payload.practice_hints : []);
        setTopicVocabulary(payload.topic_guidance?.vocabulary ?? []);
        break;
      case "examiner.thinking":
      case "asr.processing":
        setSessionState("processing");
        break;
      case "user.silence_detected":
        setNotice("Silence detected, processing your answer...");
        setSessionState("processing");
        break;
      case "user.answer_committed":
        setSessionState("processing");
        if (payload.manual_text) {
          setAsrText(payload.manual_text);
          setNotice("Manual answer submitted without audio. Waiting for the next examiner turn.");
        } else {
          setNotice("Answer uploaded. ASR is processing...");
        }
        break;
      case "examiner.message":
        setExaminerText(payload.text ?? "");
        setCueCard(payload.cue_card ?? null);
        setPracticeHints(Array.isArray(payload.practice_hints) ? payload.practice_hints : []);
        setTopicVocabulary(payload.topic_guidance?.vocabulary ?? []);
        currentTurnIdRef.current = payload.turn_id ?? null;
        setCurrentTurnId(payload.turn_id ?? null);
        {
          const eventPart = payload.part ?? currentPartRef.current;
          const speakingSeconds = payload.timer_policy?.speaking_seconds ?? payload.timer_policy?.suggested_seconds ?? 0;
          const preparationSeconds = payload.timer_policy?.preparation_seconds ?? 0;
          const shouldPrepareFirst = eventPart === 2 && preparationSeconds > 0;
          speakingSecondsRef.current = speakingSeconds;
          timerPhaseRef.current = shouldPrepareFirst ? "preparation" : "speaking";
          setSuggestedSeconds(shouldPrepareFirst ? preparationSeconds : speakingSeconds);
        }
        setAsrText("");
        setNotice("");
        setSessionState("examiner_speaking");
        break;
      case "examiner.audio_ready":
        setExaminerAudioId(payload.audio_id ?? null);
        setAudioReplayKey((current) => current + 1);
        setSessionState("examiner_speaking");
        break;
      case "timer.started":
        {
          const eventPart = payload.part ?? currentPartRef.current;
          const speakingSeconds = payload.speaking_seconds ?? payload.suggested_seconds ?? payload.duration_seconds ?? 0;
          const preparationSeconds = payload.preparation_seconds ?? 0;
          const shouldPrepareFirst = payload.purpose === "preparation" || payload.phase === "prepare_then_speak" || (eventPart === 2 && preparationSeconds > 0);
          speakingSecondsRef.current = speakingSeconds;
          timerPhaseRef.current = shouldPrepareFirst ? "preparation" : "speaking";
          setSuggestedSeconds(shouldPrepareFirst ? preparationSeconds || payload.duration_seconds || payload.suggested_seconds || 0 : speakingSeconds);
        }
        if (timerPhaseRef.current === "preparation") {
          setSessionState("user_preparing");
        }
        break;
      case "asr.final":
        setAsrText(payload.text ?? "");
        setCurrentTurnId(payload.turn_id ?? null);
        setSessionState("idle");
        break;
      case "agent.followup_planned":
        setNotice(`${payload.decision ?? "Follow-up planned"}: ${payload.reason ?? ""}`);
        break;
      case "part.completed":
        if (payload.part) {
          setCompletedParts((current) => Array.from(new Set([...current, payload.part as number])).sort());
        }
        setSessionState("idle");
        break;
      case "session.completed":
        setCompletedParts(payload.completed_parts ?? [1, 2, 3]);
        setSessionState("processing");
        setNotice("Session complete. Generating your score report...");
        break;
      case "report.ready":
        setSessionState("completed");
        router.push(`/report/${sessionId}`);
        break;
      case "error.recoverable":
        setError(payload.message || "A recoverable issue happened. Please retry.");
        setSessionState("idle");
        break;
      case "error.fatal":
        setError(payload.message || "The session cannot continue.");
        setTimeout(() => router.push("/practice"), 1600);
        break;
    }
  }, [router, sessionId]);

  useVAD(
    isRecording,
    () => {
      if (sessionState === "user_speaking") {
        setNotice("Silence detected, processing your answer...");
        sendMessage("user.silence_detected", {});
        void handleStopRecording();
      }
    },
    4500,
    recordingStream,
    {
      minRecordingMsBeforeSilence: vadMinimumBeforeSilenceMs,
      requireSpeechBeforeSilence: true,
    },
  );

  useEffect(() => {
    if (!lastEvent) return;
    applySessionEvent(lastEvent);
  }, [applySessionEvent, lastEvent]);

  useEffect(() => {
    if (!session || !user || agentPlanStartedRef.current) return;
    if (!["created", "planned", "in_progress"].includes(session.status)) return;
    void startAgentPlanRef.current();
  }, [session, user]);

  async function startAgentPlan() {
    if (!session || !user || agentPlanStartedRef.current) return;
    agentPlanStartedRef.current = true;
    setError("");
    setNotice("Preparing examiner question...");
    setSessionState("processing");

    try {
      const setupState = asRecord(session.state) ?? {};
      const background = await loadBackgroundForPlan(setupState);
      const response = await agentApi.post<AgentResponse>(`/agent/sessions/${sessionId}/plan`, {
        mode: session.mode,
        user_id: user.id,
        season_id: session.season_id ?? undefined,
        part: session.target_part ?? undefined,
        topic_ids: session.topic_id ? [session.topic_id] : [],
        topic_labels: stringArrayFromUnknown(setupState.selected_topic_name),
        session_seed: sessionId,
        ...(background ? { user_background: background } : {}),
      });
      await dispatchAgentResponse(response.data);
    } catch {
      agentPlanStartedRef.current = false;
      setSessionState("idle");
      setError("The examiner service could not prepare the first question. Check Agent Harness or try Reconnect.");
    }
  }

  async function dispatchAgentResponse(response: AgentResponse) {
    agentStateRef.current = response.state ?? {};
    for (const event of response.events ?? []) {
      applySessionEvent(await prepareAgentEvent(event));
    }
  }

  async function prepareAgentEvent(event: SessionEvent) {
    if (event.type !== "examiner.message") return event;
    const payload = event.payload as LiveEventPayload;
    if (payload.turn_id || !payload.text) return event;

    try {
      const response = await api.post<{ turn: { id: string } }>(`/sessions/${sessionId}/turns`, {
        part: payload.part ?? currentPartRef.current,
        speaker: "user",
        status: "pending",
        question_text: payload.text,
        metadata: {
          source: "agent_harness_live",
          agent_run_id: event.run_id,
          agent_question_id: payload.question_id,
          event_type: event.type,
        },
      });
      return {
        ...event,
        payload: {
          ...payload,
          turn_id: response.data.turn.id,
        },
      };
    } catch {
      setError("The answer turn could not be prepared. Reconnect before recording.");
      return event;
    }
  }

  async function processUploadedAnswer(audioId: string, audioBlob: Blob, durationMs: number, turnId: string) {
    try {
      let audioBase64: string | undefined;
      let audioUrl: string | undefined;
      try {
        audioBase64 = await blobToBase64(audioBlob);
      } catch {
        audioBase64 = undefined;
      }
      try {
        const signed = await api.get<{ signed_url: string }>(`/audio/${audioId}/signed-url`);
        audioUrl = signed.data.signed_url;
      } catch {
        audioUrl = undefined;
      }

      let transcript: TranscribeAudioResponse;
      try {
        const transcribeResponse = await agentApi.post<TranscribeAudioResponse>("/agent/audio/transcribe", {
          audio_asset_id: audioId,
          mime_type: audioBlob.type || "audio/webm",
          duration_ms: durationMs,
          language_hint: "en",
          ...(audioBase64 ? { audio_base64: audioBase64 } : audioUrl ? { audio_url: audioUrl } : {}),
        });
        transcript = transcribeResponse.data;
      } catch (err) {
        if (!shouldUseWebAsrFallback(err)) {
          throw err;
        }
        transcript = buildWebAsrFallbackTranscript(audioId, audioBlob, durationMs, err);
        setNotice("ASR service used a local fallback transcript so this turn can continue.");
      }

      await api.post(`/sessions/${sessionId}/turns/${turnId}/asr-results`, {
        audio_asset_id: audioId,
        provider: transcript.provider,
        model: transcript.model,
        transcript: transcript.asr_text,
        confidence: transcript.confidence ?? undefined,
        raw_response: {
          source: "agent_harness_transcribe",
          metadata: transcript.metadata ?? {},
        },
      });

      void api.post(`/sessions/${sessionId}/turns/${turnId}/speech-metrics`, {
        audio_asset_id: audioId,
        duration_ms: durationMs,
        transcript: transcript.asr_text,
        asr_confidence: transcript.confidence ?? undefined,
        raw_metrics: {
          source: "web_live_auto",
        },
      }).catch(() => undefined);

      const consumeResponse = await agentApi.post<AgentResponse>(`/agent/sessions/${sessionId}/consume-asr`, {
        turn_id: turnId,
        asr_text: transcript.asr_text,
        audio_asset_id: audioId,
        asr_confidence: transcript.confidence ?? undefined,
        session_state: agentStateRef.current ?? {},
      });
      await dispatchAgentResponse(consumeResponse.data);
      await continueAgentFlow(consumeResponse.data);
    } catch (err) {
      console.error("Answer processing failed", err);
      throw new Error("answer_processing_failed");
    }
  }

  async function processManualAnswer(turnId: string, manualText: string, durationMs: number) {
    try {
      await api.post(`/sessions/${sessionId}/turns/${turnId}/asr-results`, {
        provider: "manual_fallback",
        model: "manual_text",
        transcript: manualText,
        confidence: 0.5,
        raw_response: {
          source: "web_manual_fallback",
        },
      });

      void api.post(`/sessions/${sessionId}/turns/${turnId}/speech-metrics`, {
        duration_ms: durationMs,
        transcript: manualText,
        asr_confidence: 0.5,
        raw_metrics: {
          source: "web_manual_fallback",
        },
      }).catch(() => undefined);

      const consumeResponse = await agentApi.post<AgentResponse>(`/agent/sessions/${sessionId}/consume-asr`, {
        turn_id: turnId,
        asr_text: manualText,
        asr_confidence: 0.5,
        session_state: agentStateRef.current ?? {},
      });
      await dispatchAgentResponse(consumeResponse.data);
      await continueAgentFlow(consumeResponse.data);
    } catch {
      setError("Manual answer was saved locally, but the next question could not be prepared. Try Reconnect.");
      setSessionState("idle");
    }
  }

  async function continueAgentFlow(response: AgentResponse) {
    if (response.next_action === "ask_next_question") {
      const nextResponse = await agentApi.post<AgentResponse>(`/agent/sessions/${sessionId}/next-turn`, {
        session_state: response.state,
      });
      await dispatchAgentResponse(nextResponse.data);
      await continueAgentFlow(nextResponse.data);
      return;
    }

    if (response.next_action === "score_session") {
      await scorePersistAndFinish(response.state);
      return;
    }

    if (response.next_action === "finish_session") {
      if (hasScoreReport(response)) {
        await api.post(`/sessions/${sessionId}/finish`).catch(() => undefined);
        await persistScoreReport(response);
        await dispatchAgentResponse(response);
        return;
      }
      void api.post(`/sessions/${sessionId}/finish`).catch(() => undefined);
    }
  }

  async function scorePersistAndFinish(sessionState: Record<string, unknown>) {
    if (scoringInProgressRef.current) return;
    scoringInProgressRef.current = true;
    setSessionState("processing");
    setNotice("Generating your score report...");
    setError("");
    try {
      const scoringResponse = await agentApi.post<AgentResponse>(`/agent/sessions/${sessionId}/score`, {
        session_state: sessionState,
      });
      await api.post(`/sessions/${sessionId}/finish`).catch(() => undefined);
      await persistScoreReport(scoringResponse.data);
      await dispatchAgentResponse(scoringResponse.data);
      if (!scoringResponse.data.events.some((event) => event.type === "report.ready")) {
        router.push(`/report/${sessionId}`);
      }
    } catch (err) {
      console.error("Score report generation failed", err);
      setError("Score report generation failed. Please reconnect and try submitting the final answer again.");
      setSessionState("idle");
    } finally {
      scoringInProgressRef.current = false;
    }
  }

  async function persistScoreReport(response: AgentResponse) {
    const payload = buildScoreReportPayload(response);
    await api.post(`/sessions/${sessionId}/report`, payload);
  }

  async function loadBackgroundForPlan(setupState: Record<string, unknown>) {
    if (setupState.personalize_with_background === false) return null;
    try {
      const response = await api.get<{ background: Record<string, unknown> }>("/me/background");
      return response.data.background;
    } catch {
      return null;
    }
  }

  startAgentPlanRef.current = startAgentPlan;
  processUploadedAnswerRef.current = processUploadedAnswer;

  const acceptRecordingConsent = async () => {
    setConsentSaving(true);
    setError("");
    try {
      await api.post("/privacy/consents", {
        consent_type: "recording",
        version: "recording_consent.v1",
        accepted: true,
        metadata: {
          surface: "live_session",
          session_id: sessionId,
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

  const beginUserRecording = async () => {
    if (!recordingConsentAccepted) {
      setError("Recording consent is required before speaking.");
      return;
    }
    if (!currentTurnIdRef.current) {
      setError("The current question is still preparing. Please wait a moment or reconnect.");
      return;
    }
    setError("");
    setNotice("");
    if (recordingStopDelayRef.current) {
      clearTimeout(recordingStopDelayRef.current);
      recordingStopDelayRef.current = null;
    }
    try {
      await startRecording();
      recordingStartedAtRef.current = Date.now();
      timerPhaseRef.current = "speaking";
      if (speakingSecondsRef.current > 0) {
        setSuggestedSeconds(speakingSecondsRef.current);
      }
      setSessionState("user_speaking");
      sendMessage("user.recording_started", { turn_id: currentTurnIdRef.current });
    } catch {
      recordingStartedAtRef.current = null;
      setError("Microphone recording is not available in this browser. Check permission, HTTPS/localhost access, or try another supported browser.");
    }
  };

  const replayQuestion = () => {
    if (!examinerAudioId) return;
    setAudioReplayKey((current) => current + 1);
    setSessionState("examiner_speaking");
  };

  const handleReconnect = () => {
    reconnect();
    if (!currentTurnIdRef.current) {
      agentPlanStartedRef.current = false;
      void startAgentPlanRef.current();
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  return (
    <AcademicShell activePath="/practice" userName={user?.display_name || user?.email} userRole={user?.role} className="pb-28 md:pb-8">
      <AudioPlayer
        key={`${examinerAudioId}-${audioReplayKey}`}
        audioId={examinerAudioId}
        onFinished={() => {
          if (sessionState === "examiner_speaking") {
            void beginUserRecording();
          }
        }}
        autoPlay={sessionState === "examiner_speaking"}
      />

      <PageHeader
        eyebrow="Live Exam Room"
        title="Live Session"
        titleZh="实时口语"
        description="Stay focused on the current question, timer, recording status and ASR evidence."
        actions={
          <>
            <StatusBadge tone={socketStatus === "connected" ? "sage" : "coral"}>
              {socketStatus === "connected" ? <Wifi className="mr-1 h-3 w-3" /> : <WifiOff className="mr-1 h-3 w-3" />}
              {socketStatus}
            </StatusBadge>
            <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Practice
            </Button>
          </>
        }
      />

      {!consentLoading && !recordingConsentAccepted && (
        <Panel className="border-[#D4AF37]/35 bg-[#FFF8DF]">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex gap-3">
              <ShieldCheck className="mt-1 h-5 w-5 text-[#8A6F1D]" />
              <div>
                <h2 className="text-sm font-semibold text-slate-950">Recording Consent 录音授权</h2>
                <p className="mt-1 text-sm leading-6 text-slate-600">
                  Your microphone audio is uploaded for transcription, AI scoring, feedback, replay and report review. You can delete recordings and reports from History.
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

      {error && (
        <Panel className="border-red-200 bg-red-50 text-sm text-red-700">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        </Panel>
      )}
      {pendingUpload && (
        <Panel className="border-[#D4AF37]/35 bg-[#FFF8DF]">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <StatusBadge tone="gold">Recovery</StatusBadge>
                <span className="text-xs text-slate-500">Saved locally {formatUploadAge(pendingUpload.createdAt)}</span>
              </div>
              <h2 className="mt-3 text-sm font-semibold text-slate-950">Audio upload needs attention</h2>
              <p className="mt-1 text-sm leading-6 text-slate-600">
                Your recording is still held in this browser tab. Retry the upload, or type the answer and continue without audio.
              </p>
              <textarea
                value={manualAnswerText}
                onChange={(event) => setManualAnswerText(event.target.value)}
                className="mt-3 min-h-20 w-full resize-y rounded-md border border-[#E9DFC6] bg-white px-3 py-2 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20"
                placeholder="Type your answer here if you need to continue without the audio file."
              />
            </div>
            <div className="flex flex-col gap-2 sm:flex-row lg:w-44 lg:flex-col">
              <Button type="button" variant="gold" onClick={() => void retryPendingUpload()} disabled={retryingUpload}>
                {retryingUpload ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <UploadCloud className="mr-2 h-4 w-4" />}
                Retry upload
              </Button>
              <Button type="button" variant="soft" onClick={continueWithoutAudio} disabled={!manualAnswerText.trim()}>
                <FileText className="mr-2 h-4 w-4" />
                Continue without audio
              </Button>
            </div>
          </div>
        </Panel>
      )}
      {notice && (
        <Panel className="border-[#3A7CA5]/20 bg-[#EAF5FA] text-sm text-[#2F6384]">
          {notice}
        </Panel>
      )}

      <Panel className="lg:hidden">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-[#3A7CA5]">Session Progress</p>
            <p className="text-sm font-semibold text-slate-900">
              Part {currentPart} · {formatState(sessionState)}
            </p>
          </div>
          <StatusBadge tone={socketStatus === "connected" ? "sage" : "coral"}>{socketStatus}</StatusBadge>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-100">
          <div className="h-full rounded-full bg-[#D4AF37]" style={{ width: `${Math.max(progressPercent, ((activeStepIndex + 1) / 4) * 18)}%` }} />
        </div>
        <div className="mt-3 grid grid-cols-4 gap-2 text-center text-[11px] text-slate-500">
          {timeline.map((item) => (
            <span key={item.part} className={item.part === currentPart ? "font-semibold text-[#8A6F1D]" : ""}>
              {item.label}
            </span>
          ))}
          <span>Report</span>
        </div>
      </Panel>

      <section className="grid min-w-0 max-w-full gap-5 overflow-hidden lg:grid-cols-[220px_minmax(0,1fr)_280px] 2xl:grid-cols-[260px_minmax(0,1fr)_320px]">
        <Panel className="hidden lg:block">
          <SectionHeading icon={FileText} label="Session Timeline" labelZh="考试进度" />
          <div className="relative grid gap-4">
            <div className="absolute bottom-8 left-4 top-4 w-px bg-slate-200" />
            {timeline.map((item) => {
              const completed = completedParts.includes(item.part);
              const active = currentPart === item.part && !completed;
              return (
                <div key={item.part} className="relative flex gap-3">
                  <span
                    className={`z-10 flex h-8 w-8 items-center justify-center rounded-full border bg-white ${
                      completed ? "border-[#4F8A6B] text-[#4F8A6B]" : active ? "border-[#D4AF37] text-[#D4AF37]" : "border-slate-200 text-slate-400"
                    }`}
                  >
                    {completed ? <CheckCircle2 className="h-4 w-4" /> : item.part}
                  </span>
                  <div className="min-w-0 pb-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className={`text-sm font-semibold ${active ? "text-slate-950" : "text-slate-600"}`}>{item.label}</p>
                      <span className="font-mono text-[11px] text-slate-400">{item.duration}</span>
                    </div>
                    <p className="text-xs text-slate-500">{item.labelZh} · {item.detail}</p>
                    {active && <StatusBadge tone="gold" className="mt-2">Current</StatusBadge>}
                  </div>
                </div>
              );
            })}
            <div className="relative flex gap-3">
              <span className="z-10 flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400">
                <FileText className="h-4 w-4" />
              </span>
              <div>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-600">Report</p>
                  <span className="font-mono text-[11px] text-slate-400">02:00</span>
                </div>
                <p className="text-xs text-slate-500">评分报告 · 4D scoring</p>
              </div>
            </div>
          </div>
        </Panel>

        <Panel tone="dark" className="max-w-full overflow-hidden p-0">
          <div className="border-b border-white/10 px-4 py-4 sm:px-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wide text-[#D4AF37]">{formatMode(session?.mode)} · Part {currentPart}</p>
                <h2 className="mt-1 font-serif text-2xl text-white">Examiner Stage</h2>
              </div>
              <StatusBadge tone={sessionState === "processing" ? "coral" : sessionState === "user_speaking" ? "red" : "teal"}>
                {formatState(sessionState)}
              </StatusBadge>
            </div>
          </div>

          <div className="grid min-h-[560px] min-w-0 max-w-full grid-rows-[1fr_auto] lg:min-h-[620px]">
            <div className="flex min-w-0 flex-col items-center justify-center px-4 py-8 text-center sm:px-5">
              <ExaminerAvatar
                status={sessionState === "examiner_speaking" ? "speaking" : sessionState === "user_speaking" ? "listening" : "idle"}
                className="h-28 w-28 border-[#D4AF37]/45 bg-[#111B3B] text-[#D4AF37] sm:h-36 sm:w-36"
              />
              <p className="mt-5 text-xs font-semibold uppercase tracking-[0.22em] text-[#3A7CA5]">
                Examiner {sessionState === "examiner_speaking" ? "speaking" : sessionState === "user_speaking" ? "listening" : "ready"}
              </p>
              <h3 className="mt-4 w-full max-w-3xl break-words font-serif text-xl leading-relaxed text-white sm:text-2xl md:text-3xl">
                &quot;{examinerText}&quot;
              </h3>

              {cueCard && (
                <div className="mt-6 w-full max-w-2xl overflow-hidden rounded-lg border border-[#D4AF37]/30 bg-[#F7F4EA] p-3 text-left text-[#0B132B] sm:p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <StatusBadge tone="gold">Cue Card</StatusBadge>
                      <p className="mt-3 break-words text-base font-semibold sm:text-lg">{cueCard.prompt}</p>
                    </div>
                    <StatusBadge tone="coral">{cueCard.preparation_seconds ?? 60}s prep</StatusBadge>
                  </div>
                  {cueCard.bullet_points && cueCard.bullet_points.length > 0 && (
                    <ul className="mt-4 grid gap-2 text-sm leading-6 text-slate-700">
                      {cueCard.bullet_points.map((point, index) => (
                        <li key={`${point}-${index}`} className="flex gap-2">
                          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#D4AF37]" />
                          <span>{point}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {practiceHints.length > 0 && (
                <div className="mt-4 flex w-full max-w-2xl flex-wrap justify-center gap-2">
                  {practiceHints.map((hint) => (
                    <StatusBadge key={hint} tone="teal">{hint}</StatusBadge>
                  ))}
                </div>
              )}

              <div className="mt-6 grid w-full min-w-0 max-w-2xl grid-cols-1 gap-3 sm:grid-cols-3">
                <InlineKpi icon={Radio} label="Microphone" value={isRecording ? "Recording" : recordingConsentAccepted ? "Ready" : "Consent required"} />
                <InlineKpi icon={UploadCloud} label="Turn" value={currentTurnId ? shortId(currentTurnId) : "-"} />
                <InlineKpi icon={TimerIcon} label="Timer" value={suggestedSeconds > 0 ? `${suggestedSeconds}s` : "Manual"} />
              </div>
            </div>

            <div className="min-w-0 border-t border-white/10 bg-black/20 px-4 py-5 sm:px-5">
              <div className="mb-4 grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                <Waveform active={isRecording} bars={24} className="w-full max-w-full justify-center overflow-hidden md:justify-start" />
                <div className="flex min-w-0 items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2">
                  <TimerIcon className="h-4 w-4 text-[#3A7CA5]" />
                  {suggestedSeconds > 0 ? (
                    timerIsActive ? (
                      <Timer
                        key={`${currentTurnId ?? "turn"}-${sessionState}-${suggestedSeconds}`}
                        initialSeconds={suggestedSeconds}
                        className="bg-transparent p-0 text-lg text-[#D4AF37]"
                        onTimeUp={() => {
                          if (sessionState === "user_preparing") {
                            void beginUserRecording();
                          }
                          if (sessionState === "user_speaking") {
                            void handleStopRecording();
                          }
                        }}
                      />
                    ) : (
                      <span className="font-mono text-lg text-[#D4AF37]">{formatTimerSeconds(suggestedSeconds)}</span>
                    )
                  ) : (
                    <span className="font-mono text-lg text-[#D4AF37]">--:--</span>
                  )}
                </div>
              </div>

              <div className="fixed bottom-3 left-3 right-3 z-20 grid grid-cols-2 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white/95 p-3 shadow-2xl backdrop-blur md:static md:flex md:flex-wrap md:border-white/10 md:bg-transparent md:p-0 md:shadow-none">
                <Button type="button" variant="soft" className="w-full min-w-0 px-3 text-xs sm:text-sm md:w-auto" onClick={replayQuestion} disabled={!examinerAudioId}>
                  <Play className="mr-2 h-4 w-4" />
                  Replay
                </Button>
                {sessionState === "user_speaking" ? (
                  <Button type="button" variant="destructive" size="lg" className="w-full min-w-0 px-3 text-xs sm:text-sm md:w-auto" onClick={() => void handleStopRecording()}>
                    <Square className="mr-2 h-4 w-4" />
                    Finish
                  </Button>
                ) : (
                  <Button type="button" variant="gold" size="lg" className="w-full min-w-0 px-3 text-xs sm:text-sm md:w-auto" onClick={() => void beginUserRecording()} disabled={!currentTurnId || sessionState === "processing" || sessionState === "completed"}>
                    <Mic2 className="mr-2 h-4 w-4" />
                    Start speaking
                  </Button>
                )}
                <Button type="button" variant="soft" className="w-full min-w-0 px-3 text-xs sm:text-sm md:w-auto" onClick={handleReconnect}>
                  <RefreshCcw className="mr-2 h-4 w-4" />
                  Reconnect
                </Button>
                <Button type="button" variant="soft" className="w-full min-w-0 px-3 text-xs sm:text-sm md:w-auto" onClick={() => setNotice("Issue noted locally. Reconnect is available if the session stalls.")}>
                  <AlertTriangle className="mr-2 h-4 w-4" />
                  Issue
                </Button>
              </div>
            </div>
          </div>
        </Panel>

        <div className="grid gap-5">
          <Panel>
            <SectionHeading icon={Radio} label="Session Summary" labelZh="会话摘要" />
            <div className="grid gap-2">
              <InlineKpi icon={Wifi} label="WebSocket" value={socketStatus} />
              <InlineKpi icon={UploadCloud} label="Current turn" value={currentTurnId ? shortId(currentTurnId) : "-"} />
              <InlineKpi icon={TimerIcon} label="Session status" value={session?.status || sessionState} />
              <InlineKpi icon={ShieldCheck} label="Recording consent" value={recordingConsentAccepted ? "Accepted" : "Required"} />
            </div>
          </Panel>

          <Panel>
            <SectionHeading icon={Mic2} label="ASR Echo" labelZh="转写回显" />
            {asrText ? (
              <p className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-700">&quot;{asrText}&quot;</p>
            ) : (
              <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm leading-6 text-slate-500">
                Your transcript will appear here after answer upload and ASR processing.
              </p>
            )}
          </Panel>

          <Panel>
            <SectionHeading icon={FileText} label="Review Preview" labelZh="复盘预览" />
            <RadarChart />
            <div className="mt-3 grid gap-2">
              {criteria.map((item) => (
                <div key={item.name} className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <span className="text-sm text-slate-600">{item.name}</span>
                  <span className="font-serif text-lg text-[#3A7CA5]">{item.value}</span>
                </div>
              ))}
            </div>
            <p className="mt-4 text-xs leading-5 text-slate-500">
              AI scoring is for practice reference only, not official IELTS results.
            </p>
          </Panel>

          {topicVocabulary.length > 0 && (
            <Panel tone="paper">
              <SectionHeading icon={BrainCircuit} label="Topic Guidance" labelZh="主题提示" />
              <div className="flex flex-wrap gap-2">
                {topicVocabulary.map((word) => (
                  <StatusBadge key={word} tone="teal">{word}</StatusBadge>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </section>
    </AcademicShell>
  );
}

function formatMode(value?: string) {
  if (value === "full_exam") return "Full exam";
  if (value === "part_practice") return "Part practice";
  if (value === "topic_practice") return "Topic practice";
  return "Live session";
}

function formatState(value: SessionState) {
  const labels: Record<SessionState, string> = {
    connecting: "Connecting",
    idle: "Ready",
    examiner_speaking: "Examiner speaking",
    user_preparing: "Preparing",
    user_speaking: "Recording",
    processing: "Processing",
    completed: "Completed",
  };
  return labels[value];
}

function shortId(value: string) {
  return value.length > 12 ? `${value.slice(0, 10)}...` : value;
}

function formatTimerSeconds(totalSeconds: number) {
  const seconds = Math.max(0, totalSeconds);
  const minutesPart = Math.floor(seconds / 60);
  const secondsPart = seconds % 60;
  return `${minutesPart.toString().padStart(2, "0")}:${secondsPart.toString().padStart(2, "0")}`;
}

function shouldUseWebAsrFallback(err: unknown) {
  const status = (err as ApiError).response?.status;
  return status === 415 || status === 502 || status === 503 || status === 504;
}

function buildWebAsrFallbackTranscript(audioId: string, audioBlob: Blob, durationMs: number, err: unknown): TranscribeAudioResponse {
  const status = (err as ApiError).response?.status;
  return {
    audio_asset_id: audioId,
    asr_text: "I recorded my IELTS speaking answer, but automatic transcription was unavailable during this browser test.",
    language: "en",
    confidence: 0.45,
    provider: "web_asr_fallback",
    model: "browser-flow-fallback-v1",
    duration_ms: durationMs,
    metadata: {
      fallback: true,
      http_status: status ?? null,
      mime_type: audioBlob.type || "audio/webm",
      size_bytes: audioBlob.size,
    },
  };
}

function hasScoreReport(response: AgentResponse) {
  const state = asRecord(response.state);
  const report = asRecord(state?.score_report);
  return Boolean(report && asRecord(report.criteria));
}

function buildScoreReportPayload(response: AgentResponse): ScoreReportPayload {
  const state = asRecord(response.state);
  const report = asRecord(state?.score_report);
  if (!report) {
    throw new Error("score_report_missing");
  }
  const criteria = asRecord(report.criteria);
  if (!criteria) {
    throw new Error("score_report_criteria_missing");
  }
  const normalizedCriteria = Object.fromEntries(
    Object.entries(criteria)
      .map(([key, value]) => [key, asRecord(value)])
      .filter((entry): entry is [string, Record<string, unknown>] => Boolean(entry[1])),
  );
  const overallBand = numberFromUnknown(report.overall_band);
  const confidence = numberFromUnknown(report.confidence);
  if (overallBand === null || confidence === null) {
    throw new Error("score_report_band_missing");
  }

  const rawReport = asRecord(report.raw_report) ?? {};
  return {
    report_id: stringOrNull(report.report_id),
    version: numberFromUnknown(report.version) ?? 1,
    status: "ready",
    overall_band: overallBand,
    confidence,
    disclaimer: typeof report.disclaimer === "string" ? report.disclaimer : IELTS_DISCLAIMER,
    model_run_id: stringOrNull(report.model_run_id) ?? response.run_id,
    criteria: normalizedCriteria,
    reviewer_notes: stringArrayFromUnknown(report.reviewer_notes),
    next_practice_plan: recordArrayFromUnknown(report.next_practice_plan),
    feedback_items: recordArrayFromUnknown(state?.feedback_items),
    reference_answers: recordArrayFromUnknown(state?.reference_answers),
    raw_report: {
      ...rawReport,
      agent_run_id: response.run_id,
      feedback_summary: typeof state?.feedback_summary === "string" ? state.feedback_summary : undefined,
    },
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function recordArrayFromUnknown(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.map(asRecord).filter((item): item is Record<string, unknown> => Boolean(item));
}

function stringArrayFromUnknown(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

function numberFromUnknown(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function formatUploadAge(createdAt: number) {
  const seconds = Math.max(0, Math.round((Date.now() - createdAt) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  return "over a minute ago";
}

function blobToBase64(blob: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("blob_read_failed"));
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",", 2)[1] : result);
    };
    reader.readAsDataURL(blob);
  });
}
