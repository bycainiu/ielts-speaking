import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';

interface AudioPlayerProps {
  audioId: string | null;
  onFinished?: () => void;
  autoPlay?: boolean;
}

export function AudioPlayer({ audioId, onFinished, autoPlay = true }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!audioId) {
      setAudioUrl(null);
      return;
    }

    const fetchSignedUrl = async () => {
      try {
        const res = await api.get(`/audio/${audioId}/signed-url`);
        setAudioUrl(res.data.signed_url ?? res.data.url);
      } catch (err) {
        console.error("Failed to get signed url for audio playback", err);
      }
    };

    fetchSignedUrl();
  }, [audioId]);

  useEffect(() => {
    if (audioUrl && audioRef.current && autoPlay) {
      audioRef.current.play().catch(err => console.warn("Auto-play prevented", err));
    }
  }, [audioUrl, autoPlay]);

  if (!audioUrl) return null;

  return (
    <audio 
      ref={audioRef} 
      src={audioUrl} 
      onEnded={() => onFinished && onFinished()} 
      controls={false} // Hidden by default, driven by UI
      className="hidden"
    />
  );
}
