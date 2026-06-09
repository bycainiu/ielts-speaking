# Phase 9 Quality Gate

## Langfuse 与 Trace

- `GET /agent/runs/{run_id}/trace` 返回单次 run 的 Part、question_id、节点、prompt version、模型、tokens 估算、检索来源、结构化输出合法性、评分摘要、工具调用和错误类型。
- `GET /agent/observability/summary?session_id=...&run_id=...&mode=...` 返回聚合延迟、错误率、节点耗时、工具成功率和最近 run。
- `GET /agent/observability/alerts` 使用 `OBSERVABILITY_ERROR_RATE_ALERT_THRESHOLD` 和 `OBSERVABILITY_LATENCY_P95_ALERT_MS` 评估发布阻塞风险。

## DeepEval 回归

- 本地确定性套件位于 `services/agent-harness/app/evals/deepeval_regression.py`。
- 默认样本不少于 30 个，覆盖组卷、追问、评分和反馈。
- 报告对象可输出 Markdown，失败项进入 `improvement_items`，高风险失败会设置 `block_release=true`。

## Ragas RAG 评估

- 本地等效套件位于 `services/agent-harness/app/evals/ragas_rag_eval.py`。
- 每个样本包含 query、expected doc ids、metadata filters 和 top_k。
- 输出 retrieval precision/recall；recall 不达标的样本进入改进列表。

## Promptfoo 安全红队

- 配置文件：`services/agent-harness/evals/promptfoo-redteam.yaml`。
- 本地 runner：`services/agent-harness/app/evals/promptfoo_redteam.py`。
- 覆盖考试模式与练习模式，包含 prompt 注入、系统提示泄露、隐私提取和高风险工具越权。
- 高风险或 critical 样本失败必须阻塞发布。

## E2E

- `services/agent-harness/tests/test_phase9_e2e.py` 覆盖 full_exam happy path、part_practice happy path、报告生成和 trace summary。
- 本阶段 E2E 先以 API 确定性闭环作为质量闸门，浏览器 smoke 用于验证真实前端状态和响应式布局。

## 性能基线

- 本地基线 runner：`services/agent-harness/app/evals/performance_baseline.py`。
- 记录 Live turn、ASR、TTS、评分、报告生成和 Agent node latency。
- 输出 p50/p95、错误率、TTS cache hit rate 和瓶颈列表。

## 错误恢复

- 策略入口：`POST /agent/recovery/directive`。
- ASR 连续失败后允许手动文本输入。
- TTS 失败后降级为文本考官问题。
- Agent 结构化输出多次不合法后使用受控兜底事件。
- WebSocket 断线后前端自动重连并按 session_id 恢复会话状态。

## 日志与告警

- Agent Harness 请求日志使用 JSON 格式，包含 `request_id`、`session_id`、method、path、status_code 和 latency_ms。
- `GET /metrics` 输出 Prometheus 风格指标，包括 run 总数、错误数、错误率、p95 延迟、工具成功率和 workflow node 维度指标。
- 告警优先排查顺序：错误率、p95 延迟、MCP 工具成功率、单 run trace、结构化输出错误。
