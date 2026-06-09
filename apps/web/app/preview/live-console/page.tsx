"use client";

import { Activity, ArrowLeft, BarChart3, Clock3, Mic2, Play, Radio, Send, ShieldCheck, Volume2 } from "lucide-react";
import { useRouter } from "next/navigation";

import { MetricCard, MiniSparkline, Panel, SectionHeading, StatusBadge, Waveform } from "@/components/academic";
import { ExaminerAvatar } from "@/components/ExaminerAvatar";
import { RadarChart } from "@/components/RadarChart";
import { Button } from "@/components/ui/button";

const timeline = [
  { label: "Part 1", labelZh: "日常问答", detail: "Introduction & interview", time: "04:30", active: true },
  { label: "Part 2", labelZh: "话题卡", detail: "Cue card", time: "03:00", active: false },
  { label: "Part 3", labelZh: "讨论", detail: "Discussion", time: "04:30", active: false },
  { label: "Report", labelZh: "复盘", detail: "AI feedback", time: "02:00", active: false },
];

const dimensions = [
  { label: "Fluency", labelZh: "流利度", value: "7.0", width: "78%" },
  { label: "Lexical Resource", labelZh: "词汇", value: "6.5", width: "70%" },
  { label: "Grammar", labelZh: "语法", value: "7.5", width: "84%" },
  { label: "Pronunciation", labelZh: "发音", value: "6.5", width: "70%" },
];

export default function LiveConsolePreviewPage() {
  const router = useRouter();

  return (
    <main className="min-h-screen bg-[#f5f7fb] px-4 py-5 text-[#102033] sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-[1320px] flex-col gap-5">
        <header className="flex flex-col gap-4 rounded-lg border border-slate-200 bg-white/90 px-4 py-4 shadow-sm backdrop-blur sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#0B132B] text-[#D4AF37]">
              <Mic2 className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#3A7CA5]">Visual Preview</p>
              <h1 className="truncate font-serif text-2xl text-[#0B132B]">IELTS Speaking / Live Practice Console</h1>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone="sage">API Connected</StatusBadge>
            <Button type="button" variant="soft" onClick={() => router.push("/")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Workspace
            </Button>
          </div>
        </header>

        <section className="grid gap-5 xl:grid-cols-[250px_minmax(0,1fr)_300px]">
          <Panel>
            <SectionHeading icon={Activity} label="Session Timeline" labelZh="练习进度" />
            <div className="relative grid gap-5">
              <div className="absolute bottom-10 left-4 top-4 w-px bg-slate-200" />
              {timeline.map((item, index) => (
                <div key={item.label} className="relative flex gap-3">
                  <span className={`z-10 flex h-8 w-8 items-center justify-center rounded-full border bg-white text-sm font-semibold ${item.active ? "border-[#D4AF37] text-[#D4AF37]" : "border-slate-200 text-slate-400"}`}>
                    {index + 1}
                  </span>
                  <div className="min-w-0 flex-1 pb-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className={`text-sm font-semibold ${item.active ? "text-slate-950" : "text-slate-600"}`}>{item.label}</p>
                      <span className="font-mono text-[11px] text-slate-400">{item.time}</span>
                    </div>
                    <p className="text-xs leading-5 text-slate-500">{item.labelZh} · {item.detail}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-6 rounded-lg border border-[#E9DFC6] bg-[#F7F4EA] p-4 text-center">
              <p className="text-xs uppercase tracking-wide text-slate-500">Total Time / 总时长</p>
              <p className="mt-1 font-serif text-2xl text-[#0B132B]">12:00</p>
            </div>
          </Panel>

          <Panel className="overflow-hidden p-0">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-[#3A7CA5]">Part 1 · Introduction & Interview</p>
                <h2 className="mt-1 font-serif text-2xl text-[#0B132B]">Live Practice Console</h2>
              </div>
              <StatusBadge tone="sage">
                <Radio className="mr-1 h-3 w-3" />
                Connected
              </StatusBadge>
            </div>

            <div className="px-5 py-6">
              <div className="grid gap-5 lg:grid-cols-[170px_minmax(0,1fr)]">
                <div className="flex flex-col items-center justify-center rounded-lg border border-slate-200 bg-slate-50 p-4 text-center">
                  <ExaminerAvatar status="speaking" className="h-28 w-28 border-[#D4AF37]/40 bg-white" />
                  <p className="mt-3 text-sm font-semibold text-slate-900">Examiner Emma</p>
                  <p className="text-xs text-slate-500">IELTS Examiner</p>
                  <Waveform active className="mt-4 justify-center" bars={18} />
                </div>

                <div className="rounded-lg border border-slate-200 bg-white p-5">
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                    <StatusBadge tone="teal">Question 2 / 8</StatusBadge>
                    <StatusBadge tone="gold">Time Remaining 03:28</StatusBadge>
                  </div>
                  <p className="font-serif text-3xl leading-tight text-[#0B132B]">Do you enjoy spending time with your family?</p>
                  <p className="mt-3 text-lg text-slate-500">你喜欢和家人共度时光吗？</p>
                  <div className="mt-6 rounded-lg border border-[#E9DFC6] bg-[#F7F4EA] p-4">
                    <p className="text-xs font-semibold uppercase text-[#8A6F1D]">You may talk about</p>
                    <ul className="mt-3 grid gap-2 text-sm leading-6 text-slate-700">
                      <li>what you usually do with your family</li>
                      <li>how often you get together</li>
                      <li>why it is important to spend time together</li>
                    </ul>
                  </div>
                </div>
              </div>

              <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-4">
                <Waveform active bars={54} className="justify-center" />
                <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
                  <Button type="button" variant="soft">
                    <Play className="mr-2 h-4 w-4" />
                    Replay
                  </Button>
                  <Button type="button" variant="gold" size="lg">
                    <Mic2 className="mr-2 h-4 w-4" />
                    Start Recording
                  </Button>
                  <Button type="button" variant="soft">
                    <Send className="mr-2 h-4 w-4" />
                    Submit
                  </Button>
                </div>
                <p className="mt-3 text-center text-xs text-slate-500">Click to start · 点击开始录音</p>
              </div>

              <div className="mt-5 rounded-lg border border-[#3A7CA5]/20 bg-[#EAF5FA] p-4 text-sm leading-6 text-[#2F6384]">
                <ShieldCheck className="mr-2 inline h-4 w-4" />
                Your response will be recorded and analyzed by AI. 请在安静环境中作答，确保录音清晰。
              </div>
            </div>
          </Panel>

          <div className="grid gap-5">
            <Panel>
              <SectionHeading icon={BarChart3} label="Review Preview" labelZh="评分预览" />
              <div className="rounded-lg border border-[#E9DFC6] bg-[#F7F4EA] p-4 text-center">
                <p className="text-xs font-semibold uppercase text-slate-500">Overall Score / 总分</p>
                <p className="mt-2 font-serif text-5xl text-[#8A6F1D]">7.0</p>
                <StatusBadge tone="sage" className="mt-3">Good / 良好</StatusBadge>
              </div>
              <div className="mt-4">
                <RadarChart />
              </div>
            </Panel>

            <Panel>
              <SectionHeading icon={Volume2} label="Dimension Scores" labelZh="维度分" />
              <div className="grid gap-3">
                {dimensions.map((item) => (
                  <div key={item.label}>
                    <div className="mb-1 flex items-center justify-between gap-3 text-xs">
                      <span className="font-semibold text-slate-700">{item.label}</span>
                      <span className="font-serif text-base text-[#0B132B]">{item.value}</span>
                    </div>
                    <p className="mb-1 text-[11px] text-slate-400">{item.labelZh}</p>
                    <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                      <span className="block h-full rounded-full bg-[#5B8DEF]" style={{ width: item.width }} />
                    </div>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel>
              <SectionHeading icon={Clock3} label="Signal" labelZh="运行信号" />
              <div className="grid gap-3">
                <MetricCard label="Latency" value="120 ms" helper="agent round-trip" tone="teal" />
                <MiniSparkline values={[5, 6, 5, 7, 6, 8, 7, 8]} />
              </div>
              <p className="mt-4 text-xs leading-5 text-slate-500">AI scores are for practice reference only and do not replace official IELTS assessment.</p>
            </Panel>
          </div>
        </section>
      </div>
    </main>
  );
}
