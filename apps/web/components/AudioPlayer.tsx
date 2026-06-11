import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { api } from '@/lib/api';

interface AudioPlayerProps {
  audioId: string | null;
  onFinished?: () => void;
  autoPlay?: boolean;
  onAutoplayBlocked?: () => void;
  onPlaybackError?: () => void;
}

export interface AudioPlayerHandle {
  replay: () => void;
}

export const AudioPlayer = forwardRef<AudioPlayerHandle, AudioPlayerProps>(
  function AudioPlayer({ audioId, onFinished, autoPlay = true, onAutoplayBlocked, onPlaybackError }, ref) {
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const [audioUrl, setAudioUrl] = useState<string | null>(null);
    const loadedAudioIdRef = useRef<string | null>(null);
    const onFinishedRef = useRef(onFinished);
    const onAutoplayBlockedRef = useRef(onAutoplayBlocked);
    const onPlaybackErrorRef = useRef(onPlaybackError);
    const pendingAutoPlayRef = useRef(false);

    onFinishedRef.current = onFinished;
    onAutoplayBlockedRef.current = onAutoplayBlocked;
    onPlaybackErrorRef.current = onPlaybackError;

    const playAudio = useCallback(() => {
      const audio = audioRef.current;
      if (!audio || !audio.src) return;
      audio.currentTime = 0;
      audio.play().catch(() => {
        onAutoplayBlockedRef.current?.();
      });
    }, []);

    useImperativeHandle(ref, () => ({
      replay: playAudio,
    }), [playAudio]);

    useEffect(() => {
      if (!audioId) {
        setAudioUrl(null);
        loadedAudioIdRef.current = null;
        pendingAutoPlayRef.current = false;
        return;
      }
      if (audioId === loadedAudioIdRef.current) return;
      loadedAudioIdRef.current = audioId;
      pendingAutoPlayRef.current = autoPlay;

      let cancelled = false;
      const fetchSignedUrl = async () => {
        try {
          const res = await api.get(`/audio/${audioId}/signed-url`);
          if (!cancelled) {
            setAudioUrl(res.data.signed_url ?? res.data.url);
          }
        } catch (err) {
          console.error("Failed to get signed url for audio playback", err);
          if (!cancelled) {
            onPlaybackErrorRef.current?.();
          }
        }
      };

      void fetchSignedUrl();
      return () => {
        cancelled = true;
      };
    }, [audioId, autoPlay]);

    useEffect(() => {
      if (!audioUrl || !audioRef.current) return;
      if (!pendingAutoPlayRef.current) return;
      pendingAutoPlayRef.current = false;
      audioRef.current.play().catch(() => {
        onAutoplayBlockedRef.current?.();
      });
    }, [audioUrl]);

    const handleEnded = useCallback(() => {
      onFinishedRef.current?.();
    }, []);

    const handleError = useCallback(() => {
      onPlaybackErrorRef.current?.();
    }, []);

    return (
      <audio
        ref={audioRef}
        src={audioUrl ?? undefined}
        onEnded={handleEnded}
        onError={handleError}
        controls={false}
        playsInline
        preload="auto"
        className="hidden"
      />
    );
  }
);
