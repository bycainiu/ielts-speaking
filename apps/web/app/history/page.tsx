"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  CalendarDays,
  FileText,
  Filter,
  LineChart as LineChartIcon,
  Loader2,
  RotateCcw,
  Search,
  Target,
  Trash2,
} from "lucide-react";

import { AcademicShell, EmptyState, MetricCard, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

type HistoryFilters = {
  mode: string;
  part: string;
  from: string;
  to: string;
};

type ReportHistoryCriterion = {
  band?: number;
  confidence?: number;
};

type ReportHistoryItem = {
  id: string;
  session_id: string;
  mode: string;
  session_status: string;
  target_part?: number | null;
  version: number;
  report_status: string;
  overall_band?: number | null;
  confidence?: number | null;
  criteria?: Record<string, ReportHistoryCriterion>;
  session_created_at: string;
  session_completed_at?: string | null;
  report_created_at: string;
  report_updated_at: string;
};

type HistoryResponse = {
  reports: ReportHistoryItem[];
};

type ApiError = {
  response?: {
    data?: {
      message?: string;
    };
  };
};

const defaultFilters: HistoryFilters = {
  mode: "",
  part: "",
  from: "",
  to: "",
};

const modeLabels: Record<string, string> = {
  full_exam: "Full Mock / 完整模拟",
  part_practice: "Part Practice / 单项练习",
  topic_practice: "Topic Practice / 主题练习",
};

const criterionLabels: Record<string, string> = {
  fluency_coherence: "Fluency",
  lexical_resource: "Lexical",
  grammatical_range_accuracy: "Grammar",
  pronunciation: "Pronunciation",
};

const selectClass =
  "h-11 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20";

export default function HistoryPage() {
  const router = useRouter();
  const { isAuthenticated, hasHydrated, user } = useAuthStore();
  const [draftFilters, setDraftFilters] = useState<HistoryFilters>(defaultFilters);
  const [activeFilters, setActiveFilters] = useState<HistoryFilters>(defaultFilters);
  const [reports, setReports] = useState<ReportHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ReportHistoryItem | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/login");
    }
  }, [hasHydrated, isAuthenticated, router]);

  useEffect(() => {
    if (!hasHydrated || !isAuthenticated) return;

    let cancelled = false;
    async function loadReports() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ limit: "40" });
        if (activeFilters.mode) params.set("mode", activeFilters.mode);
        if (activeFilters.part) params.set("part", activeFilters.part);
        if (activeFilters.from) params.set("from", activeFilters.from);
        if (activeFilters.to) params.set("to", activeFilters.to);

        const response = await api.get<HistoryResponse>(`/reports?${params.toString()}`);
        if (!cancelled) {
          setReports(response.data.reports ?? []);
        }
      } catch (err: unknown) {
        const apiError = err as ApiError;
        if (!cancelled) {
          setError(apiError.response?.data?.message || "报告历史加载失败。");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadReports();
    return () => {
      cancelled = true;
    };
  }, [activeFilters, hasHydrated, isAuthenticated]);

  const scoredReports = useMemo(
    () => reports.filter((item) => typeof item.overall_band === "number"),
    [reports],
  );

  const trendData = useMemo(
    () =>
      [...scoredReports].reverse().map((item, index) => ({
        label: formatShortDate(item.report_created_at),
        band: item.overall_band ?? 0,
        id: `${item.id}-${index}`,
      })),
    [scoredReports],
  );

  const latestBand = scoredReports[0]?.overall_band ?? null;
  const averageBand = scoredReports.length
    ? scoredReports.reduce((total, item) => total + (item.overall_band ?? 0), 0) / scoredReports.length
    : null;
  const deltaBand =
    scoredReports.length >= 2 && latestBand !== null
      ? latestBand - (scoredReports[scoredReports.length - 1].overall_band ?? latestBand)
      : null;

  const updateDraft = (key: keyof HistoryFilters, value: string) => {
    setDraftFilters((current) => ({ ...current, [key]: value }));
  };

  const applyFilters = () => {
    setActiveFilters(draftFilters);
  };

  const resetFilters = () => {
    setDraftFilters(defaultFilters);
    setActiveFilters(defaultFilters);
  };

  const openDeleteConfirmation = (item: ReportHistoryItem) => {
    setPendingDelete(item);
    setDeleteConfirmation("");
    setError("");
    setNotice("");
  };

  const closeDeleteConfirmation = () => {
    if (deletingSessionId) return;
    setPendingDelete(null);
    setDeleteConfirmation("");
  };

  const deleteSessionData = async () => {
    const item = pendingDelete;
    if (!item || deleteConfirmation !== "DELETE_MY_DATA") return;
    setDeletingSessionId(item.session_id);
    setError("");
    setNotice("");
    try {
      await api.post("/privacy/data-deletion", {
        session_id: item.session_id,
        delete_recordings: true,
        delete_reports: true,
        confirmation: "DELETE_MY_DATA",
      });
      setReports((current) => current.filter((report) => report.session_id !== item.session_id));
      setNotice("会话录音和报告已删除。");
      setPendingDelete(null);
      setDeleteConfirmation("");
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "会话数据删除失败。");
    } finally {
      setDeletingSessionId(null);
    }
  };

  if (!hasHydrated || !isAuthenticated) return null;

  return (
    <AcademicShell activePath="/history" userName={user?.display_name} userRole={user?.role}>
      <PageHeader
        eyebrow="Report History"
        title="Progress Review"
        titleZh="复盘趋势"
        description="Track score movement, filter completed reports, and return to detailed evidence review."
        actions={
          <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Practice / 练习
          </Button>
        }
      />

      <Panel tone="paper">
        <SectionHeading icon={Filter} label="Filters" labelZh="筛选条件" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[1.1fr_0.8fr_1fr_1fr_auto_auto]">
          <label htmlFor="history-mode" className="grid gap-2 text-sm text-slate-700">
            <span className="font-medium">Mode / 模式</span>
            <select
              id="history-mode"
              value={draftFilters.mode}
              onChange={(event) => updateDraft("mode", event.target.value)}
              className={selectClass}
            >
              <option value="">All modes</option>
              <option value="full_exam">Full Mock Exam</option>
              <option value="part_practice">Part Practice</option>
              <option value="topic_practice">Topic Practice</option>
            </select>
          </label>
          <label htmlFor="history-part" className="grid gap-2 text-sm text-slate-700">
            <span className="font-medium">Part / 题型</span>
            <select
              id="history-part"
              value={draftFilters.part}
              onChange={(event) => updateDraft("part", event.target.value)}
              className={selectClass}
            >
              <option value="">All parts</option>
              <option value="1">Part 1</option>
              <option value="2">Part 2</option>
              <option value="3">Part 3</option>
            </select>
          </label>
          <label htmlFor="history-from" className="grid gap-2 text-sm text-slate-700">
            <span className="font-medium">From / 开始</span>
            <input
              id="history-from"
              type="date"
              value={draftFilters.from}
              onChange={(event) => updateDraft("from", event.target.value)}
              className={selectClass}
            />
          </label>
          <label htmlFor="history-to" className="grid gap-2 text-sm text-slate-700">
            <span className="font-medium">To / 结束</span>
            <input
              id="history-to"
              type="date"
              value={draftFilters.to}
              onChange={(event) => updateDraft("to", event.target.value)}
              className={selectClass}
            />
          </label>
          <Button type="button" variant="gold" onClick={applyFilters} className="h-11 self-end">
            <Search className="mr-2 h-4 w-4" />
            Apply
          </Button>
          <Button type="button" variant="soft" onClick={resetFilters} className="h-11 self-end">
            <RotateCcw className="mr-2 h-4 w-4" />
            Reset
          </Button>
        </div>
      </Panel>

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}
      {notice && <Panel className="border-[#4F8A6B]/25 bg-[#EEF7F2] text-sm text-[#3E7056]">{notice}</Panel>}

      <section className="grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.65fr)]">
        <Panel>
          <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <SectionHeading icon={LineChartIcon} label="Overall Band Trend" labelZh="总分趋势" />
              <h2 className="font-serif text-4xl text-[#0B132B]">
                {formatBand(latestBand)}
                <span className="ml-2 align-middle text-sm font-sans font-medium text-slate-500">Latest band</span>
              </h2>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm sm:min-w-[240px]">
              <Metric label="Average / 平均" value={formatBand(averageBand)} />
              <Metric label="Delta / 变化" value={formatDelta(deltaBand)} />
            </div>
          </div>

          <div className="h-[260px] min-h-[260px] w-full min-w-0">
            {loading ? (
              <div className="flex h-full items-center justify-center text-sm text-slate-600">
                <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#D4AF37]" />
                Loading history / 正在加载历史
              </div>
            ) : trendData.length > 0 ? (
              <TrendChart data={trendData} />
            ) : (
              <EmptyState
                icon={LineChartIcon}
                title="No scored reports"
                body="No scored reports match the current filters. 完成练习并生成报告后会显示趋势。"
              />
            )}
          </div>
        </Panel>

        <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-1">
          <MetricCard icon={FileText} label="Reports / 报告" value={String(reports.length)} helper="Filtered report count" />
          <MetricCard
            icon={Target}
            label="Ready / 可查看"
            value={String(reports.filter((item) => item.report_status === "ready").length)}
            helper="Reports with saved score data"
            tone="sage"
          />
          <MetricCard
            icon={CalendarDays}
            label="Latest / 最近"
            value={scoredReports[0] ? formatShortDate(scoredReports[0].report_created_at) : "-"}
            helper="Most recent scored report"
            tone="teal"
          />
        </div>
      </section>

      <Panel>
        <div className="mb-5 flex items-center justify-between gap-3">
          <SectionHeading icon={FileText} label="Reports" labelZh="报告列表" />
          <span className="text-sm text-slate-500">{formatResultCount(reports.length)}</span>
        </div>

        {loading ? (
          <div className="flex min-h-40 items-center justify-center text-sm text-slate-600">
            <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#D4AF37]" />
            Loading reports / 正在加载报告
          </div>
        ) : reports.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No report history"
            body="No reports match the current filters. 没有符合当前筛选条件的复盘报告。"
          />
        ) : (
          <div className="grid gap-4">
            {reports.map((item) => (
              <article
                key={item.id}
                className="grid gap-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition-colors hover:border-[#D4AF37]/60 lg:grid-cols-[minmax(0,1fr)_auto]"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone="gold">{formatBand(item.overall_band)}</StatusBadge>
                    <StatusBadge tone="teal">{modeLabels[item.mode] ?? item.mode}</StatusBadge>
                    <StatusBadge tone="slate">{formatPart(item)}</StatusBadge>
                    <StatusBadge tone={item.report_status === "ready" ? "sage" : "coral"}>{item.report_status}</StatusBadge>
                  </div>
                  <h3 className="mt-3 break-words text-base font-semibold text-[#0B132B]">
                    {formatDateTime(item.report_created_at)}
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-slate-600">
                    Confidence {formatPercent(item.confidence)} · Session {item.session_status} · Version {item.version}
                  </p>
                  <CriterionChips criteria={item.criteria ?? {}} />
                </div>
                <div className="grid gap-2 self-center sm:grid-cols-2 lg:w-fit lg:grid-cols-1">
                  <Button
                    type="button"
                    variant="soft"
                    onClick={() => router.push(`/report/${item.session_id}`)}
                    className="h-10 w-full lg:w-fit"
                  >
                    <FileText className="mr-2 h-4 w-4" />
                    Review / 复盘
                  </Button>
                  <Button
                    type="button"
                    variant="dangerOutline"
                    disabled={deletingSessionId === item.session_id}
                    onClick={() => openDeleteConfirmation(item)}
                    className="h-10 w-full lg:w-fit"
                  >
                    {deletingSessionId === item.session_id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
                    Delete / 删除
                  </Button>
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>

      {pendingDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0B132B]/55 px-4 py-6 backdrop-blur-sm" role="presentation">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-history-title"
            className="w-full max-w-[520px] rounded-lg border border-red-200 bg-white p-5 text-[#102033] shadow-[0_24px_80px_rgba(15,23,42,0.28)]"
          >
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-red-50 text-red-700">
                <Trash2 className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <h2 id="delete-history-title" className="font-serif text-2xl leading-tight text-[#0B132B]">
                  Delete session data
                </h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  This removes the report and saved recordings for session{" "}
                  <span className="break-all font-mono text-xs text-slate-800">{pendingDelete.session_id}</span>.
                </p>
              </div>
            </div>

            <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm leading-6 text-red-700">
              This action cannot be undone. 输入确认短语后才会执行删除。
            </div>

            <label htmlFor="history-delete-confirmation" className="mt-5 grid gap-2 text-sm text-slate-700">
              <span className="font-medium">Type DELETE_MY_DATA to confirm</span>
              <input
                id="history-delete-confirmation"
                value={deleteConfirmation}
                onChange={(event) => setDeleteConfirmation(event.target.value)}
                className="h-11 rounded-md border border-slate-200 bg-white px-3 font-mono text-sm outline-none transition-colors focus:border-red-400 focus:ring-2 focus:ring-red-100"
                autoComplete="off"
              />
            </label>

            <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button type="button" variant="soft" onClick={closeDeleteConfirmation} disabled={Boolean(deletingSessionId)}>
                Cancel
              </Button>
              <Button
                type="button"
                variant="dangerOutline"
                onClick={deleteSessionData}
                disabled={deleteConfirmation !== "DELETE_MY_DATA" || Boolean(deletingSessionId)}
              >
                {deletingSessionId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
                Delete report and recordings
              </Button>
            </div>
          </section>
        </div>
      )}
    </AcademicShell>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <p className="text-xs uppercase text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-[#0B132B]">{value}</p>
    </div>
  );
}

function CriterionChips({ criteria }: { criteria: Record<string, ReportHistoryCriterion> }) {
  const items = Object.entries(criteria);
  if (items.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {items.map(([criterion, score]) => (
        <span key={criterion} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-600">
          {criterionLabels[criterion] ?? criterion}: {formatBand(score.band ?? null)}
        </span>
      ))}
    </div>
  );
}

function TrendChart({ data }: { data: Array<{ id: string; label: string; band: number }> }) {
  const width = 720;
  const height = 260;
  const padding = { top: 18, right: 24, bottom: 34, left: 36 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const points = data.map((item, index) => {
    const x = padding.left + (data.length === 1 ? innerWidth / 2 : (index / (data.length - 1)) * innerWidth);
    const y = padding.top + innerHeight - (Math.max(0, Math.min(9, item.band)) / 9) * innerHeight;
    return { ...item, x, y };
  });
  const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  const gridBands = [0, 3, 6, 9];

  return (
    <svg className="h-full w-full overflow-visible" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Overall band trend">
      {gridBands.map((band) => {
        const y = padding.top + innerHeight - (band / 9) * innerHeight;
        return (
          <g key={band}>
            <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} stroke="rgba(148,163,184,0.28)" />
            <text x={padding.left - 12} y={y + 4} textAnchor="end" className="fill-slate-400 text-[11px]">
              {band}
            </text>
          </g>
        );
      })}
      <path d={path} fill="none" stroke="#D4AF37" strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" />
      {points.map((point, index) => {
        const showLabel = data.length <= 4 || index === 0 || index === data.length - 1;
        return (
          <g key={point.id}>
            <circle cx={point.x} cy={point.y} r="5" fill="#D4AF37" />
            <circle cx={point.x} cy={point.y} r="10" fill="rgba(212,175,55,0.14)" />
            <text x={point.x} y={height - 10} textAnchor="middle" className="fill-slate-500 text-[12px]">
              {showLabel ? point.label : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function formatPart(item: ReportHistoryItem) {
  if (item.target_part) return `Part ${item.target_part}`;
  if (item.mode === "full_exam") return "Parts 1-3";
  return "Mixed parts";
}

function formatBand(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(1);
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

function formatDelta(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  if (value === 0) return "0.0";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}

function formatResultCount(value: number) {
  return `${value} ${value === 1 ? "result" : "results"} / ${value} 条`;
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "2-digit" }).format(new Date(value));
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
