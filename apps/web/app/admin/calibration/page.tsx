"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  ArrowLeft,
  BarChart3,
  BrainCircuit,
  Database,
  Filter,
  Loader2,
  RefreshCcw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Volume2,
} from "lucide-react";

import {
  AcademicShell,
  EmptyState,
  InlineKpi,
  MetricCard,
  MiniSparkline,
  MonoBlock,
  PageHeader,
  Panel,
  SectionHeading,
  StatusBadge,
} from "@/components/academic";
import { Button } from "@/components/ui/button";
import { agentApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";

type CriterionKey = "fluency_coherence" | "lexical_resource" | "grammatical_range_accuracy" | "pronunciation";
type GateStatus = "passed" | "needs_review" | "blocked";

type ApiError = {
  response?: {
    data?: {
      message?: string;
      detail?: string | { message?: string };
    };
  };
};

type AnchorCriterionScore = {
  band: number;
  rationale: string;
};

type AnchorSpeakingSample = {
  sample_id: string;
  part: 1 | 2 | 3;
  target_band: number;
  transcript: string;
  topic: string;
  source_compliance: string;
  scores: Record<CriterionKey, AnchorCriterionScore>;
  notes: string;
};

type AnchorDatasetAudit = {
  sample_count: number;
  covered_bands: number[];
  covered_criteria: string[];
  source_compliance_values: string[];
  passed: boolean;
  findings: string[];
};

type AnchorSamplesResponse = {
  audit: AnchorDatasetAudit;
  samples: AnchorSpeakingSample[];
  calibration_anchor_count: number;
  note: string;
};

type EvalCaseResult = {
  case_id: string;
  category: string;
  passed: boolean;
  score: number;
  reason: string;
  severity: "low" | "medium" | "high" | "critical";
  metadata: Record<string, unknown>;
};

type EvalSuiteReport = {
  suite_name: string;
  generated_at: string;
  sample_count: number;
  pass_count: number;
  fail_count: number;
  pass_rate: number;
  threshold: number;
  block_release: boolean;
  results: EvalCaseResult[];
  improvement_items: Record<string, unknown>[];
};

type SpeechCalibrationDatasetAudit = {
  sample_count: number;
  production_sample_count: number;
  synthetic_sample_count: number;
  authorization_passed: boolean;
  coverage_passed: boolean;
  regression_ready: boolean;
  passed: boolean;
  covered_band_buckets: number[];
  covered_parts: number[];
  covered_accent_groups: string[];
  covered_recording_qualities: string[];
  source_counts: Record<string, number>;
  issues: string[];
};

type SpeechCalibrationRegressionReport = {
  audit: SpeechCalibrationDatasetAudit;
  eval_report: EvalSuiteReport;
  mean_absolute_error: number;
  max_absolute_error: number;
  model_version: string;
  calibration_note: string;
};

type ProviderComparison = {
  provider: "gopt_baseline" | "multipa_adapter";
  sample_count: number;
  mean_absolute_error: number;
  max_absolute_error: number;
  p95_latency_ms: number;
  estimated_total_cost_usd: number;
  deployment_complexity: "low" | "medium" | "high";
};

type MultiPAExperimentReport = {
  status: "passed" | "needs_review" | "not_configured";
  benchmark_sample_count: number;
  comparisons: ProviderComparison[];
  eval_report: EvalSuiteReport;
  recommendation: string;
  deployment_risks: string[];
};

type CalibrationQualityGateCheck = {
  name: string;
  status: GateStatus;
  message: string;
  block_release: boolean;
  sample_count: number;
  metadata: Record<string, unknown>;
};

type CalibrationQualityGateResponse = {
  generated_at: string;
  status: GateStatus;
  checks: CalibrationQualityGateCheck[];
  anchor_audit: AnchorDatasetAudit;
  deepeval_report?: EvalSuiteReport | null;
  ragas_report?: EvalSuiteReport | null;
  promptfoo_report?: EvalSuiteReport | null;
  performance_report?: Record<string, unknown> | null;
  speech_calibration_report?: SpeechCalibrationRegressionReport | null;
  multipa_experiment_report?: MultiPAExperimentReport | null;
  note: string;
};

type CriterionScoreInput = {
  band: number;
  confidence: number;
  evidence: {
    turn_id: string;
    quote: string;
    reason: string;
  }[];
  suggestions: string[];
  raw_output: Record<string, unknown>;
};

type CalibrationAnchorSample = {
  anchor_sample_id: string;
  criterion: CriterionKey;
  band: number;
  score: number;
  rationale?: string;
  content?: string;
};

type ScoreCalibrationAdjustment = {
  criterion: CriterionKey;
  before_band: number;
  after_band: number;
  anchor_mean_band: number;
  deviation: number;
  action: "unchanged" | "adjusted" | "insufficient_anchors";
  reason: string;
  anchor_sample_ids: string[];
};

type ScoreCalibratorOutput = {
  status: "calibrated" | "unchanged" | "insufficient_anchors";
  calibrated_criteria: Record<CriterionKey, CriterionScoreInput>;
  adjustments: ScoreCalibrationAdjustment[];
  raw_output: Record<string, unknown>;
};

type EvalRun = {
  name: string;
  status: string;
  durationMs: number;
  passRate?: number;
  sampleCount?: number;
  note: string;
};

const criteria: CriterionKey[] = [
  "fluency_coherence",
  "lexical_resource",
  "grammatical_range_accuracy",
  "pronunciation",
];

const criterionLabels: Record<CriterionKey, string> = {
  fluency_coherence: "Fluency",
  lexical_resource: "Lexical",
  grammatical_range_accuracy: "Grammar",
  pronunciation: "Pronunciation",
};

export default function CalibrationAdminPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [anchors, setAnchors] = useState<AnchorSamplesResponse | null>(null);
  const [qualityGate, setQualityGate] = useState<CalibrationQualityGateResponse | null>(null);
  const [speechReport, setSpeechReport] = useState<SpeechCalibrationRegressionReport | null>(null);
  const [multipaReport, setMultipaReport] = useState<MultiPAExperimentReport | null>(null);
  const [scorePreview, setScorePreview] = useState<ScoreCalibratorOutput | null>(null);
  const [selectedSampleId, setSelectedSampleId] = useState("");
  const [dataset, setDataset] = useState("");
  const [part, setPart] = useState("");
  const [bandMin, setBandMin] = useState("4");
  const [bandMax, setBandMax] = useState("8");
  const [accent, setAccent] = useState("");
  const [recordingQuality, setRecordingQuality] = useState("");
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [recentRuns, setRecentRuns] = useState<EvalRun[]>([]);

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

  const loadCalibration = useCallback(async () => {
    if (!hasHydrated || !isAuthenticated || !canAdmin) return;
    setLoading(true);
    setError("");
    try {
      const anchorResponse = await agentApi.get<AnchorSamplesResponse>("/agent/calibration/anchor-samples", {
        params: { include_samples: "true" },
      });
      const calibrationAnchors = toCalibrationAnchors(anchorResponse.data.samples);
      const [qualityResponse, previewResponse] = await Promise.all([
        agentApi.post<CalibrationQualityGateResponse>("/agent/calibration/quality-gate", {
          include_deepeval_regression: true,
          include_ragas_rag: true,
          include_promptfoo_redteam: true,
          include_performance_baseline: true,
          include_speech_calibration_contract: true,
          include_multipa_contract: true,
        }),
        agentApi.post<ScoreCalibratorOutput>("/agent/calibration/score", {
          session_id: `web_calibration_preview_${Date.now()}`,
          criteria: previewCriteria(),
          anchor_samples: calibrationAnchors,
        }),
      ]);
      setAnchors(anchorResponse.data);
      setQualityGate(qualityResponse.data);
      setSpeechReport(qualityResponse.data.speech_calibration_report ?? null);
      setMultipaReport(qualityResponse.data.multipa_experiment_report ?? null);
      setScorePreview(previewResponse.data);
      setSelectedSampleId((current) => current || anchorResponse.data.samples[0]?.sample_id || "");
    } catch (err: unknown) {
      setError(apiMessage(err, "Calibration dashboard could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [canAdmin, hasHydrated, isAuthenticated]);

  useEffect(() => {
    loadCalibration();
  }, [loadCalibration]);

  const activeSpeechReport = speechReport ?? qualityGate?.speech_calibration_report ?? null;
  const activeMultiPAReport = multipaReport ?? qualityGate?.multipa_experiment_report ?? null;

  const filteredAnchors = useMemo(() => {
    const minBand = Number.parseFloat(bandMin) || 0;
    const maxBand = Number.parseFloat(bandMax) || 9;
    return (anchors?.samples ?? []).filter((sample) => {
      if (dataset && sample.source_compliance !== dataset) return false;
      if (part && String(sample.part) !== part) return false;
      return sample.target_band >= minBand && sample.target_band <= maxBand;
    });
  }, [anchors, bandMax, bandMin, dataset, part]);

  const selectedSample = useMemo(() => {
    return (anchors?.samples ?? []).find((sample) => sample.sample_id === selectedSampleId) ?? filteredAnchors[0] ?? null;
  }, [anchors, filteredAnchors, selectedSampleId]);

  const speechRows = useMemo(() => {
    return (activeSpeechReport?.eval_report.results ?? []).filter((item) => {
      if (item.case_id === "dataset_audit") return false;
      if (part && String(metadataNumber(item.metadata, "part") ?? "") !== part) return false;
      if (accent && metadataString(item.metadata, "accent_group") !== accent) return false;
      if (recordingQuality && metadataString(item.metadata, "recording_quality") !== recordingQuality) return false;
      return true;
    });
  }, [accent, activeSpeechReport, part, recordingQuality]);

  const criterionMaeRows = useMemo(() => buildCriterionMaeRows(anchors?.samples ?? []), [anchors]);
  const driftValues = useMemo(() => {
    const values = scorePreview?.adjustments.map((item) => Math.abs(item.deviation)) ?? [];
    return values.length ? values : [0, 0, 0, 0];
  }, [scorePreview]);
  const confidenceValues = useMemo(() => speechRows.map((item) => metadataNumber(item.metadata, "confidence") ?? item.score), [speechRows]);

  const runQualityGate = async (name: string, payload: Record<string, boolean>) => {
    const started = performance.now();
    setActionLoading(name);
    setError("");
    setNotice("");
    try {
      const response = await agentApi.post<CalibrationQualityGateResponse>("/agent/calibration/quality-gate", payload);
      setQualityGate(response.data);
      if (response.data.speech_calibration_report) setSpeechReport(response.data.speech_calibration_report);
      if (response.data.multipa_experiment_report) setMultipaReport(response.data.multipa_experiment_report);
      pushRun({
        name,
        status: response.data.status,
        durationMs: elapsed(started),
        passRate: passRateFromGate(response.data),
        sampleCount: response.data.checks.reduce((total, check) => total + check.sample_count, 0),
        note: response.data.checks.map((check) => check.name).join(", "),
      });
      setNotice("Operation completed.");;
    } catch (err: unknown) {
      setError(apiMessage(err, `${name} could not be completed.`));
    } finally {
      setActionLoading("");
    }
  };

  const runSpeechCalibration = async () => {
    const started = performance.now();
    const name = "Speech Calibration";
    setActionLoading(name);
    setError("");
    setNotice("");
    try {
      const response = await agentApi.post<SpeechCalibrationRegressionReport>("/agent/calibration/speech-regression", {
        use_contract_samples: true,
        allow_synthetic_contract: true,
        min_production_samples: 0,
      });
      setSpeechReport(response.data);
      pushRun({
        name,
        status: response.data.audit.passed && !response.data.eval_report.block_release ? "passed" : "blocked",
        durationMs: elapsed(started),
        passRate: response.data.eval_report.pass_rate,
        sampleCount: response.data.audit.sample_count,
        note: `mae=${formatMetric(response.data.mean_absolute_error)}, max=${formatMetric(response.data.max_absolute_error)}`,
      });
      setNotice("Speech calibration completed.");
    } catch (err: unknown) {
      setError(apiMessage(err, "Speech calibration could not be completed."));
    } finally {
      setActionLoading("");
    }
  };

  const runMultiPAExperiment = async () => {
    const started = performance.now();
    const name = "MultiPA Experiment";
    setActionLoading(name);
    setError("");
    setNotice("");
    try {
      const response = await agentApi.post<MultiPAExperimentReport>("/agent/calibration/multipa-experiment", {
        use_contract_samples: true,
        use_contract_multipa_outputs: true,
      });
      setMultipaReport(response.data);
      pushRun({
        name,
        status: response.data.status,
        durationMs: elapsed(started),
        passRate: response.data.eval_report.pass_rate,
        sampleCount: response.data.benchmark_sample_count,
        note: response.data.recommendation,
      });
      setNotice("MultiPA experiment completed.");
    } catch (err: unknown) {
      setError(apiMessage(err, "MultiPA experiment could not be completed."));
    } finally {
      setActionLoading("");
    }
  };

  const pushRun = (run: EvalRun) => {
    setRecentRuns((current) => [run, ...current].slice(0, 6));
  };

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/admin/calibration" userName={user?.display_name} userRole={user?.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">
          <SectionHeading icon={ShieldCheck} label="Access denied" labelZh="权限不足" />
          <h1 className="font-serif text-3xl text-[#0B132B]">Scoring Calibration</h1>
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
    <AcademicShell activePath="/admin/calibration" userName={user?.display_name} userRole={user?.role}>
      <PageHeader
        eyebrow="Model Quality"
        title="Scoring Calibration"
        titleZh="评分校准"
        description="Anchor samples, regression gates, speech evidence calibration and MultiPA experiments."
        actions={
          <>
            <StatusBadge tone={gateTone(qualityGate?.status)}>
              Quality Gate: {qualityGate?.status ?? "loading"}
            </StatusBadge>
            <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Practice
            </Button>
            <Button type="button" variant="teal" onClick={loadCalibration} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
              Refresh
            </Button>
          </>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}
      {notice && <Panel className="border-[#4F8A6B]/25 bg-[#EEF7F2] text-sm text-[#3E7056]">{notice}</Panel>}

      <section className="grid gap-4 md:grid-cols-4">
        <MetricCard icon={BarChart3} label="Overall MAE" value={formatMetric(activeSpeechReport?.mean_absolute_error ?? baselineMae(activeMultiPAReport))} helper="speech evidence gate" tone="gold" />
        <MetricCard icon={Volume2} label="Pronunciation MAE" value={formatMetric(activeSpeechReport?.mean_absolute_error ?? 0)} helper={`${activeSpeechReport?.audit.sample_count ?? 0} speech samples`} tone="teal" />
        <MetricCard icon={Activity} label="Max Error" value={formatMetric(activeSpeechReport?.max_absolute_error ?? 0)} helper="case absolute error" tone={(activeSpeechReport?.max_absolute_error ?? 0) > 1 ? "gold" : "sage"} />
        <MetricCard icon={Database} label="Sample Coverage" value={`${anchors?.audit.sample_count ?? 0}/${anchors?.calibration_anchor_count ?? 0}`} helper="anchors / criterion rows" />
      </section>

      <section className="grid gap-5 xl:grid-cols-[330px_minmax(0,1fr)_360px]">
        <Panel className="min-h-[620px]">
          <SectionHeading icon={Filter} label="Anchor Samples" labelZh="样本" />
          <div className="grid gap-3">
            <label className="grid gap-2 text-sm text-slate-700">
              <span className="font-medium">Dataset</span>
              <select value={dataset} onChange={(event) => setDataset(event.target.value)} className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-[#D4AF37]">
                <option value="">all</option>
                {(anchors?.audit.source_compliance_values ?? []).map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <SelectField label="Part" value={part} onChange={setPart} options={["", "1", "2", "3"]} />
              <SelectField label="Accent" value={accent} onChange={setAccent} options={["", ...(activeSpeechReport?.audit.covered_accent_groups ?? [])]} />
              <NumberField label="Band min" value={bandMin} onChange={setBandMin} />
              <NumberField label="Band max" value={bandMax} onChange={setBandMax} />
            </div>
            <SelectField label="Recording Quality" value={recordingQuality} onChange={setRecordingQuality} options={["", ...(activeSpeechReport?.audit.covered_recording_qualities ?? [])]} />
          </div>

          <div className="mt-5 grid gap-2">
            {loading ? (
              <LoadingBlock label="Loading samples..." />
            ) : filteredAnchors.length ? (
              filteredAnchors.map((sample) => (
                <button
                  key={sample.sample_id}
                  type="button"
                  onClick={() => setSelectedSampleId(sample.sample_id)}
                  className={cn(
                    "grid cursor-pointer gap-2 rounded-lg border p-3 text-left transition-colors",
                    selectedSample?.sample_id === sample.sample_id ? "border-[#D4AF37] bg-[#FFF8DF]" : "border-slate-200 bg-white hover:border-[#D4AF37]/50",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <StatusBadge tone="teal">Part {sample.part}</StatusBadge>
                    <StatusBadge tone="gold">Band {sample.target_band.toFixed(1)}</StatusBadge>
                  </div>
                  <span className="break-all font-mono text-xs text-slate-700">{sample.sample_id}</span>
                  <span className="line-clamp-2 text-xs leading-5 text-slate-500">{sample.transcript}</span>
                </button>
              ))
            ) : (
              <EmptyState icon={Search} title="No samples" body="Current filters do not match the calibration anchors." />
            )}
          </div>
        </Panel>

        <div className="grid gap-5">
          <Panel>
            <SectionHeading icon={BarChart3} label="Calibration Charts" labelZh="校准图表" />
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <h3 className="text-sm font-semibold text-slate-900">Criterion MAE</h3>
                <BarList rows={criterionMaeRows} />
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <h3 className="text-sm font-semibold text-slate-900">Score Drift</h3>
                <MiniSparkline values={driftValues} className="mt-3" />
                <div className="mt-3 grid gap-2">
                  {(scorePreview?.adjustments ?? []).map((item) => (
                    <InlineKpi key={item.criterion} icon={SlidersHorizontal} label={criterionLabels[item.criterion]} value={`${formatMetric(item.before_band)} -> ${formatMetric(item.after_band)}`} />
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-4">
              <h3 className="text-sm font-semibold text-slate-900">Confidence Distribution</h3>
              <Histogram values={confidenceValues} />
            </div>
          </Panel>

          <Panel>
            <SectionHeading icon={BrainCircuit} label="Selected Anchor" labelZh="样本详情" />
            {selectedSample ? (
              <div className="grid gap-4">
                <div className="grid gap-3 md:grid-cols-3">
                  <InlineKpi label="Topic" value={selectedSample.topic} />
                  <InlineKpi label="Part" value={String(selectedSample.part)} />
                  <InlineKpi label="Target Band" value={selectedSample.target_band.toFixed(1)} />
                </div>
                <p className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-700">{selectedSample.transcript}</p>
                <div className="grid gap-3 md:grid-cols-2">
                  {criteria.map((criterion) => (
                    <div key={criterion} className="rounded-lg border border-slate-200 bg-white p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-slate-900">{criterionLabels[criterion]}</span>
                        <StatusBadge tone="gold">{selectedSample.scores[criterion].band.toFixed(1)}</StatusBadge>
                      </div>
                      <p className="mt-2 text-xs leading-5 text-slate-500">{selectedSample.scores[criterion].rationale}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyState icon={BrainCircuit} title="No anchor selected" body="Choose an anchor sample to inspect criterion bands and rationale." />
            )}
          </Panel>
        </div>

        <div className="grid gap-5">
          <Panel>
            <SectionHeading icon={Sparkles} label="Evaluation Runs" labelZh="评测记录" />
            <div className="grid gap-2">
              <RunButton
                label="Run Regression"
                icon={BrainCircuit}
                loading={actionLoading === "Regression Gate"}
                disabled={Boolean(actionLoading)}
                onClick={() =>
                  runQualityGate("Regression Gate", {
                    include_deepeval_regression: true,
                    include_ragas_rag: true,
                    include_promptfoo_redteam: false,
                    include_performance_baseline: true,
                    include_speech_calibration_contract: false,
                    include_multipa_contract: false,
                  })
                }
              />
              <RunButton label="Run Speech Calibration" icon={Volume2} loading={actionLoading === "Speech Calibration"} disabled={Boolean(actionLoading)} onClick={runSpeechCalibration} />
              <RunButton
                label="Run Prompt Redteam"
                icon={ShieldCheck}
                loading={actionLoading === "Prompt Redteam"}
                disabled={Boolean(actionLoading)}
                onClick={() =>
                  runQualityGate("Prompt Redteam", {
                    include_deepeval_regression: false,
                    include_ragas_rag: false,
                    include_promptfoo_redteam: true,
                    include_performance_baseline: false,
                    include_speech_calibration_contract: false,
                    include_multipa_contract: false,
                  })
                }
              />
              <RunButton label="Run MultiPA Experiment" icon={Activity} loading={actionLoading === "MultiPA Experiment"} disabled={Boolean(actionLoading)} onClick={runMultiPAExperiment} />
            </div>
          </Panel>

          <Panel>
            <SectionHeading icon={Database} label="Recent Runs" labelZh="最近运行" />
            {recentRuns.length ? (
              <div className="grid gap-2">
                {recentRuns.map((run, index) => (
                  <article key={`${run.name}-${index}`} className="rounded-lg border border-slate-200 bg-white p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-slate-900">{run.name}</span>
                      <StatusBadge tone={runTone(run.status)}>{run.status}</StatusBadge>
                    </div>
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{run.note}</p>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-slate-500">
                      <span>{run.durationMs}ms</span>
                      <span>{run.passRate === undefined ? "-" : formatPercent(run.passRate)}</span>
                      <span>{run.sampleCount ?? 0} samples</span>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState icon={Activity} title="No eval runs" body="Run a regression, speech calibration, redteam, or MultiPA experiment." />
            )}
          </Panel>

          <Panel>
            <SectionHeading icon={ShieldCheck} label="Quality Checks" labelZh="质量门禁" />
            {qualityGate?.checks.length ? (
              <div className="grid gap-2">
                {qualityGate.checks.map((check) => (
                  <article key={check.name} className="rounded-lg border border-slate-200 bg-white p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-slate-900">{check.name}</span>
                      <StatusBadge tone={gateTone(check.status)}>{check.status}</StatusBadge>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-slate-500">{check.message}</p>
                  </article>
                ))}
              </div>
            ) : (
              <LoadingBlock label="Loading quality checks..." />
            )}
          </Panel>
        </div>
      </section>

      <Panel>
        <SectionHeading icon={Volume2} label="Speech Sample Detail" labelZh="语音样本" />
        {speechRows.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">Sample</th>
                  <th className="px-3 py-2">Part</th>
                  <th className="px-3 py-2">Accent</th>
                  <th className="px-3 py-2">Quality</th>
                  <th className="px-3 py-2">Human</th>
                  <th className="px-3 py-2">AI</th>
                  <th className="px-3 py-2">Confidence</th>
                  <th className="px-3 py-2">Notes</th>
                </tr>
              </thead>
              <tbody>
                {speechRows.map((item) => (
                  <tr key={item.case_id} className="border-b border-slate-100">
                    <td className="max-w-[220px] break-all px-3 py-3 font-mono text-xs text-slate-700">{item.case_id}</td>
                    <td className="px-3 py-3">{metadataNumber(item.metadata, "part") ?? "-"}</td>
                    <td className="px-3 py-3">{metadataString(item.metadata, "accent_group") || "-"}</td>
                    <td className="px-3 py-3">{metadataString(item.metadata, "recording_quality") || "-"}</td>
                    <td className="px-3 py-3">{formatMetric(metadataNumber(item.metadata, "human_pronunciation_band") ?? 0)}</td>
                    <td className="px-3 py-3">{formatMetric(metadataNumber(item.metadata, "predicted_internal_band") ?? 0)}</td>
                    <td className="px-3 py-3">{formatPercent(metadataNumber(item.metadata, "confidence") ?? item.score)}</td>
                    <td className="min-w-[260px] px-3 py-3 text-xs leading-5 text-slate-500">{item.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon={Volume2} title="No speech cases" body="Run speech calibration or adjust filters to inspect sample-level results." />
        )}
      </Panel>

      {activeMultiPAReport && (
        <Panel>
          <SectionHeading icon={Activity} label="MultiPA Comparison" labelZh="实验对比" />
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="grid gap-3 md:grid-cols-2">
              {activeMultiPAReport.comparisons.map((comparison) => (
                <div key={comparison.provider} className="rounded-lg border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-slate-900">{comparison.provider}</span>
                    <StatusBadge tone={comparison.deployment_complexity === "high" ? "coral" : "teal"}>{comparison.deployment_complexity}</StatusBadge>
                  </div>
                  <div className="mt-3 grid gap-2">
                    <InlineKpi label="MAE" value={formatMetric(comparison.mean_absolute_error)} />
                    <InlineKpi label="Max Error" value={formatMetric(comparison.max_absolute_error)} />
                    <InlineKpi label="P95 Latency" value={`${comparison.p95_latency_ms}ms`} />
                    <InlineKpi label="Cost" value={`$${comparison.estimated_total_cost_usd.toFixed(4)}`} />
                  </div>
                </div>
              ))}
            </div>
            <MonoBlock>{JSON.stringify({ status: activeMultiPAReport.status, recommendation: activeMultiPAReport.recommendation, risks: activeMultiPAReport.deployment_risks }, null, 2)}</MonoBlock>
          </div>
        </Panel>
      )}
    </AcademicShell>
  );
}

function SelectField({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  return (
    <label className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-[#D4AF37]">
        {options.map((item) => (
          <option key={item || "all"} value={item}>
            {item || "all"}
          </option>
        ))}
      </select>
    </label>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <input value={value} min={0} max={9} step={0.5} type="number" onChange={(event) => onChange(event.target.value)} className="h-11 min-w-0 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-[#D4AF37]" />
    </label>
  );
}

function RunButton({ label, icon: Icon, loading, disabled, onClick }: { label: string; icon: typeof Activity; loading: boolean; disabled: boolean; onClick: () => void }) {
  return (
    <Button type="button" variant="soft" className="justify-start" disabled={disabled} onClick={onClick}>
      {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Icon className="mr-2 h-4 w-4" />}
      {label}
    </Button>
  );
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="flex min-h-32 items-center justify-center text-sm text-slate-600">
      <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#D4AF37]" />
      {label}
    </div>
  );
}

function BarList({ rows }: { rows: { label: string; value: number }[] }) {
  const max = Math.max(...rows.map((row) => row.value), 0.01);
  return (
    <div className="mt-4 grid gap-3">
      {rows.map((row) => (
        <div key={row.label} className="grid gap-1">
          <div className="flex items-center justify-between gap-2 text-xs text-slate-600">
            <span>{row.label}</span>
            <span className="font-mono">{formatMetric(row.value)}</span>
          </div>
          <div className="h-2 rounded-full bg-white">
            <span className="block h-2 rounded-full bg-[#3A7CA5]" style={{ width: `${Math.max(5, (row.value / max) * 100)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function Histogram({ values }: { values: number[] }) {
  const buckets = [0, 0, 0, 0, 0];
  for (const value of values) {
    const index = Math.min(4, Math.max(0, Math.floor(value * 5)));
    buckets[index] += 1;
  }
  const max = Math.max(...buckets, 1);
  return (
    <div className="mt-4 flex h-28 items-end gap-2">
      {buckets.map((count, index) => (
        <div key={index} className="flex flex-1 flex-col items-center gap-2">
          <span className="w-full rounded-t-md bg-[#D4AF37]" style={{ height: `${Math.max(8, (count / max) * 88)}px` }} />
          <span className="text-[11px] text-slate-500">{(index / 5).toFixed(1)}</span>
        </div>
      ))}
    </div>
  );
}

function toCalibrationAnchors(samples: AnchorSpeakingSample[]): CalibrationAnchorSample[] {
  return samples.flatMap((sample) =>
    criteria.map((criterion) => ({
      anchor_sample_id: `${sample.sample_id}:${criterion}`,
      criterion,
      band: sample.scores[criterion].band,
      score: 1,
      rationale: sample.scores[criterion].rationale,
      content: sample.transcript,
    })),
  );
}

function previewCriteria(): Record<CriterionKey, CriterionScoreInput> {
  return {
    fluency_coherence: previewCriterion("fluency_coherence", 6.5),
    lexical_resource: previewCriterion("lexical_resource", 6.5),
    grammatical_range_accuracy: previewCriterion("grammatical_range_accuracy", 6.5),
    pronunciation: previewCriterion("pronunciation", 7.5),
  };
}

function previewCriterion(criterion: CriterionKey, band: number): CriterionScoreInput {
  return {
    band,
    confidence: 0.82,
    evidence: [
      {
        turn_id: "web_calibration_preview",
        quote: criterionLabels[criterion],
        reason: "Calibration preview uses anchor similarity evidence.",
      },
    ],
    suggestions: ["Keep reviewer decisions tied to anchor samples."],
    raw_output: {},
  };
}

function buildCriterionMaeRows(samples: AnchorSpeakingSample[]) {
  return criteria.map((criterion) => {
    const values = samples.map((sample) => Math.abs(sample.scores[criterion].band - sample.target_band));
    const mae = values.length ? values.reduce((total, value) => total + value, 0) / values.length : 0;
    return { label: criterionLabels[criterion], value: Number(mae.toFixed(3)) };
  });
}

function passRateFromGate(gate: CalibrationQualityGateResponse) {
  if (!gate.checks.length) return 1;
  const passed = gate.checks.filter((check) => check.status === "passed").length;
  return passed / gate.checks.length;
}

function baselineMae(report: MultiPAExperimentReport | null) {
  return report?.comparisons.find((item) => item.provider === "gopt_baseline")?.mean_absolute_error ?? 0;
}

function metadataString(metadata: Record<string, unknown>, key: string) {
  const value = metadata[key];
  return typeof value === "string" ? value : "";
}

function metadataNumber(metadata: Record<string, unknown>, key: string) {
  const value = metadata[key];
  return typeof value === "number" ? value : null;
}

function apiMessage(err: unknown, fallback: string) {
  const apiError = err as ApiError;
  const detail = apiError.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail.message === "string") return detail.message;
  return apiError.response?.data?.message || fallback;
}

function elapsed(started: number) {
  return Math.max(0, Math.round(performance.now() - started));
}

function gateTone(status?: string): "sage" | "coral" | "red" | "slate" {
  if (status === "passed") return "sage";
  if (status === "needs_review" || status === "not_configured") return "coral";
  if (status === "blocked" || status === "failed") return "red";
  return "slate";
}

function runTone(status: string): "sage" | "coral" | "red" | "slate" {
  if (status === "passed") return "sage";
  if (status === "blocked" || status === "failed") return "red";
  if (status === "needs_review" || status === "not_configured") return "coral";
  return "slate";
}

function formatMetric(value: number) {
  return Number.isFinite(value) ? value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "") : "0";
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}
