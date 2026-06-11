import { useCallback, useEffect, useRef } from 'react';

import { waitForAudioTrackReady } from './audioRecorderStart';

type WebAudioWindow = Window & {
  webkitAudioContext?: typeof AudioContext;
};

type UseVADOptions = {
  minRecordingMsBeforeSilence?: number;
  requireSpeechBeforeSilence?: boolean;
  silenceLevelThreshold?: number;
  speechLevelThreshold?: number;
  allowOwnStream?: boolean;
};

export function useVAD(
  isRecording: boolean,
  onSilenceDetected: () => void,
  silenceThresholdMs: number = 3000,
  recordingStream?: MediaStream | null,
  options: UseVADOptions = {},
) {
  const {
    minRecordingMsBeforeSilence = 10000,
    requireSpeechBeforeSilence = true,
    silenceLevelThreshold = 8,
    speechLevelThreshold = 14,
    allowOwnStream = true,
  } = options;
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const dataArrayRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const silenceStartRef = useRef<number | null>(null);
  const vadStartedAtRef = useRef<number | null>(null);
  const hasSpeechDetectedRef = useRef(false);
  const silenceHandledRef = useRef(false);
  const animationFrameRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const ownsStreamRef = useRef(false);

  const stopVAD = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (streamRef.current && ownsStreamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
    }
    streamRef.current = null;
    ownsStreamRef.current = false;
    vadStartedAtRef.current = null;
    hasSpeechDetectedRef.current = false;
    silenceHandledRef.current = false;
    silenceStartRef.current = null;
  }, []);

  const detectSilence = useCallback(() => {
    if (!analyserRef.current || !dataArrayRef.current) return;
    
    analyserRef.current.getByteFrequencyData(dataArrayRef.current);
    let sum = 0;
    for (let i = 0; i < dataArrayRef.current.length; i++) {
      sum += dataArrayRef.current[i];
    }
    const average = sum / dataArrayRef.current.length;

    const now = Date.now();
    const elapsedMs = vadStartedAtRef.current ? now - vadStartedAtRef.current : 0;
    if (average >= speechLevelThreshold) {
      hasSpeechDetectedRef.current = true;
      silenceStartRef.current = null;
    } else if (
      !silenceHandledRef.current &&
      average <= silenceLevelThreshold &&
      elapsedMs >= minRecordingMsBeforeSilence &&
      (!requireSpeechBeforeSilence || hasSpeechDetectedRef.current)
    ) {
      if (silenceStartRef.current === null) {
        silenceStartRef.current = now;
      } else if (now - silenceStartRef.current > silenceThresholdMs) {
        silenceHandledRef.current = true;
        onSilenceDetected();
        silenceStartRef.current = null;
      }
    } else {
      silenceStartRef.current = null;
    }
    
    animationFrameRef.current = requestAnimationFrame(detectSilence);
  }, [
    minRecordingMsBeforeSilence,
    onSilenceDetected,
    requireSpeechBeforeSilence,
    silenceLevelThreshold,
    silenceThresholdMs,
    speechLevelThreshold,
  ]);

  const startVAD = useCallback(async () => {
    try {
      if (!recordingStream && !allowOwnStream) {
        return;
      }

      const stream = recordingStream ?? await navigator.mediaDevices.getUserMedia({ audio: true });
      await waitForAudioTrackReady(stream, { timeoutMs: 1500, pollIntervalMs: 50 });
      streamRef.current = stream;
      ownsStreamRef.current = !recordingStream;

      const AudioContextConstructor = window.AudioContext || (window as WebAudioWindow).webkitAudioContext;
      if (!AudioContextConstructor) {
        throw new Error("Web Audio API is not available");
      }
      const audioContext = new AudioContextConstructor();
      if (audioContext.state === "suspended") {
        await audioContext.resume().catch(() => undefined);
      }
      audioContextRef.current = audioContext;
      
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;
      
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
      sourceRef.current = source;
      
      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(new ArrayBuffer(bufferLength));
      dataArrayRef.current = dataArray;
      
      vadStartedAtRef.current = Date.now();
      hasSpeechDetectedRef.current = false;
      silenceHandledRef.current = false;
      silenceStartRef.current = null;
      detectSilence();
    } catch (err) {
      console.warn("VAD setup skipped:", err);
    }
  }, [allowOwnStream, detectSilence, recordingStream]);

  useEffect(() => {
    if (isRecording) {
      startVAD();
    } else {
      stopVAD();
    }
    return () => stopVAD();
  }, [isRecording, startVAD, stopVAD]);
}
