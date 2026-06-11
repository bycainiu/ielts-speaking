"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, FileText, FileUp, Loader2, RefreshCcw, RotateCcw, ShieldCheck, StopCircle, UploadCloud } from "lucide-react";

import { AcademicShell, EmptyState, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import {
  actionLabel,
  apiErrorMessage,
  canCancelJob,
  canRetryJob,
  candidateCounts,
  formatBytes,
  formatDateTime,
  statusTone,
  visibilityLabel,
  type KnowledgeImportJob,
} from "@/lib/knowledgeIngestion";
import { useAuthStore } from "@/store/authStore";

type UploadForm = {
  title: string;
  visibility: "private" | "public";
  purpose: string;
  file: File | null;
};

const emptyForm: UploadForm = {
  title: "",
  visibility: "private",
  purpose: "auto",
  file: null,
};

const purposeOptions = [
  { value: "auto", label: "自动识别" },
  { value: "question_bank", label: "题库" },
  { value: "knowledge", label: "知识" },
  { value: "background", label: "背景" },
  { value: "mixed", label: "混合" },
];

export default function KnowledgeUploadPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [form, setForm] = useState<UploadForm>(emptyForm);
  const [jobs, setJobs] = useState<KnowledgeImportJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState("");
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

  const loadJobs = useCallback(async () => {
    if (!hasHydrated || !isAuthenticated) return;
    setLoading(true);
    setError("");
    try {
      const response = await api.get<{ jobs: KnowledgeImportJob[] }>("/knowledge/uploads?limit=80");
      setJobs(response.data.jobs ?? []);
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Request failed."));
    } finally {
      setLoading(false);
    }
  }, [hasHydrated, isAuthenticated]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const activeJobs = useMemo(() => jobs.filter((job) => ["queued", "running"].includes(job.status)).length, [jobs]);

  const upload = async () => {
    if (!form.file) return;
    setUploading(true);
    setError("");
    setNotice("");
    try {
      const payload = new FormData();
      payload.set("file", form.file);
      payload.set("visibility", form.visibility);
      payload.set("purpose", form.purpose);
      if (form.title.trim()) payload.set("title", form.title.trim());
      const response = await api.post<{ job: KnowledgeImportJob }>("/knowledge/uploads", payload);
      setNotice("Upload queued for parsing.");
      setForm(emptyForm);
      void loadJobs();
      router.push(`/knowledge/${response.data.job.id}`);
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Request failed."));
    } finally {
      setUploading(false);
    }
  };

  const cancelJob = async (job: KnowledgeImportJob) => {
    setActionLoadingId(job.id);
    setError("");
    try {
      await api.post(`/knowledge/uploads/${job.id}/cancel`);
      setNotice("Operation completed.");;
      await loadJobs();
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Request failed."));
    } finally {
      setActionLoadingId("");
    }
  };

  const retryJob = async (job: KnowledgeImportJob) => {
    setActionLoadingId(job.id);
    setError("");
    try {
      await api.post(`/knowledge/uploads/${job.id}/retry`);
      setNotice("Operation completed.");;
      await loadJobs();
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Request failed."));
    } finally {
      setActionLoadingId("");
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  return (
    <AcademicShell activePath="/knowledge" userName={user?.display_name} userRole={user?.role}>
      <PageHeader
        eyebrow="Knowledge Workspace"
        title="Knowledge Upload"
        titleZh="Knowledge upload"
        description="Upload materials for the document agent to extract questions, knowledge, and background candidates asynchronously."
        actions={
          <>
            {canAdmin && (
              <Button type="button" variant="teal" onClick={() => router.push("/admin/knowledge/imports")}>
                <ShieldCheck className="mr-2 h-4 w-4" />
                Import queue
              </Button>
            )}
            <Button type="button" variant="soft" onClick={() => void loadJobs()} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
              Refresh
            </Button>
          </>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}
      {notice && <Panel className="border-emerald-600/25 bg-academic-success-soft text-sm text-emerald-800">{notice}</Panel>}

      <section className="grid gap-5 lg:grid-cols-[minmax(0,0.78fr)_minmax(0,1.22fr)]">
        <Panel>
          <SectionHeading icon={FileUp} label="Upload" labelZh="上传" />
          <div className="grid gap-4">
            <label className="grid gap-2 text-sm text-slate-700">
              <span className="font-medium">标题</span>
              <input
                value={form.title}
                onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none transition-colors focus:border-academic-score focus:ring-2 focus:ring-academic-score/20"
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-2 text-sm text-slate-700">
                <span className="font-medium">可见性</span>
                <select
                  value={form.visibility}
                  onChange={(event) => setForm((current) => ({ ...current, visibility: event.target.value as UploadForm["visibility"] }))}
                  className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none transition-colors focus:border-academic-score focus:ring-2 focus:ring-academic-score/20"
                >
                  <option value="private">私有</option>
                  <option value="public">公开</option>
                </select>
              </label>
              <label className="grid gap-2 text-sm text-slate-700">
                <span className="font-medium">导入目的</span>
                <select
                  value={form.purpose}
                  onChange={(event) => setForm((current) => ({ ...current, purpose: event.target.value }))}
                  className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none transition-colors focus:border-academic-score focus:ring-2 focus:ring-academic-score/20"
                >
                  {purposeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-academic-accent/35 bg-[#F8FBFD] px-4 py-6 text-center transition-colors hover:border-academic-score/70 hover:bg-[#FFFDF5]">
              <UploadCloud className="h-9 w-9 text-academic-accent" />
              <span className="mt-3 text-sm font-semibold text-slate-900">{form.file ? form.file.name : "选择文档"}</span>
              <span className="mt-1 text-xs text-slate-500">{form.file ? formatBytes(form.file.size) : "md / txt / pdf / docx"}</span>
              <input
                type="file"
                accept=".md,.markdown,.txt,.pdf,.docx,text/markdown,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                className="sr-only"
                onChange={(event) => setForm((current) => ({ ...current, file: event.target.files?.[0] ?? null }))}
              />
            </label>
            <Button type="button" variant="gold" onClick={upload} disabled={uploading || !form.file}>
              {uploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileUp className="mr-2 h-4 w-4" />}
              上传并解析
            </Button>
          </div>
        </Panel>

        <Panel>
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <SectionHeading icon={FileText} label="My Imports" labelZh="My imports" />
            <div className="flex flex-wrap gap-2">
              <StatusBadge tone="coral">{activeJobs} processing</StatusBadge>
              <StatusBadge tone="slate">{jobs.length} total</StatusBadge>
            </div>
          </div>
          {loading ? (
            <div className="flex min-h-52 items-center justify-center text-sm text-slate-600">
              <Loader2 className="mr-2 h-5 w-5 animate-spin text-academic-score" />
              Loading...
            </div>
          ) : jobs.length === 0 ? (
            <EmptyState icon={FileText} title="No imports yet" body="Upload a document to create your first import job." />
          ) : (
            <div className="grid gap-4">
              {jobs.map((job) => {
                const counts = candidateCounts(job);
                return (
                  <article key={job.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap gap-2">
                          <StatusBadge tone={statusTone(job.status)}>{job.status}</StatusBadge>
                          <StatusBadge tone="teal">{visibilityLabel(job.requested_visibility)}</StatusBadge>
                          <StatusBadge tone="gold">{actionLabel(job.requested_action)}</StatusBadge>
                        </div>
                        <h2 className="mt-3 break-words text-base font-semibold leading-relaxed text-academic-navy">{job.source_file.title}</h2>
                        <p className="mt-1 break-words text-sm text-slate-600">{job.source_file.original_filename} · {formatBytes(job.source_file.size_bytes)}</p>
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
                      <div className="flex shrink-0 flex-wrap gap-2 xl:justify-end">
                        {canCancelJob(job.status) && (
                          <Button type="button" variant="dangerOutline" size="sm" onClick={() => void cancelJob(job)} disabled={actionLoadingId === job.id}>
                            <StopCircle className="mr-2 h-4 w-4" />
                            取消
                          </Button>
                        )}
                        {canRetryJob(job.status) && (
                          <Button type="button" variant="soft" size="sm" onClick={() => void retryJob(job)} disabled={actionLoadingId === job.id}>
                            <RotateCcw className="mr-2 h-4 w-4" />
                            重试
                          </Button>
                        )}
                        <Button type="button" variant="teal" size="sm" onClick={() => router.push(`/knowledge/${job.id}`)}>
                          <ArrowRight className="mr-2 h-4 w-4" />
                          详情

                        </Button>
                      </div>
                    </div>
                    {job.error_message && (
                      <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                        {job.error_message}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </Panel>
      </section>

      {form.visibility === "public" && (
        <Panel className="border-academic-score/30 bg-academic-score-soft text-sm text-[#6E5A18]">
          <div className="flex items-start gap-3">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
            <p>暂无导入任务。</p>
          </div>
        </Panel>
      )}
    </AcademicShell>
  );
}
