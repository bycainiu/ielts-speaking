# ADR: Speech Assessment Service

> 状态：Accepted for MVP evidence layer  
> 更新时间：2026-06-08  
> 对应任务：P6-007

## 背景

IELTS Speaking 的 Pronunciation 和 Fluency 不能只依赖转写文本。系统需要从音频中提取客观 evidence，例如音频质量、时长、词级时间戳、停顿、WPM、filler、repetition、self-correction，以及后续 GOPT / MFA / Kaldi GOP 这类发音证据。

但这些开源模型的输出不能直接等同 IELTS 官方分数，也不应直接输出最终 Pronunciation Band。最终模拟分仍由 `ScoringWorkflow` 结合 transcript、speech evidence、rubric、anchor samples、ASR confidence 和录音质量保守判断。

## 决策

新增独立 `services/speech-assessment`：

- FastAPI 服务，默认监听 `8010`。
- `GET /healthz` 暴露服务状态、能力开关和合规策略。
- `GET /metrics` 暴露 Prometheus 风格基础指标。
- `POST /speech/transcribe-timestamps` 输出 transcript、segments、word timestamps 和 alignment/downstream confidence。
- `POST /speech/assess` 输出结构化 speech evidence。
- `POST /speech/pronunciation-drill` 输出固定文本专项训练的 word-level / phoneme-level feedback。
- 共享协议 schema 位于 `packages/protocol/schemas/speech-assessment.schema.json`。
- Docker Compose 新增 `speech-assessment` 服务，并为 Go API 和 Agent Harness 预留 `SPEECH_ASSESSMENT_URL`。

## 链路分离

### Mock Exam / Free Speaking

用于真实 IELTS 口语模拟考试或开放回答练习。

输入：

- `audio_asset_id`
- `session_id`
- `turn_id`
- `transcript`
- `duration_ms`
- 可选 `word_timestamps`

输出：

- `audio_quality`
- `fluency`
- sentence-level `pronunciation`
- `confidence`

约束：

- 只输出 evidence。
- 不输出 IELTS band。
- 不输出官方成绩表述。

### Pronunciation Drill / Fixed Text

用于固定文本跟读专项训练。

输入：

- `audio_asset_id`
- `target_text`
- `transcript`
- 可选 `word_timestamps`

输出：

- word-level feedback
- phoneme-level feedback
- stress / timing review notes

约束：

- 与 Mock Exam 评分链路分离。
- 可给词级、音素级建议，但仍不输出 IELTS band。

## 当前 MVP 骨架

当前版本使用 deterministic evidence extractor：

- `POST /speech/transcribe-timestamps` 默认使用 deterministic timestamp provider，把 `expected_transcript` 切分为稳定 word timestamps，便于复盘高亮、前端联调和回归测试。
- 同一接口已预留 `provider=faster_whisper`，运行时安装 `faster-whisper` 后可通过 `audio_path` 或 `audio_base64` 调用 WhisperModel，输出 word timestamps、segments、ASR confidence、alignment confidence 和 downstream confidence。
- `app.fluency_metrics` 从 transcript、duration、VAD segments 和 word timestamps 推导 WPM、speech duration、silence ratio、pause、filler、repetition、self-correction。
- `app.gopt_scorer` 输出 GOPT-compatible sentence-level pronunciation evidence，包含 sentence score、accuracy、fluency、prosody 和 confidence。
- `app.pronunciation_drill` 提供独立 `/speech/pronunciation-drill` API，生成 MFA / Kaldi GOP-compatible word/phoneme feedback，并预留真实 MFA/Kaldi adapter provider。
- 在 response policy 中强制 `ielts_band_output_allowed=false`。

## 后续接入计划

P6-008：

- 已接入 faster-whisper adapter 边界。
- 已输出 word-level timestamps、alignment confidence 和低质量音频降权信号。
- 后续可补 WhisperX forced alignment 作为同一 response schema 的第二 provider。

P6-009：

- 已接入 VAD pause metrics。
- 已接入 deterministic GOPT-compatible sentence-level pronunciation evidence。
- 已输出 accuracy、fluency、prosody 与 confidence。
- 真实 GOPT 模型可作为 `gopt_adapter` provider 替换当前 deterministic scorer，但 response policy 仍必须禁止 direct IELTS band output。

P6-010：

- 已建立固定文本 Pronunciation Drill 独立链路和协议，详见 `docs/pronunciation_drill_mfa_kaldi_gop.md`。
- 当前 `deterministic_mfa_kaldi_gop` 用于联调和回归测试；真实 MFA / Kaldi GOP 可替换为 `mfa_adapter` 或 `kaldi_gop_adapter`。
- 输出 word-level、phoneme-level、stress/timing feedback，并保持与 Mock Exam scoring path 分离。

P10-006：

- 用 SpeechOcean762 与授权自有人工标注样本校准 evidence 到内部模拟评分区间。

## 风险与控制

- 模型授权风险：只接入授权数据和可部署模型；校准集来源必须可追溯。
- 误导性评分风险：schema 禁止 direct IELTS band output，ScoringWorkflow 只消费 evidence。
- 性能风险：语音重模型作为独立服务，可按 GPU/CPU 单独扩缩容。
- 隐私风险：服务只接收 audio asset reference、transcript 和必要 metadata，不直接处理用户完整 profile。
