"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  Eye,
  EyeOff,
  FileText,
  Loader2,
  Mic2,
  PauseCircle,
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
import { AudioPlayer, type AudioPlayerHandle } from "@/components/AudioPlayer";
import { ExaminerAvatar } from "@/components/ExaminerAvatar";
import { RadarChart } from "@/components/RadarChart";
import { Timer } from "@/components/Timer";
import { Button } from "@/components/ui/button";
import { audioFileExtension, microphoneStartErrorMessage, useAudioRecorder } from "@/hooks/useAudioRecorder";
import { useBrowserSpeechRecognition } from "@/hooks/useBrowserSpeechRecognition";
import { type SessionEvent, useSessionSocket } from "@/hooks/useSessionSocket";
import { useVAD } from "@/hooks/useVAD";
import { agentApi, api, orchestratorApi } from "@/lib/api";
import { AgentThinkingPanel } from "@/app/v2/components/AgentThinkingPanel";
import { useOrchestratorStream } from "@/hooks/useOrchestratorStream";
import { hasPersistableScoreReport, buildScoreReportPayload, scoreRetryMessage } from "@/lib/agentResponseUtils";
import {
  DEFAULT_EXAM_FLOW_SETTINGS,
  examinerAudioFinishAction,
  normalizeExamFlowSettings,
  resolveTimerPlan,
  type ExamFlowSettings,
} from "@/lib/examFlow";
import { choosePreferredTranscript, normalizeTranscriptText } from "@/lib/transcriptUtils";
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
  parts?: Array<{
    id: string;
    part: number;
    status: string;
  }>;
  turns?: Array<{
    id: string;
    part_id?: string | null;
    speaker: string;
    status?: string;
    question_text?: string | null;
    answer_text?: string | null;
    metadata?: Record<string, unknown> | null;
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
  browserTranscript?: string;
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

type SynthesizeTTSResponse = {
  audio_asset: {
    id: string;
    mime_type?: string;
    duration_ms?: number | null;
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

type SelectedTranscript =
  | ReturnType<typeof choosePreferredTranscript>
  | {
      transcript: string;
      source: "none";
      reason: string | null;
    };

type ScoreReportPayload = ReturnType<typeof buildScoreReportPayload>;

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
  const { user, isAuthenticated, hasHydrated, fetchUser, accessToken } = useAuthStore();
  const {
    isRecording,
    isStarting: isRecordingStarting,
    isStartSlow: isRecordingStartSlow,
    stream: recordingStream,
    startRecording,
    stopRecording,
    discardRecording,
    primeMicrophone,
  } = useAudioRecorder();
  const {
    finalTranscript: browserAsrFinalTranscript,
    interimTranscript: browserAsrInterimTranscript,
    startRecognition: startBrowserSpeechRecognition,
    stopRecognition: stopBrowserSpeechRecognition,
    cancelRecognition: cancelBrowserSpeechRecognition,
    resetTranscript: resetBrowserSpeechRecognition,
  } = useBrowserSpeechRecognition("en-US");

  const [session, setSession] = useState<SessionDetails | null>(null);
  const [sessionState, setSessionState] = useState<SessionState>("connecting");
  const [currentPart, setCurrentPart] = useState(1);
  const [completedParts, setCompletedParts] = useState<number[]>([]);
  const [examinerText, setExaminerText] = useState("Connecting to the examiner...");
  const [examinerAudioId, setExaminerAudioId] = useState<string | null>(null);
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
  const [showQuestionText, setShowQuestionText] = useState(true);
  const [isReplaying, setIsReplaying] = useState(false);
  const audioPlayerRef = useRef<AudioPlayerHandle>(null);
  const isReplayingRef = useRef(false);
  const socketEnabled = Boolean(session && !isReviewOnlySessionStatus(session.status));
  const { status: socketStatus, lastEvent, sendMessage, reconnect } = useSessionSocket(sessionId, { enabled: socketEnabled });
  const [orchestratorRunId, setOrchestratorRunId] = useState("");
  const orchestratorStream = useOrchestratorStream(orchestratorRunId, { enabled: Boolean(orchestratorRunId) });

  const recordingStartedAtRef = useRef<number | null>(null);
  const recordingStopDelayRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isStoppingRecordingRef = useRef(false);
  const speakingSecondsRef = useRef(0);
  const timerPhaseRef = useRef<"idle" | "preparation" | "speaking">("idle");
  const examSettingsRef = useRef<ExamFlowSettings>(DEFAULT_EXAM_FLOW_SETTINGS);
  const questionPlaybackDoneRef = useRef(true);
  const agentPlanStartedRef = useRef(false);
  const scoringInProgressRef = useRef(false);
  const agentStateRef = useRef<Record<string, unknown> | null>(null);
  const currentPartRef = useRef(1);
  const currentTurnIdRef = useRef<string | null>(null);
  const sessionStatusRef = useRef<string | null>(null);
  const isRecordingRef = useRef(false);
  const isRecordingStartingRef = useRef(false);
  const isExitingSessionRef = useRef(false);
  const completionRedirectRef = useRef(false);
  const pauseRequestInFlightRef = useRef(false);
  const startAgentPlanRef = useRef<() => Promise<void>>(async () => undefined);
  const restoreSessionFromSavedStateRef = useRef<(savedSession: SessionDetails) => Promise<boolean>>(async () => false);
  const processUploadedAnswerRef = useRef<(audioId: string, audioBlob: Blob, durationMs: number, turnId: string, browserTranscript?: string) => Promise<void>>(async () => undefined);
  const scorePersistAndFinishRef = useRef<(sessionState: Record<string, unknown>) => Promise<void>>(async () => undefined);
  const activeStepIndex = Math.max(0, timeline.findIndex((item) => item.part === currentPart));
  const progressPercent = Math.min(100, Math.max(0, ((completedParts.length + (sessionState === "completed" ? 1 : 0)) / 4) * 100));
  const timerIsActive = sessionState === "user_preparing" || sessionState === "user_speaking";
  const vadMinimumBeforeSilenceMs = suggestedSeconds > 0 ? Math.max(MIN_RECORDING_MS, Math.round(suggestedSeconds * 1000 * 0.8)) : 12000;
  const transcriptPreview = asrText || browserAsrFinalTranscript || browserAsrInterimTranscript;

  const releaseLocalRecordingResources = useCallback(() => {
    if (recordingStopDelayRef.current) {
      clearTimeout(recordingStopDelayRef.current);
      recordingStopDelayRef.current = null;
    }
    cancelBrowserSpeechRecognition();
    discardRecording();
    recordingStartedAtRef.current = null;
    isStoppingRecordingRef.current = false;
  }, [cancelBrowserSpeechRecognition, discardRecording]);

  useEffect(() => {
    currentPartRef.current = currentPart;
  }, [currentPart]);

  useEffect(() => {
    currentTurnIdRef.current = currentTurnId;
  }, [currentTurnId]);

  useEffect(() => {
    sessionStatusRef.current = session?.status ?? null;
  }, [session?.status]);

  useEffect(() => {
    isRecordingRef.current = isRecording;
  }, [isRecording]);

  useEffect(() => {
    isRecordingStartingRef.current = isRecordingStarting;
  }, [isRecordingStarting]);

  useEffect(() => {
    if (!isRecordingStartSlow || isExitingSessionRef.current) return;
    setError("");
    setNotice("浏览器仍在等待麦克风授权或音频设备真正就绪。状态切到 Recording 前请先不要开始回答；若不再继续，可点击 Cancel mic。");
  }, [isRecordingStartSlow]);

  useEffect(() => {
    if (!recordingConsentAccepted || !currentTurnId) return;
    let cancelled = false;

    async function warmMicrophoneIfGranted() {
      const permissionState = await queryMicrophonePermissionState();
      if (cancelled || permissionState !== "granted") return;
      try {
        await primeMicrophone();
      } catch {
        // 麦克风预热失败时不打断页面流程，首次点击录音时仍可重新申请。
      }
    }

    void warmMicrophoneIfGranted();
    return () => {
      cancelled = true;
    };
  }, [currentTurnId, primeMicrophone, recordingConsentAccepted]);

  useEffect(() => {
    isExitingSessionRef.current = false;
    return () => {
      isExitingSessionRef.current = true;
      releaseLocalRecordingResources();
    };
  }, [releaseLocalRecordingResources]);

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
    if (!accessToken) return;

    const pauseOnPageHide = () => {
      isExitingSessionRef.current = true;
      releaseLocalRecordingResources();
      if (completionRedirectRef.current || !isPauseableSessionStatus(sessionStatusRef.current)) return;
      const token = useAuthStore.getState().accessToken;
      if (!token) return;
      void fetch(`/api/sessions/${sessionId}/pause`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        keepalive: true,
      }).catch(() => undefined);
    };
    const resetExitStateOnPageShow = () => {
      if (!completionRedirectRef.current) {
        isExitingSessionRef.current = false;
      }
    };

    window.addEventListener("pagehide", pauseOnPageHide);
    window.addEventListener("pageshow", resetExitStateOnPageShow);
    return () => {
      window.removeEventListener("pagehide", pauseOnPageHide);
      window.removeEventListener("pageshow", resetExitStateOnPageShow);
    };
  }, [accessToken, releaseLocalRecordingResources, sessionId]);

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
          let loadedSession = sessionResponse.value.data.session;
          sessionStatusRef.current = loadedSession.status;

          const flowSettings = normalizeExamFlowSettings(asRecord(loadedSession.state));
          examSettingsRef.current = flowSettings;
          setShowQuestionText(flowSettings.showQuestionText);

          if (isReviewOnlySessionStatus(loadedSession.status)) {
            completionRedirectRef.current = true;
            setSession(loadedSession);
            router.replace(`/v2/report/${sessionId}`);
            return;
          }

          if (loadedSession.status === "paused") {
            try {
              const resumeResponse = await api.post<{ session: SessionDetails }>(`/sessions/${sessionId}/resume`);
              if (cancelled) return;
              loadedSession = resumeResponse.data.session;
              sessionStatusRef.current = loadedSession.status;
              setNotice("Paused session restored. Continue from the saved question when ready.");
            } catch {
              setError("This session is paused, but it could not be resumed. Try opening it again from Practice.");
            }
          }

          if (hasPersistedAgentState(loadedSession)) {
            agentPlanStartedRef.current = true;
            agentStateRef.current = asRecord(loadedSession.state);
          }
          setSession(loadedSession);
          if (hasPersistedAgentState(loadedSession)) {
            await restoreSessionFromSavedStateRef.current(loadedSession);
          }
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
  }, [hasHydrated, isAuthenticated, router, sessionId]);

  useEffect(() => {
    if (socketStatus === "connected" && sessionState === "connecting") {
      setSessionState("idle");
    }
  }, [socketStatus, sessionState]);

  const uploadAnswerBlob = useCallback(
    async (audioBlob: Blob, durationMs: number, turnId: string | null, browserTranscript?: string) => {
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
      await processUploadedAnswerRef.current(audioId, audioBlob, durationMs, turnId, browserTranscript);
    },
    [sendMessage, sessionId],
  );

  const handleStopRecording = useCallback(async () => {
    if (isExitingSessionRef.current) return;
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
    let browserTranscript = "";
    let browserTranscriptPromise: Promise<string> | null = null;
    try {
      browserTranscriptPromise = stopBrowserSpeechRecognition().catch(() => "");
      recordedAudioBlob = await stopRecording();
      browserTranscript = browserTranscriptPromise ? await browserTranscriptPromise : "";
      const audioBlob = recordedAudioBlob;
      if (audioBlob.size <= 0) {
        throw new Error("empty_recording");
      }
      await uploadAnswerBlob(audioBlob, durationMs, currentTurnId, browserTranscript);
    } catch (err: unknown) {
      const apiError = err as ApiError;
      if (err instanceof Error && err.message === "empty_recording") {
        setError("No audio was captured. Please start speaking again.");
      } else if (err instanceof Error && err.message === "missing_turn_id") {
        setError("The current question is not ready yet. Reconnect or wait for the examiner question to load.");
      } else if (err instanceof Error && (err.message === "synthetic_asr_transcript" || err.message === "transcript_unavailable")) {
        if (recordedAudioBlob && recordedAudioBlob.size > 0) {
          setPendingUpload({ blob: recordedAudioBlob, durationMs, turnId: currentTurnId, createdAt: Date.now(), browserTranscript });
        }
        setError("No usable transcript was captured for this answer. Retry upload or continue with typed text.");
      } else if (err instanceof Error && err.message === "answer_processing_failed") {
        if (recordedAudioBlob && recordedAudioBlob.size > 0) {
          setPendingUpload({ blob: recordedAudioBlob, durationMs, turnId: currentTurnId, createdAt: Date.now(), browserTranscript });
        }
        setError("Audio was captured, but ASR or next-question processing failed. Retry upload or continue with typed text.");
      } else {
        if (recordedAudioBlob && recordedAudioBlob.size > 0) {
          setPendingUpload({ blob: recordedAudioBlob, durationMs, turnId: currentTurnId, createdAt: Date.now(), browserTranscript });
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
  }, [currentTurnId, isRecording, sendMessage, stopBrowserSpeechRecognition, stopRecording, uploadAnswerBlob]);

  const retryPendingUpload = async () => {
    if (!pendingUpload) return;
    setRetryingUpload(true);
    setError("");
    setNotice("Retrying saved audio upload...");
    setSessionState("processing");
    try {
      await uploadAnswerBlob(pendingUpload.blob, pendingUpload.durationMs, pendingUpload.turnId, pendingUpload.browserTranscript);
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
          const audioId = payload.audio_id ?? payload.audio_asset_id ?? null;
          isReplayingRef.current = false;
          setIsReplaying(false);
          questionPlaybackDoneRef.current = !audioId;
          setExaminerAudioId(audioId);
        }
        {
          const eventPart = payload.part ?? currentPartRef.current;
          const plan = resolveTimerPlan(
            {
              part: eventPart,
              preparationSeconds: payload.timer_policy?.preparation_seconds,
              speakingSeconds: payload.timer_policy?.speaking_seconds ?? payload.timer_policy?.suggested_seconds,
            },
            examSettingsRef.current,
          );
          speakingSecondsRef.current = plan.speakingSeconds;
          timerPhaseRef.current = plan.phase;
          setSuggestedSeconds(plan.countdownSeconds);
        }
        setAsrText("");
        resetBrowserSpeechRecognition();
        setNotice("");
        setSessionState("examiner_speaking");
        break;
      case "examiner.audio_ready":
        isReplayingRef.current = false;
        setIsReplaying(false);
        questionPlaybackDoneRef.current = !payload.audio_id;
        setExaminerAudioId(payload.audio_id ?? null);
        setSessionState("examiner_speaking");
        break;
      case "timer.started":
        {
          const eventPart = payload.part ?? currentPartRef.current;
          const fallbackPreparationSeconds =
            payload.purpose === "preparation" ? payload.duration_seconds ?? payload.suggested_seconds : undefined;
          const plan = resolveTimerPlan(
            {
              part: eventPart,
              preparationSeconds: payload.preparation_seconds ?? fallbackPreparationSeconds,
              speakingSeconds: payload.speaking_seconds ?? payload.suggested_seconds ?? payload.duration_seconds,
              purpose: payload.purpose,
              phase: payload.phase,
            },
            examSettingsRef.current,
          );
          speakingSecondsRef.current = plan.speakingSeconds;
          timerPhaseRef.current = plan.phase;
          setSuggestedSeconds(plan.countdownSeconds);
          // 考官题目音频还在播放（或等待自动播放）时不进入思考倒计时，
          // 等音频播完由 onFinished 推进，保证 Part 2 进场时会先自动读题。
          if (plan.phase === "preparation" && questionPlaybackDoneRef.current) {
            setSessionState("user_preparing");
          }
        }
        break;
      case "asr.final":
        setAsrText(payload.text ?? "");
        setCurrentTurnId(payload.turn_id ?? null);
        setSessionState("idle");
        break;
      case "agent.followup_planned":
        setNotice("Operation completed.");;
        break;
      case "part.completed":
        if (payload.part) {
          setCompletedParts((current) => Array.from(new Set([...current, payload.part as number])).sort());
        }
        setSessionState("idle");
        break;
      case "session.completed":
        completionRedirectRef.current = true;
        sessionStatusRef.current = "scoring";
        setCompletedParts(payload.completed_parts ?? [1, 2, 3]);
        setSessionState("processing");
        setNotice("Session complete. Generating your score report...");
        break;
      case "report.ready":
        completionRedirectRef.current = true;
        sessionStatusRef.current = "completed";
        setSessionState("completed");
        router.replace(`/v2/report/${sessionId}`);
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
  }, [resetBrowserSpeechRecognition, router, sessionId]);

  useVAD(
    isRecording,
    () => {
      if (sessionState === "user_speaking" && examSettingsRef.current.autoStopRecording) {
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
      allowOwnStream: false,
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
      const response = await orchestratorApi.post<AgentResponse>(`/agent/sessions/${sessionId}/plan`, {
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
      setError("The examiner service could not prepare the first question. Check Agent Orchestrator or try Reconnect.");
    }
  }

  async function dispatchAgentResponse(response: AgentResponse) {
    if (response.run_id) {
      setOrchestratorRunId(response.run_id);
    }
    const preparedEvents: SessionEvent[] = [];
    for (const event of response.events ?? []) {
      preparedEvents.push(await prepareAgentEvent(event));
    }
    agentStateRef.current = response.state ?? {};
    await persistAgentState(agentStateRef.current);
    for (const event of preparedEvents) {
      applySessionEvent(event);
    }
  }

  async function persistAgentState(state: Record<string, unknown> | null) {
    if (!state || Object.keys(state).length === 0) return;
    try {
      await api.patch(`/sessions/${sessionId}/state`, { state });
    } catch {
      // 状态持久化失败不阻断当前答题流，页面内存中的状态仍会继续推进。
    }
  }

  async function restoreSessionFromSavedState(savedSession: SessionDetails) {
    const savedState = asRecord(savedSession.state);
    if (!savedState || !hasPersistedAgentState(savedSession)) return false;

    agentPlanStartedRef.current = true;
    agentStateRef.current = savedState;

    const restoredPart = numberFromUnknown(savedState.current_part) ?? inferCurrentPart(savedSession) ?? 1;
    currentPartRef.current = restoredPart;
    setCurrentPart(restoredPart);
    setCompletedParts(numberArrayFromUnknown(savedState.completed_parts));

    const plannedQuestion = currentPlannedQuestionFromState(savedState, savedSession);
    const plannedQuestionText = typeof plannedQuestion?.text === "string" ? plannedQuestion.text : "";
    let pendingTurn = findPendingAnswerTurn(savedSession, plannedQuestionText);
    if (!pendingTurn && plannedQuestionText) {
      pendingTurn = await createPendingTurnForResume(restoredPart, plannedQuestionText, plannedQuestion);
    }

    const restoredQuestionText = pendingTurn?.question_text || plannedQuestionText;
    currentTurnIdRef.current = pendingTurn?.id ?? null;
    setCurrentTurnId(pendingTurn?.id ?? null);
    setExaminerText(restoredQuestionText || "Session restored. Reconnect if the current examiner question is missing.");
    setCueCard(cueCardFromPlannedQuestion(plannedQuestion));
    setPracticeHints(stringArrayFromUnknown(savedState.practice_hints));

    const topicGuidance = asRecord(savedState.topic_guidance);
    setTopicVocabulary(stringArrayFromUnknown(topicGuidance?.vocabulary));
    {
      const restoredPlan = restoredTimerPlanFromSavedState(savedState, restoredPart, plannedQuestion, examSettingsRef.current);
      speakingSecondsRef.current = restoredPlan.speakingSeconds;
      timerPhaseRef.current = "idle";
      questionPlaybackDoneRef.current = true;
      setSuggestedSeconds(restoredPlan.countdownSeconds);
    }
    setAsrText("");
    if (savedState.status === "ready_to_score") {
      setNotice("Resuming score report generation...");
      void scorePersistAndFinishRef.current(savedState);
      return true;
    }
    setSessionState("idle");
    if (restoredQuestionText) {
      setNotice("Session restored. Continue from the saved question when ready.");
    }
    return true;
  }

  async function createPendingTurnForResume(part: number, questionText: string, plannedQuestion: Record<string, unknown> | null) {
    try {
      const response = await api.post<{ turn: NonNullable<SessionDetails["turns"]>[number] }>(`/sessions/${sessionId}/turns`, {
        part,
        speaker: "user",
        status: "pending",
        question_text: questionText,
        question_id: typeof plannedQuestion?.question_id === "string" ? plannedQuestion.question_id : undefined,
        metadata: {
          source: "web_live_resume",
          restored_from_session_state: true,
        },
      });
      return response.data.turn;
    } catch {
      setError("Saved question was restored, but the answer turn could not be prepared. Use Reconnect before recording.");
      return null;
    }
  }

  async function prepareAgentEvent(event: SessionEvent) {
    if (event.type !== "examiner.message") return event;
    const payload = event.payload as LiveEventPayload;
    if (!payload.text) return event;

    let turnId = payload.turn_id;
    try {
      if (!turnId) {
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
        turnId = response.data.turn.id;
      }
    } catch {
      setError("The answer turn could not be prepared. Reconnect before recording.");
      return event;
    }

    const audioId = payload.audio_id ?? payload.audio_asset_id ?? (await synthesizeExaminerAudio(turnId, payload.text));
    return {
      ...event,
      payload: {
        ...payload,
        turn_id: turnId,
        ...(audioId ? { audio_id: audioId, audio_asset_id: audioId } : {}),
      },
    };
  }

  async function synthesizeExaminerAudio(turnId: string, text: string) {
    try {
      const state = asRecord(session?.state);
      const voiceId = stringOrNull(state?.examiner_voice) ?? "ielts_examiner_default";
      const response = await api.post<SynthesizeTTSResponse>("/audio/tts", {
        session_id: sessionId,
        turn_id: turnId,
        text,
        voice_id: voiceId,
        speaking_rate: 1.0,
        style: "examiner",
      });
      return response.data.audio_asset.id;
    } catch (err) {
      console.warn("Examiner TTS could not be saved for replay", err);
      return null;
    }
  }

  async function processUploadedAnswer(audioId: string, audioBlob: Blob, durationMs: number, turnId: string, browserTranscript?: string) {
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

      let transcript: TranscribeAudioResponse | null = null;
      let forcedSelectedTranscript: SelectedTranscript | null = null;
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
        if (!shouldUseBrowserTranscriptFallback(err)) {
          throw err;
        }
        transcript = buildBrowserTranscriptFallback(audioId, audioBlob, durationMs, browserTranscript, null, err);
        if (!transcript) {
          transcript = buildUnavailableTranscriptFallback(audioId, audioBlob, durationMs, null, err, "service_unavailable");
          forcedSelectedTranscript = {
            transcript: "",
            source: "none",
            reason: "service_unavailable",
          };
          setNotice("Audio was captured, but no transcript was recognized. This turn continued with an empty answer. 已继续提交空回答。");
        } else {
          forcedSelectedTranscript = {
            transcript: transcript.asr_text,
            source: "browser",
            reason: "service_unavailable",
          };
          setNotice("ASR service was unavailable, so this turn continued with browser speech recognition. 已改用浏览器语音识别兜底。");
        }
      }
      if (!transcript) {
        transcript = buildUnavailableTranscriptFallback(audioId, audioBlob, durationMs, null, null, "service_unavailable");
      }

      let selectedTranscript: SelectedTranscript = forcedSelectedTranscript ?? choosePreferredTranscript({
        serviceTranscript: transcript,
        browserTranscript,
      });
      if (!selectedTranscript.transcript) {
        if (transcript.provider !== "transcript_unavailable") {
          transcript = buildUnavailableTranscriptFallback(audioId, audioBlob, durationMs, transcript, null, selectedTranscript.reason);
        }
        selectedTranscript = {
          transcript: "",
          source: "none",
          reason: selectedTranscript.reason,
        };
        setNotice("Audio was captured, but no transcript was recognized. This turn continued with an empty answer. 已继续提交空回答。");
      }

      if (selectedTranscript.source === "browser" && transcript.provider !== "browser_speech_recognition") {
        transcript = buildBrowserTranscriptFallback(audioId, audioBlob, durationMs, selectedTranscript.transcript, transcript);
        if (!transcript) {
          throw new Error("transcript_unavailable");
        }
        setNotice("The upstream ASR response was unusable, so this turn continued with browser speech recognition. 已改用浏览器语音识别转写。");
      }

      await api.post(`/sessions/${sessionId}/turns/${turnId}/asr-results`, {
        audio_asset_id: audioId,
        provider: transcript.provider,
        model: transcript.model,
        transcript: selectedTranscript.transcript,
        confidence: transcript.confidence ?? undefined,
        raw_response: {
          source: "agent_harness_transcribe",
          metadata: {
            ...(transcript.metadata ?? {}),
            transcript_source: selectedTranscript.source,
          },
        },
      });

      void api.post(`/sessions/${sessionId}/turns/${turnId}/speech-metrics`, {
        audio_asset_id: audioId,
        duration_ms: durationMs,
        transcript: selectedTranscript.transcript,
        asr_confidence: transcript.confidence ?? undefined,
        raw_metrics: {
          source: "web_live_auto",
          transcript_source: selectedTranscript.source,
        },
      }).catch(() => undefined);

      const consumeResponse = await orchestratorApi.post<AgentResponse>(`/agent/sessions/${sessionId}/consume-asr`, {
        turn_id: turnId,
        asr_text: selectedTranscript.transcript,
        audio_asset_id: audioId,
        asr_confidence: transcript.confidence ?? undefined,
        session_state: agentStateRef.current ?? {},
      });
      await dispatchAgentResponse(consumeResponse.data);
      await continueAgentFlow(consumeResponse.data);
    } catch (err) {
      console.error("Answer processing failed", err);
      if (err instanceof Error && (err.message === "synthetic_asr_transcript" || err.message === "transcript_unavailable")) {
        throw err;
      }
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

      const consumeResponse = await orchestratorApi.post<AgentResponse>(`/agent/sessions/${sessionId}/consume-asr`, {
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
      const nextResponse = await orchestratorApi.post<AgentResponse>(`/agent/sessions/${sessionId}/next-turn`, {
        session_state: response.state,
      });
      await dispatchAgentResponse(nextResponse.data);
      await continueAgentFlow(nextResponse.data);
      return;
    }

    if (response.next_action === "score_session") {
      completionRedirectRef.current = true;
      await scorePersistAndFinish(response.state);
      return;
    }

    if (response.next_action === "finish_session") {
      completionRedirectRef.current = true;
      if (hasPersistableScoreReport(response)) {
        await api.post(`/sessions/${sessionId}/finish`);
        await persistScoreReport(response);
        await dispatchAgentResponse(response);
        return;
      }
      await api.post(`/sessions/${sessionId}/finish`);
    }
  }

  async function scorePersistAndFinish(sessionState: Record<string, unknown>) {
    if (scoringInProgressRef.current) return;
    scoringInProgressRef.current = true;
    completionRedirectRef.current = true;
    sessionStatusRef.current = "scoring";
    setSessionState("processing");
    setNotice("Generating your score report...");
    setError("");
    try {
      const scoringResponse = await orchestratorApi.post<AgentResponse>(`/agent/sessions/${sessionId}/score`, {
        session_state: sessionState,
      });
      if (!hasPersistableScoreReport(scoringResponse.data)) {
        await dispatchAgentResponse(scoringResponse.data);
        setError(scoreRetryMessage(scoringResponse.data) || "No score report was generated. Please submit at least one scorable answer before finishing.");
        setNotice("");
        setSessionState("idle");
        completionRedirectRef.current = false;
        sessionStatusRef.current = session?.status ?? null;
        return;
      }

      await api.post(`/sessions/${sessionId}/finish`);
      await persistScoreReport(scoringResponse.data);
      await dispatchAgentResponse(scoringResponse.data);
      if (!scoringResponse.data.events.some((event) => event.type === "report.ready")) {
        router.replace(`/v2/report/${sessionId}`);
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
  restoreSessionFromSavedStateRef.current = restoreSessionFromSavedState;
  processUploadedAnswerRef.current = processUploadedAnswer;
  scorePersistAndFinishRef.current = scorePersistAndFinish;

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
      void primeMicrophone();
    } catch {
      setError("Recording consent could not be saved.");
    } finally {
      setConsentSaving(false);
    }
  };

  const beginUserRecording = async () => {
    if (isExitingSessionRef.current || isRecordingRef.current || isRecordingStartingRef.current) return;
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
      if (isExitingSessionRef.current) {
        discardRecording();
        return;
      }
      startBrowserSpeechRecognition();
      recordingStartedAtRef.current = Date.now();
      timerPhaseRef.current = "speaking";
      if (speakingSecondsRef.current > 0) {
        setSuggestedSeconds(speakingSecondsRef.current);
      }
      setSessionState("user_speaking");
      sendMessage("user.recording_started", { turn_id: currentTurnIdRef.current });
    } catch (err) {
      recordingStartedAtRef.current = null;
      if (err instanceof Error && err.message === "recording_cancelled") {
        return;
      }
      setError(microphoneStartErrorMessage(err));
    }
  };

  const cancelOpeningMicrophone = () => {
    releaseLocalRecordingResources();
    setNotice("Microphone opening cancelled. Tap Start speaking when you are ready.");
  };

  const replayQuestion = () => {
    if (!examinerAudioId || isRecording || isRecordingStarting) return;
    isReplayingRef.current = true;
    setIsReplaying(true);
    audioPlayerRef.current?.replay();
  };

  const handleReconnect = () => {
    reconnect();
    const savedState = agentStateRef.current;
    if (savedState?.status === "ready_to_score") {
      void scorePersistAndFinishRef.current(savedState);
      return;
    }
    if (!currentTurnIdRef.current) {
      if (session && hasPersistedAgentState(session)) {
        void restoreSessionFromSavedState(session);
        return;
      }
      agentPlanStartedRef.current = false;
      void startAgentPlanRef.current();
    }
  };

  const pauseCurrentSession = async () => {
    if (completionRedirectRef.current || !isPauseableSessionStatus(sessionStatusRef.current) || pauseRequestInFlightRef.current) return;
    pauseRequestInFlightRef.current = true;
    try {
      await persistAgentState(agentStateRef.current);
      const response = await api.post<{ session: SessionDetails }>(`/sessions/${sessionId}/pause`);
      sessionStatusRef.current = response.data.session.status;
      setSession(response.data.session);
    } finally {
      pauseRequestInFlightRef.current = false;
    }
  };

  const discardActiveRecording = async () => {
    releaseLocalRecordingResources();
    setSessionState("idle");
  };

  const handleExitSession = async () => {
    isExitingSessionRef.current = true;
    setError("");
    setNotice("Pausing session...");
    try {
      await discardActiveRecording();
      await pauseCurrentSession();
    } catch {
      setError("Session pause could not be confirmed, but you can still reopen recent in-progress sessions from Practice.");
    } finally {
      router.push("/practice");
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  return (
    <AcademicShell activePath="/v2/practice" userName={user?.display_name || user?.email} userRole={user?.role} className="pb-28 md:pb-8">
      <AudioPlayer
        ref={audioPlayerRef}
        audioId={examinerAudioId}
        onAutoplayBlocked={() => {
          const wasReplay = isReplayingRef.current;
          isReplayingRef.current = false;
          setIsReplaying(false);
          if (wasReplay) return;
          if (!questionPlaybackDoneRef.current) {
            questionPlaybackDoneRef.current = true;
            if (sessionState === "examiner_speaking") {
              if (timerPhaseRef.current === "preparation") {
                setSessionState("user_preparing");
                setNotice("浏览器阻止了考官音频自动播放，思考倒计时已开始。您可点击 Replay 收听考官语音。");
              } else {
                setSessionState("idle");
                setNotice("浏览器阻止了考官音频自动播放。请点击 Replay 收听语音，或直接点击 Start speaking 开始作答。");
              }
              return;
            }
          }
          setNotice("浏览器阻止了考官音频自动播放。您可点击 Replay 收听考官语音。");
        }}
        onPlaybackError={() => {
          isReplayingRef.current = false;
          setIsReplaying(false);
          if (!questionPlaybackDoneRef.current) {
            questionPlaybackDoneRef.current = true;
            if (sessionState === "examiner_speaking") {
              if (timerPhaseRef.current === "preparation") {
                setSessionState("user_preparing");
              } else {
                setSessionState("idle");
              }
            }
          }
          setError("考官音频加载失败。请点击 Replay 重试，或直接点击 Start speaking 开始作答。");
        }}
        onFinished={() => {
          const wasReplay = isReplayingRef.current;
          const action = examinerAudioFinishAction({
            sessionState,
            questionPlaybackDone: questionPlaybackDoneRef.current,
            timerPhase: timerPhaseRef.current,
            isReplay: wasReplay,
          });
          questionPlaybackDoneRef.current = true;
          isReplayingRef.current = false;
          setIsReplaying(false);
          if (isExitingSessionRef.current) return;
          if (action === "start_preparation") {
            setSessionState("user_preparing");
          } else if (action === "start_recording") {
            void beginUserRecording();
          }
        }}
        autoPlay={sessionState === "examiner_speaking"}
      />

      <PageHeader
        eyebrow="Live Exam Room · V2 Orchestrator"
        title="Live Session"
        titleZh="实时口语"
        description="Stay focused on the current question, timer, recording status and ASR evidence."
        actions={
          <>
            <StatusBadge tone={socketStatus === "connected" ? "sage" : "coral"}>
              {socketStatus === "connected" ? <Wifi className="mr-1 h-3 w-3" /> : <WifiOff className="mr-1 h-3 w-3" />}
              {socketStatus}
            </StatusBadge>
            <Button type="button" variant="soft" onClick={() => void handleExitSession()}>
              <PauseCircle className="mr-2 h-4 w-4" />
              Pause & exit
            </Button>
          </>
        }
      />

      {!consentLoading && !recordingConsentAccepted && (
        <Panel className="border-academic-score/35 bg-academic-score-soft">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex gap-3">
              <ShieldCheck className="mt-1 h-5 w-5 text-amber-800" />
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
        <Panel className="border-academic-score/35 bg-academic-score-soft">
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
                className="mt-3 min-h-20 w-full resize-y rounded-md border border-academic-paper-border bg-white px-3 py-2 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-academic-score focus:ring-2 focus:ring-academic-score/20"
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
        <Panel className="border-academic-accent/20 bg-academic-accent-soft text-sm text-blue-800">
          {notice}
        </Panel>
      )}

      <Panel className="lg:hidden">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-academic-accent">Session Progress</p>
            <p className="text-sm font-semibold text-slate-900">
              Part {currentPart} · {formatState(sessionState)}
            </p>
          </div>
          <StatusBadge tone={socketStatus === "connected" ? "sage" : "coral"}>{socketStatus}</StatusBadge>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-100">
          <div className="h-full rounded-full bg-academic-score" style={{ width: `${Math.max(progressPercent, ((activeStepIndex + 1) / 4) * 18)}%` }} />
        </div>
        <div className="mt-3 grid grid-cols-4 gap-2 text-center text-[11px] text-slate-500">
          {timeline.map((item) => (
            <span key={item.part} className={item.part === currentPart ? "font-semibold text-amber-800" : ""}>
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
                      completed ? "border-emerald-600 text-emerald-600" : active ? "border-academic-score text-academic-score" : "border-slate-200 text-slate-400"
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
                <p className="text-xs font-semibold uppercase tracking-wide text-academic-score">{formatMode(session?.mode)} · Part {currentPart}</p>
                <h2 className="mt-1 font-serif text-2xl text-white">Examiner Stage</h2>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="soft"
                  size="sm"
                  className="px-3 text-xs"
                  onClick={() => setShowQuestionText((current) => !current)}
                >
                  {showQuestionText ? <EyeOff className="mr-2 h-3.5 w-3.5" /> : <Eye className="mr-2 h-3.5 w-3.5" />}
                  {showQuestionText ? "Hide text 隐藏文案" : "Show text 显示文案"}
                </Button>
                <StatusBadge tone={sessionState === "processing" ? "coral" : sessionState === "user_speaking" ? "red" : "teal"}>
                  {formatState(sessionState)}
                </StatusBadge>
              </div>
            </div>
          </div>

          <div className="grid min-h-[560px] min-w-0 max-w-full grid-rows-[1fr_auto] lg:min-h-[620px]">
            <div className="flex min-w-0 flex-col items-center justify-center px-4 py-8 text-center sm:px-5">
              <ExaminerAvatar
                status={sessionState === "examiner_speaking" || isReplaying ? "speaking" : sessionState === "user_speaking" ? "listening" : "idle"}
                className="h-28 w-28 border-academic-score/45 bg-academic-navy text-academic-score sm:h-36 sm:w-36"
              />
              <p className="mt-5 text-xs font-semibold uppercase tracking-[0.22em] text-academic-accent">
                Examiner {sessionState === "examiner_speaking" || isReplaying ? "speaking" : sessionState === "user_speaking" ? "listening" : "ready"}
              </p>
              {showQuestionText ? (
                <h3 className="mt-4 w-full max-w-3xl break-words font-serif text-xl leading-relaxed text-white sm:text-2xl md:text-3xl">
                  &quot;{examinerText}&quot;
                </h3>
              ) : (
                <p className="mt-4 w-full max-w-3xl text-sm italic leading-relaxed text-slate-400">
                  Question text hidden. 考题文案已隐藏，请听考官语音，可点击 Show text 重新显示。
                </p>
              )}

              {cueCard && showQuestionText && (
                <div className="mt-6 w-full max-w-2xl overflow-hidden rounded-lg border border-academic-score/30 bg-academic-paper p-3 text-left text-academic-navy sm:p-4">
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
                          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-academic-score" />
                          <span>{point}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {cueCard && !showQuestionText && (
                <div className="mt-6 flex w-full max-w-2xl items-center justify-between gap-3 rounded-lg border border-academic-score/30 bg-white/5 px-4 py-3">
                  <StatusBadge tone="gold">Cue Card · 文案已隐藏</StatusBadge>
                  <StatusBadge tone="coral">{cueCard.preparation_seconds ?? 60}s prep</StatusBadge>
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
                <InlineKpi
                  icon={Radio}
                  label="Microphone"
                  value={isRecording ? "Recording" : isRecordingStarting ? (isRecordingStartSlow ? "Waiting permission" : "Opening") : recordingConsentAccepted ? "Ready" : "Consent required"}
                />
                <InlineKpi icon={UploadCloud} label="Turn" value={currentTurnId ? shortId(currentTurnId) : "-"} />
                <InlineKpi icon={TimerIcon} label="Timer" value={suggestedSeconds > 0 ? `${suggestedSeconds}s` : "Manual"} />
              </div>
            </div>

            <div className="min-w-0 border-t border-white/10 bg-black/20 px-4 py-5 sm:px-5">
              <div className="mb-4 grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                <Waveform active={isRecording} bars={24} className="w-full max-w-full justify-center overflow-hidden md:justify-start" />
                <div className="flex min-w-0 items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2">
                  <TimerIcon className="h-4 w-4 text-academic-accent" />
                  {suggestedSeconds > 0 ? (
                    timerIsActive ? (
                      <Timer
                        key={`${currentTurnId ?? "turn"}-${sessionState}-${suggestedSeconds}`}
                        initialSeconds={suggestedSeconds}
                        className="bg-transparent p-0 text-lg text-academic-score"
                        onTimeUp={() => {
                          if (sessionState === "user_preparing") {
                            void beginUserRecording();
                          }
                          if (sessionState === "user_speaking") {
                            if (examSettingsRef.current.autoStopRecording) {
                              void handleStopRecording();
                            } else {
                              setNotice("建议作答时间已到，录音仍在继续，准备好后请点击 Finish 提交。Suggested time is up; press Finish when ready.");
                            }
                          }
                        }}
                      />
                    ) : (
                      <span className="font-mono text-lg text-academic-score">{formatTimerSeconds(suggestedSeconds)}</span>
                    )
                  ) : (
                    <span className="font-mono text-lg text-academic-score">--:--</span>
                  )}
                </div>
              </div>

              <div className="fixed bottom-3 left-3 right-3 z-20 grid grid-cols-2 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white/95 p-3 shadow-2xl backdrop-blur md:static md:flex md:flex-wrap md:border-white/10 md:bg-transparent md:p-0 md:shadow-none">
                <Button
                  type="button"
                  variant="soft"
                  className="w-full min-w-0 px-3 text-xs sm:text-sm md:w-auto"
                  onClick={replayQuestion}
                  disabled={!examinerAudioId || isRecording || isRecordingStarting}
                >
                  <Play className="mr-2 h-4 w-4" />
                  Replay
                </Button>
                {sessionState === "user_speaking" ? (
                  <Button type="button" variant="destructive" size="lg" className="w-full min-w-0 px-3 text-xs sm:text-sm md:w-auto" onClick={() => void handleStopRecording()}>
                    <Square className="mr-2 h-4 w-4" />
                    Finish
                  </Button>
                ) : isRecordingStarting ? (
                  <Button type="button" variant="soft" size="lg" className="w-full min-w-0 px-3 text-xs sm:text-sm md:w-auto" onClick={cancelOpeningMicrophone}>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Cancel mic
                  </Button>
                ) : (
                  <Button type="button" variant="gold" size="lg" className="w-full min-w-0 px-3 text-xs sm:text-sm md:w-auto" onClick={() => void beginUserRecording()} disabled={!currentTurnId || isRecordingStarting || sessionState === "processing" || sessionState === "completed"}>
                    <Mic2 className="mr-2 h-4 w-4" />
                    Start speaking
                  </Button>
                )}
                <Button type="button" variant="soft" className="w-full min-w-0 px-3 text-xs sm:text-sm md:w-auto" onClick={handleReconnect}>
                  <RefreshCcw className="mr-2 h-4 w-4" />
                  Reconnect
                </Button>
                <Button type="button" variant="soft" className="w-full min-w-0 px-3 text-xs sm:text-sm md:w-auto" onClick={() => setNotice("Operation completed.")}>
                  <AlertTriangle className="mr-2 h-4 w-4" />
                  Issue
                </Button>
              </div>
            </div>
          </div>
        </Panel>

        <div className="grid gap-5">
          <AgentThinkingPanel
            events={orchestratorStream.events}
            status={orchestratorStream.status}
            error={orchestratorStream.error}
            onReconnect={orchestratorStream.reconnect}
          />

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
            {transcriptPreview ? (
              <p className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-700">&quot;{transcriptPreview}&quot;</p>
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
                  <span className="font-serif text-lg text-academic-accent">{item.value}</span>
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

function isReviewOnlySessionStatus(status?: string | null) {
  return status === "completed" || status === "scoring";
}

function isPauseableSessionStatus(status?: string | null) {
  return status === "created" || status === "planned" || status === "in_progress" || status === "paused";
}

function hasPersistedAgentState(session: SessionDetails) {
  const state = asRecord(session.state);
  return Boolean(state && asRecord(state.question_plan));
}

function inferCurrentPart(session: SessionDetails) {
  const active = session.parts?.find((item) => item.status === "in_progress" || item.status === "paused");
  if (active) return active.part;
  const firstOpen = session.parts?.find((item) => item.status !== "completed");
  return firstOpen?.part ?? session.target_part ?? null;
}

function findPendingAnswerTurn(session: SessionDetails, questionText: string) {
  const turns = [...(session.turns ?? [])].reverse().filter((turn) => turn.speaker === "user" && turn.question_text);
  const pending = turns.find(isOpenAnswerTurn);
  if (pending) return pending;
  if (!questionText) return null;
  return turns.find((turn) => isOpenAnswerTurn(turn) && normalizeText(turn.question_text) === normalizeText(questionText)) ?? null;
}

function isOpenAnswerTurn(turn: NonNullable<SessionDetails["turns"]>[number]) {
  return turn.status !== "completed" && !turn.answer_text;
}

function currentPartPlanFromState(state: Record<string, unknown>, part: number) {
  const questionPlan = asRecord(state.question_plan);
  const parts = Array.isArray(questionPlan?.parts) ? questionPlan.parts : [];
  return parts.map(asRecord).find((item) => numberFromUnknown(item?.part) === part) ?? null;
}

function currentPlannedQuestionFromState(state: Record<string, unknown>, session?: SessionDetails) {
  const part = numberFromUnknown(state.current_part) ?? 1;
  const partPlan = currentPartPlanFromState(state, part);
  const questions = Array.isArray(partPlan?.questions) ? partPlan.questions : [];
  const questionIndex = Math.max(0, numberFromUnknown(state.question_index) ?? 0);
  const answeredTexts = answeredQuestionTextsFromState(state, part, session);
  for (let index = questionIndex; index < questions.length; index += 1) {
    const question = asRecord(questions[index]);
    const text = typeof question?.text === "string" ? normalizeText(question.text) : "";
    if (text && !answeredTexts.has(text)) {
      return question;
    }
  }
  const fallback = asRecord(questions[questionIndex]);
  const fallbackText = typeof fallback?.text === "string" ? normalizeText(fallback.text) : "";
  return fallbackText && !answeredTexts.has(fallbackText) ? fallback : null;
}

function answeredQuestionTextsFromState(state: Record<string, unknown>, part: number, session?: SessionDetails) {
  const answers = Array.isArray(state.answers) ? state.answers : [];
  const texts = new Set<string>();
  for (const rawAnswer of answers) {
    const answer = asRecord(rawAnswer);
    if (!answer || numberFromUnknown(answer.part) !== part) continue;
    const text = typeof answer.question_text === "string" ? normalizeText(answer.question_text) : "";
    if (text) texts.add(text);
  }
  const partById = new Map((session?.parts ?? []).map((item) => [item.id, item.part]));
  for (const turn of session?.turns ?? []) {
    if (turn.speaker !== "user" || turn.status !== "completed") continue;
    const turnPart = (turn.part_id ? partById.get(turn.part_id) : undefined) ?? numberFromUnknown(asRecord(turn.metadata)?.part);
    if (turnPart && turnPart !== part) continue;
    const text = typeof turn.question_text === "string" ? normalizeText(turn.question_text) : "";
    if (text) texts.add(text);
  }
  return texts;
}

function cueCardFromPlannedQuestion(question: Record<string, unknown> | null): CueCard | null {
  const cue = asRecord(question?.cue_card);
  if (!cue || typeof cue.prompt !== "string") return null;
  return {
    prompt: cue.prompt,
    bullet_points: stringArrayFromUnknown(cue.bullet_points),
    preparation_seconds: numberFromUnknown(cue.preparation_seconds) ?? undefined,
    speaking_seconds: numberFromUnknown(cue.speaking_seconds) ?? undefined,
  };
}

function restoredTimerPlanFromSavedState(
  state: Record<string, unknown>,
  part: number,
  question: Record<string, unknown> | null,
  settings: ExamFlowSettings,
) {
  const cueCard = cueCardFromPlannedQuestion(question);
  const partPlan = currentPartPlanFromState(state, part);
  return resolveTimerPlan(
    {
      part,
      preparationSeconds: cueCard?.preparation_seconds,
      speakingSeconds:
        cueCard?.speaking_seconds ??
        numberFromUnknown(question?.suggested_seconds) ??
        numberFromUnknown(partPlan?.suggested_seconds) ??
        30,
    },
    settings,
  );
}

function numberArrayFromUnknown(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value
    .map(numberFromUnknown)
    .filter((item): item is number => item !== null)
    .map((item) => Math.trunc(item));
}

function normalizeText(value?: string | null) {
  return (value ?? "").replace(/\s+/g, " ").trim().toLowerCase();
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

function shouldUseBrowserTranscriptFallback(err: unknown) {
  const status = (err as ApiError).response?.status;
  return status === undefined || status === 415 || status === 422 || status === 502 || status === 503 || status === 504;
}

function buildBrowserTranscriptFallback(
  audioId: string,
  audioBlob: Blob,
  durationMs: number,
  browserTranscript?: string,
  upstreamTranscript?: TranscribeAudioResponse | null,
  err?: unknown,
): TranscribeAudioResponse | null {
  const normalizedBrowserTranscript = normalizeTranscriptText(browserTranscript);
  if (!normalizedBrowserTranscript) {
    return null;
  }
  const status = (err as ApiError).response?.status;
  return {
    audio_asset_id: audioId,
    asr_text: normalizedBrowserTranscript,
    language: upstreamTranscript?.language || "en",
    confidence: 0.58,
    provider: "browser_speech_recognition",
    model: "web_speech_api",
    duration_ms: durationMs,
    metadata: {
      browser_fallback: true,
      http_status: status ?? null,
      mime_type: audioBlob.type || "audio/webm",
      size_bytes: audioBlob.size,
      upstream_provider: upstreamTranscript?.provider ?? null,
      upstream_model: upstreamTranscript?.model ?? null,
    },
  };
}

function buildUnavailableTranscriptFallback(
  audioId: string,
  audioBlob: Blob,
  durationMs: number,
  upstreamTranscript?: TranscribeAudioResponse | null,
  err?: unknown,
  reason?: string | null,
): TranscribeAudioResponse {
  const status = (err as ApiError).response?.status;
  return {
    audio_asset_id: audioId,
    asr_text: "",
    language: upstreamTranscript?.language || "en",
    confidence: null,
    provider: "transcript_unavailable",
    model: "empty_transcript",
    duration_ms: durationMs,
    metadata: {
      transcript_unavailable: true,
      fallback_reason: reason ?? "service_unavailable",
      http_status: status ?? null,
      mime_type: audioBlob.type || "audio/webm",
      size_bytes: audioBlob.size,
      upstream_provider: upstreamTranscript?.provider ?? null,
      upstream_model: upstreamTranscript?.model ?? null,
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

async function queryMicrophonePermissionState() {
  if (typeof window === "undefined" || !navigator.permissions?.query) {
    return "unknown";
  }
  try {
    const status = await navigator.permissions.query({ name: "microphone" as PermissionName });
    return status.state;
  } catch {
    return "unknown";
  }
}
