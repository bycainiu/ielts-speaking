"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  Hash,
  Loader2,
  PlayCircle,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";

import { AcademicShell, EmptyState, InlineKpi, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
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

const vocabularyByTopic: Record<string, string[]> = {
  technology: ["digital tools", "privacy", "convenience", "automation"],
  travel: ["itinerary", "local culture", "memorable", "public transport"],
  hometown: ["neighborhood", "community", "urban planning", "local identity"],
  work: ["career path", "productivity", "teamwork", "work-life balance"],
  study: ["academic pressure", "research", "motivation", "learning style"],
};

export default function TopicPracticeSetupPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [season, setSeason] = useState<Season | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [search, setSearch] = useState("");
  const [selectedTopicId, setSelectedTopicId] = useState("");
  const [selectedParts, setSelectedParts] = useState<number[]>([1, 2, 3]);
  const [personalize, setPersonalize] = useState(true);
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
          api.get<{ questions: Question[] }>("/questions?limit=160"),
        ]);
        if (cancelled) return;
        if (seasonResponse.status === "fulfilled") setSeason(seasonResponse.value.data.season);
        if (topicResponse.status === "fulfilled") {
          const activeTopics = topicResponse.value.data.topics ?? [];
          setTopics(activeTopics);
          setSelectedTopicId((current) => current || activeTopics[0]?.id || "");
        }
        if (questionResponse.status === "fulfilled") setQuestions(questionResponse.value.data.questions ?? []);
      } catch (err: unknown) {
        const apiError = err as ApiError;
        if (!cancelled) {
          setError(apiError.response?.data?.message || "Topic catalog could not be loaded.");
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

  const filteredTopics = useMemo(() => {
    const query = search.trim().toLowerCase();
    return topics
      .filter((topic) => topic.status === "active")
      .filter((topic) => !query || topic.name.toLowerCase().includes(query) || topic.slug.toLowerCase().includes(query));
  }, [search, topics]);

  const selectedTopic = topics.find((topic) => topic.id === selectedTopicId) ?? filteredTopics[0] ?? null;
  const selectedTopicQuestions = useMemo(
    () => questions.filter((question) => question.topic_id === selectedTopic?.id),
    [questions, selectedTopic?.id],
  );
  const partCounts = [1, 2, 3].map((part) => ({
    part,
    count: selectedTopicQuestions.filter((question) => question.part === part).length,
  }));
  const vocabulary = inferVocabulary(selectedTopic);

  const togglePart = (part: number) => {
    setSelectedParts((current) => {
      if (current.includes(part)) {
        const next = current.filter((item) => item !== part);
        return next.length ? next : current;
      }
      return [...current, part].sort();
    });
  };

  const startPractice = async () => {
    if (!selectedTopic) {
      setError("Choose an active topic first.");
      return;
    }
    setStarting(true);
    setError("");
    try {
      const targetPart = selectedParts.length === 1 ? selectedParts[0] : undefined;
      const response = await api.post("/sessions", {
        mode: "topic_practice",
        season_id: season?.id,
        topic_id: selectedTopic.id,
        target_part: targetPart,
        state: {
          setup_surface: "topic_practice",
          selected_topic_name: selectedTopic.name,
          selected_parts: selectedParts,
          personalize_with_background: personalize,
          topic_guidance_requested: true,
          ui_locale_hint: "en-CN",
        },
      });
      const sessionId = response.data.session.id;
      await api.post(`/sessions/${sessionId}/start`);
      router.push(`/v2/live/${sessionId}`);
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Topic practice could not be started.");
    } finally {
      setStarting(false);
    }
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  return (
    <AcademicShell activePath="/practice" userName={user?.display_name || user?.email} userRole={user?.role}>
      <PageHeader
        eyebrow="Seasonal Practice"
        title="Topic Practice"
        titleZh="主题练习配置"
        description="Search active question-bank topics, select Part coverage and let the Agent combine topic guidance with your background profile."
        actions={
          <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Dashboard
          </Button>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_390px]">
        <Panel>
          <SectionHeading icon={BookOpenCheck} label="Topic Catalog" labelZh="话题目录" />
          <label htmlFor="topic-search" className="mb-4 flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              id="topic-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search topic, e.g. technology"
              className="min-w-0 flex-1 bg-transparent text-sm outline-none"
            />
          </label>

          {loading ? (
            <div className="flex min-h-60 items-center justify-center text-sm text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin text-academic-score" />
              Loading topics...
            </div>
          ) : filteredTopics.length === 0 ? (
            <EmptyState title="No active topic found" body="Active public topics are required before topic practice can start." />
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {filteredTopics.map((topic) => {
                const counts = [1, 2, 3].map((part) => questions.filter((question) => question.topic_id === topic.id && question.part === part).length);
                const selected = selectedTopic?.id === topic.id;
                return (
                  <button
                    key={topic.id}
                    type="button"
                    onClick={() => setSelectedTopicId(topic.id)}
                    className={`min-h-[138px] cursor-pointer rounded-lg border p-4 text-left transition-colors ${
                      selected ? "border-academic-score bg-academic-score-soft" : "border-slate-200 bg-white hover:border-academic-score/50 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-academic-navy text-academic-score">
                        <BookOpenCheck className="h-5 w-5" />
                      </span>
                      <StatusBadge tone={topic.status === "active" ? "sage" : "slate"}>{topic.status}</StatusBadge>
                    </div>
                    <h2 className="mt-3 text-base font-semibold text-slate-950">{topic.name}</h2>
                    <p className="mt-1 text-xs text-slate-500">{topic.slug}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {counts.map((count, index) => (
                        <StatusBadge key={index} tone={count > 0 ? "teal" : "slate"}>
                          P{index + 1}: {count}
                        </StatusBadge>
                      ))}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </Panel>

        <div className="grid gap-5">
          <Panel tone="paper">
            <SectionHeading icon={Target} label="Selected Topic" labelZh="当前主题" />
            {selectedTopic ? (
              <div className="grid gap-4">
                <div>
                  <StatusBadge tone="gold">{season?.title || "Active season"}</StatusBadge>
                  <h2 className="mt-3 font-serif text-3xl text-academic-navy">{selectedTopic.name}</h2>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    Use active topic questions with optional background personalization and topic knowledge guidance.
                  </p>
                </div>

                <div>
                  <p className="mb-2 text-sm font-semibold text-slate-700">Part coverage 练习范围</p>
                  <div className="grid grid-cols-3 gap-2">
                    {[1, 2, 3].map((part) => (
                      <button
                        key={part}
                        type="button"
                        onClick={() => togglePart(part)}
                        className={`min-h-11 cursor-pointer rounded-lg border text-sm font-semibold transition-colors ${
                          selectedParts.includes(part)
                            ? "border-academic-score bg-academic-navy text-white"
                            : "border-slate-200 bg-white text-slate-600 hover:border-academic-score/50"
                        }`}
                      >
                        Part {part}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid gap-2">
                  {partCounts.map((item) => (
                    <div key={item.part} className="grid grid-cols-[56px_1fr_36px] items-center gap-2 text-sm">
                      <span className="font-semibold text-slate-600">P{item.part}</span>
                      <span className="h-2 overflow-hidden rounded-full bg-white">
                        <span className="block h-full rounded-full bg-academic-accent" style={{ width: `${Math.min(100, item.count * 18)}%` }} />
                      </span>
                      <span className="text-right text-xs text-slate-500">{item.count}</span>
                    </div>
                  ))}
                </div>

                <div className="flex flex-wrap gap-2">
                  {vocabulary.map((word) => (
                    <StatusBadge key={word} tone="teal">
                      {word}
                    </StatusBadge>
                  ))}
                </div>

                <label className="flex min-h-14 cursor-pointer items-center justify-between gap-3 rounded-lg border border-academic-score/25 bg-white px-3 py-2">
                  <span className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-academic-score" />
                    <span>
                      <span className="block text-sm font-semibold text-slate-900">Personalize with my background</span>
                      <span className="text-xs text-slate-500">结合个人画像追问</span>
                    </span>
                  </span>
                  <input
                    type="checkbox"
                    checked={personalize}
                    onChange={(event) => setPersonalize(event.target.checked)}
                    className="h-5 w-5 cursor-pointer accent-academic-score"
                  />
                </label>

                <Button type="button" variant="gold" onClick={startPractice} disabled={starting}>
                  {starting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlayCircle className="mr-2 h-4 w-4" />}
                  Start Topic Practice
                </Button>
              </div>
            ) : (
              <EmptyState icon={Hash} title="Choose a topic" body="Select an active topic from the catalog to configure practice." />
            )}
          </Panel>

          <Panel>
            <SectionHeading icon={ShieldCheck} label="Practice Contract" labelZh="对接说明" />
            <div className="grid gap-3">
              <InlineKpi icon={CheckCircle2} label="Mode" value="topic_practice" />
              <InlineKpi icon={Hash} label="Topic ID" value={selectedTopic?.id ? shortId(selectedTopic.id) : "-"} />
              <InlineKpi icon={BrainCircuit} label="Target part" value={selectedParts.length === 1 ? `Part ${selectedParts[0]}` : "Full topic sweep"} />
            </div>
          </Panel>
        </div>
      </section>
    </AcademicShell>
  );
}

function inferVocabulary(topic: Topic | null) {
  if (!topic) return ["topic", "examples", "opinion"];
  const key = Object.keys(vocabularyByTopic).find((candidate) => topic.slug.includes(candidate) || topic.name.toLowerCase().includes(candidate));
  return key ? vocabularyByTopic[key] : ["examples", "personal story", "advantages", "future trend"];
}

function shortId(value: string) {
  return value.length > 10 ? `${value.slice(0, 8)}...` : value;
}
