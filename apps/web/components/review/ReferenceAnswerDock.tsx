"use client";

import { BookOpen, CheckCircle2, Info, Lightbulb } from "lucide-react";

import { EmptyState, Panel, SectionHeading, StatusBadge } from "@/components/academic";

import { InlineAudioControl } from "./InlineAudioControl";
import type { ReferenceAnswer, ReviewConversationItem } from "./types";

export function ReferenceAnswerDock({
  referenceAnswers,
  selectedItem,
}: {
  referenceAnswers: ReferenceAnswer[];
  selectedItem?: ReviewConversationItem;
}) {
  const selectedReference =
    (selectedItem?.referenceAnswer || referenceAnswers.find((item) => item.turn_id === selectedItem?.id)) ?? referenceAnswers[0];

  return (
    <Panel>
      <SectionHeading
        icon={BookOpen}
        label="Reference Answer"
        labelZh="参考答案"
        action={
          <div className="flex flex-wrap gap-2">
            <StatusBadge tone="teal">Sources: User Background</StatusBadge>
            <StatusBadge tone="slate">IELTSBRO Bank</StatusBadge>
          </div>
        }
      />
      {!selectedReference ? (
        <EmptyState icon={BookOpen} title="暂无参考答案" body="完成评分后会显示个性化参考答案。" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.8fr)_minmax(260px,0.8fr)]">
          <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-academic-navy">Better Answer <span className="text-xs font-normal text-slate-500">(Model Answer)</span></p>
              <span className="font-mono text-xs text-slate-500">01:58</span>
            </div>
            <InlineAudioControl label="Reference audio" compact />
            <p className="mt-3 line-clamp-5 text-sm leading-6 text-slate-700">{selectedReference.answer_text}</p>
            <button type="button" className="mt-3 cursor-pointer text-xs font-semibold text-blue-800 hover:text-academic-navy">
              View full answer
            </button>
          </article>

          <article className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="mb-3 text-sm font-semibold text-academic-navy">Answer Skeleton</p>
            <div className="grid gap-2">
              {Object.entries(selectedReference.skeleton ?? defaultSkeleton()).map(([key, value], index) => (
                <div key={key} className="flex gap-2 text-sm text-slate-700">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                  <span>
                    {index + 1}. {humanizeKey(key)} <span className="text-slate-500">({value})</span>
                  </span>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-academic-navy">
              <Lightbulb className="h-4 w-4 text-academic-score" />
              Personalized Notes
            </p>
            <div className="space-y-3 text-sm leading-6 text-slate-700">
              {(selectedReference.personalization_notes || defaultNotes()).split("\n").filter(Boolean).slice(0, 4).map((note, index) => (
                <p key={`${note}-${index}`} className="flex gap-2">
                  <Info className="mt-1 h-4 w-4 shrink-0 text-academic-accent" />
                  <span>{note.replace(/^[-*]\s*/, "")}</span>
                </p>
              ))}
            </div>
            <button type="button" className="mt-3 cursor-pointer text-xs font-semibold text-blue-800 hover:text-academic-navy">
              View all notes
            </button>
          </article>
        </div>
      )}
    </Panel>
  );
}

function defaultSkeleton() {
  return {
    introduction: "place and location",
    description: "what it is like",
    activities: "what you do there",
    reason: "why you enjoy it",
    linking: "linking words and expressions",
  };
}

function defaultNotes() {
  return "Add more specific details about the place.\nUse a wider range of linkers.\nTry more complex sentences with relative clauses.";
}

function humanizeKey(value: string) {
  return value.replaceAll("_", " ");
}
