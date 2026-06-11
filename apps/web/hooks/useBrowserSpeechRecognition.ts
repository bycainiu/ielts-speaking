import { useCallback, useEffect, useRef, useState } from 'react';

type SpeechRecognitionAlternativeLike = {
  transcript?: string;
};

type SpeechRecognitionResultLike = {
  isFinal?: boolean;
  length: number;
  [index: number]: SpeechRecognitionAlternativeLike;
};

type SpeechRecognitionEventLike = {
  resultIndex?: number;
  results?: ArrayLike<SpeechRecognitionResultLike>;
};

type SpeechRecognitionErrorEventLike = {
  error?: string;
};

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

type BrowserSpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

function recognitionConstructor() {
  if (typeof window === 'undefined') return null;
  const browserWindow = window as BrowserSpeechWindow;
  return browserWindow.SpeechRecognition || browserWindow.webkitSpeechRecognition || null;
}

function transcriptFromResult(result?: SpeechRecognitionResultLike | null) {
  if (!result || result.length <= 0) return '';
  return String(result[0]?.transcript || '').replace(/\s+/g, ' ').trim();
}

export function useBrowserSpeechRecognition(language = 'en-US') {
  const [isSupported, setIsSupported] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [finalTranscript, setFinalTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [lastError, setLastError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const finalTranscriptRef = useRef('');
  const interimTranscriptRef = useRef('');
  const stopResolverRef = useRef<((transcript: string) => void) | null>(null);

  const mergedTranscript = useCallback(() => {
    return `${finalTranscriptRef.current} ${interimTranscriptRef.current}`.replace(/\s+/g, ' ').trim();
  }, []);

  const resetTranscript = useCallback(() => {
    finalTranscriptRef.current = '';
    interimTranscriptRef.current = '';
    setFinalTranscript('');
    setInterimTranscript('');
    setLastError(null);
  }, []);

  const cancelRecognition = useCallback(() => {
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    stopResolverRef.current?.(mergedTranscript());
    stopResolverRef.current = null;
    if (recognition) {
      try {
        recognition.abort();
      } catch {
        // 浏览器已经结束识别时无需再抛错。
      }
    }
    setIsCapturing(false);
  }, [mergedTranscript]);

  const stopRecognition = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      return Promise.resolve(mergedTranscript());
    }
    return new Promise<string>((resolve) => {
      stopResolverRef.current = resolve;
      try {
        recognition.stop();
      } catch {
        resolve(mergedTranscript());
      }
    });
  }, [mergedTranscript]);

  const startRecognition = useCallback(() => {
    const Recognition = recognitionConstructor();
    if (!Recognition || recognitionRef.current) {
      return false;
    }

    resetTranscript();

    const recognition = new Recognition();
    recognition.lang = language;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => {
      setIsCapturing(true);
    };
    recognition.onresult = (event) => {
      const results = event.results;
      if (!results) return;
      let nextFinal = finalTranscriptRef.current;
      let nextInterim = '';
      const resultIndex = event.resultIndex ?? 0;
      for (let index = resultIndex; index < results.length; index += 1) {
        const text = transcriptFromResult(results[index]);
        if (!text) continue;
        if (results[index]?.isFinal) {
          nextFinal = `${nextFinal} ${text}`.replace(/\s+/g, ' ').trim();
        } else {
          nextInterim = `${nextInterim} ${text}`.replace(/\s+/g, ' ').trim();
        }
      }
      finalTranscriptRef.current = nextFinal;
      interimTranscriptRef.current = nextInterim;
      setFinalTranscript(nextFinal);
      setInterimTranscript(nextInterim);
    };
    recognition.onerror = (event) => {
      const error = String(event.error || 'speech_recognition_error');
      if (error !== 'aborted') {
        setLastError(error);
      }
    };
    recognition.onend = () => {
      const finalText = mergedTranscript();
      recognitionRef.current = null;
      interimTranscriptRef.current = '';
      setInterimTranscript('');
      setIsCapturing(false);
      stopResolverRef.current?.(finalText);
      stopResolverRef.current = null;
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
      return true;
    } catch (error) {
      recognitionRef.current = null;
      setIsCapturing(false);
      setLastError(error instanceof Error ? error.message : 'speech_recognition_start_failed');
      return false;
    }
  }, [language, mergedTranscript, resetTranscript]);

  useEffect(() => {
    setIsSupported(Boolean(recognitionConstructor()));
  }, []);

  useEffect(() => {
    return () => {
      cancelRecognition();
    };
  }, [cancelRecognition]);

  return {
    isSupported,
    isCapturing,
    finalTranscript,
    interimTranscript,
    lastError,
    startRecognition,
    stopRecognition,
    cancelRecognition,
    resetTranscript,
  };
}
