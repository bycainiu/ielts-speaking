export function finiteDurationMs(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : 0;
}

export function mediaSecondsToDurationMs(value?: number | null) {
  return finiteDurationMs(typeof value === "number" ? value * 1000 : 0);
}

export function resolveAudioDurationMs(...values: Array<number | null | undefined>) {
  for (const value of values) {
    const duration = finiteDurationMs(value);
    if (duration > 0) return duration;
  }
  return 0;
}

export function audioProgressPercent(currentTimeSeconds: number, durationMs?: number | null) {
  const duration = finiteDurationMs(durationMs);
  if (!duration || !Number.isFinite(currentTimeSeconds) || currentTimeSeconds <= 0) return 0;
  return Math.min(100, Math.max(0, (currentTimeSeconds * 1000 / duration) * 100));
}
