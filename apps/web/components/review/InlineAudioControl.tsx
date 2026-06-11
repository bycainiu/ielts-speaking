"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, Loader2, Pause, Play, RefreshCw, Volume2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { audioProgressPercent, finiteDurationMs, mediaSecondsToDurationMs, resolveAudioDurationMs } from "@/lib/audioTiming";
import { cn } from "@/lib/utils";

import type { ReviewAudioAsset } from "./types";

type SignedUrlState = {
  assetId: string;
  url: string;
  expiresAt: number;
};

export function InlineAudioControl({
  asset,
  label,
  compact = false,
  className,
}: {
  asset?: ReviewAudioAsset;
  label: string;
  compact?: boolean;
  className?: string;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const signedUrlRef = useRef<SignedUrlState | null>(null);
  const retryingRef = useRef(false);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(finiteDurationMs(asset?.duration_ms));
  const [error, setError] = useState("");

  const totalDuration = resolveAudioDurationMs(duration, asset?.duration_ms);
  const progress = audioProgressPercent(currentTime, totalDuration);

  useEffect(() => {
    setCurrentTime(0);
    setDuration(finiteDurationMs(asset?.duration_ms));
    setPlaying(false);
    setError("");
    retryingRef.current = false;
    signedUrlRef.current = null;
  }, [asset?.id, asset?.duration_ms]);

  const fetchSignedUrl = async (force = false) => {
    if (!asset) return "";
    const cached = signedUrlRef.current;
    if (!force && cached?.assetId === asset.id && cached.expiresAt - Date.now() > 30_000) return cached.url;
    const response = await api.get(`/audio/${asset.id}/signed-url`, { params: { expires_seconds: 300 } });
    const url = response.data.signed_url ?? response.data.url;
    const expiresAt = response.data.expires_at ? Date.parse(response.data.expires_at) : Date.now() + 300_000;
    signedUrlRef.current = { assetId: asset.id, url, expiresAt };
    return url;
  };

  const play = async (forceRefresh = false) => {
    if (!asset || loading) return;
    const audio = audioRef.current;
    if (!audio) return;
    if (!forceRefresh && playing) {
      audio.pause();
      setPlaying(false);
      return;
    }

    setLoading(true);
    setError("");
    try {
      const url = await fetchSignedUrl(forceRefresh);
      if (audio.src !== url) {
        audio.src = url;
        audio.currentTime = 0;
        setCurrentTime(0);
      }
      await audio.play();
      retryingRef.current = false;
      setPlaying(true);
    } catch {
      setError("Audio unavailable");
      setPlaying(false);
    } finally {
      setLoading(false);
    }
  };

  const handleAudioError = async () => {
    if (!asset || retryingRef.current) {
      setError("Audio link expired or unavailable");
      setPlaying(false);
      return;
    }
    retryingRef.current = true;
    await play(true);
  };

  if (!asset) {
    return (
      <div
        onClick={(event) => event.stopPropagation()}
        className={cn("flex min-h-10 items-center gap-2 rounded-md border border-dashed border-slate-200 bg-slate-50 px-3 text-xs text-slate-500", className)}
      >
        <Volume2 className="h-4 w-4 text-slate-400" />
        {label}: 暂无音频
      </div>
    );
  }

  return (
    <div onClick={(event) => event.stopPropagation()} className={cn("rounded-md border border-slate-200 bg-white px-3 py-2", className)}>
      <audio
        ref={audioRef}
        className="hidden"
        playsInline
        preload="metadata"
        onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
        onLoadedMetadata={(event) => setDuration(mediaSecondsToDurationMs(event.currentTarget.duration))}
        onDurationChange={(event) => setDuration(mediaSecondsToDurationMs(event.currentTarget.duration))}
        onEnded={() => setPlaying(false)}
        onError={handleAudioError}
      />
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          aria-label={playing ? `Pause ${label}` : `Play ${label}`}
          title={playing ? `Pause ${label}` : `Play ${label}`}
          onClick={() => void play()}
          disabled={loading}
          className="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-md border border-academic-score/40 bg-academic-score-soft text-amber-800 transition-colors hover:bg-academic-paper disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center justify-between gap-2 text-[11px] text-slate-500">
            <span className="truncate font-medium text-slate-600">{label}</span>
            <span className="shrink-0 font-mono">{formatClock(totalDuration)}</span>
          </div>
          {compact ? (
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-academic-accent" style={{ width: `${progress}%` }} />
            </div>
          ) : (
            <div className="flex h-6 items-end gap-0.5 overflow-hidden">
              {Array.from({ length: 36 }).map((_, index) => (
                <span
                  key={index}
                  className={cn("w-1 rounded-full", index <= Math.floor(progress / 3) ? "bg-[#7DB7D8]" : "bg-slate-200")}
                  style={{ height: `${5 + ((index * 7) % 18)}px` }}
                />
              ))}
            </div>
          )}
        </div>
        <Button type="button" variant="ghost" size="icon" title="Refresh signed URL" onClick={() => void play(true)} disabled={loading} className="h-8 w-8 shrink-0">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>
      {error && (
        <div className="mt-2 flex items-center gap-1 text-[11px] text-red-700">
          <AlertCircle className="h-3.5 w-3.5" />
          {error}
        </div>
      )}
    </div>
  );
}

function formatClock(value?: number | null) {
  if (!value || value <= 0 || !Number.isFinite(value)) return "0:00";
  const seconds = Math.max(0, Math.floor(value / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${remainder.toString().padStart(2, "0")}`;
}
