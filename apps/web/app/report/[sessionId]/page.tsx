"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  BookOpen,
  ClipboardList,
  FileText,
  History,
  Loader2,
  MessageSquare,
  Send,
  Target,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import { AcademicShell, EmptyState, InlineKpi, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { RadarChart } from "@/components/RadarChart";
import { ReplayAudioPanel, type ReplayTurn } from "@/components/ReplayAudioPanel";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

type SessionResponse = {
  session: {
    id: string;
    mode: string;
    status: string;
    turns: ReplayTurn[];
  };
};

type CriterionName =
  | "fluency_coherence"
  | "lexical_resource"
  | "grammatical_range_accuracy"
  | "pronunciation";

type ReportEvidence = {
  turn_id?: string;
  quote?: string;
  reason?: string;
};

type CriterionScore = {
  id?: string;
  criterion: CriterionName | string;
  band: number;
  confidence: number;
  evidence?: ReportEvidence[];
  suggestions?: string[];
};

type FeedbackItem = {
  id: string;
  category: string;
  priority: number;
  title: string;
  body: string;
  evidence_refs?: ReportEvidence[];
};

type ReferenceAnswer = {
  id: string;
  turn_id?: string | null;
  band_target?: number | null;
  skeleton?: Record<string, string>;
  answer_text: string;
  personalization_notes?: string | null;
};

type StudyPlan = {
  id: string;
  priority: number;
  focus: string;
  task: string;
  due_on?: string | null;
};

type ScoreReport = {
  id: string;
  session_id: string;
  version: number;
  status: string;
  overall_band?: number | null;
  confidence?: number | null;
  disclaimer: string;
  criteria: CriterionScore[];
  feedback_items: FeedbackItem[];
  reference_answers: ReferenceAnswer[];
  study_plans: StudyPlan[];
};

type ReportResponse = {
  report: ScoreReport;
};

type ApiError = {
  response?: {
    data?: {
      message?: string;
    };
  };
};

type FeedbackTargetType = "overall" | "score" | "feedback" | "reference_answer";
type FeedbackVote = "up" | "down";

type FeedbackFormState = {
  vote?: FeedbackVote;
  comment: string;
  saving: boolean;
  notice?: string;
  error?: string;
};

const criterionLabels: Record<string, string> = {
  fluency_coherence: "Fluency",
  lexical_resource: "Lexical",
  grammatical_range_accuracy: "Grammar",
  pronunciation: "Pronunciation",
};

export default function ReportPage() {
  const params = useParams();
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const sessionId = params.sessionId as string;
  const [session, setSession] = useState<SessionResponse["session"] | null>(null);
  const [report, setReport] = useState<ScoreReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reportNotice, setReportNotice] = useState<string | null>(null);
  const [feedbackForms, setFeedbackForms] = useState<Record<string, FeedbackFormState>>({});

  useEffect(() => {
    let cancelled = false;

    async function loadReportPage() {
      setLoading(true);
      setError(null);
      setReportNotice(null);
      try {
        const sessionResponse = await api.get<SessionResponse>(`/sessions/${sessionId}`);
        if (!cancelled) {
          setSession(sessionResponse.data.session);
        }

        try {
          const reportResponse = await api.get<ReportResponse>(`/sessions/${sessionId}/report`);
          if (!cancelled) {
            setReport(reportResponse.data.report);
          }
        } catch {
          if (!cancelled) {
            setReport(null);
            setReportNotice("Score report is not ready yet. 评分报告尚未生成，仍可查看回放和转写。");
          }
        }
      } catch {
        if (!cancelled) {
          setError("Session report could not be loaded. 会话复盘加载失败。");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadReportPage();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const turnById = useMemo(() => {
    const items = new Map<string, ReplayTurn>();
    for (const turn of session?.turns ?? []) {
      items.set(turn.id, turn);
    }
    return items;
  }, [session?.turns]);

  const radarScores = useMemo(
    () =>
      (report?.criteria ?? []).map((item) => ({
        subject: criterionLabels[item.criterion] ?? item.criterion,
        score: item.band,
      })),
    [report?.criteria],
  );

  const feedbackKey = (targetType: FeedbackTargetType, targetId?: string | null) =>
    `${targetType}:${targetId ?? "overall"}`;

  const feedbackForm = (targetType: FeedbackTargetType, targetId?: string | null): FeedbackFormState =>
    feedbackForms[feedbackKey(targetType, targetId)] ?? { comment: "", saving: false };

  const updateFeedbackForm = (
    targetType: FeedbackTargetType,
    targetId: string | null,
    patch: Partial<FeedbackFormState>,
  ) => {
    const key = feedbackKey(targetType, targetId);
    setFeedbackForms((current) => ({
      ...current,
      [key]: {
        ...(current[key] ?? { comment: "", saving: false }),
        ...patch,
      },
    }));
  };

  const submitReportFeedback = async (targetType: FeedbackTargetType, targetId?: string | null, vote?: FeedbackVote) => {
    if (!report) return;
    const key = feedbackKey(targetType, targetId);
    const current = feedbackForms[key] ?? { comment: "", saving: false };
    const selectedVote = vote ?? current.vote;
    if (!selectedVote) {
      updateFeedbackForm(targetType, targetId ?? null, { error: "Choose a vote first. 请先选择反馈方向。", notice: undefined });
      return;
    }

    updateFeedbackForm(targetType, targetId ?? null, {
      vote: selectedVote,
      saving: true,
      error: undefined,
      notice: undefined,
    });
    try {
      const payload: Record<string, unknown> = {
        target_type: targetType,
        vote: selectedVote,
        comment: current.comment.trim() || undefined,
        metadata: {
          session_id: sessionId,
          surface: "report_page",
        },
      };
      if (targetType !== "overall" && targetId) {
        payload.target_id = targetId;
      }
      await api.post(`/reports/${report.id}/feedback`, payload);
      updateFeedbackForm(targetType, targetId ?? null, {
        saving: false,
        vote: selectedVote,
        notice: "Feedback saved. 反馈已保存。",
        error: undefined,
      });
    } catch (err: unknown) {
      const apiError = err as ApiError;
      updateFeedbackForm(targetType, targetId ?? null, {
        saving: false,
        error: apiError.response?.data?.message || "Feedback could not be saved. 反馈保存失败。",
        notice: undefined,
      });
    }
  };

  return (
    <AcademicShell activePath="/history" userName={user?.display_name} userRole={user?.role}>
      <PageHeader
        eyebrow="Session Report"
        title="Score Review"
        titleZh="会话复盘"
        description="Review simulated IELTS criteria, evidence, feedback, reference answers, and replay audio."
        actions={
          <>
            <Button type="button" variant="soft" onClick={() => router.push("/history")}>
              <History className="mr-2 h-4 w-4" />
              History / 历史
            </Button>
            <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Practice / 练习
            </Button>
          </>
        }
      />

      {loading && (
        <Panel className="flex min-h-64 items-center justify-center">
          <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#D4AF37]" />
          <span className="text-sm text-slate-600">Loading report / 正在加载复盘</span>
        </Panel>
      )}

      {error && !loading && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}

      {session && !loading && (
        <>
          {reportNotice && <Panel className="border-[#D4AF37]/30 bg-[#FFF8DF] text-sm text-[#8A6F1D]">{reportNotice}</Panel>}

          <div className="grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.8fr)]">
            <Panel>
              <div className="mb-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
                <div className="min-w-0">
                  <SectionHeading icon={Target} label="Score Overview" labelZh="评分概览" />
                  <h2 className="font-serif text-5xl text-[#0B132B]">
                    {formatBand(report?.overall_band)}
                    <span className="ml-3 align-middle text-base font-sans font-medium text-slate-500">Overall Band</span>
                  </h2>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <StatusBadge tone="teal">Confidence {formatPercent(report?.confidence)}</StatusBadge>
                    <StatusBadge tone="slate">Version {report?.version ?? "-"}</StatusBadge>
                    <StatusBadge tone="gold">{session.mode}</StatusBadge>
                  </div>
                </div>
                <div className="min-w-0 rounded-lg border border-slate-200 bg-slate-50">
                  <RadarChart scores={radarScores.length ? radarScores : undefined} tone="light" />
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                {(report?.criteria ?? []).map((criterion) => (
                  <article key={criterion.criterion} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="break-words text-sm font-semibold text-[#0B132B]">
                          {criterionLabels[criterion.criterion] ?? criterion.criterion}
                        </h3>
                        <p className="mt-1 text-xs text-slate-500">Confidence {formatPercent(criterion.confidence)}</p>
                      </div>
                      <StatusBadge tone="gold" className="text-sm">
                        {formatBand(criterion.band)}
                      </StatusBadge>
                    </div>
                    <EvidenceList evidence={criterion.evidence ?? []} turnById={turnById} />
                    <SuggestionList suggestions={criterion.suggestions ?? []} />
                    {criterion.id && (
                      <InlineFeedbackControls
                        state={feedbackForm("score", criterion.id)}
                        onVote={(vote) => submitReportFeedback("score", criterion.id, vote)}
                      />
                    )}
                  </article>
                ))}
              </div>

              {!report && (
                <EmptyState
                  icon={FileText}
                  title="No persisted score report"
                  body="No persisted score report has been saved for this session yet. 评分完成后这里会显示四维证据。"
                />
              )}
            </Panel>

            <aside className="flex flex-col gap-5">
              <SummaryPanel session={session} report={report} />
              {report && (
                <ReportFeedbackPanel
                  state={feedbackForm("overall")}
                  onVote={(vote) => updateFeedbackForm("overall", null, { vote, error: undefined, notice: undefined })}
                  onCommentChange={(comment) => updateFeedbackForm("overall", null, { comment, error: undefined, notice: undefined })}
                  onSubmit={() => submitReportFeedback("overall")}
                />
              )}
              <FeedbackPanel
                feedbackItems={report?.feedback_items ?? []}
                feedbackState={(targetId) => feedbackForm("feedback", targetId)}
                onVote={(targetId, vote) => submitReportFeedback("feedback", targetId, vote)}
              />
              <StudyPlanPanel studyPlans={report?.study_plans ?? []} />
            </aside>
          </div>

          <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
            <ReplayAudioPanel turns={session.turns ?? []} />
            <ReferenceAnswerPanel
              referenceAnswers={report?.reference_answers ?? []}
              turnById={turnById}
              feedbackState={(targetId) => feedbackForm("reference_answer", targetId)}
              onVote={(targetId, vote) => submitReportFeedback("reference_answer", targetId, vote)}
            />
          </section>

          <p className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs leading-relaxed text-slate-500">
            {report?.disclaimer ?? "AI scoring is for practice reference only, not official IELTS results."}
          </p>
        </>
      )}
    </AcademicShell>
  );
}

function SummaryPanel({ session, report }: { session: SessionResponse["session"]; report: ScoreReport | null }) {
  return (
    <Panel>
      <SectionHeading icon={FileText} label="Summary" labelZh="摘要" />
      <div className="grid gap-3">
        <InlineKpi label="Mode / 模式" value={session.mode} />
        <InlineKpi label="Session / 会话" value={session.status} />
        <InlineKpi label="Report / 报告" value={report?.status ?? "not ready"} />
        <InlineKpi label="Turns / 轮次" value={String(session.turns?.length ?? 0)} />
      </div>
    </Panel>
  );
}

function ReportFeedbackPanel({
  state,
  onVote,
  onCommentChange,
  onSubmit,
}: {
  state: FeedbackFormState;
  onVote: (vote: FeedbackVote) => void;
  onCommentChange: (comment: string) => void;
  onSubmit: () => void;
}) {
  return (
    <Panel tone="paper">
      <SectionHeading icon={MessageSquare} label="Report Feedback" labelZh="报告反馈" />
      <div className="flex gap-2">
        <VoteButton vote="up" active={state.vote === "up"} disabled={state.saving} onClick={() => onVote("up")} />
        <VoteButton vote="down" active={state.vote === "down"} disabled={state.saving} onClick={() => onVote("down")} />
      </div>
      <label className="mt-4 grid gap-2 text-sm text-slate-700">
        <span className="font-medium">Comment / 备注</span>
        <textarea
          value={state.comment}
          onChange={(event) => onCommentChange(event.target.value)}
          rows={3}
          maxLength={2000}
          className="min-h-24 resize-y rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20"
          placeholder="What helped or missed the mark"
        />
      </label>
      <Button type="button" variant="gold" onClick={onSubmit} disabled={state.saving} className="mt-4 w-full">
        {state.saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
        Send / 发送
      </Button>
      {state.notice && <p className="mt-3 text-xs text-[#3E7056]">{state.notice}</p>}
      {state.error && <p className="mt-3 text-xs text-red-700">{state.error}</p>}
    </Panel>
  );
}

function FeedbackPanel({
  feedbackItems,
  feedbackState,
  onVote,
}: {
  feedbackItems: FeedbackItem[];
  feedbackState: (targetId: string) => FeedbackFormState;
  onVote: (targetId: string, vote: FeedbackVote) => void;
}) {
  return (
    <Panel>
      <SectionHeading icon={MessageSquare} label="Feedback" labelZh="改进建议" />
      <div className="space-y-3">
        {feedbackItems.length === 0 && (
          <EmptyState
            icon={MessageSquare}
            title="No feedback yet"
            body="Feedback items will appear after scoring is saved. 评分保存后会显示建议。"
          />
        )}
        {feedbackItems.map((item) => (
          <article key={item.id} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-start justify-between gap-3">
              <h3 className="break-words text-sm font-semibold text-[#0B132B]">{item.title}</h3>
              <StatusBadge tone="coral">P{item.priority}</StatusBadge>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">{item.body}</p>
            <InlineFeedbackControls state={feedbackState(item.id)} onVote={(vote) => onVote(item.id, vote)} />
          </article>
        ))}
      </div>
    </Panel>
  );
}

function StudyPlanPanel({ studyPlans }: { studyPlans: StudyPlan[] }) {
  return (
    <Panel>
      <SectionHeading icon={ClipboardList} label="Next Practice" labelZh="下一步训练" />
      <div className="space-y-3">
        {studyPlans.length === 0 && (
          <EmptyState
            icon={ClipboardList}
            title="No practice tasks"
            body="Practice tasks will appear after feedback is generated. 训练任务会在反馈生成后出现。"
          />
        )}
        {studyPlans.map((item) => (
          <article key={item.id} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-start justify-between gap-3">
              <h3 className="break-words text-sm font-semibold text-[#0B132B]">{item.focus}</h3>
              <StatusBadge tone="gold">P{item.priority}</StatusBadge>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">{item.task}</p>
            {item.due_on && <p className="mt-2 text-xs text-slate-500">Due {item.due_on}</p>}
          </article>
        ))}
      </div>
    </Panel>
  );
}

function ReferenceAnswerPanel({
  referenceAnswers,
  turnById,
  feedbackState,
  onVote,
}: {
  referenceAnswers: ReferenceAnswer[];
  turnById: Map<string, ReplayTurn>;
  feedbackState: (targetId: string) => FeedbackFormState;
  onVote: (targetId: string, vote: FeedbackVote) => void;
}) {
  return (
    <Panel>
      <SectionHeading icon={BookOpen} label="Reference Answer" labelZh="参考答案" />
      <div className="space-y-4">
        {referenceAnswers.length === 0 && (
          <EmptyState
            icon={BookOpen}
            title="No reference answers"
            body="Reference answers will appear after feedback is saved. 参考答案会在反馈生成后显示。"
          />
        )}
        {referenceAnswers.map((item) => {
          const turn = item.turn_id ? turnById.get(item.turn_id) : undefined;
          return (
            <article key={item.id} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <StatusBadge tone="gold">Target {formatBand(item.band_target)}</StatusBadge>
                {turn && <span className="text-xs text-slate-500">Turn {turn.turn_index + 1}</span>}
              </div>
              <SkeletonList skeleton={item.skeleton ?? {}} />
              <p className="mt-3 text-sm leading-relaxed text-slate-700">{item.answer_text}</p>
              {item.personalization_notes && (
                <p className="mt-3 border-t border-slate-200 pt-3 text-xs leading-relaxed text-slate-500">
                  {item.personalization_notes}
                </p>
              )}
              <InlineFeedbackControls state={feedbackState(item.id)} onVote={(vote) => onVote(item.id, vote)} />
            </article>
          );
        })}
      </div>
    </Panel>
  );
}

function InlineFeedbackControls({
  state,
  onVote,
}: {
  state: FeedbackFormState;
  onVote: (vote: FeedbackVote) => void;
}) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-200 pt-3">
      <VoteButton vote="up" active={state.vote === "up"} disabled={state.saving} compact onClick={() => onVote("up")} />
      <VoteButton vote="down" active={state.vote === "down"} disabled={state.saving} compact onClick={() => onVote("down")} />
      {state.saving && <Loader2 className="h-4 w-4 animate-spin text-[#D4AF37]" />}
      {state.notice && <span className="text-xs text-[#3E7056]">{state.notice}</span>}
      {state.error && <span className="text-xs text-red-700">{state.error}</span>}
    </div>
  );
}

function VoteButton({
  vote,
  active,
  disabled,
  compact = false,
  onClick,
}: {
  vote: FeedbackVote;
  active: boolean;
  disabled?: boolean;
  compact?: boolean;
  onClick: () => void;
}) {
  const Icon = vote === "up" ? ThumbsUp : ThumbsDown;
  const label = vote === "up" ? "Useful" : "Not useful";
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={[
        "inline-flex h-9 cursor-pointer items-center justify-center rounded-md border text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        compact ? "w-9" : "min-w-24 gap-2 px-3",
        active
          ? "border-[#D4AF37]/60 bg-[#D4AF37]/15 text-[#8A6F1D]"
          : "border-slate-200 bg-white text-slate-600 hover:border-[#D4AF37]/50 hover:bg-[#F7F4EA] hover:text-[#0B132B]",
      ].join(" ")}
    >
      <Icon className="h-4 w-4" />
      {!compact && <span>{label}</span>}
    </button>
  );
}

function EvidenceList({ evidence, turnById }: { evidence: ReportEvidence[]; turnById: Map<string, ReplayTurn> }) {
  if (evidence.length === 0) return null;
  return (
    <div className="mt-4 space-y-3">
      {evidence.slice(0, 2).map((item, index) => {
        const turn = item.turn_id ? turnById.get(item.turn_id) : undefined;
        const transcript = turn?.answer_text || turn?.question_text;
        return (
          <div key={`${item.turn_id ?? "evidence"}-${index}`} className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <p className="text-xs font-semibold uppercase text-[#3A7CA5]">Evidence</p>
            {item.quote && <blockquote className="mt-1 text-sm leading-relaxed text-slate-700">{item.quote}</blockquote>}
            {item.reason && <p className="mt-2 text-xs leading-relaxed text-slate-500">{item.reason}</p>}
            {transcript && (
              <p className="mt-2 border-t border-slate-200 pt-2 text-xs leading-relaxed text-slate-500">
                Original: {transcript}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function SuggestionList({ suggestions }: { suggestions: string[] }) {
  if (suggestions.length === 0) return null;
  return (
    <ul className="mt-4 space-y-2">
      {suggestions.slice(0, 2).map((item) => (
        <li key={item} className="rounded-md bg-[#FFF8DF] px-3 py-2 text-sm leading-relaxed text-slate-700">
          {item}
        </li>
      ))}
    </ul>
  );
}

function SkeletonList({ skeleton }: { skeleton: Record<string, string> }) {
  const items = Object.entries(skeleton);
  if (items.length === 0) return null;
  return (
    <dl className="grid gap-2">
      {items.map(([key, value]) => (
        <div key={key} className="rounded-md border border-slate-200 bg-white px-3 py-2">
          <dt className="text-xs uppercase text-slate-500">{key.replaceAll("_", " ")}</dt>
          <dd className="text-sm text-slate-700">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function formatBand(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(1);
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}
