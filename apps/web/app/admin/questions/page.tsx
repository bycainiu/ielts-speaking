"use client";

import { useEffect, useId, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Archive,
  FilePenLine,
  Filter,
  Loader2,
  Save,
  Search,
  ShieldCheck,
  Upload,
} from "lucide-react";

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

type Season = {
  id: string;
  code: string;
  title: string;
  status: string;
  is_active: boolean;
};

type Topic = {
  id: string;
  name: string;
  slug: string;
  status: string;
};

type CueCard = {
  prompt: string;
  bullet_points?: string[];
  preparation_seconds?: number;
  speaking_seconds?: number;
};

type FollowupTemplate = {
  part: number;
  text: string;
  trigger_hint?: string | null;
  sort_order?: number;
  review_status?: string;
};

type Question = {
  id: string;
  season_id?: string | null;
  topic_id?: string | null;
  part: number;
  text: string;
  difficulty?: number | null;
  source_type: string;
  license?: string | null;
  review_status: string;
  metadata?: Record<string, unknown>;
  cue_card?: CueCard | null;
  followup_templates?: FollowupTemplate[];
  updated_at: string;
};

type QuestionPayload = {
  season_id?: string | null;
  topic_id?: string | null;
  part: number;
  text: string;
  difficulty?: number | null;
  source_type?: string;
  license?: string | null;
  review_status?: string;
  metadata?: Record<string, unknown>;
  cue_card?: CueCard;
  followup_templates?: FollowupTemplate[];
};

type Filters = {
  seasonId: string;
  topicId: string;
  part: string;
  status: string;
};

type QuestionForm = {
  seasonId: string;
  topicId: string;
  part: string;
  text: string;
  difficulty: string;
  sourceType: string;
  license: string;
  reviewStatus: string;
  cuePrompt: string;
  cueBullets: string;
};

const emptyFilters: Filters = {
  seasonId: "",
  topicId: "",
  part: "",
  status: "",
};

const emptyForm: QuestionForm = {
  seasonId: "",
  topicId: "",
  part: "1",
  text: "",
  difficulty: "",
  sourceType: "original",
  license: "",
  reviewStatus: "draft",
  cuePrompt: "",
  cueBullets: "",
};

const statusOptions = ["draft", "reviewing", "active", "archived"];
const sourceOptions = ["original", "authorized", "user_recall", "internal"];

export default function QuestionAdminPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [activeFilters, setActiveFilters] = useState<Filters>(emptyFilters);
  const [seasons, setSeasons] = useState<Season[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [form, setForm] = useState<QuestionForm>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [importText, setImportText] = useState("");
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
    async function loadCatalogs() {
      try {
        const [seasonResponse, topicResponse] = await Promise.all([
          api.get<{ seasons: Season[] }>("/admin/question-bank/seasons"),
          api.get<{ topics: Topic[] }>("/admin/question-bank/topics"),
        ]);
        if (!cancelled) {
          setSeasons(seasonResponse.data.seasons ?? []);
          setTopics(topicResponse.data.topics ?? []);
        }
      } catch (err: unknown) {
        const apiError = err as ApiError;
        if (!cancelled) {
          setError(apiError.response?.data?.message || "Admin catalogs could not be loaded.");
        }
      }
    }

    loadCatalogs();
    return () => {
      cancelled = true;
    };
  }, [canAdmin, hasHydrated, isAuthenticated]);

  useEffect(() => {
    if (!hasHydrated || !isAuthenticated || !canAdmin) return;

    let cancelled = false;
    async function loadQuestions() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ limit: "80" });
        if (activeFilters.seasonId) params.set("season_id", activeFilters.seasonId);
        if (activeFilters.topicId) params.set("topic_id", activeFilters.topicId);
        if (activeFilters.part) params.set("part", activeFilters.part);
        if (activeFilters.status) params.set("review_status", activeFilters.status);
        const response = await api.get<{ questions: Question[] }>(`/admin/question-bank/questions?${params.toString()}`);
        if (!cancelled) {
          setQuestions(response.data.questions ?? []);
        }
      } catch (err: unknown) {
        const apiError = err as ApiError;
        if (!cancelled) {
          setError(apiError.response?.data?.message || "Questions could not be loaded.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadQuestions();
    return () => {
      cancelled = true;
    };
  }, [activeFilters, canAdmin, hasHydrated, isAuthenticated]);

  const seasonById = useMemo(() => new Map(seasons.map((item) => [item.id, item])), [seasons]);
  const topicById = useMemo(() => new Map(topics.map((item) => [item.id, item])), [topics]);

  const updateFilter = (key: keyof Filters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const updateForm = (key: keyof QuestionForm, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const resetForm = () => {
    setEditingId(null);
    setForm(emptyForm);
  };

  const reloadQuestions = () => {
    setActiveFilters((current) => ({ ...current }));
  };

  const saveQuestion = async () => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = buildPayload(form);
      if (editingId) {
        await api.put(`/admin/question-bank/questions/${editingId}`, payload);
        setNotice("Question updated.");
      } else {
        await api.post("/admin/question-bank/questions", payload);
        setNotice("Question created.");
      }
      resetForm();
      reloadQuestions();
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Question could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const editQuestion = (question: Question) => {
    setEditingId(question.id);
    setForm({
      seasonId: question.season_id ?? "",
      topicId: question.topic_id ?? "",
      part: String(question.part),
      text: question.text,
      difficulty: question.difficulty ? String(question.difficulty) : "",
      sourceType: question.source_type || "original",
      license: question.license ?? "",
      reviewStatus: question.review_status || "draft",
      cuePrompt: question.cue_card?.prompt ?? "",
      cueBullets: (question.cue_card?.bullet_points ?? []).join("\n"),
    });
  };

  const updateStatus = async (question: Question, reviewStatus: string) => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api.put(`/admin/question-bank/questions/${question.id}`, questionToPayload(question, { review_status: reviewStatus }));
      setNotice("Review status updated.");
      reloadQuestions();
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Review status could not be updated.");
    } finally {
      setSaving(false);
    }
  };

  const archiveQuestion = async (question: Question) => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api.delete(`/admin/question-bank/questions/${question.id}`);
      setNotice("Question archived.");
      reloadQuestions();
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Question could not be archived.");
    } finally {
      setSaving(false);
    }
  };

  const importQuestions = async () => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const parsed = JSON.parse(importText) as QuestionPayload[];
      if (!Array.isArray(parsed) || parsed.length === 0) {
        throw new Error("invalid import payload");
      }
      for (const item of parsed) {
        await api.post("/admin/question-bank/questions", item);
      }
      setImportText("");
      setNotice("Operation completed.");;
      reloadQuestions();
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Batch import could not be completed.");
    } finally {
      setSaving(false);
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/admin/questions" userName={user?.display_name} userRole={user?.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">
          <SectionHeading icon={ShieldCheck} label="Access denied" labelZh="权限不足" />
          <h1 className="font-serif text-3xl text-[#0B132B]">Question Admin</h1>
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
    <AcademicShell activePath="/admin/questions" userName={user?.display_name} userRole={user?.role}>
      <PageHeader
        eyebrow="Content Operations"
        title="Question Admin"
        titleZh="题库管理"
        description="Quarterly question bank review, import, status flow, and publishing."
        actions={
          <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Practice / 练习
          </Button>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}
      {notice && (
        <Panel className="border-[#4F8A6B]/25 bg-[#EEF7F2] text-sm text-[#3E7056]">
          {notice}
        </Panel>
      )}

      <Panel tone="paper">
        <SectionHeading icon={Filter} label="Filters" labelZh="筛选" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[1fr_1fr_0.7fr_0.9fr_auto_auto]">
          <SelectField label="Season" value={filters.seasonId} onChange={(value) => updateFilter("seasonId", value)}>
            <option value="">All seasons</option>
            {seasons.map((season) => (
              <option key={season.id} value={season.id}>
                {season.code} {season.is_active ? "(active)" : ""}
              </option>
            ))}
          </SelectField>
          <SelectField label="Topic" value={filters.topicId} onChange={(value) => updateFilter("topicId", value)}>
            <option value="">All topics</option>
            {topics.map((topic) => (
              <option key={topic.id} value={topic.id}>
                {topic.name}
              </option>
            ))}
          </SelectField>
          <SelectField label="Part" value={filters.part} onChange={(value) => updateFilter("part", value)}>
            <option value="">All parts</option>
            <option value="1">Part 1</option>
            <option value="2">Part 2</option>
            <option value="3">Part 3</option>
          </SelectField>
          <SelectField label="Status" value={filters.status} onChange={(value) => updateFilter("status", value)}>
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
          <Button
            type="button"
            variant="soft"
            onClick={() => {
              setFilters(emptyFilters);
              setActiveFilters(emptyFilters);
            }}
            className="h-11 self-end"
          >
            Reset
          </Button>
        </div>
      </Panel>

      <section className="grid gap-5 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <Panel>
          <SectionHeading icon={FilePenLine} label={editingId ? "Edit Question" : "Create Question"} labelZh={editingId ? "编辑题目" : "新建题目"} />
          <div className="grid gap-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <SelectField label="Season" value={form.seasonId} onChange={(value) => updateForm("seasonId", value)}>
                <option value="">No season</option>
                {seasons.map((season) => (
                  <option key={season.id} value={season.id}>
                    {season.code}
                  </option>
                ))}
              </SelectField>
              <SelectField label="Topic" value={form.topicId} onChange={(value) => updateForm("topicId", value)}>
                <option value="">No topic</option>
                {topics.map((topic) => (
                  <option key={topic.id} value={topic.id}>
                    {topic.name}
                  </option>
                ))}
              </SelectField>
              <SelectField label="Part" value={form.part} onChange={(value) => updateForm("part", value)}>
                <option value="1">Part 1</option>
                <option value="2">Part 2</option>
                <option value="3">Part 3</option>
              </SelectField>
              <SelectField label="Review Status" value={form.reviewStatus} onChange={(value) => updateForm("reviewStatus", value)}>
                {statusOptions.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </SelectField>
              <SelectField label="Source" value={form.sourceType} onChange={(value) => updateForm("sourceType", value)}>
                {sourceOptions.map((source) => (
                  <option key={source} value={source}>
                    {source}
                  </option>
                ))}
              </SelectField>
              <TextField label="Difficulty" value={form.difficulty} onChange={(value) => updateForm("difficulty", value)} type="number" />
            </div>
            <TextAreaField label="Question Text" value={form.text} onChange={(value) => updateForm("text", value)} minHeight="140px" />
            <TextField label="License" value={form.license} onChange={(value) => updateForm("license", value)} />
            {form.part === "2" && (
              <div className="grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
                <TextAreaField label="Cue Card Prompt" value={form.cuePrompt} onChange={(value) => updateForm("cuePrompt", value)} minHeight="96px" />
                <TextAreaField label="Bullet Points" value={form.cueBullets} onChange={(value) => updateForm("cueBullets", value)} minHeight="120px" />
              </div>
            )}
            <div className="flex flex-wrap gap-3">
              <Button type="button" variant="gold" onClick={saveQuestion} disabled={saving || !form.text.trim()}>
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                Save
              </Button>
              <Button type="button" variant="soft" onClick={resetForm}>
                Clear
              </Button>
            </div>
          </div>
        </Panel>

        <Panel>
          <SectionHeading icon={Upload} label="Batch Import" labelZh="批量导入" />
          <TextAreaField label="Batch JSON" value={importText} onChange={setImportText} minHeight="245px" />
          <Button type="button" variant="gold" onClick={importQuestions} disabled={saving || !importText.trim()} className="mt-4">
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
            Import
          </Button>
        </Panel>
      </section>

      <Panel>
        <div className="mb-5 flex items-center justify-between gap-3">
          <SectionHeading icon={FilePenLine} label="Questions" labelZh="题目列表" />
          <span className="text-sm text-slate-500">{questions.length} items</span>
        </div>

        {loading ? (
          <div className="flex min-h-40 items-center justify-center text-sm text-slate-600">
            <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#D4AF37]" />
            Loading questions...
          </div>
        ) : questions.length === 0 ? (
          <EmptyState icon={FilePenLine} title="No questions" body="暂无题目。" />
        ) : (
          <div className="grid gap-4">
            {questions.map((question) => (
              <article key={question.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap gap-2">
                      <Badge>Part {question.part}</Badge>
                      <Badge>{question.review_status}</Badge>
                      <Badge>{question.source_type}</Badge>
                      {question.season_id && <Badge>{seasonById.get(question.season_id)?.code ?? "Season"}</Badge>}
                      {question.topic_id && <Badge>{topicById.get(question.topic_id)?.name ?? "Topic"}</Badge>}
                    </div>
                    <h2 className="mt-3 break-words text-base font-semibold leading-relaxed text-[#0B132B]">{question.text}</h2>
                    {question.cue_card && (
                      <p className="mt-2 text-sm leading-relaxed text-slate-600">{question.cue_card.prompt}</p>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2 lg:justify-end">
                    <select
                      value={question.review_status}
                      onChange={(event) => updateStatus(question, event.target.value)}
                      className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-[#D4AF37]"
                    >
                      {statusOptions.map((status) => (
                        <option key={status} value={status}>
                          {status}
                        </option>
                      ))}
                    </select>
                    <Button type="button" variant="soft" onClick={() => editQuestion(question)}>
                      <FilePenLine className="mr-2 h-4 w-4" />
                      Edit
                    </Button>
                    <Button type="button" variant="soft" onClick={() => archiveQuestion(question)}>
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
    </AcademicShell>
  );
}

function SelectField({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  const generatedId = useId();
  const id = `admin-${label.toLowerCase().replaceAll(" ", "-")}-${generatedId}`;
  return (
    <label htmlFor={id} className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20"
      >
        {children}
      </select>
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  const generatedId = useId();
  const id = `admin-${label.toLowerCase().replaceAll(" ", "-")}-${generatedId}`;
  return (
    <label htmlFor={id} className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20"
      />
    </label>
  );
}

function TextAreaField({
  label,
  value,
  onChange,
  minHeight,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  minHeight: string;
}) {
  const generatedId = useId();
  const id = `admin-${label.toLowerCase().replaceAll(" ", "-")}-${generatedId}`;
  return (
    <label htmlFor={id} className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <textarea
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        style={{ minHeight }}
        className="w-full resize-y rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-relaxed text-slate-900 outline-none transition-colors focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20"
      />
    </label>
  );
}

function Badge({ children }: { children: ReactNode }) {
  return <StatusBadge tone="slate">{children}</StatusBadge>;
}

function buildPayload(form: QuestionForm): QuestionPayload {
  const part = Number(form.part);
  const payload: QuestionPayload = {
    season_id: form.seasonId || null,
    topic_id: form.topicId || null,
    part,
    text: form.text.trim(),
    difficulty: form.difficulty ? Number(form.difficulty) : null,
    source_type: form.sourceType,
    license: form.license.trim() || null,
    review_status: form.reviewStatus,
    metadata: {},
    followup_templates: [],
  };
  if (part === 2) {
    payload.cue_card = {
      prompt: form.cuePrompt.trim() || form.text.trim(),
      bullet_points: form.cueBullets
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
      preparation_seconds: 60,
      speaking_seconds: 120,
    };
  }
  return payload;
}

function questionToPayload(question: Question, overrides: Partial<QuestionPayload> = {}): QuestionPayload {
  const payload: QuestionPayload = {
    season_id: question.season_id ?? null,
    topic_id: question.topic_id ?? null,
    part: question.part,
    text: question.text,
    difficulty: question.difficulty ?? null,
    source_type: question.source_type,
    license: question.license ?? null,
    review_status: question.review_status,
    metadata: question.metadata ?? {},
    followup_templates: question.followup_templates ?? [],
  };
  if (question.part === 2 && question.cue_card) {
    payload.cue_card = {
      prompt: question.cue_card.prompt,
      bullet_points: question.cue_card.bullet_points ?? [],
      preparation_seconds: question.cue_card.preparation_seconds ?? 60,
      speaking_seconds: question.cue_card.speaking_seconds ?? 120,
    };
  }
  return { ...payload, ...overrides };
}
