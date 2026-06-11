"use client";

import type { ReactNode } from "react";
import { CheckCircle2, FileAudio2, MessageSquareText, UserRound } from "lucide-react";

import { SectionHeading, StatusBadge } from "@/components/academic";
import { cn } from "@/lib/utils";

import { InlineAudioControl } from "./InlineAudioControl";
import { criterionLabels, type ReviewConversationItem } from "./types";

export function ConversationReplay({
  items,
  selectedId,
  onSelect,
}: {
  items: ReviewConversationItem[];
  selectedId?: string | null;
  onSelect: (id: string) => void;
}) {
  if (items.length === 0) {
    return (
      <section className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
        <MessageSquareText className="mx-auto h-8 w-8 text-academic-accent" />
        <h2 className="mt-3 text-base font-semibold text-academic-navy">No replay yet</h2>
        <p className="mt-2 text-sm text-slate-500">Complete at least one answer turn to see examiner questions, responses, and audio here.</p>
      </section>
    );
  }

  return (
    <section className="grid gap-4">
      <SectionHeading icon={MessageSquareText} label="Conversation Replay" labelZh="轮次对话" />
      {items.map((item) => {
        const selected = item.id === selectedId;
        const cueCard = cueCardFromMetadata(item.metadata);
        if (!selected) {
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
              className="grid min-w-0 cursor-pointer gap-2 rounded-lg border border-slate-200 bg-white p-3 text-left shadow-sm transition-colors hover:border-academic-score/50 hover:bg-[#FFFDF6] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-academic-score"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone="teal">Part {item.part}</StatusBadge>
                  <StatusBadge tone="slate">Turn {item.turnIndex + 1}</StatusBadge>
                </div>
                <StatusBadge tone="slate">Open</StatusBadge>
              </div>
              <div className="grid gap-2 text-xs leading-5 text-slate-600 md:grid-cols-2">
                <p className="min-w-0 break-words">
                  <span className="font-semibold text-slate-800">Q: </span>
                  {truncateText(item.questionText || "No examiner question text saved.", 150)}
                </p>
                <p className="min-w-0 break-words">
                  <span className="font-semibold text-slate-800">A: </span>
                  {truncateText(item.answerText || "No usable transcript saved.", 150)}
                </p>
              </div>
            </button>
          );
        }

        return (
          <article
            key={item.id}
            id={`turn-${item.id}`}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(item.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect(item.id);
              }
            }}
            className={cn(
              "min-w-0 cursor-pointer rounded-lg border bg-white p-4 shadow-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-academic-score",
              selected ? "border-academic-score bg-[#FFFDF6]" : "border-slate-200 hover:border-academic-score/50",
            )}
          >
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge tone="teal">Part {item.part}</StatusBadge>
                <StatusBadge tone="slate">Turn {item.turnIndex + 1}</StatusBadge>
                {item.questionId && <StatusBadge tone="slate">QID {shortId(item.questionId)}</StatusBadge>}
              </div>
              {selected && (
                <StatusBadge tone="gold">
                  <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
                  Current Turn
                </StatusBadge>
              )}
            </div>

            <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,0.96fr)_minmax(0,1.04fr)]">
              <ConversationSide
                speaker="Examiner"
                subLabel="English question"
                tone="examiner"
                text={item.questionText || "No examiner question text saved."}
                audio={<InlineAudioControl asset={item.examinerAudio} label="Examiner audio" compact />}
                meta={
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone="slate">Source: IELTSBRO Bank</StatusBadge>
                    <StatusBadge tone="slate">{formatClock(item.examinerAudio?.duration_ms)}</StatusBadge>
                  </div>
                }
              />

              <ConversationSide
                speaker="You"
                subLabel="English answer + audio"
                tone="user"
                align="right"
                text={item.answerText || "No usable transcript saved. Please review the recording."}
                audio={<InlineAudioControl asset={item.userAudio} label="Your recording" compact />}
                beforeText={cueCard ? <CueCardBlock cueCard={cueCard} /> : null}
                afterText={<MetricsGrid item={item} />}
                meta={
                  <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                    <StatusBadge tone="teal">ASR {formatPercent(item.asr?.confidence ?? item.metrics?.asr_confidence)}</StatusBadge>
                    <StatusBadge tone="slate">{formatClock(item.userAudio?.duration_ms)}</StatusBadge>
                  </div>
                }
              />
            </div>

            <EvidenceChips evidence={item.evidence} />
          </article>
        );
      })}
    </section>
  );
}

function ConversationSide({
  speaker,
  subLabel,
  tone,
  text,
  audio,
  meta,
  beforeText,
  afterText,
  align = "left",
}: {
  speaker: string;
  subLabel: string;
  tone: "examiner" | "user";
  text: string;
  audio: ReactNode;
  meta?: ReactNode;
  beforeText?: ReactNode;
  afterText?: ReactNode;
  align?: "left" | "right";
}) {
  const reverse = align === "right";

  return (
    <div className={cn("flex min-w-0 flex-col gap-2", reverse && "lg:items-end")}>
      <SpeakerHeader label={speaker} subLabel={subLabel} tone={tone} reverse={reverse} />
      <div
        className={cn(
          "w-full rounded-lg border p-3",
          tone === "examiner" ? "border-slate-200 bg-slate-50" : "border-academic-score/30 bg-white",
        )}
      >
        {meta && <div className={cn("mb-2 flex flex-wrap gap-2", reverse && "lg:justify-end")}>{meta}</div>}
        {beforeText}
        <p className={cn("whitespace-pre-wrap break-words text-sm leading-6 text-academic-navy", reverse && "lg:text-right")}>{text}</p>
        <div className="mt-3">{audio}</div>
        {afterText}
      </div>
    </div>
  );
}

function SpeakerHeader({
  label,
  subLabel,
  tone,
  reverse = false,
}: {
  label: string;
  subLabel: string;
  tone: "examiner" | "user";
  reverse?: boolean;
}) {
  return (
    <div className={cn("flex items-center gap-2", reverse && "lg:flex-row-reverse lg:text-right")}>
      <span
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-full border",
          tone === "examiner" ? "border-academic-score/35 bg-academic-score-soft text-amber-800" : "border-academic-accent/25 bg-academic-accent-soft text-blue-800",
        )}
      >
        {tone === "examiner" ? <FileAudio2 className="h-4 w-4" /> : <UserRound className="h-4 w-4" />}
      </span>
      <div>
        <p className="text-xs font-semibold text-academic-navy">{label}</p>
        <p className="text-[11px] text-slate-500">{subLabel}</p>
      </div>
    </div>
  );
}

function CueCardBlock({ cueCard }: { cueCard: { prompt: string; bullet_points: string[] } }) {
  return (
    <div className="mb-3 rounded-md border border-academic-score/40 bg-academic-score-soft p-3 text-left">
      <p className="text-xs font-semibold uppercase text-amber-800">Cue Card</p>
      <p className="mt-1 text-sm font-medium text-academic-navy">{cueCard.prompt}</p>
      {cueCard.bullet_points.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-slate-600">
          {cueCard.bullet_points.slice(0, 4).map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MetricsGrid({ item }: { item: ReviewConversationItem }) {
  return (
    <div className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-2 xl:grid-cols-4">
      <Metric label="WPM" value={formatNumber(item.metrics?.wpm)} />
      <Metric label="Long pauses" value={formatInteger(item.metrics?.long_pause_count)} />
      <Metric label="Filler ratio" value={formatPercent(item.metrics?.filler_ratio)} />
      <Metric label="Words" value={formatInteger(item.metrics?.words_count)} />
    </div>
  );
}

function EvidenceChips({ evidence }: { evidence: ReviewConversationItem["evidence"] }) {
  const unique = Array.from(new Set(evidence.map((item) => item.criterion)));
  if (unique.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
      <span className="text-xs font-semibold text-slate-500">Evidence:</span>
      {unique.map((criterion) => (
        <StatusBadge key={criterion} tone="teal">
          {criterionLabels[criterion] ?? criterion}
        </StatusBadge>
      ))}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-2 py-1">
      <span className="block text-[10px] uppercase text-slate-400">{label}</span>
      <span className="font-medium text-slate-700">{value}</span>
    </div>
  );
}

function cueCardFromMetadata(metadata?: Record<string, unknown> | null) {
  const raw = metadata?.cue_card;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const record = raw as Record<string, unknown>;
  const prompt = typeof record.prompt === "string" ? record.prompt : "You should say:";
  const bulletPoints = Array.isArray(record.bullet_points)
    ? record.bullet_points.map((item) => String(item).trim()).filter(Boolean)
    : [];
  return { prompt, bullet_points: bulletPoints };
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${Math.round(value * 100)}%`;
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${Math.round(value)}`;
}

function formatInteger(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return String(value);
}

function formatClock(value?: number | null) {
  if (!value || value <= 0 || !Number.isFinite(value)) return "--";
  const seconds = Math.max(0, Math.floor(value / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${remainder.toString().padStart(2, "0")}`;
}

function shortId(value: string) {
  return value.length > 8 ? value.slice(0, 8) : value;
}

function truncateText(value: string, limit: number) {
  return value.length > limit ? `${value.slice(0, limit - 1)}...` : value;
}
