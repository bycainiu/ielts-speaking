import { useState, useRef, useCallback } from 'react';

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
  const [stream, setStream] = useState<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const mimeTypeRef = useRef('audio/webm');
  const stopPromiseRef = useRef<Promise<Blob> | null>(null);

  const cleanupStream = useCallback((target?: MediaStream | null) => {
    const activeStream = target ?? mediaRecorderRef.current?.stream ?? stream;
    activeStream?.getTracks().forEach((track) => track.stop());
    setStream((current) => (!target || current === activeStream ? null : current));
  }, [stream]);

  const startRecording = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('microphone_not_supported');
    }
    if (typeof MediaRecorder === 'undefined') {
      throw new Error('media_recorder_not_supported');
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      return;
    }

    const microphoneStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    try {
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
      setStream(microphoneStream);
      mediaRecorder.start(250);
      setIsRecording(true);
    } catch (err) {
      microphoneStream.getTracks().forEach((track) => track.stop());
      setStream(null);
      throw err;
    }
  }, []);

  const stopRecording = useCallback((): Promise<Blob> => {
    if (stopPromiseRef.current) {
      return stopPromiseRef.current;
    }

    return new Promise((resolve, reject) => {
      const mediaRecorder = mediaRecorderRef.current;
      if (!mediaRecorder) {
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
  }, [cleanupStream]);

  const stopRecordingWithCache = useCallback((): Promise<Blob> => {
    const promise = stopRecording();
    stopPromiseRef.current = promise;
    return promise;
  }, [stopRecording]);

  return { isRecording, stream, startRecording, stopRecording: stopRecordingWithCache };
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
