export const MICROPHONE_START_TIMEOUT_MS = 10000;
const TRACK_READY_TIMEOUT_MS = 2000;
const TRACK_READY_POLL_INTERVAL_MS = 50;

type WaitForMicrophoneStreamOptions<TStream> = {
  requestStream: () => Promise<TStream>;
  attemptGeneration: number;
  getCurrentGeneration: () => number;
  onSlow?: () => void;
  onCancelledStream?: (stream: TStream) => void;
  slowTimeoutMs?: number;
};

export async function waitForMicrophoneStream<TStream>({
  requestStream,
  attemptGeneration,
  getCurrentGeneration,
  onSlow,
  onCancelledStream,
  slowTimeoutMs = MICROPHONE_START_TIMEOUT_MS,
}: WaitForMicrophoneStreamOptions<TStream>) {
  let slowTimerId: ReturnType<typeof setTimeout> | null = null;
  try {
    if (slowTimeoutMs > 0) {
      slowTimerId = setTimeout(() => {
        if (getCurrentGeneration() === attemptGeneration) {
          onSlow?.();
        }
      }, slowTimeoutMs);
    }

    const stream = await requestStream();
    if (getCurrentGeneration() !== attemptGeneration) {
      onCancelledStream?.(stream);
      throw new Error('recording_cancelled');
    }
    return stream;
  } finally {
    if (slowTimerId) {
      clearTimeout(slowTimerId);
    }
  }
}

type AudioTrackLike = {
  muted?: boolean;
  readyState?: string;
  addEventListener?: (type: string, listener: () => void, options?: AddEventListenerOptions) => void;
  removeEventListener?: (type: string, listener: () => void, options?: EventListenerOptions) => void;
};

type AudioStreamLike = {
  getAudioTracks?: () => AudioTrackLike[];
};

type WaitForAudioTrackReadyOptions = {
  timeoutMs?: number;
  pollIntervalMs?: number;
};

export async function waitForAudioTrackReady(
  stream: AudioStreamLike | null | undefined,
  {
    timeoutMs = TRACK_READY_TIMEOUT_MS,
    pollIntervalMs = TRACK_READY_POLL_INTERVAL_MS,
  }: WaitForAudioTrackReadyOptions = {},
) {
  const track = stream?.getAudioTracks?.()[0];
  if (!track) return;
  if (isAudioTrackReady(track)) return;

  await new Promise<void>((resolve) => {
    let settled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const finish = () => {
      if (settled) return;
      settled = true;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      if (intervalId) {
        clearInterval(intervalId);
      }
      track.removeEventListener?.("unmute", onReady);
      track.removeEventListener?.("ended", onReady);
      resolve();
    };

    const onReady = () => {
      if (isAudioTrackReady(track) || track.readyState === "ended") {
        finish();
      }
    };

    track.addEventListener?.("unmute", onReady, { once: true });
    track.addEventListener?.("ended", onReady, { once: true });
    intervalId = setInterval(onReady, Math.max(10, pollIntervalMs));
    timeoutId = setTimeout(finish, Math.max(0, timeoutMs));
    onReady();
  });
}

export function shouldResetActiveStream<TStream>(
  currentStream: TStream | null,
  attemptStream: TStream | null,
  isCurrentAttempt: boolean,
) {
  return isCurrentAttempt || (attemptStream !== null && currentStream === attemptStream);
}

function isAudioTrackReady(track: AudioTrackLike) {
  return track.readyState === "live" && track.muted !== true;
}
