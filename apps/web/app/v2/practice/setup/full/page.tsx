"use client";

import { useEffect, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  CalendarDays,
  Eye,
  Loader2,
  Mic2,
  PlayCircle,
  Radio,
  Save,
  ShieldCheck,
  StopCircle,
  TimerReset,
  UserRound,
} from "lucide-react";

import { AcademicShell, InlineKpi, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { microphoneStartErrorMessage } from "@/hooks/useAudioRecorder";
import { api } from "@/lib/api";
import { clampPartTimingSeconds, PART_TIMING_LIMITS, type PartTimingKey } from "@/lib/examFlow";
import { useAuthStore } from "@/store/authStore";

type Season = {
  id: string;
  code: string;
  title: string;
  status: string;
  is_active: boolean;
};

type ApiError = {
  response?: {
    data?: {
      message?: string;
    };
  };
};

const examSteps = [
  { part: "Part 1", title: "Daily Topics", titleZh: "日常话题", time: "4-5 min", detail: "Warm-up questions with short follow-ups." },
  { part: "Part 2", title: "Cue Card", titleZh: "话题", time: "3-4 min", detail: "1 minute preparation and long-turn answer." },
  { part: "Part 3", title: "Deep Discussion", titleZh: "深入讨论", time: "4-5 min", detail: "Abstract follow-ups linked to Part 2." },
  { part: "Report", title: "4D Scoring", titleZh: "四维评分", time: "ready after scoring", detail: "Band, evidence, replay and next practice plan." },
];

export default function FullExamSetupPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [season, setSeason] = useState<Season | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [checkingMic, setCheckingMic] = useState(false);
  const [micStatus, setMicStatus] = useState<"idle" | "ok" | "failed">("idle");
  const [recordingConsentAccepted, setRecordingConsentAccepted] = useState(false);
  const [error, setError] = useState("");
  const [settings, setSettings] = useState({
    examinerVoice: "academic_female",
    avatarEnabled: true,
    strictTiming: true,
    saveRecording: true,
    showQuestionText: true,
    autoStopRecording: true,
  });
  const [partTiming, setPartTiming] = useState<Record<PartTimingKey, number>>({
    part1AnswerSeconds: PART_TIMING_LIMITS.part1AnswerSeconds.fallback,
    part2PreparationSeconds: PART_TIMING_LIMITS.part2PreparationSeconds.fallback,
    part2SpeakingSeconds: PART_TIMING_LIMITS.part2SpeakingSeconds.fallback,
    part3AnswerSeconds: PART_TIMING_LIMITS.part3AnswerSeconds.fallback,
  });

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
    async function loadSetupData() {
      setLoading(true);
      setError("");
      try {
        const [seasonResponse, consentResponse] = await Promise.allSettled([
          api.get<{ season: Season }>("/seasons/active"),
          api.get("/privacy/consents?consent_type=recording"),
        ]);
        if (cancelled) return;
        if (seasonResponse.status === "fulfilled") {
          setSeason(seasonResponse.value.data.season);
        }
        if (consentResponse.status === "fulfilled") {
          setRecordingConsentAccepted(Boolean(consentResponse.value.data.latest?.accepted));
        }
      } catch (err: unknown) {
        const apiError = err as ApiError;
        if (!cancelled) {
          setError(apiError.response?.data?.message || "Exam setup data could not be loaded.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadSetupData();
    return () => {
      cancelled = true;
    };
  }, [hasHydrated, isAuthenticated]);

  const updateSetting = (key: keyof typeof settings, value: string | boolean) => {
    setSettings((current) => ({ ...current, [key]: value }));
  };

  const updatePartTiming = (key: PartTimingKey, value: number) => {
    setPartTiming((current) => ({ ...current, [key]: value }));
  };

  const checkMicrophone = async () => {
    setCheckingMic(true);
    setMicStatus("idle");
    try {
      if (typeof window !== "undefined" && window.isSecureContext === false) {
        throw new Error("microphone_insecure_context");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      setMicStatus("ok");
    } catch (err: unknown) {
      setMicStatus("failed");
      setError(microphoneStartErrorMessage(err));
    } finally {
      setCheckingMic(false);
    }
  };

  const startExam = async () => {
    setStarting(true);
    setError("");
    try {
      const response = await api.post("/sessions", {
        mode: "full_exam",
        season_id: season?.id,
        state: {
          strict_timing: settings.strictTiming,
          avatar_enabled: settings.avatarEnabled,
          save_original_recording: settings.saveRecording,
          examiner_voice: settings.examinerVoice,
          show_question_text: settings.showQuestionText,
          auto_stop_recording: settings.autoStopRecording,
          part_timing: {
            part1_answer_seconds: clampPartTimingSeconds("part1AnswerSeconds", partTiming.part1AnswerSeconds),
            part2_preparation_seconds: clampPartTimingSeconds("part2PreparationSeconds", partTiming.part2PreparationSeconds),
            part2_speaking_seconds: clampPartTimingSeconds("part2SpeakingSeconds", partTiming.part2SpeakingSeconds),
            part3_answer_seconds: clampPartTimingSeconds("part3AnswerSeconds", partTiming.part3AnswerSeconds),
          },
          ui_locale_hint: "en-CN",
          setup_surface: "full_exam",
        },
      });
      const sessionId = response.data.session.id;
      await api.post(`/sessions/${sessionId}/start`);
      router.push(`/v2/live/${sessionId}`);
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Mock exam could not be started.");
    } finally {
      setStarting(false);
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  return (
    <AcademicShell activePath="/practice" userName={user?.display_name || user?.email} userRole={user?.role}>
      <PageHeader
        eyebrow="Practice Setup"
        title="Full Mock Exam"
        titleZh="完整模考配置"
        description="Confirm timing, voice, avatar and recording policy before entering the Live exam room."
        actions={
          <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Dashboard
          </Button>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}

      <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_390px]">
        <Panel>
          <SectionHeading icon={TimerReset} label="Exam Flow" labelZh="考试流程" />
          <div className="relative grid gap-3">
            <div className="absolute bottom-8 left-5 top-8 hidden w-px bg-slate-200 sm:block" />
            {examSteps.map((step, index) => (
              <article key={step.part} className="relative grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 sm:grid-cols-[46px_1fr_auto] sm:items-center">
                <span className="z-10 flex h-10 w-10 items-center justify-center rounded-lg border border-academic-score/35 bg-white text-sm font-semibold text-amber-800">
                  {index + 1}
                </span>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone={index < 3 ? "teal" : "gold"}>{step.part}</StatusBadge>
                    <h2 className="text-base font-semibold text-slate-950">
                      {step.title}
                      <span className="ml-2 text-sm font-medium text-slate-500">{step.titleZh}</span>
                    </h2>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{step.detail}</p>
                </div>
                <StatusBadge tone="slate">{step.time}</StatusBadge>
              </article>
            ))}
          </div>
        </Panel>

        <Panel>
          <SectionHeading icon={ShieldCheck} label="Exam Settings" labelZh="考试设置" />
          <div className="grid gap-4">
            <label htmlFor="season" className="grid gap-2 text-sm font-medium text-slate-700">
              <span>Season 当季题库</span>
              <select id="season" value={season?.id ?? ""} disabled className="h-11 rounded-md border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700">
                <option value="">{loading ? "Loading active season..." : season ? season.title : "No active season"}</option>
              </select>
            </label>

            <label htmlFor="examinerVoice" className="grid gap-2 text-sm font-medium text-slate-700">
              <span>Examiner voice 考官声音</span>
              <select
                id="examinerVoice"
                value={settings.examinerVoice}
                onChange={(event) => updateSetting("examinerVoice", event.target.value)}
                className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none transition-colors focus:border-academic-score"
              >
                <option value="academic_female">Academic female</option>
                <option value="academic_male">Academic male</option>
                <option value="neutral">Neutral examiner</option>
              </select>
            </label>

            <ToggleRow
              icon={UserRound}
              title="Avatar enabled"
              titleZh="显示考官头像"
              checked={settings.avatarEnabled}
              onChange={(value) => updateSetting("avatarEnabled", value)}
            />
            <ToggleRow
              icon={TimerReset}
              title="Strict timing"
              titleZh="严格计时"
              checked={settings.strictTiming}
              onChange={(value) => updateSetting("strictTiming", value)}
            />
            <ToggleRow
              icon={Save}
              title="Save original recording"
              titleZh="保存原始录音"
              checked={settings.saveRecording}
              onChange={(value) => updateSetting("saveRecording", value)}
            />
            <ToggleRow
              icon={Eye}
              title="Show question text"
              titleZh="显示题目文本"
              checked={settings.showQuestionText}
              onChange={(value) => updateSetting("showQuestionText", value)}
            />
            <ToggleRow
              icon={StopCircle}
              title="Auto stop recording"
              titleZh="到时或静音时自动停止录音"
              checked={settings.autoStopRecording}
              onChange={(value) => updateSetting("autoStopRecording", value)}
            />

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="mb-3 flex items-center gap-2">
                <TimerReset className="h-4 w-4 text-academic-accent" />
                <div>
                  <p className="text-sm font-semibold text-slate-900">Part timing</p>
                  <p className="text-xs text-slate-500">各 Part 用时与思考时间（秒）</p>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <TimingField
                  id="part1AnswerSeconds"
                  label="Part 1 answer"
                  labelZh="每题作答"
                  value={partTiming.part1AnswerSeconds}
                  onChange={(value) => updatePartTiming("part1AnswerSeconds", value)}
                />
                <TimingField
                  id="part2PreparationSeconds"
                  label="Part 2 preparation"
                  labelZh="思考时间（0 表示跳过"
                  value={partTiming.part2PreparationSeconds}
                  onChange={(value) => updatePartTiming("part2PreparationSeconds", value)}
                />
                <TimingField
                  id="part2SpeakingSeconds"
                  label="Part 2 long turn"
                  labelZh="陈述时间"
                  value={partTiming.part2SpeakingSeconds}
                  onChange={(value) => updatePartTiming("part2SpeakingSeconds", value)}
                />
                <TimingField
                  id="part3AnswerSeconds"
                  label="Part 3 answer"
                  labelZh="每题作答"
                  value={partTiming.part3AnswerSeconds}
                  onChange={(value) => updatePartTiming("part3AnswerSeconds", value)}
                />
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Mic2 className="h-4 w-4 text-academic-accent" />
                  <div>
                    <p className="text-sm font-semibold text-slate-900">Microphone pre-check</p>
                    <p className="text-xs text-slate-500">浏览器麦克风检.</p>
                  </div>
                </div>
                <Button type="button" variant="soft" size="sm" onClick={checkMicrophone} disabled={checkingMic}>
                  {checkingMic ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Radio className="mr-2 h-4 w-4" />}
                  Check
                </Button>
              </div>
              <div className="mt-3">
                {micStatus === "ok" && <StatusBadge tone="sage">Microphone ready</StatusBadge>}
                {micStatus === "failed" && <StatusBadge tone="red">Permission or device issue</StatusBadge>}
                {micStatus === "idle" && <StatusBadge tone="slate">Not checked</StatusBadge>}
              </div>
            </div>

            <InlineKpi icon={CalendarDays} label="Active season" value={season?.title || "Fallback question plan"} />
            <InlineKpi icon={ShieldCheck} label="Recording consent" value={recordingConsentAccepted ? "Accepted" : "Confirm in Live"} />

            <Button type="button" variant="gold" onClick={startExam} disabled={starting || loading}>
              {starting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlayCircle className="mr-2 h-4 w-4" />}
              Start Mock Exam
            </Button>
          </div>
        </Panel>
      </section>
    </AcademicShell>
  );
}

function TimingField({
  id,
  label,
  labelZh,
  value,
  onChange,
}: {
  id: PartTimingKey;
  label: string;
  labelZh: string;
  value: number;
  onChange: (value: number) => void;
}) {
  const { min, max } = PART_TIMING_LIMITS[id];
  return (
    <label htmlFor={id} className="grid gap-1 text-sm font-medium text-slate-700">
      <span>
        {label}
        <span className="ml-1 text-xs font-normal text-slate-500">{labelZh}</span>
      </span>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        onBlur={(event) => {
          const clamped = clampPartTimingSeconds(id, Number(event.target.value));
          onChange(clamped ?? PART_TIMING_LIMITS[id].fallback);
        }}
        className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none transition-colors focus:border-academic-score"
      />
      <span className="text-[11px] font-normal text-slate-400">{min}–{max}s</span>
    </label>
  );
}

function ToggleRow({
  icon: Icon,
  title,
  titleZh,
  checked,
  onChange,
}: {
  icon: LucideIcon;
  title: string;
  titleZh: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex min-h-14 cursor-pointer items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
      <span className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-academic-accent" />
        <span>
          <span className="block text-sm font-semibold text-slate-900">{title}</span>
          <span className="text-xs text-slate-500">{titleZh}</span>
        </span>
      </span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-5 w-5 cursor-pointer rounded border-slate-300 text-academic-score accent-academic-score"
      />
    </label>
  );
}
