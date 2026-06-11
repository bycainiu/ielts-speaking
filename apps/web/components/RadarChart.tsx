"use client";

import {
  Radar,
  RadarChart as RechartsRadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
} from "recharts";

type RadarScore = {
  subject: string;
  score: number;
};

type RadarChartProps = {
  scores?: RadarScore[];
  tone?: "dark" | "light";
};

const defaultScores = [
  { subject: "Fluency", score: 7.0 },
  { subject: "Lexical", score: 6.5 },
  { subject: "Grammar", score: 6.0 },
  { subject: "Pronunciation", score: 6.5 },
];

export function RadarChart({ scores = defaultScores, tone = "dark" }: RadarChartProps) {
  const data = scores.map((item) => ({ subject: item.subject, A: item.score, fullMark: 9 }));
  const gridStroke = tone === "light" ? "rgba(148,163,184,0.34)" : "rgba(255,255,255,0.15)";
  const tickFill = tone === "light" ? "#475569" : "rgba(255,255,255,0.8)";

  return (
    <div className="flex h-[220px] min-h-[220px] w-full min-w-0 items-center justify-center overflow-hidden">
      <RechartsRadarChart width={300} height={220} cx="50%" cy="50%" outerRadius="65%" data={data}>
        <PolarGrid stroke={gridStroke} />
        <PolarAngleAxis
          dataKey="subject"
          tick={{ fill: tickFill, fontSize: 11, fontFamily: "var(--font-inter)" }}
        />
        <PolarRadiusAxis angle={30} domain={[0, 9]} tick={false} axisLine={false} />
        <Radar
          name="Score"
          dataKey="A"
          stroke="hsl(var(--academic-accent))"
          strokeWidth={2}
          fill="hsl(var(--academic-accent))"
          fillOpacity={0.35}
        />
      </RechartsRadarChart>
    </div>
  );
}
