"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, BookOpenCheck, Download, FileText, Loader2, MessageSquareText, ShieldCheck, ThumbsDown, ThumbsUp } from "lucide-react";

import { AcademicShell, EmptyState, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

type ApiError = {
  response?: {
    data?: {
      message?: string;
    };
  };
};

type SummaryItem = {
  content_type: string;
  status: string;
  count: number;
};

type ReferenceAnswer = {
  id: string;
  report_id: string;
  turn_id?: string;
  band_target?: number;
  answer_text: string;
  personalization_notes?: string;
  review_status: string;
  created_at: string;
};

type ReportUserFeedback = {
  id: string;
  report_id: string;
  session_id: string;
  user_id: string;
  target_type: string;
  target_id?: string | null;
  vote: "up" | "down" | string;
  comment?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
};

type VoiceClonePolicy = {
  enabled: boolean;
  version: string;
  requires_explicit_consent: boolean;
  updated_by?: string | null;
  updated_at: string;
};

const statusOptions = ["draft", "reviewing", "active", "archived"];

export default function ReviewBoardPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [summary, setSummary] = useState<SummaryItem[]>([]);
  const [references, setReferences] = useState<ReferenceAnswer[]>([]);
  const [feedback, setFeedback] = useState<ReportUserFeedback[]>([]);
  const [voicePolicy, setVoicePolicy] = useState<VoiceClonePolicy | null>(null);
  const [status, setStatus] = useState("draft");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [policySaving, setPolicySaving] = useState(false);
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
      fetchUser();
    }
  }, [fetchUser, hasHydrated, isAuthenticated, user]);

  useEffect(() => {
    if (!hasHydrated || !isAuthenticated || !canAdmin) return;

    let cancelled = false;
    async function loadReviewData() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ limit: "40" });
        if (status) params.set("status", status);
        const [summaryResponse, referenceResponse, feedbackResponse, policyResponse] = await Promise.all([
          api.get<{ summary: SummaryItem[] }>("/admin/content-review/summary"),
          api.get<{ reference_answers: ReferenceAnswer[] }>(`/admin/content-review/reference-answers?${params.toString()}`),
          api.get<{ feedback: ReportUserFeedback[] }>("/reports/feedback/export?limit=20"),
          api.get<{ policy: VoiceClonePolicy }>("/admin/compliance/voice-clone-policy"),
        ]);
        if (!cancelled) {
          setSummary(summaryResponse.data.summary ?? []);
          setReferences(referenceResponse.data.reference_answers ?? []);
          setFeedback(feedbackResponse.data.feedback ?? []);
          setVoicePolicy(policyResponse.data.policy ?? null);
        }
      } catch (err: unknown) {
        const apiError = err as ApiError;
        if (!cancelled) {
          setError(apiError.response?.data?.message || "Review board could not be loaded.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadReviewData();
    return () => {
      cancelled = true;
    };
  }, [canAdmin, hasHydrated, isAuthenticated, status]);

  const summaryByType = useMemo(() => {
    const grouped = new Map<string, SummaryItem[]>();
    for (const item of summary) {
      grouped.set(item.content_type, [...(grouped.get(item.content_type) ?? []), item]);
    }
    return grouped;
  }, [summary]);

  const updateReferenceStatus = async (item: ReferenceAnswer, nextStatus: string) => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api.put(`/admin/content-review/reference-answers/${item.id}/status`, { status: nextStatus });
      setNotice("Reference answer status updated.");
      setReferences((current) => current.map((entry) => (entry.id === item.id ? { ...entry, review_status: nextStatus } : entry)));
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Reference answer status could not be updated.");
    } finally {
      setSaving(false);
    }
  };

  const downloadFeedbackExport = async () => {
    setExporting(true);
    setError("");
    setNotice("");
    try {
      const response = await api.get<{ feedback: ReportUserFeedback[] }>("/reports/feedback/export?limit=500");
      const payload = JSON.stringify(response.data.feedback ?? [], null, 2);
      const blob = new Blob([payload], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `report-feedback-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setNotice("Feedback export prepared.");
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Feedback export could not be prepared.");
    } finally {
      setExporting(false);
    }
  };

  const updateVoiceClonePolicy = async (enabled: boolean) => {
    setPolicySaving(true);
    setError("");
    setNotice("");
    try {
      const response = await api.put<{ policy: VoiceClonePolicy }>("/admin/compliance/voice-clone-policy", {
        enabled,
        requires_explicit_consent: true,
      });
      setVoicePolicy(response.data.policy);
      setNotice(enabled ? "Voice clone policy enabled." : "Voice clone policy disabled.");
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Voice clone policy could not be updated.");
    } finally {
      setPolicySaving(false);
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/admin/review" userName={user?.display_name} userRole={user?.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">
          <SectionHeading icon={ShieldCheck} label="Access denied" labelZh="权限不足" />
          <h1 className="font-serif text-3xl text-[#0B132B]">Review Board</h1>
          <p className="mt-2 text-sm leading-6">This workspace is available to operator and admin accounts.</p>
          <Button type="button" variant="soft" className="mt-5" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Practice / 练习
          </Button>
        </Panel>
      </AcademicShell>
    );
  }

  return (
    <AcademicShell activePath="/admin/review" userName={user?.display_name} userRole={user?.role}>
      <PageHeader
        eyebrow="Content Quality"
        title="Review Board"
        titleZh="内容审核"
        description="Draft, reviewing, active, and archived publishing flow across content types."
        actions={
          <>
          <Button type="button" variant="soft" onClick={() => router.push("/admin/questions")}>
            Questions
          </Button>
          <Button type="button" variant="soft" onClick={() => router.push("/admin/knowledge")}>
            Knowledge
          </Button>
          <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Practice / 练习
          </Button>
          </>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}
      {notice && <Panel className="border-[#4F8A6B]/25 bg-[#EEF7F2] text-sm text-[#3E7056]">{notice}</Panel>}

      <section className="grid gap-4 md:grid-cols-3">
        <SummaryPanel icon={<BookOpenCheck className="h-4 w-4" />} title="Questions" items={summaryByType.get("question") ?? []} />
        <SummaryPanel icon={<FileText className="h-4 w-4" />} title="Knowledge Docs" items={summaryByType.get("knowledge_doc") ?? []} />
        <SummaryPanel icon={<MessageSquareText className="h-4 w-4" />} title="Reference Answers" items={summaryByType.get("reference_answer") ?? []} />
      </section>

      <Panel>
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <SectionHeading icon={MessageSquareText} label="User Feedback" labelZh="用户反馈" />
            <p className="mt-1 text-sm text-slate-500">Latest report votes and comments from learner review pages.</p>
          </div>
          <Button type="button" variant="soft" disabled={exporting} onClick={downloadFeedbackExport} className="w-fit">
            {exporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
            Export JSON
          </Button>
        </div>

        {loading ? (
          <div className="flex min-h-32 items-center justify-center text-sm text-slate-600">
            <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#D4AF37]" />
            Loading user feedback...
          </div>
        ) : feedback.length === 0 ? (
          <EmptyState icon={MessageSquareText} title="No user feedback" body="No user feedback has been submitted yet. 暂无用户反馈。" />
        ) : (
          <div className="grid gap-3">
            {feedback.map((item) => (
              <article key={item.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge>{item.target_type}</Badge>
                      <span className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-600">
                        {item.vote === "up" ? <ThumbsUp className="h-3.5 w-3.5 text-[#D4AF37]" /> : <ThumbsDown className="h-3.5 w-3.5 text-red-600" />}
                        {item.vote}
                      </span>
                      <Badge>{new Date(item.created_at).toLocaleDateString()}</Badge>
                    </div>
                    {item.comment && <p className="mt-3 text-sm leading-relaxed text-slate-700">{item.comment}</p>}
                    <p className="mt-2 break-all text-xs text-slate-500">
                      report {item.report_id} · session {item.session_id}
                    </p>
                  </div>
                  {item.target_id && <span className="break-all text-xs text-slate-500 md:max-w-64">target {item.target_id}</span>}
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>

      <Panel tone="paper">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <SectionHeading icon={ShieldCheck} label="Voice Clone Policy" labelZh="音色克隆策略" />
            <p className="mt-1 text-sm text-slate-500">Authorized voice clone remains disabled unless an operator explicitly enables it.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge>{voicePolicy?.enabled ? "enabled" : "disabled"}</Badge>
            <Button
              type="button"
              variant="soft"
              disabled={policySaving || loading}
              onClick={() => updateVoiceClonePolicy(false)}
            >
              {policySaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldCheck className="mr-2 h-4 w-4" />}
              Disable
            </Button>
            <Button
              type="button"
              variant="gold"
              disabled={policySaving || loading}
              onClick={() => updateVoiceClonePolicy(true)}
            >
              {policySaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldCheck className="mr-2 h-4 w-4" />}
              Enable
            </Button>
          </div>
        </div>
        {voicePolicy && (
          <p className="mt-3 text-xs text-slate-500">
            {voicePolicy.version} · explicit consent {voicePolicy.requires_explicit_consent ? "required" : "not required"}
          </p>
        )}
      </Panel>

      <Panel>
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <SectionHeading icon={MessageSquareText} label="Reference Answer Review" labelZh="参考答案审核" />
            <p className="mt-1 text-sm text-slate-500">Generated reference answers stay draft until an operator publishes them.</p>
          </div>
          <label className="grid gap-2 text-sm text-slate-700 sm:w-56">
            <span className="font-medium">Status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)} className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20">
              <option value="">All statuses</option>
              {statusOptions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
        </div>

        {loading ? (
          <div className="flex min-h-40 items-center justify-center text-sm text-slate-600">
            <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#D4AF37]" />
            Loading review items...
          </div>
        ) : references.length === 0 ? (
          <EmptyState icon={MessageSquareText} title="No reference answers" body="No reference answers match the current filter. 当前筛选条件下暂无参考答案。" />
        ) : (
          <div className="grid gap-4">
            {references.map((item) => (
              <article key={item.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap gap-2">
                      <Badge>{item.review_status}</Badge>
                      {item.band_target != null && <Badge>Band {item.band_target.toFixed(1)}</Badge>}
                      <Badge>{new Date(item.created_at).toLocaleDateString()}</Badge>
                    </div>
                    <p className="mt-3 text-sm leading-relaxed text-slate-700">{item.answer_text}</p>
                    {item.personalization_notes && <p className="mt-2 text-sm text-slate-500">{item.personalization_notes}</p>}
                  </div>
                  <select value={item.review_status} disabled={saving} onChange={(event) => updateReferenceStatus(item, event.target.value)} className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-[#D4AF37]">
                    {statusOptions.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>
    </AcademicShell>
  );
}

function SummaryPanel({ icon, title, items }: { icon: ReactNode; title: string; items: SummaryItem[] }) {
  const total = items.reduce((sum, item) => sum + item.count, 0);
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2 text-sm font-semibold uppercase text-[#3A7CA5]">
        {icon}
        {title}
      </div>
      <div className="mt-3 text-3xl font-semibold text-[#0B132B]">{total}</div>
      <div className="mt-4 grid gap-2">
        {statusOptions.map((status) => {
          const count = items.find((item) => item.status === status)?.count ?? 0;
          return (
            <div key={status} className="flex items-center justify-between text-sm text-slate-600">
              <span>{status}</span>
              <span className="font-semibold text-[#0B132B]">{count}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Badge({ children }: { children: ReactNode }) {
  return <StatusBadge tone="slate">{children}</StatusBadge>;
}
