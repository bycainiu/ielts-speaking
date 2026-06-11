"use client";

import { CheckCircle2, Circle, FileText, Mic2 } from "lucide-react";

import { Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { cn } from "@/lib/utils";

import type { ReviewConversationItem, ScoreReport } from "./types";

export function ReviewTimeline({
  items,
  selectedId,
  report,
  onSelect,
}: {
  items: ReviewConversationItem[];
  selectedId?: string | null;
  report: ScoreReport | null;
  onSelect: (id: string) => void;
}) {
  const grouped = groupByPart(items);

  return (
    <Panel className="h-fit overflow-hidden lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)]">
      <SectionHeading icon={FileText} label="Session Timeline" labelZh="会话时间线" />
      <div className="relative grid max-h-[calc(100vh-12rem)] gap-5 overflow-y-auto pr-1">
        <div className="absolute bottom-12 left-4 top-5 w-px bg-slate-200" />
        {[1, 2, 3].map((part) => {
          const partItems = grouped.get(part) ?? [];
          if (partItems.length === 0) return null;
          return (
            <div key={part} className="relative grid gap-2">
              <div className="flex items-center gap-3">
                <span className="z-10 flex h-8 w-8 items-center justify-center rounded-full border border-emerald-600 bg-white text-emerald-600">
                  <CheckCircle2 className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <p className="text-base font-semibold text-academic-navy">Part {part}</p>
                  <p className="text-xs text-slate-500">{partLabel(part)}</p>
                </div>
              </div>
              <div className="ml-10 grid gap-2">
                {partItems.map((item) => {
                  const selected = item.id === selectedId;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => onSelect(item.id)}
                      className={cn(
                        "grid min-h-20 cursor-pointer gap-2 rounded-lg border px-3 py-2 text-left transition-colors",
                        selected
                          ? "border-academic-score bg-academic-score-soft shadow-sm"
                          : "border-slate-200 bg-white hover:border-academic-score/50 hover:bg-academic-paper",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-slate-900">Turn {item.turnIndex + 1}</span>
                        <span className="font-mono text-xs text-slate-500">{formatClock(item.userAudio?.duration_ms || item.examinerAudio?.duration_ms)}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                        <span>ASR {formatPercent(item.asr?.confidence ?? item.metrics?.asr_confidence)}</span>
                        <span>Audio</span>
                        <Mic2 className="h-3.5 w-3.5 text-academic-accent" />
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}

        <div className="relative flex gap-3">
          <span className="z-10 flex h-8 w-8 items-center justify-center rounded-full border border-emerald-600 bg-white text-emerald-600">
            {report ? <CheckCircle2 className="h-4 w-4" /> : <Circle className="h-4 w-4" />}
          </span>
          <div className="min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-3">
            <p className="text-base font-semibold text-academic-navy">Report <span className="text-xs font-normal text-slate-500">报告</span></p>
            <StatusBadge tone={report ? "sage" : "slate"} className="mt-2">{report ? "Ready" : "Pending"}</StatusBadge>
            <p className="mt-2 text-xs text-slate-500">{report ? "Report generated" : "等待评分报告"}</p>
          </div>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-500">
        <LegendDot className="bg-emerald-600" label="Completed" />
        <LegendDot className="bg-academic-score" label="Current" />
        <LegendDot className="bg-slate-300" label="Pending" />
      </div>
    </Panel>
  );
}

function LegendDot({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("h-2 w-2 rounded-full", className)} />
      {label}
    </span>
  );
}

function groupByPart(items: ReviewConversationItem[]) {
  const grouped = new Map<number, ReviewConversationItem[]>();
  for (const item of items) {
    const part = item.part || 1;
    grouped.set(part, [...(grouped.get(part) ?? []), item]);
  }
  return grouped;
}

function partLabel(part: number) {
  if (part === 1) return "Hometown";
  if (part === 2) return "Cue Card";
  if (part === 3) return "City life";
  return "Speaking";
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${Math.round(value * 100)}%`;
}

function formatClock(value?: number | null) {
  if (!value || value <= 0 || !Number.isFinite(value)) return "--";
  const seconds = Math.max(0, Math.floor(value / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes.toString().padStart(2, "0")}:${remainder.toString().padStart(2, "0")}`;
}
