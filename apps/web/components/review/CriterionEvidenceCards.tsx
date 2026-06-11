"use client";

import { BarChart3, ChevronDown, Languages, Mic2, Waves } from "lucide-react";

import { Panel, SectionHeading, StatusBadge } from "@/components/academic";

import { criterionLabels, type CriterionScore, type ReviewConversationItem } from "./types";

const criterionIcons = {
  fluency_coherence: Waves,
  lexical_resource: BarChart3,
  grammatical_range_accuracy: Languages,
  pronunciation: Mic2,
};

export function CriterionEvidenceCards({
  criteria,
  items,
}: {
  criteria: CriterionScore[];
  items: ReviewConversationItem[];
}) {
  return (
    <section className="grid gap-4 lg:grid-cols-4">
      {criteria.map((criterion) => {
        const Icon = criterionIcons[criterion.criterion as keyof typeof criterionIcons] ?? BarChart3;
        const usedTurns = turnsUsed(criterion, items);
        return (
          <Panel key={criterion.criterion} className="p-4">
            <SectionHeading icon={Icon} label={criterionLabels[criterion.criterion] ?? criterion.criterion} action={<ChevronDown className="h-4 w-4 text-slate-400" />} />
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="font-serif text-4xl leading-none text-academic-accent">{formatBand(criterion.band)}</p>
                <StatusBadge tone={bandTone(criterion.band)} className="mt-2">{bandLabel(criterion.band)}</StatusBadge>
              </div>
              <p className="text-xs text-slate-500">Confidence {formatPercent(criterion.confidence)}</p>
            </div>
            <dl className="mt-4 grid gap-2 text-xs">
              <EvidenceRow label="Turns used" value={usedTurns || "T1-T5"} />
              <EvidenceRow label="Metrics" value={metricsLabel(criterion.criterion)} />
              <EvidenceRow label="Sources" value="Rubric v2.1, Anchor Set A" />
              <EvidenceRow label="Evidence" value={`${criterion.evidence?.length ?? 0} items`} />
            </dl>
          </Panel>
        );
      })}
    </section>
  );
}

function EvidenceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[84px_minmax(0,1fr)] gap-2 border-t border-slate-100 pt-2">
      <dt className="font-semibold text-slate-500">{label}</dt>
      <dd className="break-words text-slate-700">{value}</dd>
    </div>
  );
}

function turnsUsed(criterion: CriterionScore, items: ReviewConversationItem[]) {
  const ids = new Set((criterion.evidence ?? []).map((item) => item.turn_id).filter(Boolean));
  if (ids.size === 0) return "";
  return items
    .filter((item) => ids.has(item.id))
    .map((item) => `T${item.turnIndex + 1}`)
    .join(", ");
}

function metricsLabel(criterion: string) {
  if (criterion === "fluency_coherence") return "WPM, Pause ratio, Speech length";
  if (criterion === "lexical_resource") return "Lexical diversity, Accuracy";
  if (criterion === "grammatical_range_accuracy") return "Complexity, Accuracy, Range";
  if (criterion === "pronunciation") return "Intelligibility, Stress, Segmentals";
  return "Transcript and evidence";
}

function bandTone(value: number): "sage" | "gold" | "coral" {
  if (value >= 7) return "sage";
  if (value >= 5.5) return "gold";
  return "coral";
}

function bandLabel(value: number) {
  if (value >= 7) return "Strong";
  if (value >= 6) return "Good";
  if (value >= 5) return "Average";
  return "Limited";
}

function formatBand(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(1);
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${Math.round(value * 100)}%`;
}
