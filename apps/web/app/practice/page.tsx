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
  PlayCircle,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  UserRound,
  Volume2,
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
import { api } from "@/lib/api";
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
    meta: "11-14 min · strict",
    href: "/practice/setup/full",
    icon: PlayCircle,
    tone: "gold" as const,
    cta: "Configure exam",
  },
  {
    title: "Part Practice",
    titleZh: "单项练习",
    body: "Train one target part with practice hints, follow-up intensity and immediate review focus.",
    meta: "5-8 min · coached",
    href: "/practice/setup/part",
    icon: SlidersHorizontal,
    tone: "teal" as const,
    cta: "Choose part",
  },
  {
    title: "Topic Practice",
    titleZh: "主题练习",
    body: "Select seasonal topics, combine question bank content with your background profile.",
    meta: "6-10 min · topic-led",
    href: "/practice/setup/topic",
    icon: BookOpenCheck,
    tone: "teal" as const,
    cta: "Choose topic",
  },
  {
    title: "Pronunciation Drill",
    titleZh: "发音专项",
    body: "Fixed-text read-aloud practice with word and phoneme-level evidence. No official band score.",
    meta: "3-5 min · evidence only",
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
  const [reportsLoading, setReportsLoading] = useState(false);
  const [quickStartLoading, setQuickStartLoading] = useState(false);
  const [error, setError] = useState("");

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
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Practice session could not be started.");
    } finally {
      setQuickStartLoading(false);
    }
  };

  const signOut = () => {
    logout();
    router.push("/login");
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
        </Panel>
      )}

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Panel>
          <SectionHeading icon={Mic2} label="Practice Modes" labelZh="训练模式" />
          <div className="grid gap-4 md:grid-cols-2">
            {modeCards.map((card) => {
              const Icon = card.icon;
              return (
                <article
                  key={card.href}
                  className="group flex min-h-[210px] flex-col rounded-lg border border-slate-200 bg-white p-4 transition-colors hover:border-[#D4AF37]/50 hover:bg-[#FFFDF7]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-[#0B132B] text-[#D4AF37]">
                      <Icon className="h-5 w-5" />
                    </span>
                    <StatusBadge tone={card.tone}>{card.meta}</StatusBadge>
                  </div>
                  <h2 className="mt-4 text-lg font-semibold text-slate-950">
                    {card.title}
                    <span className="ml-2 text-sm font-medium text-[#3A7CA5]">{card.titleZh}</span>
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
            <SectionHeading icon={Target} label="Next Practice" labelZh="下一步建议" />
            <div className="grid gap-3">
              <div className="flex items-end justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-600">Latest overall band</p>
                  <p className="mt-1 font-serif text-5xl text-[#0B132B]">{formatBand(latestBand)}</p>
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
            <MetricCard label="Reports" value={String(reports.length)} helper="历史复盘" />
            <MetricCard label="Ready" value={String(reports.filter((item) => item.report_status === "ready").length)} helper="可查看" tone="sage" />
            <MetricCard label="Role" value={user?.role || "user"} helper="权限" tone="teal" />
          </div>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Panel>
          <SectionHeading icon={FileText} label="Recent Reports" labelZh="最近复盘" action={<Button type="button" variant="soft" size="sm" onClick={() => router.push("/history")}>Open history</Button>} />
          {reportsLoading ? (
            <div className="flex min-h-40 items-center justify-center text-sm text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#D4AF37]" />
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
                    <p className="mt-1 text-xs text-slate-500">Confidence {formatPercent(item.confidence)} · {item.report_status}</p>
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
          <SectionHeading icon={ShieldCheck} label="Operations" labelZh="运营入口" />
          {canAdmin ? (
            <div className="grid gap-3">
              {adminLinks.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.href}
                    type="button"
                    onClick={() => router.push(item.href)}
                    className="flex min-h-12 cursor-pointer items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 text-left transition-colors hover:border-[#D4AF37]/50 hover:bg-[#FFFDF7]"
                  >
                    <span className="flex items-center gap-3">
                      <Icon className="h-4 w-4 text-[#3A7CA5]" />
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
            <EmptyState icon={ShieldCheck} title="Learner workspace" body="Admin tools are hidden from learner accounts. 学员账号不会暴露运营后台。" />
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

function formatPart(item: ReportHistoryItem) {
  if (item.target_part) return `Part ${item.target_part}`;
  if (item.mode === "full_exam") return "Parts 1-3";
  return "Mixed parts";
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
