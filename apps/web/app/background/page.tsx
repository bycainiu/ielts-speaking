"use client";

import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  BookOpenCheck,
  CalendarDays,
  Goal,
  Languages,
  Loader2,
  NotebookPen,
  ShieldCheck,
  Sparkles,
  Target,
  Trash2,
  UserRound,
} from "lucide-react";

import { AcademicShell, InlineKpi, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

type ApiError = {
  response?: {
    status?: number;
    data?: {
      message?: string;
    };
  };
};

type BackgroundFact = {
  topic?: string | null;
  fact_key: string;
  fact_value: string;
  privacy_level: "normal" | "sensitive" | "private" | string;
  allowed_usage: string[];
  is_excluded: boolean;
};

type BackgroundResponse = {
  profile?: {
    display_name?: string | null;
    timezone?: string;
    target_band?: number | null;
    current_band?: number | null;
    preferred_exam_date?: string | null;
  };
  questionnaire?: {
    answers?: Record<string, unknown>;
    privacy_exclusions?: string[];
  } | null;
  facts?: BackgroundFact[];
  agent_facts?: BackgroundFact[];
};

type FactPayload = {
  topic?: string;
  fact_key: string;
  fact_value: string;
  privacy_level?: "normal" | "sensitive" | "private";
  allowed_usage?: string[];
  is_excluded?: boolean;
};

const inputClass =
  "h-11 border-slate-200 bg-white text-slate-900 placeholder:text-slate-400 focus-visible:ring-[#D4AF37] focus-visible:ring-offset-0";
const textareaClass =
  "min-h-24 w-full resize-y rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20";

const defaultFormData = {
  profile: {
    display_name: "",
    timezone: "Asia/Shanghai",
    target_band: "",
    current_band: "",
    preferred_exam_date: "",
  },
  answers: {
    native_language: "",
    study_goal: "",
    hobbies: "",
    weaknesses: "",
    familiar_topics: "",
    speaking_preferences: "",
    free_note: "",
  },
};

type BackgroundFormData = typeof defaultFormData;

export default function BackgroundPage() {
  const router = useRouter();
  const { isAuthenticated, hasHydrated, user } = useAuthStore();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [privacyNotice, setPrivacyNotice] = useState("");
  const [privacyError, setPrivacyError] = useState("");
  const [deletingBackground, setDeletingBackground] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [privacyExclusionsText, setPrivacyExclusionsText] = useState("");
  const [formData, setFormData] = useState<BackgroundFormData>(defaultFormData);

  useEffect(() => {
    if (!hasHydrated) return;
    if (!isAuthenticated) {
      router.push("/login");
      return;
    }

    let cancelled = false;
    const fetchBackground = async () => {
      try {
        const res = await api.get<{ background: BackgroundResponse }>("/me/background");
        if (cancelled) return;
        const background = res.data.background;
        if (background) {
          const answers = background.questionnaire?.answers ?? {};
          const facts = background.facts ?? [];
          const nextFormData = {
            profile: {
              display_name: background.profile?.display_name ?? user?.display_name ?? "",
              timezone: background.profile?.timezone ?? "Asia/Shanghai",
              target_band: valueToText(background.profile?.target_band),
              current_band: valueToText(background.profile?.current_band),
              preferred_exam_date: background.profile?.preferred_exam_date ?? "",
            },
            answers: {
              native_language: answerText(answers, facts, "native_language"),
              study_goal: answerText(answers, facts, "study_goal"),
              hobbies: answerListText(answers, facts, "hobbies"),
              weaknesses: answerListText(answers, facts, "weaknesses"),
              familiar_topics: answerListText(answers, facts, "familiar_topics"),
              speaking_preferences: answerText(answers, facts, "speaking_preferences"),
              free_note: answerText(answers, facts, "free_note"),
            },
          };
          setFormData(nextFormData);
          setPrivacyExclusionsText((background.questionnaire?.privacy_exclusions ?? []).join(", "));
        }
      } catch (err: unknown) {
        const apiError = err as ApiError;
        if (!cancelled && apiError.response?.status !== 404) {
          setError("画像加载失败，请稍后重试。");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchBackground();
    return () => {
      cancelled = true;
    };
  }, [hasHydrated, isAuthenticated, router, user?.display_name]);

  const privacyExclusions = useMemo(() => parseTags(privacyExclusionsText), [privacyExclusionsText]);
  const previewFacts = useMemo(() => buildFacts(formData, privacyExclusions), [formData, privacyExclusions]);
  const allowedPreviewFacts = previewFacts.filter((item) => !item.is_excluded).slice(0, 7);
  const weaknessTags = parseTags(formData.answers.weaknesses);
  const hobbyTags = parseTags(formData.answers.hobbies);
  const familiarTopicTags = parseTags(formData.answers.familiar_topics);

  const updateProfile = (key: keyof BackgroundFormData["profile"], value: string) => {
    setFormData((current) => ({
      ...current,
      profile: { ...current.profile, [key]: value },
    }));
  };

  const updateAnswers = (key: keyof BackgroundFormData["answers"], value: string) => {
    setFormData((current) => ({
      ...current,
      answers: { ...current.answers, [key]: value },
    }));
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError("");

    try {
      await api.put("/me/background", {
        profile: {
          display_name: emptyToUndefined(formData.profile.display_name),
          timezone: formData.profile.timezone || "Asia/Shanghai",
          target_band: numberOrUndefined(formData.profile.target_band),
          current_band: numberOrUndefined(formData.profile.current_band),
          preferred_exam_date: emptyToUndefined(formData.profile.preferred_exam_date),
        },
        version: 1,
        submitted: true,
        answers: {
          native_language: formData.answers.native_language.trim(),
          study_goal: formData.answers.study_goal.trim(),
          hobbies: hobbyTags,
          weaknesses: weaknessTags,
          familiar_topics: familiarTopicTags,
          speaking_preferences: formData.answers.speaking_preferences.trim(),
          free_note: formData.answers.free_note.trim(),
        },
        privacy_exclusions: privacyExclusions,
        facts: previewFacts,
      });
      router.push("/practice");
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "画像保存失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  };

  const deleteBackgroundData = async () => {
    setDeletingBackground(true);
    setPrivacyError("");
    setPrivacyNotice("");
    try {
      await api.post("/privacy/data-deletion", {
        delete_background: true,
        confirmation: deleteConfirmation,
      });
      setFormData(defaultFormData);
      setPrivacyExclusionsText("");
      setDeleteConfirmation("");
      setPrivacyNotice("背景画像数据已删除。");
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setPrivacyError(apiError.response?.data?.message || "背景画像数据删除失败。");
    } finally {
      setDeletingBackground(false);
    }
  };

  if (!hasHydrated || !isAuthenticated) return null;

  return (
    <AcademicShell activePath="/background" userName={user?.display_name} userRole={user?.role}>
      <PageHeader
        eyebrow="Learner Profile"
        title="Your Profile"
        titleZh="学习画像"
        description="Tell us about your IELTS goals, speaking habits and privacy boundaries."
        actions={
          <>
            <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
              Skip / 跳过
            </Button>
            <Button type="submit" form="background-form" variant="gold" disabled={saving || loading}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <NotebookPen className="mr-2 h-4 w-4" />}
              Save Profile
            </Button>
          </>
        }
      />

      {loading ? (
        <Panel className="flex min-h-64 items-center justify-center">
          <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#D4AF37]" />
          <span className="text-sm text-slate-600">Loading profile / 正在加载画像</span>
        </Panel>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <form id="background-form" onSubmit={handleSubmit} className="grid min-w-0 gap-5">
            <Panel tone="paper">
              <SectionHeading icon={UserRound} label="Basic Information" labelZh="基础信息" />
              <div className="grid gap-4 md:grid-cols-3">
                <TextInput label="Display name / 昵称" value={formData.profile.display_name} onChange={(value) => updateProfile("display_name", value)} placeholder="Learner" />
                <TextInput label="Native language / 母语" value={formData.answers.native_language} onChange={(value) => updateAnswers("native_language", value)} placeholder="Mandarin" icon={Languages} />
                <TextInput label="Timezone / 时区" value={formData.profile.timezone} onChange={(value) => updateProfile("timezone", value)} placeholder="Asia/Shanghai" />
              </div>
            </Panel>

            <Panel>
              <SectionHeading icon={Target} label="IELTS Goal" labelZh="备考目标" />
              <div className="grid gap-4 md:grid-cols-4">
                <NumberInput label="Target band / 目标分" value={formData.profile.target_band} onChange={(value) => updateProfile("target_band", value)} placeholder="7.0" />
                <NumberInput label="Current band / 当前水平" value={formData.profile.current_band} onChange={(value) => updateProfile("current_band", value)} placeholder="6.0" />
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="preferred_exam_date" className="text-slate-700">
                    Exam date / 考试日期
                  </Label>
                  <Input
                    id="preferred_exam_date"
                    type="date"
                    value={formData.profile.preferred_exam_date}
                    onChange={(event) => updateProfile("preferred_exam_date", event.target.value)}
                    className={inputClass}
                  />
                </div>
                <div className="space-y-2 md:col-span-4">
                  <Label htmlFor="study_goal" className="text-slate-700">
                    Study goal / 备考目的
                  </Label>
                  <Input
                    id="study_goal"
                    value={formData.answers.study_goal}
                    onChange={(event) => updateAnswers("study_goal", event.target.value)}
                    placeholder="University admission, immigration interview, scholarship application"
                    className={inputClass}
                  />
                </div>
              </div>
            </Panel>

            <Panel>
              <SectionHeading icon={Goal} label="Speaking Preferences" labelZh="口语偏好" />
              <div className="grid gap-4 md:grid-cols-2">
                <TagInput label="Hobbies / 兴趣爱好" value={formData.answers.hobbies} onChange={(value) => updateAnswers("hobbies", value)} placeholder="reading, travel, cooking" tags={hobbyTags} />
                <TagInput label="Weaknesses / 薄弱项" value={formData.answers.weaknesses} onChange={(value) => updateAnswers("weaknesses", value)} placeholder="long pauses, grammar accuracy" tags={weaknessTags} tone="coral" />
                <TagInput label="Familiar topics / 熟悉话题" value={formData.answers.familiar_topics} onChange={(value) => updateAnswers("familiar_topics", value)} placeholder="technology, education, city life" tags={familiarTopicTags} />
                <div className="space-y-2">
                  <Label htmlFor="speaking_preferences" className="text-slate-700">
                    Speaking preferences / 练习偏好
                  </Label>
                  <textarea
                    id="speaking_preferences"
                    value={formData.answers.speaking_preferences}
                    onChange={(event) => updateAnswers("speaking_preferences", event.target.value)}
                    placeholder="I prefer direct feedback after each answer."
                    className={textareaClass}
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="free_note" className="text-slate-700">
                    Free note / 自由补充
                  </Label>
                  <textarea
                    id="free_note"
                    value={formData.answers.free_note}
                    onChange={(event) => updateAnswers("free_note", event.target.value)}
                    placeholder="Anything the examiner should know when personalizing follow-up questions."
                    className={textareaClass}
                  />
                </div>
              </div>
            </Panel>

            <Panel tone="paper">
              <SectionHeading icon={ShieldCheck} label="Privacy Boundaries" labelZh="隐私边界" />
              <TagInput
                label="Excluded facts / 不参与个性化的事实"
                value={privacyExclusionsText}
                onChange={setPrivacyExclusionsText}
                placeholder="workplace, family details, exact address"
                tags={privacyExclusions}
                tone="slate"
              />
            </Panel>

            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm leading-5 text-red-700">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}
          </form>

          <aside className="grid h-fit gap-5">
            <Panel>
              <SectionHeading icon={CalendarDays} label="Profile Snapshot" labelZh="画像摘要" />
              <div className="grid gap-3">
                <InlineKpi label="Target band / 目标分" value={formData.profile.target_band || "-"} />
                <InlineKpi label="Current band / 当前分" value={formData.profile.current_band || "-"} />
                <InlineKpi label="Exam date / 考试日期" value={formData.profile.preferred_exam_date || "-"} />
                <InlineKpi label="Agent facts / 可用事实" value={String(allowedPreviewFacts.length)} />
              </div>
            </Panel>

            <Panel>
              <SectionHeading icon={Sparkles} label="Personalization Preview" labelZh="个性化预览" />
              <div className="space-y-3">
                {allowedPreviewFacts.length > 0 ? (
                  allowedPreviewFacts.map((item) => (
                    <div key={`${item.topic}-${item.fact_key}`} className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold uppercase text-slate-500">{formatFactKey(item.fact_key)}</p>
                        <p className="mt-1 line-clamp-2 text-sm leading-5 text-slate-700">{item.fact_value}</p>
                      </div>
                      <StatusBadge tone={item.privacy_level === "sensitive" ? "coral" : "teal"}>{item.topic || "profile"}</StatusBadge>
                    </div>
                  ))
                ) : (
                  <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm leading-6 text-slate-500">
                    Add a few goals, interests or weak points to preview what the Agent can use. 添加目标、兴趣或弱项后可预览 Agent 可用事实。
                  </p>
                )}
              </div>
              <div className="mt-4 rounded-lg border border-[#D4AF37]/25 bg-[#FFF8DF] p-3 text-xs leading-5 text-slate-600">
                <StatusBadge tone="gold">Practice reference</StatusBadge>
                <p className="mt-2">Personalization guides questions and feedback emphasis only. 个性化仅用于练习追问与反馈侧重点。</p>
              </div>
            </Panel>

            <Panel>
              <SectionHeading icon={BookOpenCheck} label="Privacy Exclusions" labelZh="排除项" />
              {privacyExclusions.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {privacyExclusions.map((item) => (
                    <StatusBadge key={item} tone="slate">{item}</StatusBadge>
                  ))}
                </div>
              ) : (
                <p className="text-sm leading-6 text-slate-500">No exclusions yet. 当前没有排除项。</p>
              )}
            </Panel>

            <Panel className="border-red-200 bg-red-50">
              <SectionHeading icon={Trash2} label="Delete Profile Data" labelZh="删除画像" />
              <p className="text-sm leading-6 text-red-700">
                This removes saved questionnaire answers and background facts from future personalization.
              </p>
              <div className="mt-4 space-y-2">
                <Label htmlFor="delete_confirmation" className="text-red-700">
                  Confirmation / 确认文本
                </Label>
                <Input
                  id="delete_confirmation"
                  value={deleteConfirmation}
                  onChange={(event) => setDeleteConfirmation(event.target.value)}
                  placeholder="DELETE_MY_DATA"
                  className="h-11 border-red-200 bg-white text-red-900 placeholder:text-red-300 focus-visible:ring-red-300 focus-visible:ring-offset-0"
                />
              </div>
              <Button
                type="button"
                variant="dangerOutline"
                disabled={deletingBackground || deleteConfirmation !== "DELETE_MY_DATA"}
                onClick={deleteBackgroundData}
                className="mt-4 w-full"
              >
                {deletingBackground ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
                Delete / 删除
              </Button>
              {privacyNotice && <p className="mt-3 text-sm text-[#3E7056]">{privacyNotice}</p>}
              {privacyError && <p className="mt-3 text-sm text-red-700">{privacyError}</p>}
            </Panel>
          </aside>
        </div>
      )}
    </AcademicShell>
  );
}

function TextInput({
  label,
  value,
  onChange,
  placeholder,
  icon: Icon,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  icon?: LucideIcon;
}) {
  return (
    <div className="space-y-2">
      <Label className="text-slate-700">
        {Icon && <Icon className="mr-1 inline h-3.5 w-3.5 text-[#3A7CA5]" />}
        {label}
      </Label>
      <Input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} className={inputClass} />
    </div>
  );
}

function NumberInput({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <div className="space-y-2">
      <Label className="text-slate-700">{label}</Label>
      <Input type="number" step="0.5" min="0" max="9" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} className={inputClass} />
    </div>
  );
}

function TagInput({
  label,
  value,
  onChange,
  placeholder,
  tags,
  tone = "teal",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  tags: string[];
  tone?: "teal" | "coral" | "slate";
}) {
  return (
    <div className="space-y-2">
      <Label className="text-slate-700">{label}</Label>
      <Input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} className={inputClass} />
      <div className="flex min-h-7 flex-wrap gap-2">
        {tags.length > 0 ? (
          tags.map((tag) => (
            <StatusBadge key={tag} tone={tone}>
              {tag}
            </StatusBadge>
          ))
        ) : (
          <span className="text-xs leading-7 text-slate-400">Separate items with commas / 使用英文逗号分隔</span>
        )}
      </div>
    </div>
  );
}

function buildFacts(formData: BackgroundFormData, exclusions: string[]): FactPayload[] {
  const excluded = new Set(exclusions);
  const facts: FactPayload[] = [];

  addFact(facts, excluded, "profile", "native_language", formData.answers.native_language);
  addFact(facts, excluded, "goal", "study_goal", formData.answers.study_goal);
  addFact(facts, excluded, "goal", "target_band", formData.profile.target_band, "normal", ["question_personalization", "feedback_personalization", "scoring_context"]);
  addFact(facts, excluded, "goal", "current_band", formData.profile.current_band, "normal", ["feedback_personalization", "scoring_context"]);
  addFact(facts, excluded, "interests", "hobbies", parseTags(formData.answers.hobbies).join(", "));
  addFact(facts, excluded, "skills", "weaknesses", parseTags(formData.answers.weaknesses).join(", "), "sensitive", ["feedback_personalization", "scoring_context"]);
  addFact(facts, excluded, "topics", "familiar_topics", parseTags(formData.answers.familiar_topics).join(", "));
  addFact(facts, excluded, "preference", "speaking_preferences", formData.answers.speaking_preferences, "normal", ["question_personalization", "feedback_personalization"]);
  addFact(facts, excluded, "note", "free_note", formData.answers.free_note, "sensitive", ["question_personalization", "feedback_personalization"]);

  return facts;
}

function addFact(
  facts: FactPayload[],
  excluded: Set<string>,
  topic: string,
  key: string,
  value: string,
  privacyLevel: "normal" | "sensitive" | "private" = "normal",
  allowedUsage: string[] = ["question_personalization", "feedback_personalization"],
) {
  const trimmed = value.trim();
  if (!trimmed) return;
  facts.push({
    topic,
    fact_key: key,
    fact_value: trimmed,
    privacy_level: privacyLevel,
    allowed_usage: allowedUsage,
    is_excluded: excluded.has(key) || excluded.has(`${topic}.${key}`),
  });
}

function parseTags(value: string) {
  return Array.from(
    new Set(
      value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

function answerText(answers: Record<string, unknown>, facts: BackgroundFact[], key: string) {
  const value = answers[key];
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.filter((item) => typeof item === "string").join(", ");
  return facts.find((item) => item.fact_key === key)?.fact_value ?? "";
}

function answerListText(answers: Record<string, unknown>, facts: BackgroundFact[], key: string) {
  const value = answers[key];
  if (Array.isArray(value)) return value.filter((item) => typeof item === "string").join(", ");
  if (typeof value === "string") return value;
  return facts.find((item) => item.fact_key === key)?.fact_value ?? "";
}

function valueToText(value: number | null | undefined) {
  return typeof value === "number" ? String(value) : "";
}

function numberOrUndefined(value: string) {
  if (!value.trim()) return undefined;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function emptyToUndefined(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function formatFactKey(value: string) {
  return value.replaceAll("_", " ");
}
