import { useState, useRef, useCallback, useEffect } from 'react';

import { MICROPHONE_START_TIMEOUT_MS, shouldResetActiveStream, waitForAudioTrackReady, waitForMicrophoneStream } from './audioRecorderStart';

const AUDIO_MIME_TYPE_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4;codecs=mp4a.40.2',
  'audio/mp4',
  'audio/ogg;codecs=opus',
  'audio/ogg',
];

export function useAudioRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isStartSlow, setIsStartSlow] = useState(false);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const mimeTypeRef = useRef('audio/webm');
  const stopPromiseRef = useRef<Promise<Blob> | null>(null);
  const startPromiseRef = useRef<Promise<void> | null>(null);
  const primePromiseRef = useRef<Promise<void> | null>(null);
  const startGenerationRef = useRef(0);

  const setActiveStream = useCallback((nextStream: MediaStream | null) => {
    streamRef.current = nextStream;
    setStream(nextStream);
  }, []);

  const cleanupStream = useCallback((target?: MediaStream | null) => {
    const activeStream = target ?? mediaRecorderRef.current?.stream ?? streamRef.current;
    activeStream?.getTracks().forEach((track) => {
      try {
        track.stop();
      } catch {
        // 浏览器已经释放轨道时无需额外处理。
      }
    });
    if (!target || streamRef.current === activeStream) {
      setActiveStream(null);
    }
  }, [setActiveStream]);

  const discardRecording = useCallback(() => {
    startGenerationRef.current += 1;
    const mediaRecorder = mediaRecorderRef.current;
    startPromiseRef.current = null;
    primePromiseRef.current = null;
    setIsStarting(false);
    setIsStartSlow(false);
    setIsRecording(false);

    if (mediaRecorder) {
      try {
        if (mediaRecorder.state === 'recording' && typeof mediaRecorder.requestData === 'function') {
          mediaRecorder.requestData();
        }
      } catch {
        // 丢弃录音时不依赖最后一次 dataavailable。
      }
      try {
        if (mediaRecorder.state !== 'inactive') {
          mediaRecorder.stop();
        }
      } catch {
        // 部分移动端在轨道已停止后会抛错，继续释放轨道即可。
      }
      cleanupStream(mediaRecorder.stream);
      mediaRecorderRef.current = null;
    } else {
      cleanupStream();
    }

    audioChunksRef.current = [];
    stopPromiseRef.current = null;
  }, [cleanupStream]);

  const startRecording = useCallback(async () => {
    if (startPromiseRef.current) {
      return startPromiseRef.current;
    }
    if (typeof window !== 'undefined' && window.isSecureContext === false) {
      throw new Error('microphone_insecure_context');
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('microphone_not_supported');
    }
    if (typeof MediaRecorder === 'undefined') {
      throw new Error('media_recorder_not_supported');
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      setIsStartSlow(false);
      setIsRecording(true);
      return;
    }

    const startPromise = (async () => {
      const generation = startGenerationRef.current + 1;
      startGenerationRef.current = generation;
      setIsStarting(true);
      setIsStartSlow(false);

      let microphoneStream: MediaStream | null = null;
      try {
        microphoneStream = await waitForMicrophoneStream({
          requestStream: () => navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
          }),
          attemptGeneration: generation,
          getCurrentGeneration: () => startGenerationRef.current,
          onSlow: () => {
            if (!mediaRecorderRef.current) {
              setIsStartSlow(true);
            }
          },
          onCancelledStream: (nextStream) => {
            nextStream.getTracks().forEach((track) => track.stop());
          },
          slowTimeoutMs: MICROPHONE_START_TIMEOUT_MS,
        });
        await waitForAudioTrackReady(microphoneStream);

        const mimeType = preferredAudioMimeType();
        const options = mimeType ? { mimeType, audioBitsPerSecond: 128000 } : undefined;
        const mediaRecorder = options ? new MediaRecorder(microphoneStream, options) : new MediaRecorder(microphoneStream);
        mimeTypeRef.current = mediaRecorder.mimeType || mimeType || 'audio/webm';

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            audioChunksRef.current.push(event.data);
          }
        };

        mediaRecorderRef.current = mediaRecorder;
        audioChunksRef.current = [];
        stopPromiseRef.current = null;
        setActiveStream(microphoneStream);
        mediaRecorder.start(250);
        setIsStartSlow(false);
        setIsRecording(true);
      } catch (err) {
        microphoneStream?.getTracks().forEach((track) => track.stop());
        if (shouldResetActiveStream(streamRef.current, microphoneStream, startGenerationRef.current === generation)) {
          setActiveStream(null);
          setIsStartSlow(false);
        }
        throw err;
      } finally {
        if (startGenerationRef.current === generation) {
          setIsStarting(false);
          setIsStartSlow(false);
        }
      }
    })().finally(() => {
      if (startPromiseRef.current === startPromise) {
        startPromiseRef.current = null;
      }
    });

    startPromiseRef.current = startPromise;
    return startPromise;
  }, [setActiveStream]);

  const primeMicrophone = useCallback(async () => {
    if (primePromiseRef.current) {
      return primePromiseRef.current;
    }
    if (typeof window !== 'undefined' && window.isSecureContext === false) {
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      return;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      return;
    }

    const primePromise = (async () => {
      let previewStream: MediaStream | null = null;
      try {
        previewStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
        await waitForAudioTrackReady(previewStream, { timeoutMs: 2500, pollIntervalMs: 50 });
      } catch {
        // 首次预热失败不阻断正式录音，仍允许用户在点击录音时再次申请设备。
      } finally {
        previewStream?.getTracks().forEach((track) => {
          try {
            track.stop();
          } catch {
            // 预热流已被浏览器释放时无需重复处理。
          }
        });
      }
    })().finally(() => {
      if (primePromiseRef.current === primePromise) {
        primePromiseRef.current = null;
      }
    });

    primePromiseRef.current = primePromise;
    return primePromise;
  }, []);

  const stopRecording = useCallback((): Promise<Blob> => {
    if (stopPromiseRef.current) {
      return stopPromiseRef.current;
    }

    const stopPromise = new Promise<Blob>((resolve, reject) => {
      const mediaRecorder = mediaRecorderRef.current;
      if (!mediaRecorder) {
        setIsRecording(false);
        setIsStarting(false);
        setIsStartSlow(false);
        cleanupStream();
        resolve(new Blob([], { type: mimeTypeRef.current || 'audio/webm' }));
        return;
      }

      let timeoutId: ReturnType<typeof setTimeout> | null = null;
      let stopDelayId: ReturnType<typeof setTimeout> | null = null;
      let settled = false;

      const clearTimers = () => {
        if (timeoutId) {
          clearTimeout(timeoutId);
          timeoutId = null;
        }
        if (stopDelayId) {
          clearTimeout(stopDelayId);
          stopDelayId = null;
        }
      };

      const finish = () => {
        if (settled) return;
        settled = true;
        clearTimers();
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeTypeRef.current || mediaRecorder.mimeType || 'audio/webm' });
        setIsRecording(false);
        setIsStarting(false);
        setIsStartSlow(false);
        cleanupStream(mediaRecorder.stream);
        mediaRecorderRef.current = null;
        audioChunksRef.current = [];
        stopPromiseRef.current = null;
        resolve(audioBlob);
      };

      mediaRecorder.onstop = finish;
      mediaRecorder.onerror = () => {
        if (settled) return;
        settled = true;
        clearTimers();
        setIsRecording(false);
        setIsStarting(false);
        setIsStartSlow(false);
        cleanupStream(mediaRecorder.stream);
        mediaRecorderRef.current = null;
        audioChunksRef.current = [];
        stopPromiseRef.current = null;
        reject(new Error('recording_failed'));
      };

      if (mediaRecorder.state === 'inactive') {
        finish();
        return;
      }
      if (mediaRecorder.state === 'recording' && typeof mediaRecorder.requestData === 'function') {
        try {
          mediaRecorder.requestData();
        } catch {
          // 部分移动端浏览器在编码器已 flush 时会抛错。
        }
      }

      timeoutId = setTimeout(finish, 5000);
      stopDelayId = setTimeout(() => {
        try {
          if (mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
          } else {
            finish();
          }
        } catch {
          finish();
        }
      }, 120);
    });

    stopPromiseRef.current = stopPromise;
    return stopPromise;
  }, [cleanupStream]);

  useEffect(() => {
    return () => {
      discardRecording();
    };
  }, [discardRecording]);

  return { isRecording, isStarting, isStartSlow, stream, startRecording, stopRecording, discardRecording, primeMicrophone };
}

export function microphoneStartErrorMessage(err: unknown) {
  if (err instanceof Error) {
    if (err.message === 'microphone_insecure_context') {
      return '当前页面不是安全来源，移动端浏览器会禁止麦克风。请使用 HTTPS 地址访问，或仅在服务器本机用 localhost 测试。';
    }
    if (err.message === 'microphone_start_timeout') {
      return '麦克风打开超时。请关闭其他占用麦克风的应用，然后重新点击开始录音。';
    }
    if (err.message === 'media_recorder_not_supported') {
      return '当前浏览器不支持录音编码能力，请改用最新版 Chrome、Edge 或 Safari。';
    }
    if (err.message === 'microphone_not_supported') {
      return '当前浏览器没有开放麦克风 API。移动端请确认使用 HTTPS 地址访问，并授予麦克风权限。';
    }
    if (err.name === 'NotAllowedError' || err.name === 'SecurityError') {
      return '麦克风权限被浏览器拒绝。请在地址栏站点设置中允许麦克风，并确认页面通过 HTTPS 打开。';
    }
    if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
      return '未检测到可用麦克风。请检查系统麦克风权限或外接设备。';
    }
    if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
      return '麦克风当前被其他应用占用，或系统暂时无法读取输入设备。';
    }
  }
  return '麦克风录音不可用。请检查浏览器权限、HTTPS 访问方式，或更换支持录音的浏览器。';
}

export function audioFileExtension(mimeType: string) {
  const normalized = mimeType.toLowerCase();
  if (normalized.includes('mp4')) return 'm4a';
  if (normalized.includes('ogg')) return 'ogg';
  if (normalized.includes('wav')) return 'wav';
  return 'webm';
}

function preferredAudioMimeType() {
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
    return '';
  }
  return AUDIO_MIME_TYPE_CANDIDATES.find((mimeType) => MediaRecorder.isTypeSupported(mimeType)) ?? '';
}
