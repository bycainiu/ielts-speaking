# Protocol Package

本包存放前端、Go Backend、Agent Harness 共享的协议 schema。

## 当前 schema

- `session-event.schema.json`：AG-UI 风格事件。
- `agent-api.schema.json`：Agent Harness HTTP API 请求与响应。
- `agent-run.schema.json`：Agent Run / Step / Tool Call 审计结构。
- `scoring-report.schema.json`：IELTS Speaking 四维模拟评分报告，包含必填 `version` 用于报告版本追踪。
- `speech-assessment.schema.json`：独立语音 evidence 服务的请求、VAD/word timestamp、GOPT-compatible pronunciation evidence、时间戳转写响应、Pronunciation Drill 请求/响应与 evidence 响应，明确禁止直接输出 IELTS band。

`agent-api.schema.json` 当前覆盖会话规划、下一轮推进、ASR 消费，以及 `TranscribeAudioRequest` / `TranscribeAudioResponse`、`SynthesizeSpeechRequest` / `SynthesizeSpeechResponse`，用于 Agent Harness 的 `POST /agent/audio/transcribe` 和 `POST /agent/audio/synthesize`。

## 校验

```powershell
node packages/protocol/scripts/validate-schemas.mjs
```

该脚本会使用 Ajv 2020 编译全部 schema，并对 `scoring-report.schema.json` 执行合法样例与缺少版本号的反例校验，对 `speech-assessment.schema.json` 执行合法 evidence 样例、timestamp 样例、Pronunciation Drill 样例与 direct band 输出反例校验。
