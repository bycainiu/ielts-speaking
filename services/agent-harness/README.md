# Agent Harness Service

Python FastAPI Agent Harness。当前版本提供考试工作流、练习工作流、评分工作流、AG-UI 风格事件适配、MCP、RAG、MiMo 模型边界、Trace、隐私防护和反馈工作流，并已建立 Microsoft Agent Framework core 适配边界。

## 本地运行

```powershell
cd services/agent-harness
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 接口

- `GET /healthz`
- `POST /agent/sessions/{session_id}/plan`
- `POST /agent/sessions/{session_id}/consume-asr`
- `POST /agent/sessions/{session_id}/next-turn`
- `POST /agent/audio/transcribe`
- `POST /agent/audio/synthesize`
- `GET /agent/runs/{run_id}`
- `GET /agent/runs/{run_id}/trace`
- `GET /agent/observability/summary`
- `GET /agent/observability/alerts`
- `GET /agent/calibration/anchor-samples`
- `POST /agent/calibration/score`
- `POST /agent/calibration/speech-regression`
- `POST /agent/calibration/multipa-experiment`
- `POST /agent/calibration/quality-gate`
- `POST /agent/recovery/directive`
- `GET /metrics`
- `POST /agent/runs/{run_id}/cancel`

## 当前边界

- 工作流使用确定性状态机和可控 fallback question，保证协议和状态推进可测试。
- 运行时边界见 `../../docs/agent_runtime_boundary.md`；`/healthz` 会返回 `adapter=microsoft-agent-framework`、`adapter_package=agent-framework-core`、`framework=deterministic-workflow`。
- `full_exam` 使用 `ExamWorkflow`，不输出练习提示，保持考试模式的严肃流程。
- `part_practice` / `topic_practice` 使用 `PracticeWorkflow`，会在事件 payload 中输出 `practice_hints`、`practice_mode`，Part 2 会附带 cue card。
- Agent 输出使用 Pydantic model 校验。
- 模型访问通过 `app.models.mimo_client.MiMoChatClient` 封装，工作流不直接依赖底层 HTTP。
- 不在本服务内处理用户鉴权，调用方必须注入可信 `user_id` 和 `session_id`。

## ASR Service

`app.audio.asr_service.AsrService` 是 P6 语音链路的 ASR 边界：

- `POST /agent/audio/transcribe` 接收 `audio_asset_id`、`mime_type`、可选 `duration_ms`、`language_hint`、`audio_url` 或 `audio_base64`。
- 支持 `audio/wav`、`audio/x-wav`、`audio/mpeg`、`audio/mp3` 和 `audio/webm`；`audio/webm;codecs=opus` 会规范化为 `audio/webm`。
- 默认 `MOCK_MODEL_ENABLED=true` 时使用确定性 mock，不调用真实 MiMo，也不消耗额度；返回 `asr_text`、`language`、`confidence`、`provider`、`model`、`duration_ms` 和安全 metadata。
- `MOCK_MODEL_ENABLED=false` 时使用 `mimo-v2.5-asr`，并要求请求带 `audio_url` 或 `audio_base64`；真实音频资产拉取、ASR 结果持久化和 turn 关联由 Go Audio Service 与 P6-002 继续衔接。
- 错误会结构化返回：不支持格式返回 415，真实模式缺少音频源返回 422，上游可重试错误返回 503。

示例请求：

```json
{
  "audio_asset_id": "audio_001",
  "mime_type": "audio/webm",
  "duration_ms": 12000,
  "language_hint": "en"
}
```

## TTS Service

`app.audio.tts_service.TTSService` 是 P6 考官语音合成边界：

- `POST /agent/audio/synthesize` 接收 `text`、`voice_id`、`speaking_rate`、`emotion` 和 `style`。
- 默认 `MOCK_MODEL_ENABLED=true` 时生成确定性 mock wav 音频，不调用真实 MiMo，也不消耗额度。
- `MOCK_MODEL_ENABLED=false` 时使用 `mimo-v2.5-tts` 供应商边界，解析 `audio_base64`、`mime_type` 和 `duration_ms`。
- Agent Harness 只负责生成音频 payload；Go Audio API 的 `POST /api/audio/tts` 会调用该接口并把音频保存到对象存储。

示例请求：

```json
{
  "text": "Let's talk about your hometown.",
  "voice_id": "ielts_examiner_default",
  "speaking_rate": 1.0,
  "emotion": "neutral",
  "style": "examiner"
}
```

示例响应：

```json
{
  "audio_asset_id": "audio_001",
  "asr_text": "Mock IELTS speaking transcript for audio asset audio_001.",
  "language": "en",
  "confidence": 0.86,
  "provider": "mock_asr",
  "model": "mimo-v2.5-asr",
  "duration_ms": 12000,
  "metadata": {
    "mock": true,
    "mime_type": "audio/webm",
    "format_strategy": "provider_compatible",
    "source_type": "asset_reference"
  }
}
```

## QuestionSetPlannerAgent

`app.agents.question_planner_agent.QuestionSetPlannerAgent` 是 P5 阶段题组规划的统一入口：

- `full_exam` 默认规划 Part 1、Part 2、Part 3，当前 MVP 题量为 4/1/2，Part 1 已覆盖多个日常话题。
- `part_practice` 只规划请求中的目标 Part；`topic_practice` 在未指定 Part 时规划 Part 1 -> Part 2 -> Part 3。
- 优先通过 `question-bank-mcp` 检索 active season 题库；没有接入题库工具或检索不足时，使用内置 fallback catalog 保证工作流可运行。
- 输出 `QuestionSetPlan`，包含 `target_parts`、每个 Part 的题目、timer policy、Part 2 cue card、Part 3 讨论关联 metadata、题目来源 evidence 和 fallback rationale。
- 会按 `question_id` 和题面 token 相似度去重，避免同一题或高度相似题进入同一题组。
- Part 3 会继承 Part 2 的首题上下文，题目 metadata 会写入 `linked_part2_question_id`、`linked_part2_topic`、`discussion_level` 和 `discussion_focus`，便于前端、Trace 和后续 ScoringWorkflow 判断讨论是否自然升级。

`ExamWorkflow` 与 `PracticeWorkflow` 已消费 `question_plan` 状态推进题目；旧状态仍会回退到 `PART_CONFIG`，保证已有 API 调用和前端状态恢复兼容。

## ExaminerAgent

`app.agents.examiner_agent.ExaminerAgent` 是考官话术风格控制边界：

- `full_exam` 输出克制、简短的 IELTS 考官风格问题，不携带练习提示或内部评分说明。
- Part 2 首题会生成真实考试式 cue-card 引导语，提醒用户按一到两分钟 long turn 作答。
- `part_practice` / `topic_practice` 允许更明确的练习引导，但训练建议仍通过 `practice_hints` 独立字段传递，避免把提示混进考试模式。
- 话术输出会过滤 `system prompt`、`rubric`、`scoring rule` 等内部术语，后续 GuardrailAgent 接入前先保住基础边界。

`ExamWorkflow` 与 `PracticeWorkflow` 已统一通过 `ExaminerAgent` 生成 `examiner.message.payload.text`，并保留 `style_tags` 方便前端或 Trace 观察话术来源。

## FollowupPlannerAgent

`app.agents.followup_planner_agent.FollowupPlannerAgent` 是用户回答后的追问决策边界：

- `/agent/sessions/{session_id}/consume-asr` 支持可选 `session_state`，用于判断当前模式、Part、题目序号和已追问次数；不传时仍按旧请求兼容。
- 短回答会返回 `agent.followup_planned`，并直接追加一个 `examiner.message` 追问事件，`next_action=wait_for_user_answer`。
- 回答包含邮箱、手机号、地址、薪资、证件、密码、工作地点等敏感线索时，不追问私人细节，直接进入下一题。
- 每个题目默认最多追问一次，避免同一题过度追问。
- Part 3 追问更抽象，Part 1 追问更自然，Part 2 追问聚焦补充具体细节。

练习模式下追问事件会保留 `practice_mode`、`practice_hints` 和 `topic_ids`，考试模式不会混入练习提示。

## ModePolicy

`app.workflows.mode_policy` 是考试/练习差异控制边界：

- `full_exam` 使用 `prompt_profile=examiner_exam`、`ui_profile=exam`，禁用 `practice_hints`、结构建议、参考答案、topic guidance 和中文策略提示。
- `part_practice` / `topic_practice` 使用 `prompt_profile=coach_practice`、`ui_profile=practice`，允许结构建议、参考答案和诊断式评分；`topic_practice` 额外允许 topic guidance。
- `mode_policy` 会写入 workflow state，并随 `session.started`、`part.started`、`examiner.message`、`timer.started`、`session.completed`、`scoring.started` 等关键事件透出，供前端 UI 和后续 Prompt/Scoring/Feedback 节点统一判断。
- 回归测试会阻止 `full_exam` payload 出现练习提示、练习模式字段或中文策略提示。

## ExamWorkflow Part 1

`ExamWorkflow` 当前已实现 Part 1 多题流程：

- Part 1 默认规划 4 道题，覆盖 hometown、work/study、daily routine、free time 等日常话题。
- `part.started`、`timer.started` 和 `examiner.message` payload 会携带 Part 1 的 `timebox_seconds=300` 或 `part_timebox_seconds=300`。
- 每题默认建议 30 秒；前端可按 `part_elapsed_seconds` 回传当前 Part 已用时间。
- 当 `part_elapsed_seconds >= timebox_seconds` 或 Part 1 题目全部问完时，`next-turn` 会输出 `part.completed` 并自动进入 Part 2。
- 进入下一题或下一 Part 时会重置当前题追问计数，避免上一题的追问状态污染后续题目。

## ExamWorkflow Part 2

`ExamWorkflow` 当前已实现 Part 2 cue card 与计时语义：

- Part 2 题目会在 `examiner.message.payload.cue_card` 返回 prompt、bullet points、`preparation_seconds=60` 和 `speaking_seconds=120`。
- `part.started` 会返回 `preparation_seconds`、`speaking_seconds` 和 `warning_seconds=[60,30,10]`，方便前端初始化长轮次 UI。
- `timer.started` 会标记 `phase=prepare_then_speak`，同时携带准备时间、回答时间、Part 时间盒和提醒节点。
- `part_practice`、`topic_practice` 和 `full_exam` 进入 Part 2 时使用同一套 payload 字段，避免前端按模式分叉处理。

## ExamWorkflow Part 3

`ExamWorkflow` 当前已实现 Part 3 抽象讨论语义：

- Part 3 题目会从 Part 2 cue card 的主题继续展开，例如由个人地点经历上升到公共空间、城市生活和社会层面的讨论。
- `part.started` 与 `examiner.message` 会携带 `linked_part2_question_id`、`linked_part2_topic`、`discussion_level` 和 `discussion_focus`，帮助前端和 Trace 识别 Part 3 与 Part 2 的关联。
- Part 3 每题默认建议 45 秒，Part 时间盒为 300 秒，题面保持简短口语化，避免生成写作式长问题。
- `part_practice` 直接练 Part 3、`topic_practice` 从 Part 2 进入 Part 3、`full_exam` 从 Part 2 进入 Part 3 均使用同一套讨论 metadata。

## Full Exam Mode

`full_exam` 当前可完整串联 Part 1 -> Part 2 -> Part 3：

- `plan` 初始化 `state.status=in_progress`，并写入完整 `question_plan`、`target_parts`、`current_part`、`question_index`、`completed_parts` 和 `answers`。
- `/consume-asr` 会把当前回答追加进 `state.answers`，记录 turn、Part、question、ASR 文本、音频资产、ASR 置信度和追问决策，调用方可把返回的 state 持久化用于断线恢复或后续评分。
- `/next-turn` 会按题目数量或 Part 时间盒推进，Part 1 完成后进入 Part 2，Part 2 完成后进入 Part 3，Part 3 完成后进入评分阶段。
- 完整考试结束时会输出 `part.completed`、`session.completed` 和 `scoring.started`，并把 `state.status` 设置为 `scoring`，`next_action=score_session`。

## PracticeWorkflow

`PracticeWorkflow` 当前支持两类 MVP 练习流程：

- `part_practice`：按 `part` 只练 Part 1、Part 2 或 Part 3，完成目标 Part 后进入 `score_session`。
- `topic_practice`：带 `topic_ids` 进入 topic 练习；如果 `topic_ids` 是题库 UUID，会通过 `topic_id` 过滤题库；`topic_labels` 用于自然语言检索提示。如果请求带 `part`，只练目标 Part；如果不带 `part`，按 Part 1 -> Part 2 -> Part 3 推进。

练习模式会在 `part.started`、`examiner.message` 和 `timer.started` 事件中标记 `practice_mode=true`。其中 `examiner.message.payload.practice_hints` 可供前端展示训练提示；`full_exam` 不包含该字段。

`part_practice` 当前具备完整单项练习状态语义：

- `plan` 会根据请求的 `part` 设置 `target_parts=[part]`、`current_part=part` 和 `state.status=in_progress`。
- Part 1/2/3 都会输出对应练习提示；Part 2 会输出 cue card、准备时间、回答时间和提醒节点；Part 3 会输出抽象讨论 metadata。
- `/consume-asr` 会把当前回答追加进 `state.answers`，记录 turn、Part、question、ASR 文本、音频资产、ASR 置信度和追问决策。
- 目标 Part 完成后会输出 `part.completed`、`session.completed` 和 `scoring.started`，并把 `state.status` 设置为 `scoring`，`next_action=score_session`。

`topic_practice` 当前具备主题练习上下文：

- `plan` 会保留 `topic_ids`/`topic_labels`，并生成 `state.topic_guidance`，包含 `primary_topic`、`topic_label`、主题词汇、可用表达和后续反馈关注点；`session_seed` 会让同一会话题目可复现、不同会话在同一题库内稳定换题。
- fallback 题组会把 `selected topic` 占位文案渲染成具体主题，例如 `technology`、`travel`、`hometown`，题目 metadata 也会保留对应 topic。
- `session.started`、`part.started`、`examiner.message`、`state.answers`、`session.completed` 和 `scoring.started` 都会携带 `topic_guidance`，后续 FeedbackWorkflow 可直接生成主题词汇与表达建议。
- 请求带 `part` 时只练目标 Part；不带 `part` 时按 Part 1 -> Part 2 -> Part 3 推进。

## AG-UI 事件适配器

`app.protocols.ag_ui_events.build_event` 是工作流输出到前端事件协议的统一入口：

- 事件类型与 `packages/protocol/schemas/session-event.schema.json` 的枚举保持一致。
- `examiner.message`、`timer.started`、`part.started`、`scoring.started` 等关键事件会做 payload 校验。
- 返回值是 `SessionEvent`，Go Backend 可直接按共享 schema 转发给 WebSocket 客户端。

## Trace 与 Langfuse

Agent API 会为每次 `/plan`、`/consume-asr`、`/next-turn`、`/score` 调用记录一条 Agent Run Trace：

- `GET /agent/runs/{run_id}` 返回 run 状态。
- `GET /agent/runs/{run_id}/trace` 返回符合共享 Agent Run schema 的 trace。
- `GET /agent/observability/summary` 可按 `session_id`、`run_id`、`mode` 查询聚合延迟、错误率、节点耗时、工具成功率和最近 run。
- `GET /agent/observability/alerts` 基于错误率、p95 延迟和工具成功率生成发布前告警。
- `GET /metrics` 输出 Prometheus 风格指标，便于接入 Grafana、Prometheus 或等效监控方案。
- trace 包含 `session_id`、`run_id`、`user_id_hash`、`mode`、`part`、`question_id`、工作流节点、prompt version、模型名、tokens 估算、retrieved chunks、结构化输出合法性、评分摘要、tool calls、节点耗时和输入/输出摘要。
- 输入摘要会脱敏，不保存完整 ASR 文本、密钥、Bearer token 或邮箱。

本地默认 `LANGFUSE_ENABLED=false`，trace 只保存在 Agent Harness 内存中。配置 `LANGFUSE_ENABLED=true`、`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY` 后，会尝试导出到 `LANGFUSE_HOST/api/public/ingestion`。

Phase 9 质量闸门见 `docs/phase9_quality_gate.md`，本地确定性套件覆盖 DeepEval 回归、Ragas RAG 评估、Promptfoo 红队、E2E、性能基线和错误恢复策略。

## Calibration API

Agent Harness 直接提供评分校准与质量门禁 API，供后台或 Go BFF 调用：

- `GET /agent/calibration/anchor-samples` 返回默认 anchor samples、coverage/compliance audit 和可用于 `ScoreCalibrator` 的 anchor 数量。
- `POST /agent/calibration/score` 接收四维 `CriterionScoreInput` 与 anchor samples，返回校准前后 band、confidence、anchor mean、偏差、action 和 reason。
- `POST /agent/calibration/speech-regression` 接收真实 `SpeechCalibrationSample` JSON 或显式 contract samples，输出授权/覆盖审计、MAE、max error 和 release gate。合成 contract samples 只用于 CI 或本地门禁，不能替代生产校准集。
- `POST /agent/calibration/multipa-experiment` 在固定 benchmark 上比较 GOPT baseline 与 MultiPA adapter output，输出 MAE、p95 latency、成本和部署复杂度。
- `POST /agent/calibration/quality-gate` 聚合 anchor audit、DeepEval-like 回归、Ragas-like RAG、Promptfoo-like 红队、性能基线、speech calibration contract 和 MultiPA contract，返回 `passed` / `needs_review` / `blocked`。

## 结构化输出校验

`app.models.structured_output` 提供模型输出的统一校验入口：

- `response_format_for_model()` 根据 Pydantic model 生成 JSON Schema response format。
- `parse_structured_output()` 从纯 JSON 或 Markdown JSON fence 中提取并校验输出。
- `ModelRouter.complete_structured()` 会调用模型、校验 Pydantic schema，校验失败时追加修复指令并重试。
- 重试后仍不合法会抛出 `RecoverableStructuredOutputError`，可用 `build_recoverable_error_event()` 转成 `error.recoverable` 事件。
- 如果结构化错误穿过 Agent API，Trace 会记录 `error_code=structured_output_invalid`。

关键 Agent 输出 schema 已在 `app.models.output_schemas` 中定义，当前覆盖 examiner message、follow-up decision、criterion score 和 feedback plan。

## Knowledge Service

`app.rag.llamaindex_service.LlamaIndexKnowledgeService` 是 Agent Harness 的统一 RAG 入口：

- `ingest_documents()` 支持写入 question bank、rubric、user profile、topic knowledge、review history 文档。
- `retrieve()` 支持 Top K 检索和 metadata filter。
- 写入时会按 `docs/knowledge_chunk_spec.md` 校验关键 metadata，确保题库、Rubric、用户背景等 chunk 可解释、可过滤。
- 默认 `KNOWLEDGE_STORE_BACKEND=memory`，使用确定性 hash embedding，便于本地测试。
- 配置 `KNOWLEDGE_STORE_BACKEND=pgvector` 后会连接 PostgreSQL/pgvector，并使用 `knowledge_docs`、`knowledge_chunks` 表。
- `/healthz` 会返回 `knowledge_service` 摘要，包括 backend、embedding model、embedding dimension 和 chunk 配置。

当前实现提供 LlamaIndex 风格服务边界和 pgvector 适配，后续可在该接口后替换为真实 LlamaIndex index / retriever。

## Question Bank Indexer

`app.rag.ingestion.question_bank_indexer.QuestionBankIndexer` 负责把 Go 题库记录同步到 `question_bank_index`：

- 一道题稳定映射为一个 `KnowledgeDocument`，`doc_id/source_id/question_id` 使用 `questions.id`，新增或更新同一题会重建旧 chunk。
- 只索引 `review_status=active` 的题目；传入 `active_season_id` 后会只同步当前 active season。
- Part 2 会把 cue card prompt、bullet points 和 active follow-up questions 合进检索文本。
- `search_questions()` 默认追加 `doc_type=question_bank` filter，并支持按 `active_season_id`、`part`、`topic` 检索；结果 metadata 会返回 `question_id`。
- `PostgresQuestionBankSource` 可从现有 PostgreSQL 题库表读取 active 题目，后续接入后台索引任务或 worker 时复用该边界。

## Rubric Indexer

`app.rag.ingestion.rubric_indexer.RubricIndexer` 负责把 IELTS 四维评分标准、内部评分策略和 anchor samples 同步到 `rubric_index`：

- 每条 rubric 记录稳定映射为一个 UUID 格式 `KnowledgeDocument.doc_id`，原始 `rubric_id` 保留在 metadata 中，适配 pgvector 的 uuid 主键。
- 支持 `official_descriptor`、`internal_policy`、`anchor_example` 三类 `policy_type`。
- `search_rubric()` 默认追加 `doc_type=rubric` filter，并支持按 `criterion`、band 范围、`policy_type`、`anchor_sample_id` 检索。
- band 范围会展开为 0.5 递增的离散 metadata filter，例如 `min_band=6,max_band=7` 会检索 `6/6.5/7`。
- anchor sample 会保留 `anchor_sample_id`、answer excerpt、score rationale 和 evidence，供后续 ScoringWorkflow 引用评分样本。

## User Profile Indexer

`app.rag.ingestion.user_profile_indexer.UserProfileIndexer` 负责把背景问卷事实同步到 `user_profile_index`：

- 默认跳过 `is_excluded=true` 和 `privacy_level=private` 的 facts，避免用户禁用字段进入 Agent 可用上下文。
- `sync_from_source()` 默认按用户执行 replace：先删除该用户旧 `user_profile` chunks，再写入当前可用 facts，保证问卷更新后索引不会残留旧事实。
- `search_user_facts()` 必须传入 `user_id`，默认追加 `doc_type=user_profile`、`owner_user_id` 和 `privacy_level in normal/sensitive` filter。
- 支持按 `topic` 与 `allowed_usage` 检索，例如只取 `question_personalization` 或 `scoring_context`。
- `PostgresUserProfileSource` 读取最新 `background_questionnaires` 下的 `background_facts`，后续 profile-mcp 可复用该边界。

## MCP Security Middleware

`app.mcp.security` 是所有 MCP 工具的统一权限与工具调用审计边界：

- 工具调用必须携带 `McpToolContext(user_id, session_id)`，`user_id/session_id` 由可信服务端注入，Agent 不自行声明。
- `authorize_tool_call()` 会统一校验 required scope、`allowed_tools` allowlist、`disabled_tools` 禁用清单和高风险工具开关。
- `disable_high_risk_tools=true` 时默认禁用 `save_score_report`、`save_feedback`、`save_reference_answer` 等写入类高风险工具；即使调用方显式传入 `high_risk_tools=None`，也会回退到默认高风险清单。
- 每次允许或拒绝的工具调用都会写入 `McpAuditSink`，记录 `user_id_hash`、`session_id`、`tool_name`、`request_id`、授权状态、拒绝原因、required scopes 与 granted scopes。
- 默认审计 sink 是进程内 `InMemoryMcpAuditSink`，便于本地测试；后续接入 Langfuse 或数据库审计表时可替换为持久化 sink。

## Question Bank MCP

`app.mcp.question_bank_mcp.QuestionBankMcpTools` 是题库 MCP 的业务工具边界：

- `search_questions()` 复用 `QuestionBankIndexer.search_questions()`，按 active season、Part、topic 检索题库，并返回 source doc/chunk。
- `get_cue_card()` 基于题库 chunk 的结构化 cue card metadata 返回 Part 2 cue card。
- `get_followup_templates()` 返回 active follow-up templates，可按 Part 过滤。
- 工具调用必须携带 `McpToolContext(user_id, session_id)`，并具备 `question_bank:read` scope；`allowed_tools` 可限制本次 Agent run 能调用的工具集合。

## Profile MCP

`app.mcp.profile_mcp.ProfileMcpTools` 是用户背景 MCP 的业务工具边界：

- `get_user_background_summary()` 只使用 `McpToolContext.user_id` 检索当前用户可用背景事实，不接受外部传入 user_id。
- 默认不返回 `privacy_level=private` 的 facts，并可按 `topic` 与 `allowed_usage` 过滤。
- `get_privacy_exclusions()` 通过 `ProfilePrivacySource` 读取最新背景问卷的隐私排除字段；PostgreSQL 实现为 `PostgresProfilePrivacySource`。
- 工具调用必须携带 `profile:read` scope；`allowed_tools` 可限制本次 Agent run 能调用的工具集合。

## Rubric MCP

`app.mcp.rubric_mcp.RubricMcpTools` 是评分标准 MCP 的业务工具边界：

- `retrieve_speaking_band_descriptor()` 按 `criterion`、band 范围、band 列表与 `policy_type` 检索 official descriptor / internal policy。
- `get_anchor_samples()` 默认只返回 `policy_type=anchor_example` 的 anchor samples，可按 `criterion`、band 或 `anchor_sample_id` 过滤。
- 工具结果保留 `source_ref.doc_id`、`source_ref.chunk_id` 和 `source_ref.source`，方便 ScoringWorkflow 写入评分证据和 Trace。
- 工具调用必须携带 `rubric:read` scope；`allowed_tools` 可限制本次 Agent run 能调用的工具集合。

## Speech Metrics MCP

`app.mcp.speech_metrics_mcp.SpeechMetricsMcpTools` 是语音指标 MCP 的业务工具边界：

- `compute_wpm()` 可基于 `duration_ms + words_count` 或 `duration_ms + transcript` 计算 WPM，并返回 confidence。
- `detect_long_pauses()` 根据 pause segments 和阈值返回 long pause 数量、总停顿时长、平均长停顿与 confidence。
- `estimate_filler_ratio()` 基于 transcript 估算 filler count / filler ratio。
- `get_asr_confidence()` 将 ASR confidence 规范化为工具输出。
- `get_turn_audio_metrics()` 通过 `SpeechMetricsSource` 读取已持久化的 turn 级音频指标；PostgreSQL 实现为 `PostgresSpeechMetricsSource`，查询时使用 `McpToolContext.user_id/session_id` 做归属约束。
- 工具调用必须携带 `speech_metrics:read` scope；`allowed_tools` 可限制本次 Agent run 能调用的工具集合。

## Report MCP

`app.mcp.report_mcp.ReportMcpTools` 是报告写入 MCP 的业务工具边界：

- `save_score_report()` 保存评分报告主表、四维 `criterion_scores` 和 `study_plans`，要求报告 `session_id` 与 `McpToolContext.session_id` 一致。
- `save_feedback()` 保存 `feedback_items`，用于反馈和改进建议。
- `save_reference_answer()` 保存 `reference_answers`，用于复盘页参考答案。
- 写入工具必须携带 `report:write` scope；`allowed_tools` 可限制本次 Agent run 能调用的工具集合。
- 每次成功写入都会通过 `ReportAuditSink` 记录 `user_id`、`session_id`、`tool_name`、`request_id` 和 target id；PostgreSQL 实现为 `PostgresReportStore`。

## MiMoChatClient

`MiMoChatClient` 支持 OpenAI-compatible 与 Anthropic-compatible 两种 API 格式，统一返回文本、tool calls、usage 和错误分类：

```python
from app.core.config import get_settings
from app.models.mimo_client import ChatMessage, MiMoChatClient, MiMoClientConfig

settings = get_settings()
config = MiMoClientConfig.from_settings(settings)

async with MiMoChatClient(config) as client:
    response = await client.complete(
        [ChatMessage(role="user", content="Plan one IELTS Speaking Part 1 question.")],
        tools=[{"type": "function", "function": {"name": "search_questions", "parameters": {"type": "object"}}}],
        response_format={"type": "json_object"},
    )
```

关键环境变量：

- `MIMO_API_KEY`
- `MIMO_BASE_URL`
- `MIMO_DEFAULT_MODEL=mimo-v2.5-pro`
- `MIMO_API_FORMAT=openai`
- `MIMO_TIMEOUT_SECONDS=30`
- `MIMO_MAX_RETRIES=2`
- `MIMO_MODEL_ROUTES_JSON={}`

## ModelRouter

`ModelRouter` 在 `MiMoChatClient` 之上按任务选择模型和默认生成参数，工作流只需要传入任务类型：

```python
from app.core.config import get_settings
from app.models.model_router import ModelRouter

settings = get_settings()

async with ModelRouter.from_settings(settings) as router:
    response = await router.complete(
        "scoring",
        [{"role": "user", "content": "Score this IELTS Speaking answer."}],
        response_format={"type": "json_object"},
    )
```

内置任务类型包括：

- `question_planning`
- `examiner`
- `followup_planning`
- `scoring`
- `feedback`
- `cheap`
- `default`

`MIMO_MODEL_ROUTES_JSON` 可覆盖模型、fallback 模型、`temperature` 和 `max_tokens`：

```json
{
  "scoring": {
    "model": "mimo-v2.5-pro",
    "fallback_model": "mimo-v2.5",
    "temperature": 0.0,
    "max_tokens": 1800
  },
  "cheap": {
    "model": "mimo-v2.5",
    "temperature": 0.2,
    "max_tokens": 512
  }
}
```

fallback 只会在 `MiMoChatClient` 标记为可重试的错误上触发，例如 5xx、429、网络错误或超时；401/403 等鉴权错误会直接抛出，便于尽早发现配置问题。
