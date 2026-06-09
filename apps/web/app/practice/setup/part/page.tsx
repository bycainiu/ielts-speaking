"use client";

import { useEffect, useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  Hash,
  HelpCircle,
  Loader2,
  PlayCircle,
  Radar,
  SlidersHorizontal,
  Target,
  TimerReset,
} from "lucide-react";

import { AcademicShell, InlineKpi, MiniSparkline, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

type Season = {
  id: string;
  title: string;
};

type Topic = {
  id: string;
  name: string;
  slug: string;
  status: string;
};

type Question = {
  id: string;
  topic_id?: string | null;
  part: number;
  review_status: string;
};

type ApiError = {
  response?: {
    data?: {
      message?: string;
    };
  };
};

const partProfiles = {
  1: {
    title: "Part 1",
    titleZh: "日常问答",
    duration: "4-5 min",
    focus: "Short natural answers, fluency warm-up, common daily topics.",
    recommendation: "Answer in 2-4 sentences. Avoid memorized long speeches.",
  },
  2: {
    title: "Part 2",
    titleZh: "话题卡长轮次",
    duration: "3-4 min",
    focus: "Cue card structure, preparation notes, long-turn coherence.",
    recommendation: "Use a simple story arc: context, details, feeling, reflection.",
  },
  3: {
    title: "Part 3",
    titleZh: "抽象讨论",
    duration: "4-5 min",
    focus: "Abstract reasoning, examples, comparison and opinion depth.",
    recommendation: "State your view first, then explain with one concrete example.",
  },
};

export default function PartPracticeSetupPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [season, setSeason] = useState<Season | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [selectedPart, setSelectedPart] = useState<1 | 2 | 3>(2);
  const [selectedTopicId, setSelectedTopicId] = useState("");
  const [questionCount, setQuestionCount] = useState(4);
  const [followupIntensity, setFollowupIntensity] = useState(2);
  const [hintsEnabled, setHintsEnabled] = useState(true);
  const [immediateScoring, setImmediateScoring] = useState(true);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

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
    async function loadCatalog() {
      setLoading(true);
      setError("");
      try {
        const [seasonResponse, topicResponse, questionResponse] = await Promise.allSettled([
          api.get<{ season: Season }>("/seasons/active"),
          api.get<{ topics: Topic[] }>("/topics"),
          api.get<{ questions: Question[] }>("/questions?limit=120"),
        ]);
        if (cancelled) return;
        if (seasonResponse.status === "fulfilled") setSeason(seasonResponse.value.data.season);
        if (topicResponse.status === "fulfilled") setTopics(topicResponse.value.data.topics ?? []);
        if (questionResponse.status === "fulfilled") setQuestions(questionResponse.value.data.questions ?? []);
      } catch (err: unknown) {
        const apiError = err as ApiError;
        if (!cancelled) {
          setError(apiError.response?.data?.message || "Practice catalog could not be loaded.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadCatalog();
    return () => {
      cancelled = true;
    };
  }, [hasHydrated, isAuthenticated]);

  const selectedTopic = topics.find((topic) => topic.id === selectedTopicId) ?? null;
  const partQuestionCount = useMemo(
    () => questions.filter((question) => question.part === selectedPart && (!selectedTopicId || question.topic_id === selectedTopicId)).length,
    [questions, selectedPart, selectedTopicId],
  );
  const topicOptions = useMemo(() => topics.filter((topic) => topic.status === "active"), [topics]);
  const profile = partProfiles[selectedPart];

  const startPractice = async () => {
    setStarting(true);
    setError("");
    try {
      const response = await api.post("/sessions", {
        mode: "part_practice",
        season_id: season?.id,
        topic_id: selectedTopicId || undefined,
        target_part: selectedPart,
        state: {
          setup_surface: "part_practice",
          hints_enabled: hintsEnabled,
          immediate_scoring: immediateScoring,
          followup_intensity: followupIntensity,
          question_count: questionCount,
          selected_topic_name: selectedTopic?.name,
          ui_locale_hint: "en-CN",
        },
      });
      const sessionId = response.data.session.id;
      await api.post(`/sessions/${sessionId}/start`);
      router.push(`/live/${sessionId}`);
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Part practice could not be started.");
    } finally {
      setStarting(false);
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  return (
    <AcademicShell activePath="/practice" userName={user?.display_name || user?.email} userRole={user?.role}>
      <PageHeader
        eyebrow="Focused Practice"
        title="Part Practice"
        titleZh="单项练习配置"
        description="Choose one IELTS Speaking part and tune the practice intensity before entering the Live room."
        actions={
          <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Dashboard
          </Button>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}

      <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
        <Panel>
          <SectionHeading icon={SlidersHorizontal} label="Training Setup" labelZh="练习设置" />
          <div className="grid gap-5">
            <div>
              <p className="mb-2 text-sm font-semibold text-slate-700">Part 分段选择</p>
              <div className="grid grid-cols-3 gap-2 rounded-lg border border-slate-200 bg-slate-50 p-1">
                {[1, 2, 3].map((part) => (
                  <button
                    key={part}
                    type="button"
                    onClick={() => setSelectedPart(part as 1 | 2 | 3)}
                    className={`min-h-12 cursor-pointer rounded-md px-3 text-sm font-semibold transition-colors ${
                      selectedPart === part ? "bg-[#0B132B] text-white shadow-sm" : "text-slate-600 hover:bg-white"
                    }`}
                  >
                    Part {part}
                    <span className="block text-[11px] font-medium opacity-70">{partProfiles[part as 1 | 2 | 3].titleZh}</span>
                  </button>
                ))}
              </div>
            </div>

            <label htmlFor="topic" className="grid gap-2 text-sm font-medium text-slate-700">
              <span>Topic 主题</span>
              <select
                id="topic"
                value={selectedTopicId}
                onChange={(event) => setSelectedTopicId(event.target.value)}
                className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none transition-colors focus:border-[#D4AF37]"
              >
                <option value="">Any active topic</option>
                {topicOptions.map((topic) => (
                  <option key={topic.id} value={topic.id}>
                    {topic.name}
                  </option>
                ))}
              </select>
            </label>

            <div className="grid gap-4 md:grid-cols-2">
              <label htmlFor="questionCount" className="grid gap-2 text-sm font-medium text-slate-700">
                <span>Question count 题量</span>
                <input
                  id="questionCount"
                  type="number"
                  min={1}
                  max={10}
                  value={questionCount}
                  onChange={(event) => setQuestionCount(Number(event.target.value))}
                  className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none transition-colors focus:border-[#D4AF37]"
                />
              </label>
              <label htmlFor="intensity" className="grid gap-2 text-sm font-medium text-slate-700">
                <span>Follow-up intensity 追问强度</span>
                <input
                  id="intensity"
                  type="range"
                  min={1}
                  max={3}
                  value={followupIntensity}
                  onChange={(event) => setFollowupIntensity(Number(event.target.value))}
                  className="h-11 cursor-pointer accent-[#D4AF37]"
                />
              </label>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <ToggleOption icon={HelpCircle} label="Preparation hints" labelZh="显示提示" checked={hintsEnabled} onChange={setHintsEnabled} />
              <ToggleOption icon={Radar} label="Immediate scoring" labelZh="即时评分" checked={immediateScoring} onChange={setImmediateScoring} />
            </div>

            <Button type="button" variant="gold" onClick={startPractice} disabled={starting || loading}>
              {starting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlayCircle className="mr-2 h-4 w-4" />}
              Start Part Practice
            </Button>
          </div>
        </Panel>

        <div className="grid gap-5">
          <Panel tone="paper">
            <SectionHeading icon={Target} label="Coach Preview" labelZh="训练目标" />
            <div className="grid gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone="gold">{profile.title}</StatusBadge>
                  <StatusBadge tone="teal">{profile.duration}</StatusBadge>
                </div>
                <h2 className="mt-3 text-xl font-semibold text-slate-950">
                  {profile.title} <span className="text-sm font-medium text-[#3A7CA5]">{profile.titleZh}</span>
                </h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">{profile.focus}</p>
              </div>
              <MiniSparkline values={[5.5, 5.8, 6.2, 6.3, 6.6]} />
              <InlineKpi icon={BookOpenCheck} label="Catalog matches" value={loading ? "..." : String(partQuestionCount)} />
              <InlineKpi icon={Hash} label="Selected topic" value={selectedTopic?.name || "Any topic"} />
              <InlineKpi icon={BrainCircuit} label="Coach strategy" value={profile.recommendation} />
            </div>
          </Panel>

          <Panel>
            <SectionHeading icon={TimerReset} label="Mode Contract" labelZh="后端契约" />
            <div className="grid gap-2 text-sm text-slate-600">
              <p>
                This page creates <code className="rounded bg-slate-100 px-1">mode=part_practice</code> with
                <code className="rounded bg-slate-100 px-1">target_part={selectedPart}</code>.
              </p>
              <p>练习偏好写入 session state，保持 Go API 字段边界稳定。</p>
              <Button type="button" variant="soft" onClick={() => router.push("/practice/setup/topic")}>
                Try topic practice
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </Panel>
        </div>
      </section>
    </AcademicShell>
  );
}

function ToggleOption({
  icon: Icon,
  label,
  labelZh,
  checked,
  onChange,
}: {
  icon: LucideIcon;
  label: string;
  labelZh: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex min-h-14 cursor-pointer items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <span className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-[#3A7CA5]" />
        <span>
          <span className="block text-sm font-semibold text-slate-900">{label}</span>
          <span className="text-xs text-slate-500">{labelZh}</span>
        </span>
      </span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-5 w-5 cursor-pointer accent-[#D4AF37]"
      />
    </label>
  );
}
