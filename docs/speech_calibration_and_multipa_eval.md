# Speech Calibration 与 MultiPA 实验方案

> 状态：Engineering-ready, data-gated  
> 更新时间：2026-06-08  
> 对应任务：P10-006、P10-007

## 目标

Phase 10 的语音质量建设需要两件事：

1. 用 SpeechOcean762 与授权自有人工标注样本校准 GOPT / Fluency Metrics 等语音 evidence。
2. 在固定 benchmark 上比较 MultiPA 对 IELTS Part 2/3 开放回答发音评估的效果、延迟、成本和部署复杂度。

当前已完成工程化 harness，但真实校准集和 MultiPA 实验结果仍受外部数据授权、人工标注和模型运行环境约束，不能用合成样本替代生产验收。

## P10-006 校准集 Manifest

Manifest 使用 JSONL，每行一条样本。核心字段：

- `source`：`speechocean762`、`authorized_internal` 或 `synthetic_contract`。
- `source_license_id`：SpeechOcean762 样本必须以 `speechocean762:` 开头。
- `consent_record_id`：自有样本必须提供授权/同意记录。
- `annotator_count`：自有样本生产验收要求至少 2 名标注者。
- `part`：IELTS Part 1 / 2 / 3。
- `accent_group`：覆盖不同口音组，只用于覆盖率分析，不作为扣分依据。
- `recording_quality`：`good`、`fair`、`poor`。
- `human_pronunciation_band`、`human_fluency_band`：人工标注的内部模拟分。
- `evidence`：GOPT sentence score、WPM、silence ratio、long pause、filler ratio、audio quality、confidence。

样例文件：`services/agent-harness/evals/speech_calibration_manifest.example.jsonl`。

## 校验与回归

工程入口：

- `app.evals.speech_calibration.audit_speech_calibration_dataset`
- `app.evals.speech_calibration.SpeechCalibrationRegressionRunner`
- `app.evals.speech_calibration.load_speech_calibration_manifest`
- CLI：`python -m app.evals.speech_eval_cli calibration`
- API：`POST /agent/calibration/speech-regression`

生产门禁默认要求：

- 至少 200 条 production samples。
- 同时包含 SpeechOcean762 与授权自有样本。
- 覆盖至少 5 个 pronunciation band bucket。
- 覆盖 Part 1 / 2 / 3。
- 覆盖至少 4 类口音组。
- 覆盖 good / fair / poor 录音质量。
- 合成 `synthetic_contract` 样本不得通过生产门禁。

回归指标：

- case-level absolute error。
- mean absolute error。
- max absolute error。
- release gate 是否被高严重度样本阻断。

该 runner 只评估内部 speech evidence calibration，不发布 direct IELTS band。

Agent Harness 后端也提供同等能力的 API：

```text
GET  /agent/calibration/anchor-samples
POST /agent/calibration/score
POST /agent/calibration/speech-regression
POST /agent/calibration/multipa-experiment
POST /agent/calibration/quality-gate
```

API 只接受结构化 JSON 样本或显式 contract samples，不从请求中读取任意本地 manifest 路径。`speech-regression` 返回的 case metadata 包含 Part、accent group、recording quality、confidence 与 transcript excerpt，供后台校准页筛选和排障。生产验收仍必须提交真实授权样本，不能用 synthetic contract samples 代替。

生成报告示例：

```powershell
cd services/agent-harness
python -m app.evals.speech_eval_cli calibration `
  --manifest evals/speech_calibration_manifest.jsonl `
  --output-json ../../tmp/speech-calibration-report.json `
  --output-md ../../tmp/speech-calibration-report.md
```

CI 合约样本只能这样运行：

```powershell
cd services/agent-harness
python -m app.evals.speech_eval_cli calibration `
  --contract-samples `
  --allow-synthetic-contract `
  --min-production-samples 0
```

## P10-007 MultiPA 实验

工程入口：

- `app.evals.multipa_open_response.MultiPAOpenResponseExperimentRunner`
- `app.evals.multipa_open_response.MultiPAAdapterOutput`
- CLI：`python -m app.evals.speech_eval_cli multipa`
- API：`POST /agent/calibration/multipa-experiment`
- MultiPA 输出样例：`services/agent-harness/evals/multipa_outputs.example.jsonl`

实验流程：

1. 固定 P10-006 校准集中的 regression / holdout split。
2. 记录 GOPT baseline 的内部预测误差。
3. 收集 MultiPA adapter 对同一 `sample_id` 的预测、延迟、成本和部署备注。
4. 输出 `ProviderComparison`：
   - sample count
   - mean/max absolute error
   - p95 latency
   - estimated total cost
   - deployment complexity
5. 只有 MultiPA 在误差容忍范围内、p95 延迟不超过阈值、成本可接受时，才建议进入 feature-flagged 实验。

生成报告示例：

```powershell
cd services/agent-harness
python -m app.evals.speech_eval_cli multipa `
  --manifest evals/speech_calibration_manifest.jsonl `
  --multipa-outputs evals/multipa_outputs.jsonl `
  --output-json ../../tmp/multipa-experiment-report.json `
  --output-md ../../tmp/multipa-experiment-report.md
```

## 当前边界

- `synthetic_contract` 样本只用于 schema、runner 和 CI 合约测试。
- P10-006 生产验收仍需要真实授权数据与人工标注。
- P10-007 生产验收仍需要真实 MultiPA adapter 输出和固定 benchmark 报告。
- Mock Exam 主评分链路继续使用保守 speech evidence，不把开源模型输出直接映射成 IELTS 官方分。
