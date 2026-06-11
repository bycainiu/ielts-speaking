export type ReviewAudioAsset = {
  id: string;
  kind: "user_recording" | "examiner_tts" | "reference" | string;
  mime_type?: string;
  duration_ms?: number | null;
  created_at?: string;
};

export type ReviewASRResult = {
  id: string;
  turn_id: string;
  audio_asset_id?: string | null;
  provider: string;
  model: string;
  transcript: string;
  corrected_transcript?: string | null;
  confidence?: number | null;
  created_at?: string;
};

export type ReviewSpeechMetrics = {
  id: string;
  turn_id: string;
  audio_asset_id?: string | null;
  duration_ms?: number | null;
  words_count?: number | null;
  wpm?: number | null;
  long_pause_count?: number | null;
  mean_pause_ms?: number | null;
  total_pause_ms?: number | null;
  filler_count?: number | null;
  filler_ratio?: number | null;
  asr_confidence?: number | null;
  raw_metrics?: Record<string, unknown>;
  created_at?: string;
};

export type ReviewSessionPart = {
  id: string;
  part: number;
  status: string;
  order_index?: number;
};

export type ReviewTurn = {
  id: string;
  session_id?: string;
  part_id?: string | null;
  question_id?: string | null;
  turn_index: number;
  speaker: "examiner" | "user" | string;
  status: string;
  question_text?: string | null;
  answer_text?: string | null;
  agent_run_id?: string | null;
  metadata?: Record<string, unknown> | null;
  audio_assets?: ReviewAudioAsset[];
  asr_results?: ReviewASRResult[];
  speech_metrics?: ReviewSpeechMetrics[];
};

export type ReportEvidence = {
  turn_id?: string | null;
  quote?: string | null;
  reason?: string | null;
};

export type CriterionScore = {
  id?: string;
  criterion: string;
  band: number;
  confidence: number;
  evidence?: ReportEvidence[];
  suggestions?: string[];
};

export type FeedbackItem = {
  id: string;
  category: string;
  priority: number;
  title: string;
  body: string;
  evidence_refs?: ReportEvidence[];
};

export type ReferenceAnswer = {
  id: string;
  turn_id?: string | null;
  band_target?: number | null;
  skeleton?: Record<string, string>;
  answer_text: string;
  personalization_notes?: string | null;
};

export type StudyPlan = {
  id: string;
  priority: number;
  focus: string;
  task: string;
  due_on?: string | null;
};

export type ScoreReport = {
  id: string;
  session_id: string;
  version: number;
  status: string;
  overall_band?: number | null;
  confidence?: number | null;
  disclaimer: string;
  model_run_id?: string | null;
  raw_report?: Record<string, unknown>;
  criteria: CriterionScore[];
  feedback_items: FeedbackItem[];
  reference_answers: ReferenceAnswer[];
  study_plans: StudyPlan[];
};

export type ReviewConversationItem = {
  id: string;
  turnIndex: number;
  part: number;
  questionId?: string | null;
  questionText?: string | null;
  answerText?: string | null;
  agentRunId?: string | null;
  metadata?: Record<string, unknown> | null;
  examinerAudio?: ReviewAudioAsset;
  userAudio?: ReviewAudioAsset;
  asr?: ReviewASRResult;
  metrics?: ReviewSpeechMetrics;
  evidence: Array<ReportEvidence & { criterion: string }>;
  referenceAnswer?: ReferenceAnswer;
  status: string;
};

export type TraceToolCall = {
  tool_name: string;
  scope?: string | null;
  status: "completed" | "failed";
  latency_ms: number;
  error_code?: string | null;
  input_summary?: string | null;
  output_summary?: string | null;
  result_summary?: string | null;
  input_payload?: Record<string, unknown> | string | null;
  output_payload?: Record<string, unknown> | string | null;
  arguments?: Record<string, unknown> | string | null;
  parameters?: Record<string, unknown> | string | null;
  request?: Record<string, unknown> | string | null;
  response?: Record<string, unknown> | string | null;
  metadata?: Record<string, unknown> | null;
};

export type TraceMessage = {
  role?: string | null;
  content?: string | null;
  type?: string | null;
};

export type TraceLlmCall = {
  llm_call_id: string;
  call_name: string;
  agent_name?: string | null;
  execution_kind?: "llm" | "deterministic" | "tool" | string;
  payload_origin?: "captured" | "derived" | string;
  provider?: string | null;
  model_name?: string | null;
  prompt_version?: string | null;
  status: "running" | "completed" | "failed";
  input_summary?: string | null;
  output_summary?: string | null;
  request_payload?: Record<string, unknown> | string | null;
  response_payload?: Record<string, unknown> | string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  latency_ms?: number | null;
  error_code?: string | null;
  started_at: string;
  finished_at?: string | null;
};

export type TraceStep = {
  step_id: string;
  workflow_node: string;
  part?: number | null;
  question_id?: string | null;
  agent_name?: string | null;
  execution_kind?: "llm" | "deterministic" | "tool" | string;
  prompt_version?: string | null;
  model_name?: string | null;
  status: "running" | "completed" | "failed";
  input_summary?: string | null;
  output_summary?: string | null;
  input_payload?: Record<string, unknown> | string | null;
  input_detail?: Record<string, unknown> | string | null;
  output_payload?: Record<string, unknown> | string | null;
  messages?: TraceMessage[] | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  estimated_cost_usd?: number | null;
  retrieved_chunks?: Record<string, unknown>[];
  structured_output_validity?: boolean | null;
  scoring_result?: Record<string, unknown> | null;
  latency_ms?: number | null;
  error_code?: string | null;
  error_type?: string | null;
  started_at: string;
  finished_at?: string | null;
  llm_calls?: TraceLlmCall[];
  tool_calls: TraceToolCall[];
};

export type AgentRunTrace = {
  run_id: string;
  session_id: string;
  user_id_hash?: string | null;
  mode?: string | null;
  part?: number | null;
  question_id?: string | null;
  status: "running" | "completed" | "failed" | "cancelled";
  started_at: string;
  finished_at?: string | null;
  steps: TraceStep[];
};

export const criterionLabels: Record<string, string> = {
  fluency_coherence: "Fluency",
  lexical_resource: "Lexical",
  grammatical_range_accuracy: "Grammar",
  pronunciation: "Pronunciation",
};
