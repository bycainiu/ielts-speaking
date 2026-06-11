"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  BrainCircuit,
  CalendarCheck,
  Database,
  FileText,
  History,
  Loader2,
  LogOut,
  Mic2,
  PauseCircle,
  PlayCircle,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  UserRound,
  Volume2,
  XCircle,
} from "lucide-react";

import {
  AcademicShell,
  EmptyState,
  InlineKpi,
  MetricCard,
  MiniSparkline,
  PageHeader,
  Panel,
  SectionHeading,
  StatusBadge,
} from "@/components/academic";
import { Button } from "@/components/ui/button";
import { api, billingApi } from "@/lib/api";
import { type SubscriptionSummary } from "@/lib/billing";
import { useAuthStore } from "@/store/authStore";

type ReportHistoryCriterion = {
  band?: number;
  confidence?: number;
};

type ReportHistoryItem = {
  id: string;
  session_id: string;
  mode: string;
  target_part?: number | null;
  report_status: string;
  overall_band?: number | null;
  confidence?: number | null;
  criteria?: Record<string, ReportHistoryCriterion>;
  report_created_at: string;
};

type PracticeSessionItem = {
  id: string;
  mode: string;
  status: string;
  target_part?: number | null;
  started_at?: string | null;
  updated_at: string;
  created_at: string;
};

type ApiError = {
  response?: {
    data?: {
      message?: string;
    };
  };
};

const criterionLabels: Record<string, string> = {
  fluency_coherence: "Fluency",
  lexical_resource: "Lexical",
  grammatical_range_accuracy: "Grammar",
  pronunciation: "Pronunciation",
};

const modeCards = [
  {
    title: "Full Mock Exam",
    titleZh: "完整模考",
    body: "Parts 1-3 with strict timing, examiner TTS, recording, ASR and four-dimension scoring.",
    meta: "11-14 min  |  strict",
    href: "/practice/setup/full",
    icon: PlayCircle,
    tone: "gold" as const,
    cta: "Configure exam",
  },
  {
    title: "Part Practice",
    titleZh: "单项练习",
    body: "Train one target part with practice hints, follow-up intensity and immediate review focus.",
    meta: "5-8 min  |  coached",
    href: "/practice/setup/part",
    icon: SlidersHorizontal,
    tone: "teal" as const,
    cta: "Choose part",
  },
  {
    title: "Topic Practice",
    titleZh: "主题练习",
    body: "Select seasonal topics, combine question bank content with your background profile.",
    meta: "6-10 min  |  topic-led",
    href: "/practice/setup/topic",
    icon: BookOpenCheck,
    tone: "teal" as const,
    cta: "Choose topic",
  },
  {
    title: "Pronunciation Drill",
    titleZh: "发音专项",
    body: "Fixed-text read-aloud practice with word and phoneme-level evidence. No official band score.",
    meta: "3-5 min  |  evidence only",
    href: "/pronunciation",
    icon: Volume2,
    tone: "gold" as const,
    cta: "Open drill",
  },
];

const adminLinks = [
  { label: "Question Admin", labelZh: "题库", href: "/admin/questions", icon: ShieldCheck },
  { label: "Knowledge", labelZh: "知识库", href: "/admin/knowledge", icon: Database },
  { label: "Prompts", labelZh: "提示词", href: "/admin/prompts", icon: Sparkles },
  { label: "Review", labelZh: "审核", href: "/admin/review", icon: BookOpenCheck },
  { label: "Observability", labelZh: "观测", href: "/admin/observability", icon: Activity },
  { label: "Calibration", labelZh: "校准", href: "/admin/calibration", icon: BarChart3 },
];

export default function PracticePage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, logout, fetchUser } = useAuthStore();
  const [reports, setReports] = useState<ReportHistoryItem[]>([]);
  const [resumeSessions, setResumeSessions] = useState<PracticeSessionItem[]>([]);
  const [reportsLoading, setReportsLoading] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [quickStartLoading, setQuickStartLoading] = useState(false);
  const [closingSessionId, setClosingSessionId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [subscription, setSubscription] = useState<SubscriptionSummary | null>(null);

  const canAdmin = user?.role === "operator" || user?.role === "admin";

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/login");
    }
  }, [hasHydrated, isAuthenticated, router]);

  useEffect(() => {
    if (hasHydrated && isAuthenticated && !user) {
      fetchUser();
    }
  }, [fetchUser, hasHydrated, isAuthenticated, user]);

  useEffect(() => {
    if (!hasHydrated || !isAuthenticated) return;

    let cancelled = false;
    async function loadReports() {
      setReportsLoading(true);
      try {
        const response = await api.get<{ reports: ReportHistoryItem[] }>("/reports?limit=6");
        if (!cancelled) {
          setReports(response.data.reports ?? []);
        }
      } catch {
        if (!cancelled) {
          setReports([]);
        }
      } finally {
        if (!cancelled) {
          setReportsLoading(false);
        }
      }
    }

    loadReports();
    return () => {
      cancelled = true;
    };
  }, [hasHydrated, isAuthenticated]);

  useEffect(() => {
    if (!hasHydrated || !isAuthenticated) return;

    let cancelled = false;
    async function loadResumeSessions() {
      setSessionsLoading(true);
      try {
        const responses = await Promise.allSettled([
          api.get<{ sessions: PracticeSessionItem[] }>("/sessions?status=paused&limit=6"),
          api.get<{ sessions: PracticeSessionItem[] }>("/sessions?status=in_progress&limit=6"),
        ]);
        if (cancelled) return;
        const byID = new Map<string, PracticeSessionItem>();
        for (const response of responses) {
          if (response.status !== "fulfilled") continue;
          for (const item of response.value.data.sessions ?? []) {
            byID.set(item.id, item);
          }
        }
        setResumeSessions(
          Array.from(byID.values())
            .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime())
            .slice(0, 5),
        );
      } catch {
        if (!cancelled) {
          setResumeSessions([]);
        }
      } finally {
        if (!cancelled) {
          setSessionsLoading(false);
        }
      }
    }

    loadResumeSessions();
    return () => {
      cancelled = true;
    };
  }, [hasHydrated, isAuthenticated]);

  useEffect(() => {
    if (!hasHydrated || !isAuthenticated || canAdmin) return;
    billingApi
      .getSubscription()
      .then((res) => setSubscription(res.data.subscription))
      .catch(() => setSubscription(null));
  }, [hasHydrated, isAuthenticated, canAdmin]);

  const scoredReports = useMemo(() => reports.filter((item) => typeof item.overall_band === "number"), [reports]);
  const latestBand = scoredReports[0]?.overall_band ?? null;
  const averageBand = scoredReports.length
    ? scoredReports.reduce((total, item) => total + (item.overall_band ?? 0), 0) / scoredReports.length
    : null;
  const trendValues = scoredReports.length
    ? [...scoredReports].reverse().map((item) => item.overall_band ?? 0)
    : [5.5, 6, 6.2, 6.5, 6.5];
  const weakest = useMemo(() => findWeakestCriterion(scoredReports[0]), [scoredReports]);

  const quickStart = async () => {
    setQuickStartLoading(true);
    setError("");
    try {
      const response = await api.post("/sessions", {
        mode: "full_exam",
        state: {
          entry_point: "dashboard_quick_start",
          strict_timing: true,
          ui_locale_hint: "en-CN",
        },
      });
      const sessionId = response.data.session.id;
      await api.post(`/sessions/${sessionId}/start`);
      router.push(`/live/${sessionId}`);
    } catch (err: unknown) {
      const apiError = err as ApiError & { response?: { status?: number; data?: { message?: string; error?: string } } };
      if (apiError.response?.status === 402) {
        setError("练习额度不足，请升级订阅或稍后重试。");
      } else {
        setError(apiError.response?.data?.message || "Practice session could not be started.");
      }
    } finally {
      setQuickStartLoading(false);
    }
  };

  const signOut = () => {
    logout();
    router.push("/login");
  };

  const continueSession = (item: PracticeSessionItem) => {
    if (item.status === "completed" || item.status === "scoring") {
      router.push(`/report/${item.id}`);
      return;
    }
    router.push(`/live/${item.id}`);
  };

  const closeSession = async (item: PracticeSessionItem) => {
    setClosingSessionId(item.id);
    setError("");
    try {
      await api.post(`/sessions/${item.id}/cancel`);
      setResumeSessions((current) => current.filter((sessionItem) => sessionItem.id !== item.id));
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Saved session could not be closed.");
    } finally {
      setClosingSessionId(null);
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  return (
    <AcademicShell activePath="/practice" userName={user?.display_name || user?.email} userRole={user?.role}>
      <PageHeader
        eyebrow="IELTS Speaking Studio"
        title="Practice Dashboard"
        titleZh="练习工作台"
        description={`Welcome back, ${user?.display_name || user?.email}. Choose a realistic mock exam, focused practice, topic rehearsal, or evidence-only pronunciation drill.`}
        actions={
          <>
            <Button type="button" variant="soft" onClick={() => router.push("/history")}>
              <History className="mr-2 h-4 w-4" />
              History
            </Button>
            <Button type="button" variant="soft" onClick={() => router.push("/background")}>
              <UserRound className="mr-2 h-4 w-4" />
              Profile
            </Button>
            <Button type="button" variant="soft" onClick={signOut}>
              <LogOut className="mr-2 h-4 w-4" />
              Sign out
            </Button>
          </>
        }
      />

      {error && (
        <Panel className="border-red-200 bg-red-50 text-sm text-red-700">
          {error}
          {error.includes("额度不足") ? (
            <Button type="button" variant="gold" size="sm" className="ml-3" onClick={() => router.push("/pricing/subscribe")}>
              升级套餐
            </Button>
          ) : null}
        </Panel>
      )}

      {subscription && !canAdmin ? (
        <Panel tone="paper" className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-slate-600">订阅用量</p>
            <p className="mt-1 text-sm text-slate-700">
              {subscription.plan.name_zh}  |  已用 {subscription.credits_used}
              {subscription.credit_limit !== null ? ` / ${subscription.credit_limit}` : " / 不限"}
            </p>
          </div>
          <Button type="button" variant="soft" size="sm" onClick={() => router.push("/settings/subscription")}>
            查看订阅
          </Button>
        </Panel>
      ) : null}

      {(sessionsLoading || resumeSessions.length > 0) && (
        <Panel tone="paper">
          <SectionHeading icon={PauseCircle} label="Continue Sessions" labelZh="继续练习" />
          {sessionsLoading ? (
            <div className="flex min-h-20 items-center justify-center text-sm text-slate-600">
              <Loader2 className="mr-2 h-5 w-5 animate-spin text-academic-accent" />
              Loading saved sessions...
            </div>
          ) : (
            <div className="grid gap-3">
              {resumeSessions.map((item) => (
                <article key={item.id} className="grid gap-3 rounded-lg border border-academic-paper-border bg-white p-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone={item.status === "paused" ? "gold" : "teal"}>{formatSessionStatus(item.status)}</StatusBadge>
                      <StatusBadge tone="slate">{formatMode(item.mode)}</StatusBadge>
                      <StatusBadge tone="teal">{formatPart(item)}</StatusBadge>
                    </div>
                    <p className="mt-2 break-words text-sm font-semibold text-slate-900">{formatDateTime(item.updated_at)}</p>
                    <p className="mt-1 text-xs text-slate-500">Saved progress is kept for this session.</p>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2 md:w-fit">
                    <Button type="button" variant="gold" size="sm" onClick={() => continueSession(item)} className="w-full md:w-fit">
                      Continue
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                    <Button type="button" variant="soft" size="sm" onClick={() => void closeSession(item)} disabled={closingSessionId === item.id} className="w-full md:w-fit">
                      {closingSessionId === item.id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <XCircle className="mr-2 h-4 w-4" />}
                      Close
                    </Button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Panel>
      )}

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px] 2xl:grid-cols-[minmax(0,1fr)_340px]">
        <Panel>
          <SectionHeading icon={Mic2} label="Practice Modes" labelZh="训练模式" />
          <div className="grid gap-4 md:grid-cols-2">
            {modeCards.map((card) => {
              const Icon = card.icon;
              return (
                <article
                  key={card.href}
                  className="group flex min-h-[210px] flex-col rounded-lg border border-slate-200 bg-white p-4 transition-colors hover:border-academic-accent/40 hover:bg-slate-50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-academic-navy text-white">
                      <Icon className="h-5 w-5" />
                    </span>
                    <StatusBadge tone={card.tone}>{card.meta}</StatusBadge>
                  </div>
                  <h2 className="mt-4 text-lg font-semibold text-slate-950">
                    {card.title}
                    <span className="ml-2 text-sm font-medium text-academic-accent">{card.titleZh}</span>
                  </h2>
                  <p className="mt-2 flex-1 text-sm leading-6 text-slate-600">{card.body}</p>
                  <Button type="button" variant={card.tone} className="mt-4 w-full" onClick={() => router.push(card.href)}>
                    {card.cta}
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </article>
              );
            })}
          </div>
        </Panel>

        <div className="grid gap-5">
          <Panel tone="paper">
            <SectionHeading icon={Target} label="Next Practice" labelZh="下一次练习" />
            <div className="grid gap-3">
              <div className="flex items-end justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-600">Latest overall band</p>
                  <p className="mt-1 font-serif text-5xl text-academic-navy">{formatBand(latestBand)}</p>
                </div>
                <StatusBadge tone={weakest.tone}>{weakest.label}</StatusBadge>
              </div>
              <MiniSparkline values={trendValues} />
              <InlineKpi icon={BrainCircuit} label="Recommended focus" value={weakest.recommendation} />
              <InlineKpi icon={CalendarCheck} label="Average band" value={formatBand(averageBand)} />
              <Button type="button" variant="gold" onClick={quickStart} disabled={quickStartLoading}>
                {quickStartLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlayCircle className="mr-2 h-4 w-4" />}
                Start recommended task
              </Button>
            </div>
          </Panel>

          <div className="grid grid-cols-3 gap-3">
            <MetricCard label="Reports" value={String(reports.length)} helper="最近记录" />
            <MetricCard label="Ready" value={String(reports.filter((item) => item.report_status === "ready").length)} helper="可复盘" tone="sage" />
            <MetricCard label="Role" value={user?.role || "user"} helper="当前权限" tone="teal" />
          </div>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px] 2xl:grid-cols-[minmax(0,1fr)_340px]">
        <Panel>
          <SectionHeading icon={FileText} label="Recent Reports" labelZh="最近复盘" action={<Button type="button" variant="soft" size="sm" onClick={() => router.push("/history")}>Open history</Button>} />
          {reportsLoading ? (
            <div className="flex min-h-40 items-center justify-center text-sm text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin text-academic-accent" />
              Loading report history...
            </div>
          ) : reports.length === 0 ? (
            <EmptyState
              title="No report yet"
              body="Complete a mock exam or focused practice session to generate your first score report."
              action={<Button type="button" variant="gold" onClick={() => router.push("/practice/setup/full")}>Configure first exam</Button>}
            />
          ) : (
            <div className="grid gap-3">
              {reports.slice(0, 5).map((item) => (
                <article key={item.id} className="grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 md:grid-cols-[1fr_auto] md:items-center">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone="gold">{formatBand(item.overall_band)}</StatusBadge>
                      <StatusBadge tone="teal">{formatMode(item.mode)}</StatusBadge>
                      <StatusBadge tone="slate">{formatPart(item)}</StatusBadge>
                    </div>
                    <p className="mt-2 truncate text-sm font-semibold text-slate-900">{formatDateTime(item.report_created_at)}</p>
                    <p className="mt-1 text-xs text-slate-500">Confidence {formatPercent(item.confidence)}  |  {item.report_status}</p>
                  </div>
                  <Button type="button" variant="soft" size="sm" onClick={() => router.push(`/report/${item.session_id}`)}>
                    Open review
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </article>
              ))}
            </div>
          )}
        </Panel>

        <Panel>
          <SectionHeading icon={ShieldCheck} label="Operations" labelZh="运营后台" />
          {canAdmin ? (
            <div className="grid gap-3">
              {adminLinks.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.href}
                    type="button"
                    onClick={() => router.push(item.href)}
                    className="flex min-h-12 cursor-pointer items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 text-left transition-colors hover:border-academic-accent/40 hover:bg-slate-50"
                  >
                    <span className="flex items-center gap-3">
                      <Icon className="h-4 w-4 text-academic-accent" />
                      <span>
                        <span className="block text-sm font-semibold text-slate-900">{item.label}</span>
                        <span className="text-xs text-slate-500">{item.labelZh}</span>
                      </span>
                    </span>
                    <ArrowRight className="h-4 w-4 text-slate-400" />
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState icon={ShieldCheck} title="Learner workspace" body="Admin tools are hidden from learner accounts. 管理员工具仅对运营账号可见。" />
          )}
        </Panel>
      </section>
    </AcademicShell>
  );
}

function findWeakestCriterion(item?: ReportHistoryItem) {
  const entries = Object.entries(item?.criteria ?? {}).filter(([, score]) => typeof score.band === "number");
  if (entries.length === 0) {
    return {
      label: "Baseline",
      recommendation: "Full exam",
      tone: "gold" as const,
    };
  }
  const [criterion] = entries.sort(([, left], [, right]) => (left.band ?? 9) - (right.band ?? 9))[0];
  const label = criterionLabels[criterion] ?? criterion;
  return {
    label,
    recommendation: label === "Pronunciation" ? "Pronunciation drill" : "Part practice",
    tone: label === "Pronunciation" ? ("coral" as const) : ("teal" as const),
  };
}

function formatBand(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(1);
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

function formatMode(value: string) {
  if (value === "full_exam") return "Full exam";
  if (value === "part_practice") return "Part practice";
  if (value === "topic_practice") return "Topic practice";
  return value;
}

function formatPart(item: { target_part?: number | null; mode: string }) {
  if (item.target_part) return `Part ${item.target_part}`;
  if (item.mode === "full_exam") return "Parts 1-3";
  return "Mixed parts";
}

function formatSessionStatus(value: string) {
  if (value === "paused") return "Paused";
  if (value === "in_progress") return "In progress";
  if (value === "scoring") return "Scoring";
  if (value === "completed") return "Completed";
  return value;
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
