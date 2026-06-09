import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const currentDir = fileURLToPath(new URL(".", import.meta.url));
const schemaDir = join(currentDir, "..", "schemas");
const files = (await readdir(schemaDir)).filter((file) => file.endsWith(".json"));
const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);

if (files.length === 0) {
  throw new Error("未找到协议 schema 文件");
}

const schemas = [];

for (const file of files) {
  const raw = await readFile(join(schemaDir, file), "utf8");
  const schema = JSON.parse(raw);
  schemas.push({ file, schema });
  ajv.addSchema(schema, schema.$id);
}

for (const { file, schema } of schemas) {
  ajv.compile(schema);
  console.log(`OK ${file}`);
}

const scoringReportSchema = schemas.find(({ file }) => file === "scoring-report.schema.json")?.schema;
if (!scoringReportSchema) {
  throw new Error("缺少 scoring-report.schema.json");
}

const validateScoringReport = ajv.getSchema(scoringReportSchema.$id);
if (!validateScoringReport) {
  throw new Error("无法加载 scoring-report schema 校验器");
}

const scoringReportExample = {
  report_id: "report_001",
  session_id: "session_001",
  version: 1,
  overall_band: 6.5,
  confidence: 0.82,
  criteria: {
    fluency_coherence: criterionExample("turn_001"),
    lexical_resource: criterionExample("turn_001"),
    grammatical_range_accuracy: criterionExample("turn_001"),
    pronunciation: criterionExample("turn_001"),
  },
  reviewer_notes: ["Use conservative scoring for low-confidence audio."],
  next_practice_plan: [
    {
      priority: 1,
      focus: "fluency",
      task: "Record a 90-second answer with one planned example.",
    },
  ],
  disclaimer: "AI 模拟评分仅用于练习参考，不代表 IELTS 官方成绩。",
};

if (!validateScoringReport(scoringReportExample)) {
  throw new Error(`scoring-report valid example failed: ${ajv.errorsText(validateScoringReport.errors)}`);
}

const missingVersion = structuredClone(scoringReportExample);
delete missingVersion.version;
if (validateScoringReport(missingVersion)) {
  throw new Error("scoring-report missing version should fail validation");
}
console.log("OK scoring-report examples");

const speechAssessmentSchema = schemas.find(({ file }) => file === "speech-assessment.schema.json")?.schema;
if (!speechAssessmentSchema) {
  throw new Error("缺少 speech-assessment.schema.json");
}

const validateSpeechAssessmentResponse = ajv.getSchema(
  `${speechAssessmentSchema.$id}#/$defs/SpeechAssessmentResponse`,
);
if (!validateSpeechAssessmentResponse) {
  throw new Error("无法加载 speech-assessment response schema 校验器");
}
const validateTimestampResponse = ajv.getSchema(
  `${speechAssessmentSchema.$id}#/$defs/TimestampTranscriptionResponse`,
);
if (!validateTimestampResponse) {
  throw new Error("无法加载 timestamp transcription response schema 校验器");
}
const validatePronunciationDrillRequest = ajv.getSchema(
  `${speechAssessmentSchema.$id}#/$defs/PronunciationDrillRequest`,
);
if (!validatePronunciationDrillRequest) {
  throw new Error("无法加载 pronunciation drill request schema 校验器");
}
const validatePronunciationDrillResponse = ajv.getSchema(
  `${speechAssessmentSchema.$id}#/$defs/PronunciationDrillResponse`,
);
if (!validatePronunciationDrillResponse) {
  throw new Error("无法加载 pronunciation drill response schema 校验器");
}

const speechAssessmentExample = {
  evidence_id: "speech_ev_001",
  audio_asset_id: "audio_001",
  mode: "mock_exam",
  provider: "deterministic_speech_assessment",
  model: "speech-evidence-v0",
  audio_quality: {
    duration_ms: 12000,
    quality_label: "usable",
    clipping_detected: false,
    estimated_snr_db: 28,
    confidence: 0.82,
  },
  fluency: {
    duration_sec: 12,
    speech_duration_sec: 8.2,
    silence_ratio: 0.317,
    wpm: 105,
    long_pause_count: 1,
    mean_pause_ms: 900,
    filler_count: 1,
    filler_ratio: 0.04,
    repetition_count: 1,
    self_correction_count: 0,
    confidence: 0.82,
  },
  pronunciation: {
    evidence_level: "sentence",
    sentence_score: 0.74,
    accuracy: 0.73,
    fluency: 0.76,
    prosody: 0.72,
    confidence: 0.82,
    gopt: {
      provider: "deterministic_gopt",
      model: "gopt-evidence-v0",
      sentence_score: 0.74,
      accuracy: 0.73,
      fluency: 0.76,
      prosody: 0.72,
      confidence: 0.82,
      calibration_note: "Use as pronunciation evidence only.",
    },
    word_feedback: [],
    phoneme_feedback: [],
  },
  confidence: 0.82,
  policy: {
    ielts_band_output_allowed: false,
    consumer_instruction: "Use this payload as speech evidence only.",
    separated_paths: ["mock_exam", "pronunciation_drill"],
  },
  warnings: [],
};

if (!validateSpeechAssessmentResponse(speechAssessmentExample)) {
  throw new Error(`speech-assessment valid example failed: ${ajv.errorsText(validateSpeechAssessmentResponse.errors)}`);
}

const speechAssessmentWithBand = structuredClone(speechAssessmentExample);
speechAssessmentWithBand.overall_band = 6.5;
if (validateSpeechAssessmentResponse(speechAssessmentWithBand)) {
  throw new Error("speech-assessment response must not allow direct IELTS band output");
}

const timestampExample = {
  audio_asset_id: "audio_001",
  provider: "deterministic",
  model: "deterministic-word-timestamp-v0",
  transcript: "Technology helps students learn faster.",
  language: "en",
  duration_ms: 5000,
  word_timestamps: [
    {
      word: "technology",
      start_ms: 0,
      end_ms: 720,
      confidence: 0.8,
    },
  ],
  segments: [
    {
      segment_id: 0,
      start_ms: 0,
      end_ms: 5000,
      text: "Technology helps students learn faster.",
      confidence: 0.78,
      words: [
        {
          word: "technology",
          start_ms: 0,
          end_ms: 720,
          confidence: 0.8,
        },
      ],
    },
  ],
  asr_confidence: 0.82,
  alignment_confidence: 0.8,
  downstream_confidence: 0.81,
  audio_quality_label: "usable",
  warnings: [],
  metadata: {
    source: "expected_transcript",
  },
};

if (!validateTimestampResponse(timestampExample)) {
  throw new Error(`timestamp transcription valid example failed: ${ajv.errorsText(validateTimestampResponse.errors)}`);
}

const pronunciationDrillRequestExample = {
  audio_asset_id: "audio_drill_001",
  target_text: "Technology improves education",
  transcript: "Technology improve education",
  duration_ms: 3600,
  word_timestamps: [
    {
      word: "Technology",
      start_ms: 0,
      end_ms: 850,
      confidence: 0.84,
    },
  ],
  phoneme_hints: [
    {
      word: "technology",
      phonemes: ["T", "EH", "K", "N", "AA", "L", "AH", "JH", "IY"],
    },
  ],
  provider: "deterministic_mfa_kaldi_gop",
  metadata: {
    route: "fixed_text_drill",
  },
};

if (!validatePronunciationDrillRequest(pronunciationDrillRequestExample)) {
  throw new Error(
    `pronunciation drill request valid example failed: ${ajv.errorsText(validatePronunciationDrillRequest.errors)}`,
  );
}

const pronunciationDrillResponseExample = {
  drill_id: "pron_drill_001",
  audio_asset_id: "audio_drill_001",
  mode: "pronunciation_drill",
  provider: "deterministic_mfa_kaldi_gop",
  model: "mfa-kaldi-gop-drill-v0",
  target_text: "Technology improves education",
  transcript: "Technology improve education",
  alignment: {
    target_word_count: 3,
    spoken_word_count: 3,
    aligned_word_count: 3,
    missing_word_count: 0,
    substituted_word_count: 1,
    alignment_confidence: 0.79,
  },
  word_feedback: [
    {
      target_index: 0,
      target_word: "technology",
      spoken_word: "technology",
      start_ms: 0,
      end_ms: 850,
      gop_score: 0.9,
      accuracy: 0.9,
      timing: "on_time",
      stress: "acceptable",
      status: "matched",
      note: "MFA/Kaldi GOP-compatible word evidence is acceptable for this drill.",
    },
  ],
  phoneme_feedback: [
    {
      target_index: 0,
      word: "technology",
      phoneme: "T",
      position: 0,
      gop_score: 0.9,
      accuracy: 0.9,
      status: "acceptable",
      note: "Segment-level GOP-compatible evidence is acceptable.",
    },
  ],
  confidence: 0.82,
  policy: {
    ielts_band_output_allowed: false,
    consumer_instruction: "Use this payload only for fixed-text pronunciation drills.",
    separated_paths: ["mock_exam", "pronunciation_drill"],
  },
  warnings: ["deterministic_drill_provider: replace with MFA/Kaldi GOP adapters for production scoring"],
};

if (!validatePronunciationDrillResponse(pronunciationDrillResponseExample)) {
  throw new Error(
    `pronunciation drill response valid example failed: ${ajv.errorsText(validatePronunciationDrillResponse.errors)}`,
  );
}

const pronunciationDrillWithBand = structuredClone(pronunciationDrillResponseExample);
pronunciationDrillWithBand.overall_band = 6.5;
if (validatePronunciationDrillResponse(pronunciationDrillWithBand)) {
  throw new Error("pronunciation drill response must not allow direct IELTS band output");
}
console.log("OK speech-assessment examples");

function criterionExample(turnId) {
  return {
    band: 6.5,
    confidence: 0.8,
    evidence: [
      {
        turn_id: turnId,
        quote: "I think it is useful.",
        reason: "Clear answer with a basic explanation.",
      },
    ],
    suggestions: ["Add one concrete example."],
  };
}
