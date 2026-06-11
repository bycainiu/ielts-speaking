"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, FileText, Gauge, Loader2, PauseCircle, PlayCircle, RefreshCcw, Search, ShieldCheck, SlidersHorizontal } from "lucide-react";

import { AcademicShell, EmptyState, InlineKpi, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import {
  actionLabel,
  apiErrorMessage,
  candidateCounts,
  formatBytes,
  formatDateTime,
  statusTone,
  visibilityLabel,
  type KnowledgeImportJob,
  type RuntimePolicy,
} from "@/lib/knowledgeIngestion";
import { useAuthStore } from "@/store/authStore";

type Filters = {
  status: string;
  visibility: string;
  ownerUserId: string;
};

const emptyFilters: Filters = { status: "", visibility: "", ownerUserId: "" };
const statusOptions = ["", "queued", "running", "awaiting_review", "awaiting_user_confirmation", "completed", "failed", "cancelled", "rejected"];
const visibilityOptions = ["", "private", "public"];

export default function AdminKnowledgeImportsPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [activeFilters, setActiveFilters] = useState<Filters>(emptyFilters);
  const [jobs, setJobs] = useState<KnowledgeImportJob[]>([]);
  const [policy, setPolicy] = useState<RuntimePolicy | null>(null);
  const [maxConcurrency, setMaxConcurrency] = useState(2);
  const [paused, setPaused] = useState(false);
  const [loading, setLoading] = useState(true);
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const canAdmin = user?.role === "operator" || user?.role === "admin";

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/login");
    }
  }, [hasHydrated, isAuthenticated, router]);

  useEffect(() => {
    if (hasHydrated && isAuthenticated && !user) {
      void fetchUser();
    }
  }, [fetchUser, hasHydrated, isAuthenticated, user]);

  const loadData = useCallback(async () => {
    if (!hasHydrated || !isAuthenticated || !canAdmin) return;
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ limit: "120" });
      if (activeFilters.status) params.set("status", activeFilters.status);
      if (activeFilters.visibility) params.set("visibility", activeFilters.visibility);
      if (activeFilters.ownerUserId.trim()) params.set("owner_user_id", activeFilters.ownerUserId.trim());
      const [jobsResponse, policyResponse] = await Promise.all([
        api.get<{ jobs: KnowledgeImportJob[] }>(`/admin/knowledge/imports?${params.toString()}`),
        api.get<{ policy: RuntimePolicy }>("/admin/agent-runtime/document-ingestion"),
      ]);
      setJobs(jobsResponse.data.jobs ?? []);
      setPolicy(policyResponse.data.policy);
      setMaxConcurrency(policyResponse.data.policy.max_concurrency);
      setPaused(policyResponse.data.policy.paused);
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Failed to load import queue."));
    } finally {
      setLoading(false);
    }
  }, [activeFilters, canAdmin, hasHydrated, isAuthenticated]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const savePolicy = async () => {
    setSavingPolicy(true);
    setError("");
    setNotice("");
    try {
      const response = await api.put<{ policy: RuntimePolicy }>("/admin/agent-runtime/document-ingestion", {
        max_concurrency: maxConcurrency,
        paused,
      });
      setPolicy(response.data.policy);
      setNotice("Run policy updated.");
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Failed to update run policy."));
    } finally {
      setSavingPolicy(false);
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/admin/knowledge/imports" userName={user?.display_name} userRole={user?.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">
          <SectionHeading icon={ShieldCheck} label="Access denied" labelZh="权限不足" />
          <h1 className="font-serif text-3xl text-academic-navy">Knowledge Imports</h1>
          <p className="mt-2 text-sm leading-6">该页面仅对 operator 和 admin 账号开放。</p>
        </Panel>
      </AcademicShell>
    );
  }

  const runningCount = jobs.filter((job) => job.status === "running").length;
  const queuedCount = jobs.filter((job) => job.status === "queued").length;
  const reviewCount = jobs.filter((job) => job.status === "awaiting_review").length;

  return (
    <AcademicShell activePath="/admin/knowledge/imports" userName={user?.display_name} userRole={user?.role} wide>
      <PageHeader
        eyebrow="Knowledge Operations"
        title="Import Queue"
        titleZh="Import queue"
        description="Monitor document ingestion queue, concurrency policy, review backlog, and runtime health."
        actions={
          <>
            <Button type="button" variant="soft" onClick={() => router.push("/admin/knowledge")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Knowledge base
            </Button>
            <Button type="button" variant="teal" onClick={() => void loadData()} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
              Refresh
            </Button>
          </>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}
      {notice && <Panel className="border-emerald-600/25 bg-academic-success-soft text-sm text-emerald-800">{notice}</Panel>}

      <section className="grid gap-4 md:grid-cols-4">
        <InlineKpi icon={Gauge} label="Running" value={`${runningCount}`} />
        <InlineKpi icon={RefreshCcw} label="Queued" value={`${queuedCount}`} />
        <InlineKpi icon={ShieldCheck} label="Review" value={`${reviewCount}`} />
        <InlineKpi icon={SlidersHorizontal} label="Concurrency" value={`${policy?.max_concurrency ?? maxConcurrency}${policy?.paused ? " paused" : ""}`} />
      </section>

      <section className="grid gap-5 xl:grid-cols-[340px_minmax(0,1fr)]">
        <div className="grid gap-5">
          <Panel>
            <SectionHeading icon={SlidersHorizontal} label="Runtime Policy" labelZh="运行策略" />
            <div className="grid gap-4">
              <label className="grid gap-2 text-sm text-slate-700">
                <span className="font-medium">并发上限</span>
                <input
                  type="number"
                  min={1}
                  max={16}
                  value={maxConcurrency}
                  onChange={(event) => setMaxConcurrency(Math.max(1, Math.min(16, Number(event.target.value) || 1)))}
                  className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-academic-score"
                />
              </label>
              <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-700">
                <span className="font-medium">暂停调度</span>
                <input type="checkbox" checked={paused} onChange={(event) => setPaused(event.target.checked)} className="h-4 w-4 rounded border-slate-300 text-academic-accent" />
              </label>
              <Button type="button" variant={paused ? "soft" : "gold"} onClick={savePolicy} disabled={savingPolicy}>
                {savingPolicy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : paused ? <PauseCircle className="mr-2 h-4 w-4" /> : <PlayCircle className="mr-2 h-4 w-4" />}
                保存策略
              </Button>
            </div>
          </Panel>

          <Panel tone="paper">
            <SectionHeading icon={Search} label="Filters" labelZh="筛选" />
            <div className="grid gap-3">
              <SelectField label="Status" value={filters.status} onChange={(value) => setFilters((current) => ({ ...current, status: value }))} values={statusOptions} />
              <SelectField label="Visibility" value={filters.visibility} onChange={(value) => setFilters((current) => ({ ...current, visibility: value }))} values={visibilityOptions} />
              <label className="grid gap-2 text-sm text-slate-700">
                <span className="font-medium">User ID</span>
                <input
                  value={filters.ownerUserId}
                  onChange={(event) => setFilters((current) => ({ ...current, ownerUserId: event.target.value }))}
                  className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-academic-score"
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="gold" onClick={() => setActiveFilters(filters)}>
                  <Search className="mr-2 h-4 w-4" />
                  应用
                </Button>
                <Button
                  type="button"
                  variant="soft"
                  onClick={() => {
                    setFilters(emptyFilters);
                    setActiveFilters(emptyFilters);
                  }}
                >
                  重置
                </Button>
              </div>
            </div>
          </Panel>
        </div>

        <Panel>
          <SectionHeading icon={FileText} label="Imports" labelZh="导入任务" />
          {loading ? (
            <div className="flex min-h-64 items-center justify-center text-sm text-slate-600">
              <Loader2 className="mr-2 h-5 w-5 animate-spin text-academic-score" />
              加载中…
            </div>
          ) : jobs.length === 0 ? (
            <EmptyState icon={FileText} title="暂无导入任务" body="队列中还没有文档导入记录。" />
          ) : (
            <div className="grid gap-4">
              {jobs.map((job) => {
                const counts = candidateCounts(job);
                return (
                  <article key={job.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                    <div className="flex flex-col gap-4 2xl:flex-row 2xl:items-start 2xl:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap gap-2">
                          <StatusBadge tone={statusTone(job.status)}>{job.status}</StatusBadge>
                          <StatusBadge tone="teal">{visibilityLabel(job.requested_visibility)}</StatusBadge>
                          <StatusBadge tone="gold">{actionLabel(job.requested_action)}</StatusBadge>
                          {job.classifier_label && <StatusBadge tone="blue">{job.classifier_label}</StatusBadge>}
                        </div>
                        <h2 className="mt-3 break-words text-base font-semibold leading-relaxed text-academic-navy">{job.source_file.title}</h2>
                        <p className="mt-1 break-words text-sm text-slate-600">{job.source_file.original_filename} · {formatBytes(job.source_file.size_bytes)}</p>
                        <p className="mt-2 break-all text-xs text-slate-500">owner {job.owner_user_id}</p>
                        <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
                          <div className="h-full rounded-full bg-academic-accent" style={{ width: `${Math.max(3, job.progress_pct)}%` }} />
                        </div>
                        <p className="mt-2 text-xs text-slate-500">
                          {job.stage} · {job.progress_pct}% · {formatDateTime(job.updated_at)}
                        </p>
                        <p className="mt-2 text-xs text-slate-500">
                          题目 {counts.question} · 知识 {counts.knowledge} · 背景 {counts.background}
                        </p>
                      </div>
                      <Button type="button" variant="teal" size="sm" onClick={() => router.push(`/admin/knowledge/imports/${job.id}`)}>
                        <ArrowRight className="mr-2 h-4 w-4" />
                        观察
                      </Button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </Panel>
      </section>
    </AcademicShell>
  );
}

function SelectField({ label, value, values, onChange }: { label: string; value: string; values: string[]; onChange: (value: string) => void }) {
  return (
    <label className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-academic-score">
        {values.map((item) => (
          <option key={item || "all"} value={item}>
            {item || "全部"}
          </option>
        ))}
      </select>
    </label>
  );
}
