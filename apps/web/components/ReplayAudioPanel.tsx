"use client";

import { useMemo, useRef, useState } from "react";
import { AlertCircle, Loader2, Pause, Play, RefreshCw, Volume2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export type ReplayAudioAsset = {
  id: string;
  kind: "user_recording" | "examiner_tts" | "reference" | string;
  mime_type?: string;
  duration_ms?: number | null;
  created_at?: string;
};

export type ReplayTurn = {
  id: string;
  turn_index: number;
  speaker: "examiner" | "user" | string;
  question_text?: string | null;
  answer_text?: string | null;
  audio_assets?: ReplayAudioAsset[];
};

type ReplayItem = {
  asset: ReplayAudioAsset;
  turn: ReplayTurn;
};

type SignedUrlState = {
  url: string;
  expiresAt: number;
};

type ReplayAudioPanelProps = {
  turns: ReplayTurn[];
  className?: string;
};

const assetLabel: Record<string, string> = {
  user_recording: "User recording",
  examiner_tts: "Examiner audio",
  reference: "Reference audio",
};

export function ReplayAudioPanel({ turns, className }: ReplayAudioPanelProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const signedUrlsRef = useRef<Record<string, SignedUrlState>>({});
  const retryingRef = useRef<string | null>(null);

  const [activeAssetId, setActiveAssetId] = useState<string | null>(null);
  const [loadingAssetId, setLoadingAssetId] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const replayTurns = useMemo(
    () =>
      turns
        .map((turn) => ({
          turn,
          assets: (turn.audio_assets ?? []).filter((asset) =>
            ["user_recording", "examiner_tts", "reference"].includes(asset.kind),
          ),
        }))
        .filter((item) => item.assets.length > 0),
    [turns],
  );

  const activeDuration = duration || selectedAsset(replayTurns, activeAssetId)?.duration_ms || 0;
  const progress = activeDuration > 0 ? Math.min(100, (currentTime * 1000 / activeDuration) * 100) : 0;

  const fetchSignedUrl = async (assetId: string, force = false) => {
    const cached = signedUrlsRef.current[assetId];
    if (!force && cached && cached.expiresAt - Date.now() > 30_000) {
      return cached.url;
    }

    const response = await api.get(`/audio/${assetId}/signed-url`, {
      params: { expires_seconds: 300 },
    });
    const url = response.data.signed_url ?? response.data.url;
    const expiresAt = response.data.expires_at ? Date.parse(response.data.expires_at) : Date.now() + 300_000;
    signedUrlsRef.current[assetId] = { url, expiresAt };
    return url;
  };

  const playAsset = async (item: ReplayItem, forceRefresh = false) => {
    if (loadingAssetId) return;

    const audio = audioRef.current;
    if (!audio) return;

    if (!forceRefresh && activeAssetId === item.asset.id && playing) {
      audio.pause();
      setPlaying(false);
      return;
    }

    setError(null);
    setLoadingAssetId(item.asset.id);
    try {
      const url = await fetchSignedUrl(item.asset.id, forceRefresh);
      if (activeAssetId !== item.asset.id || audio.src !== url) {
        audio.src = url;
        audio.currentTime = 0;
        setCurrentTime(0);
      }
      setActiveAssetId(item.asset.id);
      await audio.play();
      retryingRef.current = null;
      setPlaying(true);
    } catch {
      setError("Audio is not ready for playback.");
      setPlaying(false);
    } finally {
      setLoadingAssetId(null);
    }
  };

  const refreshActive = async () => {
    const item = activeItem(replayTurns, activeAssetId);
    if (item) {
      await playAsset(item, true);
    }
  };

  const handleAudioError = async () => {
    const item = activeItem(replayTurns, activeAssetId);
    if (!item || retryingRef.current === item.asset.id) {
      setError("Signed URL expired or audio storage is unavailable.");
      setPlaying(false);
      return;
    }
    retryingRef.current = item.asset.id;
    await playAsset(item, true);
  };

  if (replayTurns.length === 0) {
    return (
      <section className={cn("rounded-lg border border-slate-200 bg-white p-5 shadow-sm", className)}>
        <div className="flex items-center gap-3 text-slate-600">
          <Volume2 className="h-5 w-5 text-[#3A7CA5]" />
          <p className="text-sm">暂无音频可回放。</p>
        </div>
      </section>
    );
  }

  return (
    <section className={cn("rounded-lg border border-slate-200 bg-white p-5 shadow-sm", className)}>
      <audio
        ref={audioRef}
        className="hidden"
        onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
        onLoadedMetadata={(event) => setDuration(event.currentTarget.duration * 1000)}
        onEnded={() => setPlaying(false)}
        onError={handleAudioError}
      />

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-serif text-xl text-[#0B132B]">Session Replay</h2>
          <p className="text-sm text-slate-600">保存的录音、考官语音与参考音频会在这里回放。</p>
        </div>
        <Button
          type="button"
          variant="soft"
          size="sm"
          onClick={refreshActive}
          disabled={!activeAssetId || Boolean(loadingAssetId)}
          className="w-fit"
        >
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh URL
        </Button>
      </div>

      {activeAssetId && (
        <div className="mb-5 rounded-md border border-slate-200 bg-slate-50 p-4">
          <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
            <span>{formatClock(currentTime * 1000)}</span>
            <span>{formatClock(activeDuration)}</span>
          </div>
          <input
            aria-label="Replay progress"
            type="range"
            min={0}
            max={100}
            value={Number.isFinite(progress) ? progress : 0}
            onChange={(event) => {
              const audio = audioRef.current;
              if (!audio || activeDuration <= 0) return;
              const nextTime = (Number(event.target.value) / 100) * (activeDuration / 1000);
              audio.currentTime = nextTime;
              setCurrentTime(nextTime);
            }}
            className="h-2 w-full cursor-pointer accent-academic-gold"
          />
        </div>
      )}

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}

      <div className="space-y-4">
        {replayTurns.map(({ turn, assets }) => (
          <div key={turn.id} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase text-[#3A7CA5]">Turn {turn.turn_index + 1}</span>
              <p className="break-words text-sm text-slate-700">{turn.question_text || turn.answer_text || "Saved audio turn"}</p>
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              {assets.map((asset) => {
                const isActive = activeAssetId === asset.id;
                const isLoading = loadingAssetId === asset.id;
                return (
                  <button
                    key={asset.id}
                    type="button"
                    onClick={() => playAsset({ turn, asset })}
                    className={cn(
                      "flex min-h-16 cursor-pointer items-center justify-between rounded-md border px-3 py-2 text-left transition-colors",
                      isActive
                        ? "border-[#D4AF37]/60 bg-[#D4AF37]/10 text-[#0B132B]"
                        : "border-slate-200 bg-white text-slate-700 hover:border-[#D4AF37]/50 hover:bg-[#F7F4EA]",
                    )}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">{assetLabel[asset.kind] ?? "Audio"}</span>
                      <span className="block text-xs text-slate-500">{formatClock(asset.duration_ms)} 路 {asset.mime_type ?? "audio"}</span>
                    </span>
                    <span className="ml-3 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-slate-100 text-[#0B132B]">
                      {isLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : isActive && playing ? (
                        <Pause className="h-4 w-4" />
                      ) : (
                        <Play className="h-4 w-4" />
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function selectedAsset(groups: Array<{ turn: ReplayTurn; assets: ReplayAudioAsset[] }>, assetId: string | null) {
  if (!assetId) return undefined;
  return groups.flatMap((group) => group.assets).find((asset) => asset.id === assetId);
}

function activeItem(groups: Array<{ turn: ReplayTurn; assets: ReplayAudioAsset[] }>, assetId: string | null): ReplayItem | null {
  if (!assetId) return null;
  for (const group of groups) {
    const asset = group.assets.find((item) => item.id === assetId);
    if (asset) return { turn: group.turn, asset };
  }
  return null;
}

function formatClock(value?: number | null) {
  if (!value || value <= 0 || !Number.isFinite(value)) return "0:00";
  const seconds = Math.max(0, Math.floor(value / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${remainder.toString().padStart(2, "0")}`;
}
