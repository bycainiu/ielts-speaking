// 考试流程的纯函数决策层：考前设置解析、计时方案、考官音频播放完成后的动作。
// 与 live 页面解耦，便于单元测试覆盖 Part 1/2/3 的流程差异。

export type PartTimingSettings = {
  part1AnswerSeconds: number | null;
  part2PreparationSeconds: number | null;
  part2SpeakingSeconds: number | null;
  part3AnswerSeconds: number | null;
};

export type ExamFlowSettings = {
  showQuestionText: boolean;
  autoStopRecording: boolean;
  partTiming: PartTimingSettings;
};

export type PartTimingKey = keyof PartTimingSettings;

export const PART_TIMING_LIMITS: Record<PartTimingKey, { min: number; max: number; fallback: number }> = {
  part1AnswerSeconds: { min: 15, max: 90, fallback: 30 },
  part2PreparationSeconds: { min: 0, max: 120, fallback: 60 },
  part2SpeakingSeconds: { min: 60, max: 240, fallback: 120 },
  part3AnswerSeconds: { min: 20, max: 120, fallback: 45 },
};

export const DEFAULT_EXAM_FLOW_SETTINGS: ExamFlowSettings = {
  showQuestionText: true,
  autoStopRecording: true,
  partTiming: {
    part1AnswerSeconds: null,
    part2PreparationSeconds: null,
    part2SpeakingSeconds: null,
    part3AnswerSeconds: null,
  },
};

export function clampPartTimingSeconds(key: PartTimingKey, value: unknown): number | null {
  const parsed = secondsFromUnknown(value);
  if (parsed === null) return null;
  const { min, max } = PART_TIMING_LIMITS[key];
  return Math.min(max, Math.max(min, Math.round(parsed)));
}

export function normalizeExamFlowSettings(state: Record<string, unknown> | null | undefined): ExamFlowSettings {
  const record = isRecord(state) ? state : {};
  const timing = isRecord(record.part_timing) ? record.part_timing : {};
  return {
    showQuestionText: booleanWithDefault(record.show_question_text, true),
    autoStopRecording: booleanWithDefault(record.auto_stop_recording, true),
    partTiming: {
      part1AnswerSeconds: clampPartTimingSeconds("part1AnswerSeconds", timing.part1_answer_seconds),
      part2PreparationSeconds: clampPartTimingSeconds("part2PreparationSeconds", timing.part2_preparation_seconds),
      part2SpeakingSeconds: clampPartTimingSeconds("part2SpeakingSeconds", timing.part2_speaking_seconds),
      part3AnswerSeconds: clampPartTimingSeconds("part3AnswerSeconds", timing.part3_answer_seconds),
    },
  };
}

export type TimerPlanInput = {
  part: number;
  preparationSeconds?: number | null;
  speakingSeconds?: number | null;
  purpose?: string | null;
  phase?: string | null;
};

export type TimerPlan = {
  phase: "preparation" | "speaking";
  countdownSeconds: number;
  preparationSeconds: number;
  speakingSeconds: number;
};

// 把后端事件里的计时策略和用户考前覆盖合并为一份计时方案。
// Part 2 在思考时间大于 0 时先进入 preparation 阶段。
export function resolveTimerPlan(input: TimerPlanInput, settings: ExamFlowSettings): TimerPlan {
  const timing = settings.partTiming;
  let speakingSeconds = secondsFromUnknown(input.speakingSeconds) ?? 0;
  let preparationSeconds = secondsFromUnknown(input.preparationSeconds) ?? 0;

  if (input.part === 1 && timing.part1AnswerSeconds !== null) {
    speakingSeconds = timing.part1AnswerSeconds;
  }
  if (input.part === 3 && timing.part3AnswerSeconds !== null) {
    speakingSeconds = timing.part3AnswerSeconds;
  }
  if (input.part === 2) {
    if (timing.part2SpeakingSeconds !== null) {
      speakingSeconds = timing.part2SpeakingSeconds;
    }
    if (timing.part2PreparationSeconds !== null) {
      preparationSeconds = timing.part2PreparationSeconds;
    }
  }

  const preparationRequested =
    input.part === 2 || input.purpose === "preparation" || input.phase === "prepare_then_speak";
  const phase: TimerPlan["phase"] = preparationRequested && preparationSeconds > 0 ? "preparation" : "speaking";

  return {
    phase,
    preparationSeconds,
    speakingSeconds,
    countdownSeconds: phase === "preparation" ? preparationSeconds : speakingSeconds,
  };
}

export type ExaminerAudioFinishInput = {
  sessionState: string;
  questionPlaybackDone: boolean;
  timerPhase: "idle" | "preparation" | "speaking";
  isReplay?: boolean;
};

export type ExaminerAudioFinishAction = "none" | "start_preparation" | "start_recording";

// 考官音频播放完成后的动作：只有"首次读完当前题目"才推进流程；
// 用户手动 Replay（题目已读过）或状态已离开 examiner_speaking 时不做任何事，
// 避免重播题目后误触发录音。isReplay 由调用方显式传入作为双重保护。
export function examinerAudioFinishAction(input: ExaminerAudioFinishInput): ExaminerAudioFinishAction {
  if (input.isReplay) return "none";
  if (input.questionPlaybackDone) return "none";
  if (input.sessionState !== "examiner_speaking") return "none";
  return input.timerPhase === "preparation" ? "start_preparation" : "start_recording";
}

function secondsFromUnknown(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function booleanWithDefault(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  if (value === "true") return true;
  if (value === "false") return false;
  return fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
