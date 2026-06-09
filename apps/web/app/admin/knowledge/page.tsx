"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Archive, ArrowLeft, Database, FileUp, Loader2, RefreshCcw, Save, Search, ShieldCheck } from "lucide-react";

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

type KnowledgeDoc = {
  id: string;
  doc_type: string;
  title: string;
  content_hash: string;
  metadata: Record<string, unknown>;
  status: string;
  chunk_count: number;
  token_count: number;
  embedding_model?: string;
  updated_at: string;
};

type Filters = {
  docType: string;
  status: string;
};

type FormState = {
  docType: string;
  title: string;
  status: string;
  content: string;
  metadata: string;
};

const emptyFilters: Filters = { docType: "", status: "" };
const emptyForm: FormState = {
  docType: "topic_knowledge",
  title: "",
  status: "draft",
  content: "",
  metadata: '{\n  "knowledge_type": "vocabulary"\n}',
};

const docTypeOptions = ["topic_knowledge", "rubric", "review_history"];
const statusOptions = ["draft", "reviewing", "active", "archived"];

export default function KnowledgeAdminPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [activeFilters, setActiveFilters] = useState<Filters>(emptyFilters);
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
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
    async function loadDocs() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ limit: "80" });
        if (activeFilters.docType) params.set("doc_type", activeFilters.docType);
        if (activeFilters.status) params.set("status", activeFilters.status);
        const response = await api.get<{ docs: KnowledgeDoc[] }>(`/admin/knowledge/docs?${params.toString()}`);
        if (!cancelled) {
          setDocs(response.data.docs ?? []);
        }
      } catch (err: unknown) {
        const apiError = err as ApiError;
        if (!cancelled) {
          setError(apiError.response?.data?.message || "Knowledge documents could not be loaded.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadDocs();
    return () => {
      cancelled = true;
    };
  }, [activeFilters, canAdmin, hasHydrated, isAuthenticated]);

  const reloadDocs = () => {
    setActiveFilters((current) => ({ ...current }));
  };

  const updateForm = (key: keyof FormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const createDoc = async () => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = {
        doc_type: form.docType,
        title: form.title.trim(),
        status: form.status,
        content: form.content.trim(),
        metadata: parseMetadata(form.metadata),
      };
      await api.post("/admin/knowledge/docs", payload);
      setNotice("Knowledge document uploaded and indexed.");
      setForm(emptyForm);
      reloadDocs();
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Knowledge document could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const updateStatus = async (doc: KnowledgeDoc, status: string) => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api.put(`/admin/knowledge/docs/${doc.id}`, {
        title: doc.title,
        status,
        metadata: doc.metadata ?? {},
      });
      setNotice("Knowledge document status updated.");
      reloadDocs();
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Status could not be updated.");
    } finally {
      setSaving(false);
    }
  };

  const reindexDoc = async (doc: KnowledgeDoc) => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api.post(`/admin/knowledge/docs/${doc.id}/reindex`);
      setNotice("Knowledge document reindexed.");
      reloadDocs();
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Reindex could not be completed.");
    } finally {
      setSaving(false);
    }
  };

  const archiveDoc = async (doc: KnowledgeDoc) => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api.delete(`/admin/knowledge/docs/${doc.id}`);
      setNotice("Knowledge document archived.");
      reloadDocs();
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Document could not be archived.");
    } finally {
      setSaving(false);
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/admin/knowledge" userName={user?.display_name} userRole={user?.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">
          <SectionHeading icon={ShieldCheck} label="Access denied" labelZh="权限不足" />
          <h1 className="font-serif text-3xl text-[#0B132B]">Knowledge Admin</h1>
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
    <AcademicShell activePath="/admin/knowledge" userName={user?.display_name} userRole={user?.role}>
      <PageHeader
        eyebrow="Content Operations"
        title="Knowledge Admin"
        titleZh="知识库管理"
        description="Topic knowledge, scoring material, and review-history indexing."
        actions={
          <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Practice / 练习
          </Button>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}
      {notice && <Panel className="border-[#4F8A6B]/25 bg-[#EEF7F2] text-sm text-[#3E7056]">{notice}</Panel>}

      <Panel tone="paper">
        <SectionHeading icon={Search} label="Filters" labelZh="筛选" />
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto_auto]">
          <SelectField label="Doc Type" value={filters.docType} onChange={(value) => setFilters((current) => ({ ...current, docType: value }))}>
            <option value="">All types</option>
            {docTypeOptions.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </SelectField>
          <SelectField label="Status" value={filters.status} onChange={(value) => setFilters((current) => ({ ...current, status: value }))}>
            <option value="">All statuses</option>
            {statusOptions.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </SelectField>
          <Button type="button" variant="gold" onClick={() => setActiveFilters(filters)} className="h-11 self-end">
            <Search className="mr-2 h-4 w-4" />
            Apply
          </Button>
          <Button type="button" variant="soft" onClick={() => { setFilters(emptyFilters); setActiveFilters(emptyFilters); }} className="h-11 self-end">
            Reset
          </Button>
        </div>
      </Panel>

      <section className="grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Panel>
          <SectionHeading icon={FileUp} label="Upload Document" labelZh="上传文档" />
          <div className="grid gap-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <SelectField label="Doc Type" value={form.docType} onChange={(value) => updateForm("docType", value)}>
                {docTypeOptions.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </SelectField>
              <SelectField label="Status" value={form.status} onChange={(value) => updateForm("status", value)}>
                {statusOptions.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </SelectField>
            </div>
            <TextField label="Title" value={form.title} onChange={(value) => updateForm("title", value)} />
            <TextAreaField label="Content" value={form.content} onChange={(value) => updateForm("content", value)} minHeight="220px" />
            <TextAreaField label="Metadata JSON" value={form.metadata} onChange={(value) => updateForm("metadata", value)} minHeight="120px" />
            <Button type="button" variant="gold" onClick={createDoc} disabled={saving || !form.title.trim() || !form.content.trim()}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              Save Document
            </Button>
          </div>
        </Panel>

        <Panel>
          <div className="mb-5 flex items-center justify-between gap-3">
            <SectionHeading icon={Database} label="Index Status" labelZh="索引状态" />
            <span className="text-sm text-slate-500">{docs.length} documents</span>
          </div>
          {loading ? (
            <div className="flex min-h-40 items-center justify-center text-sm text-slate-600">
              <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#D4AF37]" />
              Loading documents...
            </div>
          ) : docs.length === 0 ? (
            <EmptyState icon={Database} title="No knowledge documents" body="No knowledge documents match the current filters. 当前筛选条件下暂无知识库文档。" />
          ) : (
            <div className="grid gap-4">
              {docs.map((doc) => (
                <article key={doc.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap gap-2">
                        <Badge>{doc.doc_type}</Badge>
                        <Badge>{doc.status}</Badge>
                        <Badge>{String(doc.metadata?.index_status ?? "indexed")}</Badge>
                        <Badge>{doc.chunk_count} chunks</Badge>
                      </div>
                      <h2 className="mt-3 break-words text-base font-semibold leading-relaxed text-[#0B132B]">{doc.title}</h2>
                      <p className="mt-2 break-all text-xs text-slate-500">{doc.content_hash}</p>
                      <p className="mt-2 text-sm text-slate-600">
                        {doc.token_count} tokens · {doc.embedding_model || "no embedding"}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2 xl:justify-end">
                      <select value={doc.status} onChange={(event) => updateStatus(doc, event.target.value)} className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-[#D4AF37]">
                        {statusOptions.map((status) => (
                          <option key={status} value={status}>
                            {status}
                          </option>
                        ))}
                      </select>
                      <Button type="button" variant="soft" onClick={() => reindexDoc(doc)}>
                        <RefreshCcw className="mr-2 h-4 w-4" />
                        Reindex
                      </Button>
                      <Button type="button" variant="soft" onClick={() => archiveDoc(doc)}>
                        <Archive className="mr-2 h-4 w-4" />
                        Archive
                      </Button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Panel>
      </section>
    </AcademicShell>
  );
}

function parseMetadata(value: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed) as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("metadata must be an object");
  }
  return parsed as Record<string, unknown>;
}

function SelectField({ label, value, onChange, children }: { label: string; value: string; onChange: (value: string) => void; children: ReactNode }) {
  return (
    <label className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20">
        {children}
      </select>
    </label>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20" />
    </label>
  );
}

function TextAreaField({ label, value, onChange, minHeight }: { label: string; value: string; onChange: (value: string) => void; minHeight: string }) {
  return (
    <label className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <textarea value={value} onChange={(event) => onChange(event.target.value)} style={{ minHeight }} className="w-full resize-y rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-relaxed text-slate-900 outline-none transition-colors focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20" />
    </label>
  );
}

function Badge({ children }: { children: ReactNode }) {
  return <StatusBadge tone="slate">{children}</StatusBadge>;
}
