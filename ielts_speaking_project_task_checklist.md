# 雅思口语练习网站：详细任务清单与目标效果文档

> 文档版本：v1.0  
> 用途：项目排期、研发分工、进度控制、阶段验收、风险跟踪  
> 建议使用方式：将本清单导入 Jira、Linear、飞书项目、Notion 或 GitHub Projects；每个任务可拆为 Story / Task / Subtask。

---

## 0. 当前进度快照

> 更新时间：2026-06-08  
> 本次执行：已从空仓库建立 monorepo 工程基线，包含 `apps/web`、`services/api-go`、`services/agent-harness`、`services/speech-assessment`、`packages/protocol`、`infra`、`docs`；已补充 Docker Compose、环境变量示例、协作规范、MVP 范围、架构 ADR、共享协议 schema、Go API 健康检查、Agent Harness 最小工作流、Web Live 控制台骨架；已完成 Go API 鉴权、背景问卷 API、WebSocket Gateway、音频资产服务、ASR 结果持久化、TTS 调用与对象存储保存、TTS 缓存、语音指标提取 MVP、音频回放组件、Speech Assessment Service 语音 evidence 骨架、ASR word timestamp/faster-whisper adapter、VAD/Fluency/GOPT evidence、评分报告 Schema、FluencyCoherenceScorer、LexicalResourceScorer、GrammarScorer、PronunciationScorer、ScoreReviewerAgent、ScoreCalibrator、ScoringWorkflow、FeedbackCoachAgent、Agent Harness MiMoChatClient、ModelRouter、PracticeWorkflow、AG-UI 事件适配器、Langfuse Trace 初版、结构化输出校验、LlamaIndex Knowledge Service、Knowledge Chunk Spec、题库索引任务、Rubric 索引任务、用户背景索引任务、question-bank-mcp、profile-mcp、rubric-mcp、speech-metrics-mcp、report-mcp、MCP security middleware、QuestionSetPlannerAgent、ExaminerAgent、FollowupPlannerAgent、Part 1 Workflow、Part 2 Workflow、Part 3 Workflow、full_exam 模式、part_practice 模式、topic_practice 模式、ModePolicy 模式差异控制、ASR Service、TTS Service、Go 报告持久化/查询/历史列表 API、复盘报告页完整展示、历史报告列表页、后台权限模型、admin audit logs、题库管理页面、知识库管理页面、Prompt 版本后台、内容审核流程和 `/agent/sessions/{session_id}/score` 评分端点，并通过真实数据库/API/WebSocket/MinIO 链路、Agent Harness 容器健康检查、Speech Assessment 容器 smoke、临时 pgvector ingest/retrieve smoke、RAG metadata 校验测试、题库 active season pgvector smoke、Rubric band range/anchor pgvector smoke、用户背景隐私过滤/更新重建 pgvector smoke、报告页/历史页/Phase 8 管理后台浏览器验证。

| 模块 | 当前状态 | 说明 |
|---|---|---|
| Phase 0 工程底座 | DONE | Docker Compose 基线、环境变量示例、monorepo 与协议基线均已落地，并已通过 compose config/build/up/health 多轮验收 |
| Go API | DONE | Gin 服务骨架、配置加载、健康检查、核心 Phase 1 API、WebSocket Gateway、报告持久化/查询/历史列表 API、后台 RBAC、admin audit logs、知识库/Prompt/内容审核后台 API 已完成 |
| Auth API | DONE | 注册、登录、刷新 token、`/api/me`、Bearer 鉴权中间件、WebSocket 鉴权已完成 |
| 背景问卷 API | DONE | `GET /api/me/background`、`PUT /api/me/background` 已完成，支持 profile、answers、自由补充、privacy exclusions、facts 与 `agent_facts` 安全视图 |
| 题库 API | DONE | season、topic、question CRUD 已完成，公开查询只返回 active 内容，后台路由需要 operator/admin |
| 会话 API | DONE | full_exam、part_practice、topic_practice、状态流转、turn、ASR、audio metadata、ASR 结果持久化与人工修正、speech metrics 已完成 |
| WebSocket Gateway | DONE | `/api/ws/sessions/:id` 已完成，支持 access token 鉴权、session 归属校验、按 `session_id` 广播和断线重连基础策略 |
| 音频资产服务 | DONE | `POST /api/audio/upload`、`POST /api/audio/tts`、`DELETE /api/audio/tts/cache/expired`、`GET /api/audio/:id/signed-url` 已完成，支持 MinIO/S3 上传、`audio_assets` 持久化、TTS 考官音频保存、TTS 缓存、签名 URL 回放和类型/大小/时长限制 |
| Speech Assessment | DONE | 独立 FastAPI 语音 evidence 服务已完成，支持 `/healthz`、`/metrics`、`POST /speech/transcribe-timestamps`、`POST /speech/assess`、`POST /speech/pronunciation-drill`，输出 word timestamps、VAD/fluency metrics、GOPT-compatible pronunciation evidence、Pronunciation Drill word/phoneme feedback、audio_quality 和 confidence，并通过协议禁止 direct IELTS band 输出 |
| Agent Harness | DONE | FastAPI、AG-UI 事件适配器、ExamWorkflow、PracticeWorkflow、Agent API、MiMoChatClient、ModelRouter、Langfuse Trace 初版、结构化输出校验、LlamaIndex Knowledge Service、Knowledge Chunk Spec、题库索引任务、Rubric 索引任务、用户背景索引任务、question-bank-mcp、profile-mcp、rubric-mcp、speech-metrics-mcp、report-mcp、MCP security middleware、QuestionSetPlannerAgent、ExaminerAgent、FollowupPlannerAgent、FluencyCoherenceScorer、LexicalResourceScorer、GrammarScorer、PronunciationScorer、ScoreReviewerAgent、ScoreCalibrator、ScoringWorkflow、FeedbackCoachAgent、Part 1 Workflow、Part 2 Workflow、Part 3 Workflow、full_exam 模式、part_practice 模式、topic_practice 模式、ModePolicy 模式差异控制、ASR Service、TTS Service 和评分端点已完成；Microsoft Agent Framework core 适配边界已建立，深度图编排迁移作为后续增强 |
| Web | DONE | Next.js Live 控制台已重构为“优雅学术风格”，采用 Bento 布局、Recharts 图表与深色模式；已接入 WebSocket Gateway、录音、ASR/TTS、报告页音频回放、四维评分、evidence、建议、参考答案、训练计划展示、历史报告筛选与 overall band 趋势、题库/知识库/Prompt/审核运营后台 |
| 协议层 | DONE | JSON Schema 已建立，并已通过 Ajv 2020 编译校验；评分报告 schema 已强制包含 `version`、四维 criteria、evidence、suggestions、confidence 与免责声明 |
| 数据层 | DONE | PostgreSQL / pgvector 核心迁移已完成并通过真实数据库 up/down 验证；背景问卷、题库 CRUD、会话 API、音频上传与回放、报告持久化、查询与历史列表 API、admin_audit_logs、reference answer review_status、prompt version seed、隐私合规与 report feedback 迁移已完成 |

### 本次验证记录

- `docker compose config --quiet`：通过，Compose 配置可解析。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过；`scoring-report` 合法样例通过，缺少 `version` 的反例会失败。
- `go test ./...`：通过，Go API 配置、迁移、路由、ASR 结果持久化、人工修正、raw response 脱敏、TTS 对象存储保存、TTS 缓存、签名 URL 回放、语音指标自动推导、报告持久化/查询 handler 与 router 测试通过。
- `python -m pytest tests`：通过，Agent Harness API、AG-UI 事件适配器、PracticeWorkflow、MiMoChatClient、ModelRouter、Langfuse Trace、结构化输出校验、LlamaIndex Knowledge Service、Knowledge Chunk Spec、题库索引任务、Rubric 索引任务、用户背景索引任务、question-bank-mcp、profile-mcp、rubric-mcp、speech-metrics-mcp、report-mcp、MCP 权限与审计、QuestionSetPlannerAgent、ExaminerAgent、FollowupPlannerAgent、FluencyCoherenceScorer、LexicalResourceScorer、GrammarScorer、PronunciationScorer、ScoreReviewerAgent、ScoreCalibrator、ScoringWorkflow、FeedbackCoachAgent、Part 1 Workflow、Part 2 Workflow、Part 3 Workflow、full_exam 模式、part_practice 模式、topic_practice 模式、ModePolicy 模式差异控制、ASR Service、TTS Service、评分端点和模型供应商配置校验共 186 个测试通过。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建并包含新增 ASR Service、MCP 工具模块与 MCP security middleware。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`knowledge_service.backend=memory`、`model_provider.api_format=anthropic`、`available_models` 包含计划中的 9 个 MiMo 模型、`asr.model=mimo-v2.5-asr`；响应中未泄露 API key。
- `POST /agent/audio/transcribe` 容器 smoke：通过，`audio/webm` 返回 mock transcript、`language=en`、`confidence=0.87`、`provider=mock_asr`、`model=mimo-v2.5-asr`，验证后已停止本轮启动的 agent-harness 容器。
- `pnpm --filter @ielts-speaking/web lint`：通过。
- `pnpm --filter @ielts-speaking/web typecheck`：通过。
- `pnpm --filter @ielts-speaking/web build`：通过。
- `docker compose build --pull=false api-go agent-harness`：通过，Go API 与 Python Agent Harness 容器镜像可构建并包含报告持久化 API 与 FeedbackCoachAgent。
- `docker compose build --pull=false api-go`：路由通配符冲突修正后重新构建通过；`docker compose up -d postgres redis minio agent-harness api-go` 后 `api-go`、`agent-harness`、PostgreSQL、Redis、MinIO 均为 healthy，`http://127.0.0.1:18080/healthz` 返回 `status=ok`。
- 浏览器检查 `http://127.0.0.1:3000`：桌面与移动视口均无横向溢出，控制台无 error/warn。
- 浏览器自动化检查 `http://127.0.0.1:3000/report/session_visual_001`：使用 mock API 数据验证桌面 1440px 与移动 390px 视口均能渲染四维评分、evidence、反馈、训练计划、参考答案和回放入口；无横向溢出，控制台无 error/warn。
- `GET /api/reports`：新增 Bearer 鉴权历史报告列表 API，支持 `mode`、`part`、`from`、`to`、`limit`、`offset` 过滤，返回每个 session 的最新 report、overall band、confidence、criteria 摘要、session mode/part/status 与报告时间；未认证访问返回 401。
- 浏览器自动化检查 `http://127.0.0.1:3000/history`：使用真实 API 临时测试用户与两条 persisted reports 验证桌面与移动视口均能渲染历史列表、overall band 趋势、日期/模式/Part 筛选与 `Open review` 复盘入口；Part 2 过滤后只保留单条报告，点击后进入 `/report/<session-id>`；无横向溢出，控制台无 error/warn。
- 认证状态恢复修正：`auth-storage` 持久化 `isAuthenticated` 与 `user`，并增加 hydration gate，避免刷新或直接打开 `/practice`、`/history`、`/background` 时在 token 恢复前误跳转登录页。
- `GET /api/admin/question-bank/topics` 真实 RBAC smoke：普通 user Bearer token 返回 403，并写入 `admin_audit_logs` 的 `actor_role=user`、`resource=question_bank`、`method=GET`、`status_code=403` 记录。
- 浏览器自动化检查 `http://127.0.0.1:3000/admin/questions`：operator 登录后可渲染 `Question Admin`、Filters、Create Question、Batch Import、题目列表、Edit/Archive；完成创建题目、状态改为 `reviewing`、批量 JSON 导入、归档本轮测试题；桌面和移动视口均无横向溢出，本轮刷新后控制台无新增 error/warn。
- `admin_audit_logs` 真实库校验：本轮后台题库操作写入 `operator/question_bank` 的 GET 200、POST 201、PUT 200、DELETE 204 记录，以及普通 user 越权 GET 403 记录。
- `docker compose run --rm api-go migrate up`：通过，当前 PostgreSQL 已迁移到 version 5，包含 `000005_admin_audit_logs.sql`。
- `docker compose build --pull=false api-go`：通过，Go API 容器镜像可构建并包含后台权限审计与题库后台 API；`docker compose up -d api-go` 后 `api-go` healthy，`http://127.0.0.1:18080/healthz` 返回 `status=ok`。
- `docker compose run --rm api-go migrate up`：通过，当前 PostgreSQL 已迁移到 version 6，包含 `000006_admin_content_ops.sql`、`reference_answers.review_status` 与 Prompt 版本元信息 seed。
- Phase 8 后半真实 API smoke：operator 创建 `topic_knowledge` 文档返回 `chunk_count=1`，触发 reindex 成功；`GET /api/admin/prompts/versions?active=true` 返回 5 个 redacted prompt versions；`GET /api/admin/content-review/summary` 返回 question/knowledge/reference 状态聚合；reference answer 可从 draft 改 reviewing 并恢复 draft。
- 浏览器自动化检查 `http://127.0.0.1:3000/admin/knowledge`、`/admin/prompts`、`/admin/review`：operator 可查看知识库文档、触发 Reindex、查看 Prompt redacted 元信息、在 Review Board 更新 reference answer 状态；桌面与移动视口均无横向溢出，控制台无新增 error/warn。
- `admin_audit_logs` 真实库校验：knowledge_base、prompt_versions、content_review 均写入 GET/POST/PUT 操作审计，其中 knowledge create 为 201，reindex 为 200。
- `docker compose build --pull=false api-go`：通过，Go API 容器镜像可构建并包含报告历史列表 API；`docker compose up -d api-go` 后 `api-go` healthy，`http://127.0.0.1:18080/healthz` 返回 `status=ok`。
- `docker compose build --pull=false api-go`：通过，Go API 容器镜像可构建并包含 speech metrics MVP 迁移与字段推导逻辑。
- `docker compose run --rm api-go migrate up`：通过，该轮 PostgreSQL 已迁移到 version 4（后续 Phase 8 已升级到 version 5）。
- `POST /api/sessions/:id/turns/:turn_id/speech-metrics` 临时 API 容器 smoke：通过，未传 `duration_ms`、`transcript`、`words_count` 和 `wpm` 时，服务从当前 turn 的录音时长和最新 ASR 自动推导 `duration_ms=18000`、`words_count=11`、`wpm=36.67`，并记录 `long_pause_count=1`、`mean_pause_ms=1600`、`total_pause_ms=1600`、`filler_count=3`、`filler_ratio=0.2727`；验证后已删除临时 api-go 容器并停止本轮启动的 agent-harness，现有 `api-go`、`postgres`、`redis`、`minio` 保持运行。
- `ReplayAudioPanel` / `/report/[sessionId]` 前端回放构建验证：`pnpm --filter @ielts-speaking/web lint`、`typecheck`、`build` 均通过；报告页 dynamic route 已生成，组件支持按 turn 播放、进度拖动和签名 URL 刷新。
- 浏览器自动化检查 `http://127.0.0.1:3001/report/<session-id>`：桌面 1440px 与移动 390px 视口均能渲染 `Session Report` / `Session Replay`，无横向溢出；仅发现 `favicon.ico` 404，不影响回放功能。

### 2026-06-08 Phase 8 管理后台验证记录

- 已新增迁移 `000005_admin_audit_logs.sql`，创建 `admin_audit_logs` 表，记录 actor、role、action、resource、method、path、status_code、metadata 和 created_at。
- 已新增迁移 `000006_admin_content_ops.sql`，为 `reference_answers` 增加 `review_status`，并 seed 5 个只含 metadata/hash 的 Prompt 版本记录。
- 题库后台路由继续使用 `auth.RequireRoles("operator", "admin")`，并通过 `auditAdminAction("question_bank")` 对已认证的管理路由操作写入审计。
- 已新增 `apps/web/app/admin/questions/page.tsx`，operator/admin 可访问题库运营后台，普通用户前端显示 Access denied；`/practice` 仅对 operator/admin 显示 `Question Admin` 入口。
- 题库后台支持 season/topic/part/status 筛选，题目创建与编辑，Part 2 cue card 字段，draft/reviewing/active/archived 状态流转，Archive，以及批量 JSON 导入。
- 已新增 `services/api-go/internal/adminops`，提供知识库文档上传/列表/状态更新/reindex/archive、Prompt 版本列表、内容审核 summary 与 reference answer 状态流转 API。
- 已新增 `/admin/knowledge`、`/admin/prompts`、`/admin/review` 三个后台页面，并在 `/practice` 为 operator/admin 增加 Knowledge、Prompts、Review 入口。
- 知识库后台上传内容会写入 `knowledge_docs` 与 `knowledge_chunks`，生成 hash embedding、chunk_count、token_count 与 `index_status`；`active` 文档仍受现有 RAG `kd.status='active'` 检索边界约束。
- Prompt 后台只展示 agent、purpose、version、content_hash、active、summary、rollback 元信息和 `prompt_body_redacted=true`，不向前端暴露系统提示全文。
- 内容审核流程统一使用 draft/reviewing/active/archived；题目走 Question Admin，主题知识走 Knowledge Admin，reference answers 走 Review Board；所有后台操作写入 `admin_audit_logs`。
- `auth-storage` 的 `user` 扩展 role/status/created_at 后，后台页面可在 hydration 后稳定判断权限，避免刷新时误跳登录或误判普通用户。
- 统一测试通过：`go test ./...`、`python -m pytest tests`、`pnpm --filter @ielts-speaking/protocol validate`、`pnpm --filter @ielts-speaking/web lint`、`pnpm --filter @ielts-speaking/web typecheck`、`pnpm --filter @ielts-speaking/web build`、`docker compose config --quiet`、`docker compose build --pull=false api-go`、`docker compose run --rm api-go migrate up`、`docker compose up -d api-go` 与 `/healthz`。
- 浏览器真实链路通过：operator 在 `/admin/questions` 完成创建、状态流转、批量导入和归档；在 `/admin/knowledge` 查看文档并触发 Reindex；在 `/admin/prompts` 查看 redacted Prompt 版本；在 `/admin/review` 完成 reference answer 状态流转；普通 user 调用后台接口返回 403；审计表包含 operator 成功操作与 user 越权操作记录。

### 2026-06-08 Phase 4 前端重构记录

- 引入 `ui-ux-pro-max` 推荐的“优雅学术风格” (Elegant Academic Style)。
- 更新 `tailwind.config.ts` 与 `layout.tsx`，加入 Playfair Display 等学术感衬线字体，以及 academic 专属色板 (Gold, Navy, Slate, Teal)。
- 重构 `page.tsx` 为三栏 Bento grid 布局，包含 Timeline、主交互区与 Report 图表区。
- 集成 `recharts` 实现高颜值雷达图 (Radar Chart) 展示 4 维评分。
- 完成纯视觉高保真重构，即时响应产品设计的高质量要求，为接入真实 WebSocket 数据打好前端样式底座。
- 完全接入 Phase 4 规定的 WebSocket Gateway (`useSessionSocket`)、录音模块 (`useAudioRecorder`)、静音检测 VAD (`useVAD`)、以及 TTS 音频播放 (`AudioPlayer`)、计时器 (`Timer`)。
- 实现了前端状态机：监听 `lastEvent` 驱动考官话术显示、Avatar 动画切换、计时器倒数、录音控制以及分数报告接收。

### 2026-06-08 评分体系优化规划同步记录

- 已将附件中的开源语音评测讨论纳入 `ielts_speaking_agent_harness_plan.md` 的语音链路与评分系统后续优化。
- 明确后续采用独立 `speech-assessment-service` 作为证据提取层，不让开源模型直接输出 IELTS 官方分或最终 Pronunciation Band。
- 后续任务清单已加入 WhisperX / faster-whisper 时间戳、VAD + Fluency Metrics、GOPT pronunciation evidence、MFA / Kaldi GOP Pronunciation Drill、SpeechOcean762 + 自有人工样本校准、MultiPA 实验分支等优化项。

### 2026-06-08 ASR Service 验证记录

- 已新增 `app.audio.asr_service.AsrService`，统一处理 `mimo-v2.5-asr` 转写边界。
- 已新增 `POST /agent/audio/transcribe`，请求包含 `audio_asset_id`、`mime_type`、可选 `duration_ms`、`language_hint`、`audio_url` 或 `audio_base64`。
- 支持 `audio/wav`、`audio/x-wav`、`audio/mpeg`、`audio/mp3`、`audio/webm`，并兼容 `audio/webm;codecs=opus` 这类浏览器 MIME。
- `MOCK_MODEL_ENABLED=true` 时返回确定性 mock transcript、language、confidence、provider、model、duration_ms 和 metadata，不调用真实 MiMo、不消耗额度。
- `MOCK_MODEL_ENABLED=false` 时预留 MiMo ASR HTTP provider，要求提供 `audio_url` 或 `audio_base64`；真实音频资产拉取和 ASR 结果持久化继续由 P6-002 衔接。
- 不支持音频格式返回 415，真实模式缺少音频源返回 422，上游可重试错误返回 503。
- `/healthz` 已增加 ASR 非敏感摘要，只暴露模型、mock 状态与支持格式，不泄露 API key。
- `python -m pytest tests`：通过，Agent Harness 156 个测试通过，新增 ASR Service 9 个测试与 Agent API 3 个测试，覆盖 mock 转写、格式兼容、错误边界、真实 provider 注入、供应商 payload 构造和响应解析。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false agent-harness`：通过，容器镜像可构建并包含新增 `app.audio` 模块。
- 容器 smoke：短暂启动 agent-harness 后，`/healthz` 与 `POST /agent/audio/transcribe` 均通过；验证后仅停止本轮启动的 agent-harness，`api-go`、`postgres`、`redis`、`minio` 保持运行。

### 2026-06-08 ASR 结果持久化验证记录

- 已新增迁移 `000002_asr_result_corrections.sql`，为 `asr_results` 补充 `corrected_transcript`、`corrected_by_user_id`、`corrected_at` 和 `raw_response_redacted`。
- `POST /api/sessions/:id/turns/:turn_id/asr-results` 已支持保存脱敏后的供应商原始响应摘要；`raw_response` 入库前会递归脱敏 API key、token、authorization、base64 音频和 audio data 等敏感字段。
- 保存 ASR 结果时会校验 `audio_asset_id` 必须属于当前 turn，避免跨会话或跨用户误关联。
- 已新增 `PATCH /api/sessions/:id/turns/:turn_id/asr-results/:asr_result_id/correction`，支持人工修正 transcript，并记录修正用户与修正时间；用户 turn 的 `answer_text` 会同步更新为修正文案。
- `GetSession` 加载 turn 详情时会返回 ASR 原始转写、人工修正字段、segments 和 `raw_response_redacted`，供后续评分、报告与复盘复用同一份记录。
- `go test ./...`：通过，覆盖 handler、migration embed、ASR raw response 脱敏与人工修正接口。
- `docker compose build --pull=false api-go`：通过，Go API 容器镜像可构建。
- `docker compose run --rm api-go migrate up`：通过，当前 PostgreSQL 已迁移到 version 2。
- 数据库列校验：`asr_results` 当前包含 `corrected_transcript`、`corrected_by_user_id`、`corrected_at`、`raw_response_redacted`。
- `pnpm --filter @ielts-speaking/protocol validate` 与 `docker compose config --quiet`：通过。

### 2026-06-08 TTS Service 验证记录

- 已新增 `app.audio.tts_service.TTSService` 与 `POST /agent/audio/synthesize`，统一处理 `mimo-v2.5-tts` 考官语音合成边界。
- Agent Harness TTS 请求支持 `voice_id`、`speaking_rate`、`emotion` 和 `style`；`MOCK_MODEL_ENABLED=true` 时生成确定性 wav 音频，不调用真实 MiMo、不消耗额度。
- 已新增 Go Audio API `POST /api/audio/tts`，调用 Agent Harness TTS，解码 `audio_base64`，并以 `examiner_tts` 类型保存到 MinIO/S3，返回 `audio_asset` 与 TTS provider/model/voice 元信息。
- 已新增 `AgentHarnessTTSClient`，运行时从 `AGENT_HARNESS_URL` 调用 `/agent/audio/synthesize`。
- `python -m pytest tests`：通过，Agent Harness 161 个测试通过，新增 TTS Service 4 个测试与 Agent API 1 个测试，覆盖 mock wav、模型可用性、真实 provider 注入和供应商响应解析。
- `go test ./...`：通过，新增 Go Audio TTS service/handler 测试，覆盖 voice 参数透传、TTS base64 解码和对象存储写入。
- `pnpm --filter @ielts-speaking/protocol validate`、`docker compose config --quiet`、`docker compose build --pull=false agent-harness`、`docker compose build --pull=false api-go`：通过。
- 真实链路 smoke：短暂启动 agent-harness 与临时 `api-go` 容器 `18081`，注册测试用户、创建 session/turn、调用 `POST /api/audio/tts`；返回 `asset_kind=examiner_tts`、`mime_type=audio/wav`、`provider=mock_tts`、`model=mimo-v2.5-tts`、`storage_key_present=true`。验证后已删除临时 api-go 容器并停止本轮启动的 agent-harness，现有 `api-go`、`postgres`、`redis`、`minio` 保持运行。

### 2026-06-08 TTS 缓存验证记录

- 已新增迁移 `000003_tts_cache.sql`，创建 `tts_cache` 表，包含 `cache_key`、`text_hash`、`voice_id`、`speaking_rate`、`emotion`、`style`、provider/model、音频 payload、metadata 和 `expires_at`。
- Go Audio Service 已按 `text + voice_id + speaking_rate + emotion + style` 生成稳定 cache key；命中缓存时复用缓存音频 payload，不再调用 Agent Harness TTS provider。
- 为避免跨用户/跨会话复用 `audio_asset` 权限，缓存命中后仍会为当前 turn 保存独立 `examiner_tts` 音频资产，但不会重复消耗 TTS 模型调用。
- `POST /api/audio/tts` 响应新增 `tts.cache_hit` 和 `tts.cache_key`，便于前端或观测系统判断缓存效果。
- 已新增 `DELETE /api/audio/tts/cache/expired`，支持后台或 worker 清理过期缓存记录。
- `go test ./...`：通过，新增 Audio Service / Handler 测试覆盖缓存 miss、缓存 hit 不重复调用 provider、每个 turn 独立保存音频资产，以及过期缓存清理接口。
- `pnpm --filter @ielts-speaking/protocol validate`、`docker compose config --quiet`、`docker compose build --pull=false api-go`：通过。
- `docker compose run --rm api-go migrate up`：通过，当前 PostgreSQL 已迁移到 version 3。
- 数据库列校验：`tts_cache` 当前包含 `cache_key`、`audio_base64`、`expires_at`、`style`、`voice_id`。
- 真实链路 smoke：短暂启动 agent-harness 与临时 `api-go` 容器 `18081`，两次提交相同 TTS 请求；第一次 `cache_hit=false`，第二次 `cache_hit=true`，两次 `cache_key` 相同，且两个 turn 均返回 `asset_kind=examiner_tts`。验证后已删除临时 api-go 容器并停止本轮启动的 agent-harness，现有 `api-go`、`postgres`、`redis`、`minio` 保持运行。

### 2026-06-08 语音指标提取 MVP 验证记录

- 已新增迁移 `000004_speech_metrics_mvp.sql`，为 `speech_metrics` 补充 `duration_ms`、`words_count`、`filler_count`、`mean_pause_ms`、`total_pause_ms`，并建立 `speech_metrics_turn_created_desc_idx` 便于读取最新 turn 指标。
- `POST /api/sessions/:id/turns/:turn_id/speech-metrics` 已支持从请求、当前 turn 的用户录音时长、最新 ASR / 人工修正文案自动推导 `duration_ms`、`words_count`、`wpm`、`filler_count` 和 `filler_ratio`。
- 请求传入 `pause_segments` 时会按 `long_pause_threshold_ms` 计算 `long_pause_count`、`mean_pause_ms` 和 `total_pause_ms`；`audio_asset_id` 会校验必须属于当前 turn，避免跨会话误关联。
- `speech-metrics-mcp` 已读取新增字段，`get_turn_audio_metrics()` 返回 turn 级 `duration_ms`、`words_count`、WPM、长停顿、填充词、ASR confidence 和 raw metrics，供后续 ScoringWorkflow 使用。
- `go test ./...`：通过，覆盖 handler 层 speech metrics 自动推导、ASR 脱敏和迁移嵌入。
- `python -m pytest tests`：通过，Agent Harness 161 个测试通过，`test_speech_metrics_mcp.py` 覆盖新增字段映射与 confidence 计算。
- `pnpm --filter @ielts-speaking/protocol validate`、`docker compose config --quiet`、`docker compose build --pull=false api-go`：通过。
- `docker compose run --rm api-go migrate up`：通过，当前 PostgreSQL 已迁移到 version 4。
- 真实 API smoke：短暂启动临时 `api-go` 容器 `18081`，注册测试用户、创建 session/turn、挂载带 `duration_ms=18000` 的用户录音、保存 ASR 后调用 speech metrics；请求未显式传 `duration_ms`、`transcript`、`words_count` 或 `wpm`，响应自动推导 `duration_ms=18000`、`words_count=11`、`wpm=36.67`，并返回 `long_pause_count=1`、`mean_pause_ms=1600`、`total_pause_ms=1600`、`filler_count=3`、`filler_ratio=0.2727`、`computed_mvp=true`。验证后已删除临时 api-go 容器并停止本轮启动的 agent-harness，现有 `api-go`、`postgres`、`redis`、`minio` 保持运行。

### 2026-06-08 音频回放能力验证记录

- 已新增 `apps/web/components/ReplayAudioPanel.tsx`，按 turn 聚合 `user_recording`、`examiner_tts` 和 `reference` 音频资产，提供播放/暂停、播放进度、进度拖动和当前音频状态。
- 已新增 `/report/[sessionId]` 页面，读取 `GET /api/sessions/:id` 的 turn/audio asset 数据并挂载回放组件，为后续评分报告页接入分数、证据和建议留出右侧摘要区域。
- `ReplayAudioPanel` 每次播放前会获取 `GET /api/audio/:id/signed-url?expires_seconds=300`；若缓存 URL 临近过期、用户点击刷新或播放失败，会重新拉取签名 URL，避免前端暴露或长期缓存对象地址。
- 已修正隐藏 `AudioPlayer` 对 Go API 响应字段的读取，兼容 `signed_url`；同时修正登录/注册 token 响应解析和 practice 创建 session 后读取 `session.id` 的前端链路问题。
- 已新增 Go audio handler 测试覆盖 signed URL 返回 `signed_url`、`audio_asset.duration_ms` 和 `expires_seconds=300` 透传。
- `go test ./...`：通过，包含新增 signed URL 回放 handler 测试。
- `pnpm --filter @ielts-speaking/web lint`、`pnpm --filter @ielts-speaking/web typecheck`、`pnpm --filter @ielts-speaking/web build`：通过，报告页 `/report/[sessionId]` 成功参与 Next.js 生产构建。
- 浏览器自动化验证：使用临时用户、session、turn 和 audio assets 访问 `http://127.0.0.1:3001/report/<session-id>`，桌面与移动视口均显示 `Session Report`、`Session Replay`、用户录音和考官音频条目，未发现横向溢出；console 仅有 `favicon.ico` 404。
- `pnpm --filter @ielts-speaking/protocol validate` 与 `docker compose config --quiet`：通过。

### 2026-06-08 评分报告 Schema 验证记录

- 已补齐 `packages/protocol/schemas/scoring-report.schema.json` 的必填 `version` 字段，与 `score_reports.version` 和 `ScoreReportInput.version` 保持一致，避免前端、Go Backend 与 Agent Harness 对报告版本字段命名分裂。
- `scoring-report.schema.json` 当前固定包含 `overall_band`、`confidence`、四维 `criteria`、每维 `band/confidence/evidence/suggestions`、`next_practice_plan`、`reviewer_notes` 和官方免责声明。
- `packages/protocol/scripts/validate-schemas.mjs` 已从单纯编译升级为 Ajv 2020 编译 + scoring-report 合法样例校验 + 缺少 `version` 反例校验。
- `ReportMCP` 的 `build_raw_report_payload()` 已把 `version` 与 `status` 写入 raw report 摘要，便于 Trace、报告复盘和后续 ScoringWorkflow 追踪报告版本。
- `python -m pytest tests/test_report_mcp.py`：通过，覆盖保存评分报告、四维 criteria、官方免责声明、版本号入库/摘要、审计与 SQL helper。
- `python -m pytest tests`：通过，Agent Harness 161 个测试通过。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，输出 `OK scoring-report examples`。
- `go test ./...`、`pnpm --filter @ielts-speaking/web typecheck`、`docker compose config --quiet`：通过。

### 2026-06-08 FluencyCoherenceScorer 验证记录

- 已新增 `services/agent-harness/app/agents/fluency_scorer_agent.py`，实现确定性 `FluencyCoherenceScorerAgent` baseline，输入包含 transcript、turn 级 speech metrics、rubric descriptors 和 anchor sample ids。
- 输出 `FluencyCoherenceScorerOutput`，包含 `criterion=fluency_coherence`、`band`、`confidence`、`evidence`、`suggestions` 与 `raw_output`，并可通过 `to_report_criterion()` 转换为 `CriterionScoreInput`。
- `raw_output.dimension_boundary` 已明确标记 `fluency_coherence_only_no_grammar_penalty`，避免把语法错误主要归入 Fluency & Coherence 维度。
- 评分 evidence 会引用具体 turn、回答片段和 WPM、长停顿、连接标记等指标；建议聚焦语速、停顿、填充词和连贯展开。
- 已新增 `services/agent-harness/tests/test_fluency_scorer_agent.py`，覆盖 band/confidence 输出、指标 evidence、长停顿/低 WPM/filler/短回答扣分，以及不把 grammar、tense、subject-verb 等语法问题作为 fluency 主要证据或建议。
- `python -m pytest tests/test_fluency_scorer_agent.py`：通过，3 个测试通过。
- `python -m pytest tests`：通过，Agent Harness 164 个测试通过。
- `pnpm --filter @ielts-speaking/protocol validate`、`go test ./...`、`pnpm --filter @ielts-speaking/web typecheck`：通过。

### 2026-06-08 LexicalResourceScorer 验证记录

- 已新增 `services/agent-harness/app/agents/lexical_scorer_agent.py`，实现确定性 `LexicalResourceScorerAgent` baseline，输入包含 transcript、topic keywords、rubric descriptors 和 anchor sample ids。
- 输出 `LexicalResourceScorerOutput`，包含 `criterion=lexical_resource`、`band`、`confidence`、`evidence`、`suggestions` 与 `raw_output`，并可通过 `to_report_criterion()` 转换为 `CriterionScoreInput`。
- 评分特征覆盖内容词多样性、重复内容词、低效/空泛表达、话题词命中和替代表达；`raw_output.dimension_boundary` 明确为 `lexical_resource_only_no_rare_word_stuffing`。
- evidence 会引用具体 turn、回答片段、重复词、低效表达及话题词；suggestions 给出自然替代表达，并明确不鼓励堆砌生僻词。
- 已新增 `services/agent-harness/tests/test_lexical_scorer_agent.py`，覆盖 band/confidence 输出、报告 criterion 转换、重复词与低效表达识别、替代表达建议，以及话题词缺失时不鼓励 rare/advanced word stuffing。
- `python -m pytest tests/test_lexical_scorer_agent.py`：通过，3 个测试通过。
- `python -m pytest tests`：通过，Agent Harness 167 个测试通过。
- `pnpm --filter @ielts-speaking/protocol validate`、`go test ./...`、`pnpm --filter @ielts-speaking/web typecheck`：通过。

### 2026-06-08 GrammarScorer 验证记录

- 已新增 `services/agent-harness/app/agents/grammar_scorer_agent.py`，实现确定性 `GrammarScorerAgent` baseline，输入包含 transcript、rubric descriptors 和 anchor sample ids。
- 输出 `GrammarScorerOutput`，包含 `criterion=grammatical_range_accuracy`、`band`、`confidence`、`evidence`、`suggestions` 与 `raw_output`，并可通过 `to_report_criterion()` 转换为 `CriterionScoreInput`。
- 评分特征覆盖句子数量、平均句长、句长变化、复杂结构标记、重大语法错误和轻微语法错误；`raw_output.dimension_boundary` 明确为 `grammar_range_accuracy_only_natural_spoken_rewrites`。
- 当前 MVP 规则覆盖第三人称单数主谓一致、复数主语 be 动词、过去时间语境时态控制和常见地点名词冠词缺失；evidence 会区分 major/minor，并给出口语自然改写提示。
- 已新增 `services/agent-harness/tests/test_grammar_scorer_agent.py`，覆盖 band/confidence 输出、语法范围 evidence、重大错误识别、过去时间误用、轻微冠词缺失和自然口语改写边界。
- `python -m pytest tests/test_grammar_scorer_agent.py`：通过，3 个测试通过。
- `python -m pytest tests`：通过，Agent Harness 170 个测试通过。
- `pnpm --filter @ielts-speaking/protocol validate`、`go test ./...`、`pnpm --filter @ielts-speaking/web typecheck`：通过。

### 2026-06-08 PronunciationScorer 验证记录

- 已新增 `services/agent-harness/app/agents/pronunciation_scorer_agent.py`，实现确定性 `PronunciationScorerAgent` baseline，输入包含 transcript、turn 级 speech metrics、可选 pronunciation evidence、rubric descriptors 和 anchor sample ids。
- 输出 `PronunciationScorerOutput`，包含 `criterion=pronunciation`、`band`、`confidence`、`evidence`、`suggestions` 与 `raw_output`，并可通过 `to_report_criterion()` 转换为 `CriterionScoreInput`。
- 评分特征覆盖 ASR confidence、不可识别片段、WPM、长停顿、平均停顿、可懂度、pronunciation score、prosody score、audio quality 和 evidence source；`raw_output.dimension_boundary` 明确为 `pronunciation_only_intelligibility_rhythm_stress_no_accent_penalty`。
- 评分策略保持保守：开源或内部 pronunciation evidence 只作为可懂度、节奏、重音和清晰度证据，不直接等同 IELTS 官方分；录音质量差或证据不足时降低 confidence 并提示限制。
- 已新增 `services/agent-harness/tests/test_pronunciation_scorer_agent.py`，覆盖 band/confidence 输出、发音/韵律 evidence、低置信度限制提示、不可识别片段、录音质量影响，以及不把 non-native accent 当作错误。
- `python -m pytest tests/test_pronunciation_scorer_agent.py`：通过，3 个测试通过。
- `python -m pytest tests`：通过，Agent Harness 173 个测试通过。
- `pnpm --filter @ielts-speaking/protocol validate`、`go test ./...`、`pnpm --filter @ielts-speaking/web typecheck`：通过。

### 2026-06-08 ScoreReviewerAgent 验证记录

- 已新增 `services/agent-harness/app/agents/score_reviewer_agent.py`，实现确定性 `ScoreReviewerAgent`，对四维 scorer 输出进行二次审计而不直接重打分。
- 输入 `ScoreReviewerInput` 必须包含 `fluency_coherence`、`lexical_resource`、`grammatical_range_accuracy`、`pronunciation` 四维 `CriterionScoreInput`，输出 `ScoreReviewerOutput`，包含 `status`、`reviewed_criteria`、`findings`、`reviewer_notes` 与 `raw_output`。
- 复核规则覆盖 evidence sufficiency、低证据高置信、dimension_boundary 与维度匹配、evidence 维度词对齐；发现证据不足或维度混淆时可降低 confidence 或要求 rescore。
- `reviewed_criteria` 会保留原 band，仅对证据不足但可接受的维度做保守 confidence 下调；严重问题通过 `status=needs_rescore` 和 reviewer_notes 交给 ScoringWorkflow 重新触发对应维度评分。
- 已新增 `services/agent-harness/tests/test_score_reviewer_agent.py`，覆盖高置信无证据要求重评、dimension_boundary 错配要求重评、最低证据数量高置信自动降置信，以及证据充分时通过复核。
- `python -m pytest tests/test_score_reviewer_agent.py`：通过，4 个测试通过。
- `python -m pytest tests`：通过，Agent Harness 177 个测试通过。
- `pnpm --filter @ielts-speaking/protocol validate`、`go test ./...`、`pnpm --filter @ielts-speaking/web typecheck`：通过。

### 2026-06-08 ScoreCalibrator 验证记录

- 已新增 `services/agent-harness/app/agents/score_calibrator.py`，实现确定性 `ScoreCalibrator`，基于 anchor samples 对 Reviewer 通过后的四维 `CriterionScoreInput` 做保守校准。
- 校准策略按 criterion 聚合相似 anchor，计算加权 anchor mean band 与当前 band 的偏差；偏差达到阈值时最多移动 `0.5` band，避免少量样本过度拉动分数。
- 每个维度都会输出 `ScoreCalibrationAdjustment`，包含校准前分数、校准后分数、anchor 均值、偏差、action、reason 和 anchor_sample_ids；同时写入 criterion `raw_output.calibration`。
- anchor 不足或相似度不足时不伪造校准，明确记录 `insufficient_anchors` 并保留复核后分数。
- `python -m pytest tests/test_score_calibrator.py`：通过，4 个测试通过。

### 2026-06-08 ScoringWorkflow 验证记录

- 已新增 `services/agent-harness/app/workflows/scoring_workflow.py`，编排 FluencyCoherenceScorer、LexicalResourceScorer、GrammarScorer、PronunciationScorer、ScoreReviewerAgent 和 ScoreCalibrator。
- 已新增 `POST /agent/sessions/{session_id}/score`，从 `session_state.answers` 抽取 turn、transcript、question_text、speech_metrics、ASR confidence、pronunciation evidence 和 topic keywords，生成 `ScoreReportInput` 兼容报告。
- Workflow 输出 `scoring.dimension_completed`、`scoring.review_completed` 和 `report.ready` 事件；报告写入四维 criteria、overall_band、confidence、reviewer_notes、官方练习免责声明和 calibration raw_report。
- 失败节点可重试：没有可评分回答或 Reviewer 要求重评时，返回 `error.recoverable` 与 `next_action=retry_current_node`，并在 state 中保留错误原因。
- `python -m pytest tests/test_scoring_workflow.py tests/test_agent_api.py`：通过，26 个测试通过，覆盖 schema-valid report、retryable error 和评分端点 trace。
- `python -m pytest tests`：通过，Agent Harness 184 个测试通过。
- `pnpm --filter @ielts-speaking/protocol validate`：通过。
- `go test ./...`：通过；首次沙箱运行因 Windows Go build cache 权限失败，提升权限重跑通过。
- `pnpm --filter @ielts-speaking/web typecheck`：通过。

### 2026-06-08 MCP 权限与审计验证记录

- 已新增统一 `MCP Security Middleware`，所有 MCP 工具调用统一经过 scope、`allowed_tools` allowlist、`disabled_tools` 和高风险工具禁用校验。
- 每次允许或拒绝的工具调用都会写入 `McpAuditSink`，审计字段包含 `user_id_hash`、`session_id`、`tool_name`、`request_id`、授权状态、拒绝原因、required scopes 与 granted scopes，避免 Trace 或审计日志暴露原始 user_id。
- 写入类高风险工具默认包含 `save_score_report`、`save_feedback`、`save_reference_answer`，可通过 `disable_high_risk_tools=true` 一键禁用；显式传入 `high_risk_tools=None` 也会回退到默认高风险清单。
- `python -m pytest tests`：通过，Agent Harness 117 个测试通过，新增 MCP Security 7 个测试覆盖 allowed/denied 审计、缺失 scope、allowlist 拒绝、禁用工具、高风险工具禁用、默认审计 sink reset 和显式 `high_risk_tools=None` 的安全回退。
- `docker compose build --pull=false agent-harness`：通过，容器镜像可构建。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic`、9 个 MiMo 可用模型与 `knowledge_service.backend=memory`；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器，`docker compose ps` 无运行中服务。

### 2026-06-08 QuestionSetPlannerAgent 验证记录

- 已新增 `app.agents.question_planner_agent.QuestionSetPlannerAgent`，统一生成 `QuestionSetPlan`，覆盖 full_exam、part_practice 和 topic_practice。
- `ExamWorkflow` 与 `PracticeWorkflow` 已消费 `question_plan` 状态推进题目，旧状态仍可回退到 `PART_CONFIG`，避免前端断线恢复或旧测试状态不兼容。
- 题组规划优先支持 `question-bank-mcp` 检索 active season 题库，并在题库工具缺失或检索不足时使用 fallback catalog；规划输出包含 Part 2 cue card、timer policy、题目来源 evidence 和 fallback rationale。
- 已实现基于 `question_id` 与题面 token 相似度的去重，避免同一题或高度相似题进入同一题组。
- `python -m pytest tests`：通过，Agent Harness 122 个测试通过，新增 QuestionSetPlannerAgent 5 个测试覆盖 full_exam 三段题组、part_practice 单 Part、topic_practice topic 保留、question-bank 候选清洗去重和题面提取。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false agent-harness`：通过，容器镜像可构建并包含新增 `app.agents` 模块。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic`、9 个 MiMo 可用模型与 `knowledge_service.backend=memory`；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器。

### 2026-06-08 ExaminerAgent 验证记录

- 已新增 `app.agents.examiner_agent.ExaminerAgent`，统一控制 `examiner.message.payload.text` 的 IELTS 考官话术风格。
- `full_exam` 输出克制、简短的问题，不携带练习提示；Part 2 首题会生成真实考试式 cue-card 引导语。
- `part_practice` / `topic_practice` 允许练习式引导，但训练建议仍保留在 `practice_hints` 字段，避免和正式考试模式混淆。
- `ExamWorkflow` 与 `PracticeWorkflow` 已接入 `ExaminerAgent`，并在事件 payload 中保留 `style_tags` 供前端或 Trace 观察。
- `python -m pytest tests`：通过，Agent Harness 127 个测试通过，新增 ExaminerAgent 5 个测试覆盖 full_exam 克制话术、Part 2 考试引导、练习模式风格、full_exam 禁止 practice flag 和内部术语过滤。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false agent-harness`：通过，容器镜像可构建并包含新增 `ExaminerAgent`。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic`、9 个 MiMo 可用模型与 `knowledge_service.backend=memory`；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器。

### 2026-06-08 FollowupPlannerAgent 验证记录

- 已新增 `app.agents.followup_planner_agent.FollowupPlannerAgent`，根据 ASR 文本、当前 Part、题目序号、模式和已追问次数规划追问。
- `ConsumeAsrRequest` 与共享 `agent-api.schema.json` 已新增可选 `session_state`，用于让 `/consume-asr` 识别当前会话状态；不传时仍兼容旧请求。
- `ExamWorkflow` 与 `PracticeWorkflow` 已接入动态追问：短回答会直接返回 `agent.followup_planned`、`examiner.message` 和 `timer.started`，并设置 `next_action=wait_for_user_answer`。
- 隐私保护边界已加入：回答包含邮箱、手机号、地址、薪资、证件、密码、工作地点等敏感线索时不追问私人细节，直接进入下一题。
- 追问策略限制同一题默认最多追问一次；Part 3 追问更抽象，Part 1 更自然，Part 2 聚焦补充具体细节。
- `python -m pytest tests`：通过，Agent Harness 134 个测试通过，新增 FollowupPlannerAgent 5 个测试和 Agent API 2 个测试，覆盖短回答追问、Part 3 抽象追问、敏感信息跳过、避免重复追问、练习模式 payload 保留。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过，包含 `ConsumeAsrRequest.session_state`。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false agent-harness`：通过，容器镜像可构建并包含新增 `FollowupPlannerAgent`。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic`、9 个 MiMo 可用模型与 `knowledge_service.backend=memory`；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器。

### 2026-06-08 Part 1 Workflow 验证记录

- Part 1 默认题量已升级为 4 道，题组覆盖 hometown、work/study、daily routine、free time 等日常话题，并在 `examiner.message` payload 中返回 topic。
- Part 1 已加入 `timebox_seconds=300`，`part.started`、`timer.started` 和 `examiner.message` 均携带时间盒信息，前端可结合 `part_elapsed_seconds` 回传当前 Part 已用时间。
- `next-turn` 会在 Part 1 题目全部问完或 `part_elapsed_seconds >= timebox_seconds` 时输出 `part.completed`，并自动进入 Part 2。
- 进入下一题或下一 Part 时会重置 `followup_count`，避免上一题追问状态污染后续题。
- `python -m pytest tests`：通过，Agent Harness 135 个测试通过，新增 Agent API 测试覆盖 Part 1 时间盒触发进入 Part 2，并更新 Part 1 多题推进测试。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false agent-harness`：通过，容器镜像可构建并包含 Part 1 Workflow 更新。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic`、9 个 MiMo 可用模型与 `knowledge_service.backend=memory`；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器。

### 2026-06-08 Part 2 Workflow 验证记录

- Part 2 已统一输出 cue card payload，包含 prompt、bullet points、`preparation_seconds=60` 和 `speaking_seconds=120`。
- `part.started` 已包含 `preparation_seconds`、`speaking_seconds`、`warning_seconds=[60,30,10]` 和 `timebox_seconds=180`，用于前端初始化 Part 2 长轮次界面。
- `timer.started` 已包含 `phase=prepare_then_speak`、准备时间、回答时间和提醒节点，用于 1 分钟准备与 1-2 分钟回答倒计时。
- `full_exam` 从 Part 1 进入 Part 2、`part_practice` 直接进入 Part 2、`topic_practice` 进入 Part 2 均使用同一套字段，减少前端模式分叉。
- `python -m pytest tests`：通过，Agent Harness 135 个测试通过，Agent API 测试覆盖 Part 2 单练 cue card/计时 payload，以及 full_exam 从 Part 1 进入 Part 2 的 cue card/计时 payload。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false agent-harness`：通过，容器镜像可构建并包含 Part 2 Workflow 更新。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic`、9 个 MiMo 可用模型与 `knowledge_service.backend=memory`；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器。

### 2026-06-08 Part 3 Workflow 验证记录

- Part 3 题组已继承 Part 2 首题上下文，`PlannedQuestion` 输出 `linked_part2_question_id`、`linked_part2_topic`、`discussion_level` 和 `discussion_focus`。
- `full_exam` 从 Part 2 进入 Part 3 时，`part.started` 与 `examiner.message` 均携带 Part 3 抽象讨论 metadata，前端和 Trace 可识别 Part 3 与 Part 2 的主题关系。
- Part 3 fallback 题目会根据 Part 2/选定 topic 映射到 `public_places`、`education_and_work`、`technology_and_society`、`travel_and_culture` 或 `social_change` 等讨论焦点。
- Part 3 题面保持简短口语化，避免写作式长问题；`ExaminerAgent` 仍使用克制考官话术。
- `python -m pytest tests`：通过，Agent Harness 137 个测试通过，新增 QuestionSetPlannerAgent 与 Agent API 测试覆盖 Part 3 与 Part 2 的主题关联、讨论 metadata 和 full_exam 从 Part 2 进入 Part 3。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false agent-harness`：通过，容器镜像可构建并包含 Part 3 Workflow 更新。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic`、9 个 MiMo 可用模型与 `knowledge_service.backend=memory`；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器，现有 `api-go`、`postgres`、`redis`、`minio` 保持运行。

### 2026-06-08 full_exam 模式验证记录

- `ExamWorkflow.plan` 已初始化 `state.status=in_progress`，并保留 `question_plan`、`target_parts`、`current_part`、`question_index`、`completed_parts` 和 `answers`。
- `consume-asr` 已将用户回答追加到 `state.answers`，记录 turn、Part、题目、ASR 文本、音频资产、ASR 置信度和追问决策，供调用方持久化状态和后续 ScoringWorkflow 使用。
- `next-turn` 已支持完整考试 Part 1 -> Part 2 -> Part 3 自动推进；Part 3 完成后输出 `session.completed`、`scoring.started`，并设置 `state.status=scoring`、`next_action=score_session`。
- `python -m pytest tests`：通过，Agent Harness 138 个测试通过，新增 Agent API 测试覆盖 full_exam happy path、回答状态保留、完整考试结束进入 scoring。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false agent-harness`：通过，容器镜像可构建并包含 full_exam 状态推进更新。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic`、9 个 MiMo 可用模型与 `knowledge_service.backend=memory`；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器，现有 `api-go`、`postgres`、`redis`、`minio` 保持运行。

### 2026-06-08 part_practice 模式验证记录

- `PracticeWorkflow.plan` 已按请求 `part` 初始化 `target_parts=[part]`、`current_part=part`、`state.status=in_progress` 和 `practice_mode=true`。
- Part 1/2/3 单项练习均会输出 `practice_hints`；Part 2 输出 cue card、准备时间、回答时间和提醒节点；Part 3 输出抽象讨论 metadata。
- `consume-asr` 已将练习回答追加到 `state.answers`，记录 turn、Part、题目、ASR 文本、音频资产、ASR 置信度、追问决策和 `practice_mode`。
- 目标 Part 完成后输出 `session.completed`、`scoring.started`，并设置 `state.status=scoring`、`next_action=score_session`，为后续评分与复盘衔接。
- `python -m pytest tests`：通过，Agent Harness 141 个测试通过，新增 Agent API 测试覆盖 Part 1/2/3 选择、练习回答状态保留、Part 1 与 Part 2 单练结束进入 scoring。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false agent-harness`：通过，容器镜像可构建并包含 part_practice 状态推进更新。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic`、9 个 MiMo 可用模型与 `knowledge_service.backend=memory`；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器，现有 `api-go`、`postgres`、`redis`、`minio` 保持运行。

### 2026-06-08 topic_practice 模式验证记录

- `PracticeWorkflow.plan` 已保留 `topic_ids`，并为 `topic_practice` 生成 `state.topic_guidance`，包含 `primary_topic`、`topic_label`、`vocabulary`、`useful_expressions` 和 `feedback_focus`。
- `QuestionSetPlannerAgent` 的 topic fallback 题目已把 `selected topic` 占位文案渲染为具体主题，并在题目 metadata 中保留对应 topic。
- `session.started`、`part.started`、`examiner.message`、`state.answers`、`session.completed` 和 `scoring.started` 已携带 `topic_guidance`，后续 FeedbackWorkflow 可直接生成主题词汇与表达建议。
- `topic_practice` 不指定 Part 时按 Part 1 -> Part 2 -> Part 3 推进；指定 Part 时只练目标 Part，并在完成后进入 scoring。
- `python -m pytest tests`：通过，Agent Harness 143 个测试通过，新增 Agent API 与 QuestionSetPlannerAgent 测试覆盖主题题目渲染、主题 guidance、主题回答状态保留和完成后反馈种子传递。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false agent-harness`：通过，容器镜像可构建并包含 topic_practice 主题上下文更新。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic`、9 个 MiMo 可用模型与 `knowledge_service.backend=memory`；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器，现有 `api-go`、`postgres`、`redis`、`minio` 保持运行。

### 2026-06-08 ModePolicy 模式差异控制验证记录

- 已新增 `app.workflows.mode_policy`，统一生成 `mode_policy.v1`，包含 `prompt_profile`、`ui_profile`、`allow_practice_hints`、`allow_structure_suggestions`、`allow_reference_answer`、`allow_topic_guidance`、`allow_chinese_strategy_hints` 和 `scoring_strictness`。
- `full_exam` 使用 `examiner_exam` / `exam` 策略，禁用练习提示、结构建议、参考答案、topic guidance 和中文策略提示。
- `part_practice` / `topic_practice` 使用 `coach_practice` / `practice` 策略，允许结构建议、参考答案和诊断式评分；`topic_practice` 额外允许 topic guidance。
- `mode_policy` 已写入 workflow state，并随 `session.started`、`part.started`、`examiner.message`、`timer.started`、`session.completed`、`scoring.started` 等关键事件输出，供 Prompt 层和 UI 层统一消费。
- `python -m pytest tests`：通过，Agent Harness 145 个测试通过，新增 Agent API 测试覆盖考试模式不输出练习字段或中文策略提示、练习模式允许结构建议、topic_practice 允许 topic guidance。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false agent-harness`：通过，容器镜像可构建并包含 ModePolicy 更新。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic`、9 个 MiMo 可用模型与 `knowledge_service.backend=memory`；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器，现有 `api-go`、`postgres`、`redis`、`minio` 保持运行。

### 2026-06-08 MiMo 模型供应商配置记录

- 已将 Anthropic-compatible MiMo 供应商配置保存到本地未提交的 `.env`，包含真实 `MIMO_API_KEY`、`MIMO_BASE_URL`、`MIMO_API_FORMAT=anthropic`、默认模型、任务级路由和可用模型清单；真实 key 不写入版本化文档。
- 已新增 `MIMO_AVAILABLE_MODELS_JSON` 配置，当前可用模型清单包含 `mimo-v2.5-pro`、`mimo-v2.5`、`mimo-v2.5-asr`、`mimo-v2.5-tts-voiceclone`、`mimo-v2.5-tts-voicedesign`、`mimo-v2.5-tts`、`mimo-v2-pro`、`mimo-v2-omni`、`mimo-v2-tts`。
- 已更新 `.env.example`、`docker-compose.yml`、`docs/configuration.md`、`services/agent-harness/app/core/config.py` 与 `/healthz`，后续真实测试可先从非敏感健康检查确认模型供应商配置。
- 为避免开发阶段误消耗额度，本地 `.env` 暂保留 `MOCK_MODEL_ENABLED=true`；后续真实模型测试任务开启时再显式关闭 mock 或通过专项 smoke 命令调用。

### 2026-06-07 数据层验证记录

- `go test ./...`：通过，包含迁移命令与嵌入迁移测试。
- `docker compose config --quiet`：通过。
- `POSTGRES_PORT=55432 docker compose up -d postgres`：通过，pgvector PostgreSQL 容器健康。
- `go run ./cmd/api migrate up`：通过，`000001_core_schema.sql` 已应用。
- 数据库侧验证：`pgcrypto`、`vector` 扩展存在；public schema 下 31 张表；`knowledge_chunks.embedding` 为 `vector` 类型。
- `go run ./cmd/api migrate down && go run ./cmd/api migrate up`：通过，迁移可回滚并可重新应用。
- `docker compose build api-go`：通过，Go 1.23 Docker 基线可编译。

### 2026-06-07 鉴权模块验证记录

- `go test ./...`：通过，包含 Auth Service、JWT、Handler、Middleware 测试。
- `docker compose config --quiet`：通过。
- `pnpm --filter @ielts-speaking/protocol validate`：通过。
- 真实数据库链路验证：在 PostgreSQL/pgvector 上完成注册、登录、携带 access token 调用 `/api/me`、携带 refresh token 刷新。
- `go build ./cmd/api`：通过。
- `docker compose build api-go`：未完成，容器内 `go mod download` 访问 Go module proxy 被网络拒绝；代码已通过本地编译和真实 API 验证。

### 2026-06-07 题库 API 验证记录

- `go test ./...`：通过，包含题库 Handler、角色保护、Part 2 cue card 校验测试。
- `go build ./cmd/api`：通过。
- `docker compose config --quiet`：通过。
- `pnpm --filter @ielts-speaking/protocol validate`：通过。
- 真实数据库/API 链路验证：创建 operator 用户后完成 season 创建与激活、topic 创建、Part 1 题目创建/更新/归档、Part 2 cue card 题目创建与公开查询、Part 3 抽象讨论题创建与公开查询。
- 验证题目字段：`source_type`、`license`、`review_status` 可写入和返回。
- 验证状态边界：公开 `/api/questions` 只查询 active 内容，后台 `/api/admin/question-bank/*` 需要 operator/admin Bearer token。

### 2026-06-07 会话 API 验证记录

- `go test ./...`：通过，包含 Session Handler、鉴权、模式规划、turn/audio/asr/metrics 入口测试。
- `go build ./cmd/api`：通过。
- `docker compose config --quiet`：通过。
- `pnpm --filter @ielts-speaking/protocol validate`：通过。
- 真实数据库/API 链路验证：注册用户后创建 `full_exam`，自动生成 Part 1/2/3；启动后状态进入 `in_progress`；完成 Part 1 后 Part 1 为 `completed`、Part 2 自动进入 `in_progress`；finish 后 session 进入 `scoring`。
- 真实数据库/API 链路验证：创建 `part_practice` 只生成目标 Part；创建 `topic_practice` 可绑定 topic 和目标 Part。
- 真实数据库/API 链路验证：turn 级别成功记录 examiner/user turn、audio metadata、ASR result、speech metrics，并可通过 `GET /api/sessions/:id` 读取。

### 2026-06-07 音频资产服务验证记录

- `go test ./...`：通过，包含 Audio Service 与 Handler 测试，覆盖上传、权限校验顺序、签名 URL 过期封顶、MIME 推断、未登录、非法时长等分支。
- `go build ./cmd/api`：通过，Go 1.23 本地工具链可编译。
- `docker compose config --quiet`：通过，Compose 配置可解析；MinIO 镜像改为官方 `quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z`，规避 Docker Hub 拉取超时。
- `docker compose build --pull=false api-go`：通过，容器内 `go mod download` 与 Linux 二进制构建完成；普通 `docker compose build api-go` 曾受 Docker Hub metadata 访问超时影响。
- `pnpm --filter @ielts-speaking/protocol validate`：通过。
- `POSTGRES_PORT=55432 docker compose up -d postgres minio`：通过，pgvector PostgreSQL 与 MinIO 均 healthy。
- `go run ./cmd/api migrate up`：通过，当前迁移版本为 1。
- 真实数据库/API/MinIO 链路验证：注册用户、创建 `part_practice`、创建 user turn 后，`POST /api/audio/upload` 成功生成 `audio_assets` 记录，返回 bucket `ielts-speaking-local`、`mime_type=audio/webm`、`duration_ms=18000`、64 位 SHA-256 checksum。
- 真实回放验证：`GET /api/audio/:id/signed-url?expires_seconds=120` 返回 host 为 `localhost:9000` 的签名 URL，使用该 URL 下载对象后内容与上传内容一致。
- Docker 本地回放边界：新增 `S3_PUBLIC_ENDPOINT`，API 容器可用 `S3_ENDPOINT=http://minio:9000` 写 MinIO，同时用 public endpoint 生成浏览器可访问的签名 URL；真实验证中 `S3_PUBLIC_ENDPOINT=http://127.0.0.1:9000` 返回 host `127.0.0.1:9000`，下载内容匹配。
- 限制分支验证：不支持类型返回 `415 unsupported_audio_type`，超出 `AUDIO_MAX_DURATION_MS=600000` 返回 `400 audio_duration_too_long`，超出 `AUDIO_MAX_UPLOAD_BYTES=26214400` 返回 `413 audio_file_too_large`。

### 2026-06-07 背景问卷 API 验证记录

- `go test ./...`：通过，包含 Profile Handler、鉴权、输入校验、privacy exclusions 去重、`agent_facts` 过滤测试。
- `go build ./cmd/api`：通过，Go 1.23 本地工具链可编译。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false api-go`：通过，容器内 Linux 二进制构建完成。
- `POSTGRES_PORT=55432 docker compose up -d postgres`：通过，pgvector PostgreSQL 容器健康。
- `go run ./cmd/api migrate up`：通过，当前迁移版本为 1。
- 真实数据库/API 链路验证：注册用户后，`GET /api/me/background` 初始返回无 questionnaire；`PUT /api/me/background` 成功保存 profile、结构化 answers、自由补充 `free_note`、`privacy_exclusions=["workplace"]` 和 2 条 facts。
- 隐私过滤验证：保存后 `facts=2`、`agent_facts=1`，被 privacy exclusions 命中的 `workplace` fact 不进入 `agent_facts`；再次 `GET /api/me/background` 可读回。
- 更新语义验证：只更新 `answers.study_goal` 且省略 `facts` 时，旧 facts 保留，`agent_facts` 仍保持过滤结果。

### 2026-06-07 WebSocket Gateway 验证记录

- `go test ./...`：通过，包含 Realtime Hub、SessionEvent 校验、WebSocket 握手鉴权、session access 校验、query token 连接和事件广播测试。
- `go build ./cmd/api`：通过，Go 1.23 本地工具链可编译。
- `docker compose config --quiet`：通过。
- `docker compose build --pull=false api-go`：通过，容器内 `go mod download` 与 Linux 二进制构建完成。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，WebSocket 事件仍对齐共享 SessionEvent schema。
- `POSTGRES_PORT=55432 docker compose up -d postgres`：通过，pgvector PostgreSQL 容器健康。
- `go run ./cmd/api migrate up`：通过，当前迁移版本为 1。
- 真实数据库/API/WebSocket 链路验证：注册用户并创建 `part_practice` session 后，未携带 token 连接 `ws://127.0.0.1:18080/api/ws/sessions/:id` 被拒绝；携带 `access_token` 查询参数可连接。
- 真实事件收发验证：连接后发送符合 `session-event.schema.json` 的 `timer.tick` 事件，服务端按 session 广播并读回同一 `session_id`、`run_id` 和 payload。
- 真实广播与越权验证：同一 session 下两个 WebSocket 客户端均收到 `asr.processing` 事件；另一个用户携带自己的 token 连接该 session 被拒绝。

### 2026-06-07 MiMoChatClient 验证记录

- `python -m pytest tests`：通过，Agent Harness 9 个测试通过，新增 MiMoChatClient 6 个测试覆盖 OpenAI-compatible 非流式、流式 SSE、tools、`response_format`、Anthropic-compatible tool use、usage 解析、可重试 5xx、401 鉴权错误、429 限流错误。
- `docker compose config --quiet`：通过，Compose 配置可解析，Agent Harness 已注入 `MIMO_API_FORMAT`、`MIMO_TIMEOUT_SECONDS`、`MIMO_MAX_RETRIES`。
- `pnpm --filter @ielts-speaking/protocol validate`：通过。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器内依赖安装与镜像构建完成。
- `docker compose up -d agent-harness`：通过，容器健康；`GET http://127.0.0.1:8000/healthz` 返回 `status=ok`、`mock_model_enabled=true`。
- 交付边界验证：新增 `app.models.mimo_client.MiMoChatClient`，工作流后续可通过统一 `ChatResponse`、`ChatStreamChunk`、`MiMoError.retryable/code` 接入真实模型，而不直接依赖底层 HTTP。

### 2026-06-07 Model Router 验证记录

- `python -m pytest tests`：通过，Agent Harness 15 个测试通过，新增 ModelRouter 6 个测试覆盖默认路由、JSON 配置覆盖、任务级 `temperature`/`max_tokens` 注入、可重试错误 fallback、非可重试鉴权错误不 fallback、调用级参数覆盖。
- `docker compose config --quiet`：通过，Compose 配置可解析，Agent Harness 已注入 `MIMO_MODEL_ROUTES_JSON`。
- `pnpm --filter @ielts-speaking/protocol validate`：通过。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建。
- `docker compose up -d agent-harness`：通过，容器健康；`GET http://127.0.0.1:8000/healthz` 返回 `status=ok`、`mock_model_enabled=true`；验证后已停止本轮启动的 agent-harness 容器。
- 交付边界验证：新增 `app.models.model_router.ModelRouter`，工作流可按 `question_planning`、`examiner`、`followup_planning`、`scoring`、`feedback`、`cheap`、`default` 任务选择模型，并可通过 `MIMO_MODEL_ROUTES_JSON` 独立调整模型、fallback 模型和生成参数。

### 2026-06-07 PracticeWorkflow 验证记录

- `python -m pytest tests`：通过，Agent Harness 18 个测试通过，新增 PracticeWorkflow API 测试覆盖 `part_practice` 提示与 Part 2 cue card、`topic_practice` 从 Part 1 推进到 Part 2、单 Part 练习完成后进入 `score_session`、`full_exam` 不输出练习提示。
- `docker compose config --quiet`：通过。
- `pnpm --filter @ielts-speaking/protocol validate`：通过。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建。
- `docker compose up -d agent-harness`：通过，容器健康；`GET http://127.0.0.1:8000/healthz` 返回 `status=ok`、`mock_model_enabled=true`。
- 容器内真实 API 验证：`POST /agent/sessions/sess_practice_verify/plan` 携带 `mode=part_practice`、`part=2` 返回 `practice_mode=true`、`practice_hints`、Part 2 `cue_card` 和 `next_action=wait_for_user_answer`；验证后已停止本轮启动的 agent-harness 容器。
- 交付边界验证：新增 `app.workflows.practice_workflow.PracticeWorkflow`，`full_exam` 继续走 `ExamWorkflow`，`part_practice` 与 `topic_practice` 走练习工作流，练习提示只出现在练习模式事件 payload 中。

### 2026-06-07 AG-UI 事件适配器验证记录

- `python -m pytest tests`：通过，Agent Harness 24 个测试通过，新增 AG-UI 事件适配器 6 个测试覆盖 `examiner.message` payload 校验、未知事件拒绝、非法 `timer.started` payload 拒绝、`scoring.started` 支持、Python `SessionEvent` 枚举拒绝协议外事件、Python 事件枚举与共享 `session-event.schema.json` 完全一致。
- `docker compose config --quiet`：通过。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建。
- `docker compose up -d agent-harness`：通过，容器健康；`GET http://127.0.0.1:8000/healthz` 返回 `status=ok`、`mock_model_enabled=true`。
- 容器内真实 API 验证：`POST /agent/sessions/sess_agui_verify/plan` 携带 `mode=full_exam` 返回 `session.started`、`part.started`、`examiner.message`、`timer.started`，关键 payload 已通过适配器校验后可被 Go Backend 直接转发；验证后已停止本轮启动的 agent-harness 容器。
- 交付边界验证：`app.protocols.ag_ui_events.build_event` 现在统一校验事件类型和关键 payload，`SessionEvent.type` 与共享协议枚举对齐，并提供 `build_scoring_started_event` 支持后续评分工作流。

### 2026-06-07 Langfuse Trace 初版验证记录

- `python -m pytest tests`：通过，Agent Harness 30 个测试通过，新增 Trace 相关 6 个测试覆盖 Agent API 生成 trace、`GET /agent/runs/:run_id`、`GET /agent/runs/:run_id/trace`、取消 run 状态更新、未知 trace 404、ASR 文本不进入 input summary、敏感文本脱敏、user_id 哈希、Langfuse ingestion payload 和 `LANGFUSE_ENABLED` 配置校验。
- `docker compose config --quiet`：通过，Compose 配置可解析，Agent Harness 已注入 `LANGFUSE_ENABLED`、`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`LANGFUSE_HOST`、`LANGFUSE_TIMEOUT_SECONDS`、`TRACE_USER_HASH_SALT`、`TRACE_STORE_LIMIT`。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建。
- `docker compose up -d agent-harness`：通过，容器健康；`GET http://127.0.0.1:8000/healthz` 返回 `status=ok`、`mock_model_enabled=true`。
- 容器内真实 API 验证：`POST /agent/sessions/sess_trace_verify/plan` 携带 `mode=part_practice` 后，`GET /agent/runs/:run_id` 返回 `completed`，`GET /agent/runs/:run_id/trace` 返回 `session_id=sess_trace_verify`、`mode=part_practice`、`user_id_hash=sha256:*`、`workflow_node=plan_session`、`prompt_version=mock.practice_workflow.v1`、`model_name=mock-model`、`latency_ms>=0`；验证后已停止本轮启动的 agent-harness 容器。
- 交付边界验证：新增 `app.observability.langfuse_client.TraceRecorder`、`TraceStore` 和 `LangfuseExporter`，本地默认记录内存 trace；配置 `LANGFUSE_ENABLED=true` 且提供密钥后可向 Langfuse ingestion 端点导出 trace；输入摘要不保存完整 ASR 文本，`user_id` 只以 salted hash 进入 trace。

### 2026-06-07 结构化输出校验验证记录

- `python -m pytest tests`：通过，Agent Harness 39 个测试通过，新增结构化输出 9 个测试覆盖 Markdown JSON 提取、Pydantic schema 校验、额外字段拒绝、JSON Schema response format 生成、校验失败自动追加修复指令并重试、重试耗尽后返回 `RecoverableStructuredOutputError`、`ModelRouter.complete_structured` 注入 response format、`error.recoverable` 事件生成、`structured_output_invalid` 错误码进入 trace。
- `docker compose config --quiet`：通过。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建。
- `docker compose up -d agent-harness`：通过，容器健康；`GET http://127.0.0.1:8000/healthz` 返回 `status=ok`、`mock_model_enabled=true`。
- 容器内真实 API 验证：`POST /agent/sessions/sess_structured_verify/plan` 携带 `mode=full_exam` 正常返回 `session.started`、`part.started`、`examiner.message`、`timer.started` 和 `next_action=wait_for_user_answer`；验证后已停止本轮启动的 agent-harness 容器。
- 交付边界验证：新增 `app.models.structured_output` 和 `app.models.output_schemas`，当前关键 Agent 输出 schema 覆盖 examiner message、follow-up decision、criterion score、feedback plan；`ModelRouter.complete_structured` 后续可直接用于追问、评分和反馈工作流，结构化错误可转成 recoverable event 并写入 trace。

### 2026-06-07 LlamaIndex Knowledge Service 验证记录

- `python -m pytest tests`：通过，Agent Harness 47 个测试通过，新增 Knowledge Service 测试覆盖 ingest、retrieve Top K、metadata filter、active 状态过滤、重复 ingest 替换 chunk、长文切片、配置初始化、pgvector helper 和 hash embedding 稳定性。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过，Compose 配置可解析，Agent Harness 已注入 `KNOWLEDGE_STORE_BACKEND`、`KNOWLEDGE_DATABASE_URL`、`KNOWLEDGE_EMBEDDING_MODEL`、`KNOWLEDGE_EMBEDDING_DIMENSION`、`KNOWLEDGE_CHUNK_MAX_CHARS`、`KNOWLEDGE_CHUNK_OVERLAP_CHARS`。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建。
- `/healthz` memory 后端验证：Agent Harness 容器返回 `knowledge_service.backend=memory`，可确认默认本地 RAG 后端已挂载到服务健康检查。
- 真实 pgvector smoke：使用临时 Compose project `ielts_speaking_p3test` 启动全新 PostgreSQL，执行 `api-go migrate up` 后以 `KNOWLEDGE_STORE_BACKEND=pgvector` 写入 rubric 文档并检索成功，返回 `top_doc_type=rubric`、`top_title=P3 smoke rubric`、`chunk_count=1`。
- 临时环境清理：已执行 `docker compose -p ielts_speaking_p3test down -v` 清理临时 project 和临时卷；主项目历史 PostgreSQL 数据卷未执行破坏性清理。
- 交付边界验证：新增 `app.rag.llamaindex_service.LlamaIndexKnowledgeService`，提供 memory 与 pgvector 两种后端、确定性 hash embedding、统一 ingest/retrieve 接口和 `/healthz` 后端摘要；后续 P3-002 将固化题库、Rubric、用户背景、主题知识、历史复盘的 chunk metadata 规范。

### 2026-06-08 Knowledge Chunk Spec 验证记录

- `python -m pytest tests`：通过，Agent Harness 51 个测试通过，新增 Chunk Spec 相关测试覆盖 question chunk 必填字段与 `part` 规范化、缺少题库过滤字段时报错、Rubric `band` 规范化与 `descriptor` 必填、用户背景 `allowed_usage` 数组过滤。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过，Compose 配置可解析。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建并包含新增 RAG schema 模块。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`knowledge_service.backend=memory`、`embedding_model=hash-embedding-v1`，验证后已停止本轮启动的 agent-harness 容器。
- 交付边界验证：新增 `docs/knowledge_chunk_spec.md` 和 `app.rag.chunk_schema`，将题库、Rubric、用户背景、主题知识、历史复盘的 chunk 粒度、必填 metadata、隐私规则和过滤字段固化到文档与 ingest 校验；`allowed_usage` 等数组 metadata 已支持 memory/pgvector 过滤语义。

### 2026-06-08 题库索引任务验证记录

- `python -m pytest tests`：通过，Agent Harness 57 个测试通过，新增 QuestionBankIndexer 6 个测试覆盖 active season 过滤、按 Part/topic 检索、结果返回 `question_id`、同一题更新后稳定 `doc_id` 重建旧 chunk、Part 2 cue card/follow-up 合并、Postgres source SQL 与 row 映射。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过，Compose 配置可解析。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建并包含新增 RAG ingestion 模块。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`knowledge_service.backend=memory`，验证后已停止本轮启动的 agent-harness 容器。
- 真实 pgvector smoke：使用临时 Compose project `ielts_speaking_p3qtest` 启动全新 PostgreSQL，执行 `api-go migrate up` 后写入 active season、旧 season、topic、question、cue card 和 follow-up 样本；在 agent-harness 容器中通过 `PostgresQuestionBankSource -> QuestionBankIndexer -> PgVectorKnowledgeStore` 同步 active season 题库，返回 `indexed_count=2`、`chunk_count=2`，检索 Part 2 food 题目返回 `top_question_id=22222222-2222-2222-2222-222222222222`、`top_part=2`、`top_topic=food`、`top_has_cue_card=true`。
- 临时环境清理：已执行 `docker compose -p ielts_speaking_p3qtest down -v` 清理临时 project 和临时卷；主项目历史 PostgreSQL 数据卷未执行破坏性清理。
- 交付边界验证：新增 `app.rag.ingestion.question_bank_indexer`，一道题稳定映射为一个 `KnowledgeDocument`，`doc_id/source_id/question_id` 使用 `questions.id`；新增或更新同一题会重建旧 chunk；`search_questions()` 默认限定 `doc_type=question_bank` 并支持 active season、Part、topic 过滤。

### 2026-06-08 Rubric 索引任务验证记录

- `python -m pytest tests`：通过，Agent Harness 63 个测试通过，新增 RubricIndexer 6 个测试覆盖按 `criterion` 检索、`min_band/max_band` 展开为 0.5 递增 band 范围、anchor sample 通过 `anchor_sample_id` 与 `policy_type=anchor_example` 引用、同一 `rubric_id` 更新后稳定 UUID `doc_id` 重建旧 chunk、内部评分策略内容写入和 band 参数校验。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过，Compose 配置可解析。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建并包含新增 Rubric ingestion 模块。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`knowledge_service.backend=memory`，验证后已停止本轮启动的 agent-harness 容器。
- 真实 pgvector smoke：使用临时 Compose project `ielts_speaking_p3rubrictest` 启动全新 PostgreSQL，执行 `api-go migrate up` 后在 agent-harness 容器中通过 `RubricIndexer -> PgVectorKnowledgeStore` 写入 official descriptor、internal policy 和 anchor example，返回 `indexed_count=4`、`chunk_count=4`；按 `criterion=fluency_coherence` 和 `min_band=6,max_band=6.5` 检索返回 `range_bands=["6","6.5"]`；按 `anchor_sample_id=anchor-fc-6-a` 与 `policy_type=anchor_example` 检索返回 `anchor_count=1`、`anchor_rubric_id=fc-anchor-6-a`。
- 临时环境清理：已执行 `docker compose -p ielts_speaking_p3rubrictest down -v` 清理临时 project 和临时卷；主项目历史 PostgreSQL 数据卷未执行破坏性清理。
- 交付边界验证：新增 `app.rag.ingestion.rubric_indexer`，每条 rubric 记录稳定映射为 UUID 格式 `KnowledgeDocument.doc_id`，原始 `rubric_id` 保留在 metadata；`search_rubric()` 默认限定 `doc_type=rubric`，支持 criterion、band 范围、policy type 和 anchor sample 过滤，供后续 ScoringWorkflow 引用评分标准与 anchor examples。

### 2026-06-08 用户背景索引任务验证记录

- `python -m pytest tests`：通过，Agent Harness 71 个测试通过，新增 UserProfileIndexer 8 个测试覆盖 `is_excluded=true` 和 `privacy_level=private` 默认跳过、按 `topic` 检索、按 `allowed_usage` 区分 question personalization 与 scoring context、用户更新时 replace 旧 user_profile chunks、Postgres latest questionnaire source SQL 与 row 映射、private fact 仅显式允许时可索引。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过，Compose 配置可解析。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建并包含新增 UserProfile ingestion 模块。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`knowledge_service.backend=memory`，验证后已停止本轮启动的 agent-harness 容器。
- 真实 pgvector smoke：使用临时 Compose project `ielts_speaking_p3profiletest` 启动全新 PostgreSQL，执行 `api-go migrate up` 后写入用户、最新 background questionnaire 和 4 条 facts；在 agent-harness 容器中通过 `PostgresUserProfileSource -> UserProfileIndexer -> PgVectorKnowledgeStore` 同步，返回 `indexed_count=2`、`skipped_count=2`、`skipped_reasons=["fact_excluded","fact_private"]`，hobby fact 可按 `topic=hobbies` 与 `allowed_usage=question_personalization` 检索，grammar weakness fact 可按 `allowed_usage=scoring_context` 检索。
- 隐私边界 smoke：按 `fact_key=salary` 和 `fact_key=workplace` 精确检索 private/excluded facts，返回 `private_fact_key_count=0`、`excluded_fact_key_count=0`。
- 更新重建 smoke：删除临时库旧 facts 后写入新的 `target_band` fact，再次同步返回 `deleted_count=2`、`indexed_count=1`；旧 hobby fact 检索返回 `old_hobby_count=0`，新 goals fact 返回 `new_fact_id=44444444-4444-4444-4444-444444444444`。
- 临时环境清理：已执行 `docker compose -p ielts_speaking_p3profiletest down -v` 清理临时 project 和临时卷；主项目历史 PostgreSQL 数据卷未执行破坏性清理。
- 交付边界验证：新增 `app.rag.ingestion.user_profile_indexer`，默认跳过禁用和 private facts，`sync_from_source()` 默认按用户 replace 旧 `user_profile` chunks；`search_user_facts()` 必须传入 `user_id` 并默认限定 `doc_type=user_profile`、`owner_user_id`、`privacy_level in normal/sensitive`，支持 topic 与 allowed_usage 过滤，供后续 profile-mcp 和个性化练习/反馈复用。

### 2026-06-08 question-bank-mcp 验证记录

- `python -m pytest tests`：通过，Agent Harness 77 个测试通过，新增 QuestionBankMCP 6 个测试覆盖 `search_questions`、`get_cue_card`、`get_followup_templates`、source doc/chunk 引用、`question_bank:read` scope 校验和 `allowed_tools` 工具 allowlist。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过，Compose 配置可解析。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建并包含新增 MCP 工具模块。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`knowledge_service.backend=memory`，验证后已停止本轮启动的 agent-harness 容器。
- 交付边界验证：新增 `app.mcp.security.McpToolContext` 与 `app.mcp.question_bank_mcp.QuestionBankMcpTools`，工具调用必须携带 `user_id/session_id` 和 `question_bank:read` scope。
- 题库索引增强：`QuestionBankIndexer` 现在为 Part 2 cue card 和 active follow-up templates 写入结构化 metadata，`question-bank-mcp` 可稳定返回 cue card prompt、bullet points、准备/回答时长与追问模板。
- 文档同步：已更新 `docs/knowledge_chunk_spec.md` 和 `services/agent-harness/README.md`，说明 question-bank-mcp 的工具边界、scope 和 source 引用。

### 2026-06-08 profile-mcp 验证记录

- `python -m pytest tests`：通过，Agent Harness 88 个测试通过，新增 ProfileMCP 8 个测试覆盖 `get_user_background_summary`、`get_privacy_exclusions`、source doc/chunk 引用、`profile:read` scope 校验、`allowed_tools` 工具 allowlist、按 `allowed_usage` 过滤、隐私排除读取和跨用户边界。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过，Compose 配置可解析。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建并包含新增 Profile MCP 与模型供应商配置。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `model_provider.api_format=anthropic` 与完整 MiMo 可用模型清单；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器。
- 交付边界验证：新增 `app.mcp.profile_mcp.ProfileMcpTools` 与 `PostgresProfilePrivacySource`，背景摘要工具只使用 `McpToolContext.user_id` 检索当前用户 facts，不接受外部 user_id；默认不返回 private facts。
- 文档同步：已更新 `services/agent-harness/README.md`，说明 profile-mcp 的工具边界、scope、隐私过滤和 privacy source。

### 2026-06-08 rubric-mcp 验证记录

- `python -m pytest tests`：通过，Agent Harness 94 个测试通过，新增 RubricMCP 6 个测试覆盖 `retrieve_speaking_band_descriptor`、`get_anchor_samples`、band range、`policy_type` 过滤、`anchor_sample_id` 过滤、source doc/chunk 引用、`rubric:read` scope 校验和 `allowed_tools` 工具 allowlist。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过，Compose 配置可解析。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建并包含新增 Rubric MCP。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic` 与完整 MiMo 可用模型清单；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器。
- 交付边界验证：新增 `app.mcp.rubric_mcp.RubricMcpTools`，评分标准工具可返回 official descriptor / internal policy / anchor examples，并保留 source doc/chunk 供 ScoringWorkflow 写入评分证据和 Trace。
- 文档同步：已更新 `services/agent-harness/README.md`，说明 rubric-mcp 的工具边界、scope、检索过滤和 source 引用。

### 2026-06-08 speech-metrics-mcp 验证记录

- `python -m pytest tests`：通过，Agent Harness 102 个测试通过，新增 SpeechMetricsMCP 8 个测试覆盖 `compute_wpm`、`detect_long_pauses`、`estimate_filler_ratio`、`get_asr_confidence`、`get_turn_audio_metrics`、`speech_metrics:read` scope 校验、`allowed_tools` 工具 allowlist、PostgreSQL 归属约束 SQL 与 row 映射。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过，Compose 配置可解析。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建并包含新增 Speech Metrics MCP。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic` 与完整 MiMo 可用模型清单；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器。
- 交付边界验证：新增 `app.mcp.speech_metrics_mcp.SpeechMetricsMcpTools` 与 `PostgresSpeechMetricsSource`，可即时计算 WPM、长停顿、filler ratio、ASR confidence，也可按 `McpToolContext.user_id/session_id` 读取 turn 级持久化指标。
- 文档同步：已更新 `services/agent-harness/README.md`，说明 speech-metrics-mcp 的工具边界、scope、即时计算与 Postgres source。

### 2026-06-08 report-mcp 验证记录

- `python -m pytest tests`：通过，Agent Harness 110 个测试通过，新增 ReportMCP 8 个测试覆盖 `save_score_report`、`save_feedback`、`save_reference_answer`、四维 criteria 与官方免责声明校验、session scope 校验、`report:write` scope 校验、`allowed_tools` 工具 allowlist、写入审计记录和 PostgreSQL SQL helper。
- `pnpm --filter @ielts-speaking/protocol validate`：通过，4 个共享 schema 编译通过。
- `docker compose config --quiet`：通过，Compose 配置可解析。
- `docker compose build --pull=false agent-harness`：通过，Python 3.12 容器镜像可构建并包含新增 Report MCP。
- `/healthz` 容器验证：短暂启动 agent-harness 后返回 `status=ok`、`model_provider.api_format=anthropic` 与完整 MiMo 可用模型清单；响应中未泄露 API key，验证后已停止本轮启动的 agent-harness 容器。
- 交付边界验证：新增 `app.mcp.report_mcp.ReportMcpTools`、`PostgresReportStore` 与 `ReportAuditSink`，报告写入工具可事务化保存 `score_reports`、`criterion_scores`、`study_plans`、`feedback_items`、`reference_answers`，并为每次成功写入记录 user/session/tool/request/target 审计摘要。
- 文档同步：已更新 `services/agent-harness/README.md`，说明 report-mcp 的写入边界、scope、Postgres store 与审计要求。

## 1. 任务状态定义

| 状态 | 含义 |
|---|---|
| TODO | 尚未开始 |
| IN_PROGRESS | 研发中 |
| BLOCKED | 被依赖、资源或决策阻塞 |
| REVIEW | 已提交，等待 Code Review / 产品验收 |
| DONE | 已完成并通过验收 |
| DEFERRED | 明确延期，不属于当前阶段 |

---

## 2. 优先级定义

| 优先级 | 含义 |
|---|---|
| P0 | 没有该任务无法形成核心闭环 |
| P1 | MVP 必须完成，但可在 P0 后推进 |
| P2 | 体验增强或稳定性增强 |
| P3 | 后续迭代优化 |

---

## 3. 角色建议

| 角色 | 主要职责 |
|---|---|
| PM / Product | 产品目标、需求边界、验收标准、运营策略 |
| Tech Lead | 架构决策、模块边界、代码规范、质量门禁 |
| FE | Next.js、Live UI、音频交互、复盘页、后台页面 |
| BE-Go | Go API、WebSocket、数据库、对象存储、鉴权、任务队列 |
| AI/Agent | Agent Harness、Prompt、MCP、RAG、评分、评测 |
| DevOps | Docker、CI/CD、监控、日志、安全、环境配置 |
| QA | 测试用例、端到端测试、回归测试、兼容性测试 |
| Content/Ops | 题库、知识库、评分样本、审核与运营 |

---

## 4. 阶段总览

| 阶段 | 阶段名称 | 目标效果 | 核心交付 |
|---|---|---|---|
| Phase 0 | 项目初始化与架构确认 | 项目边界清晰，仓库、规范和环境准备完成 | 架构文档、Repo、Docker 基线、API 约定 |
| Phase 1 | 数据层与基础后端 | 用户、题库、会话、音频、报告等核心数据可存取 | DB schema、Go API、对象存储 |
| Phase 2 | Agent Harness 骨架 | Agent 服务可被 Go 调用，工作流和模型适配跑通 | Agent Runtime、MiMo Adapter、Trace |
| Phase 3 | MCP 与 RAG 知识库 | 题库、用户背景、Rubric、历史复盘可被 Agent 检索 | LlamaIndex、MCP Tools、索引任务 |
| Phase 4 | Live 口语交互闭环 | 用户能完成一次语音问答回合 | WebSocket、录音、ASR、TTS、前端状态机 |
| Phase 5 | 完整考试与练习模式 | Part 1/2/3 可完整跑通，支持单项练习 | ExamWorkflow、PracticeWorkflow |
| Phase 6 | 四维评分与复盘 | 完整报告可生成、保存、查看、回放 | ScoringWorkflow、Report UI |
| Phase 7 | 评测、观测与安全 | Agent 质量可回归，问题可追踪，安全边界可控 | Langfuse、DeepEval、Ragas、Promptfoo |
| Phase 8 | 内测优化与发布准备 | 达到内测可用质量 | Bug 修复、性能优化、部署文档 |

---

# Phase 0：项目初始化与架构确认

## P0-001 确认 MVP 范围

- 状态：DONE
- 优先级：P0
- 负责人：PM / Tech Lead
- 依赖：无
- 任务内容：确认 MVP 必须支持的用户路径、模式、题库范围、评分范围、复盘范围。
- 交付物：MVP Scope 文档。
- 完成目标效果：团队对第一版“必须做什么”和“明确不做什么”形成一致理解，避免研发过程中频繁变更核心范围。
- 验收标准：
  - 明确 full_exam、part_practice、topic_practice 三种模式是否进入 MVP。
  - 明确 Avatar、A2A、教师端、支付等是否延期。
  - 明确首版题库来源、数量、审核策略。

## P0-002 输出系统架构基线

- 状态：DONE
- 优先级：P0
- 负责人：Tech Lead
- 依赖：P0-001
- 任务内容：确认前端、Go 后端、Agent Harness、数据层、RAG、MCP、观测体系的边界。
- 交付物：Architecture Decision Record，架构图，模块边界说明。
- 完成目标效果：后续研发可以按模块并行推进，不出现 Go 后端和 Agent 层职责混乱。
- 验收标准：
  - 明确 Go Backend 不直接拼复杂 Prompt。
  - 明确 Agent Harness 不直接处理用户鉴权和业务权限。
  - 明确工具调用走 MCP 或内部受控接口。

## P0-003 初始化 Monorepo

- 状态：DONE
- 优先级：P0
- 负责人：Tech Lead / DevOps
- 依赖：P0-002
- 任务内容：创建项目仓库结构。
- 推荐结构：

```text
ielts-speaking-platform/
  apps/web
  services/api-go
  services/agent-harness
  services/worker
  packages/protocol
  infra
  docs
```

- 交付物：可克隆运行的基础仓库。
- 完成目标效果：研发人员可以统一从仓库开始开发，不再各自创建零散项目。
- 验收标准：
  - README 说明本地启动方式。
  - 每个服务有独立 README。
  - 基础 lint/test 命令存在。

## P0-004 定义代码规范与分支策略

- 状态：DONE
- 优先级：P1
- 负责人：Tech Lead
- 依赖：P0-003
- 任务内容：定义分支、提交、Code Review、版本号、发布流程。
- 交付物：CONTRIBUTING.md。
- 完成目标效果：多人协作时提交风格、Review 规则和发布节奏一致。
- 验收标准：
  - main/dev/feature 分支策略明确。
  - commit message 规则明确。
  - PR 模板包含测试、风险、回滚说明。

## P0-005 准备 Docker Compose 基线

- 状态：DONE
- 优先级：P0
- 负责人：DevOps / BE-Go
- 依赖：P0-003
- 任务内容：编写 docker-compose.yml，包含 web、api、agent、postgres、redis、minio。已完成：`docker-compose.yml` 包含 web、api-go、agent-harness、postgres、redis、minio，并配置服务依赖与健康检查。
- 交付物：本地一键启动环境。已完成：`docker compose config --quiet`、镜像构建、迁移、`docker compose up -d` 和服务 health 多轮验证通过。
- 完成目标效果：新成员能在本地快速启动基础环境。已完成：`.env.example` 提供本地默认配置，Compose 可启动完整本地链路。
- 验收标准：
  - `docker compose up` 后服务可启动。已验证：api-go、agent-harness、PostgreSQL、Redis、MinIO 均可 healthy。
  - PostgreSQL、Redis、MinIO 健康检查可用。已验证：compose healthcheck 已配置并通过。
  - 环境变量通过 `.env.example` 提供。已验证：`.env.example` 存在且不包含真实密钥。

## P0-006 制定环境变量与密钥管理规范

- 状态：DONE
- 优先级：P0
- 负责人：DevOps / Tech Lead
- 依赖：P0-005
- 任务内容：定义 MiMo API Key、数据库、对象存储、JWT、Langfuse 等配置方式。
- 交付物：.env.example、配置文档。
- 完成目标效果：密钥不会硬编码到代码或仓库，环境差异可控。
- 验收标准：
  - `.env.example` 不包含真实密钥。
  - 本地/dev/staging/prod 配置项清晰。
  - 服务启动缺失关键配置时有明确错误提示。

## P0-007 定义通用协议 Schema

- 状态：DONE
- 优先级：P0
- 负责人：Tech Lead / BE-Go / AI/Agent / FE
- 依赖：P0-002
- 任务内容：定义 WebSocket 事件、Agent API 请求响应、评分报告 JSON Schema。
- 交付物：packages/protocol 下的 schema 文件。
- 完成目标效果：前端、Go、Agent 三方可以基于协议并行开发。
- 验收标准：
  - session event schema 可校验。
  - scoring report schema 可校验。
  - agent run schema 可校验。

---

# Phase 1：数据层与基础 Go 后端

## P1-001 设计 PostgreSQL 基础 Schema

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / Tech Lead
- 依赖：P0-002
- 任务内容：设计 users、profiles、sessions、turns、questions、reports、audio_assets 等表。
- 交付物：数据库 ER 图、迁移脚本。
- 完成目标效果：核心业务数据有稳定模型，后续 Agent、前端、报告都能引用统一 ID。
- 验收标准：
  - 支持用户、题库、会话、音频、ASR、评分报告关联。
  - 关键字段包含 created_at、updated_at、deleted_at 或审计策略。
  - 可通过迁移工具初始化数据库。

## P1-002 接入 pgvector

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / AI/Agent
- 依赖：P1-001
- 任务内容：启用 pgvector，设计 knowledge_chunks / embeddings 表。
- 交付物：向量表迁移脚本、索引策略。
- 完成目标效果：MVP 可在 PostgreSQL 内完成题库和知识库相似度检索。
- 验收标准：
  - 可以写入 embedding。
  - 可以按向量相似度检索 Top K。
  - 支持 metadata filter：season、part、topic、source_type。

## P1-003 实现用户与鉴权模块

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go
- 依赖：P1-001
- 任务内容：实现登录、注册、JWT/session、用户信息获取。
- 交付物：Auth API。
- 完成目标效果：用户可以安全登录，所有业务接口可以拿到当前用户身份。
- 验收标准：
  - 支持注册/登录/刷新 token。
  - 接口有鉴权中间件。
  - WebSocket 连接可鉴权。

## P1-004 实现用户背景问卷 API

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / FE / AI/Agent
- 依赖：P1-003
- 任务内容：实现背景问卷保存、更新、查询、隐私排除字段。
- 交付物：Background API、问卷 schema。
- 完成目标效果：系统能结构化保存用户背景，为题库个性化和参考答案生成提供依据。
- 验收标准：
  - 支持结构化字段和自由补充。
  - 支持用户标记“不希望使用的信息”。
  - Agent 工具检索时不会返回禁用字段。

## P1-005 实现题库基础数据模型

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / Content/Ops
- 依赖：P1-001
- 任务内容：实现 seasons、topics、questions、cue_cards、followup_templates。
- 交付物：题库表和 CRUD API。
- 完成目标效果：系统可以按季度、Part、主题管理题目。
- 验收标准：
  - 支持 active/draft/archived 状态。
  - 题目有 source_type、license、review_status。
  - 支持 Part 1/2/3 不同题型结构。

## P1-006 实现题库导入功能

- 状态：DONE
- 优先级：P1
- 负责人：BE-Go / Content/Ops
- 依赖：P1-005
- 任务内容：支持 CSV/JSON 导入题库，返回导入结果和错误行。
- 交付物：导入 API、导入模板。
- 完成目标效果：运营可以批量维护季度题库。
- 验收标准：
  - 导入重复题目有去重或提示。
  - 错误数据不会污染正式题库。
  - 导入记录可追踪。

## P1-007 实现会话模型与 API

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go
- 依赖：P1-001、P1-005
- 任务内容：实现 practice_sessions、session_parts、session_turns。
- 交付物：Session API。
- 完成目标效果：用户可以创建练习/考试会话，系统可以记录每一轮问题和回答。
- 验收标准：
  - 支持 full_exam、part_practice、topic_practice。
  - 支持 session status 流转。
  - 支持 turn 级别记录 question、asr、audio、metrics。

## P1-008 实现音频资产服务

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / DevOps
- 依赖：P0-005、P1-007
- 任务内容：接入 MinIO/S3，支持录音上传、TTS 音频保存、签名 URL。
- 交付物：Audio API。
- 完成目标效果：用户录音和考官音频可以安全保存与回放。
- 验收标准：
  - 上传成功后生成 audio_asset 记录。
  - 支持签名 URL。
  - 文件类型、大小、时长有限制。

## P1-009 实现 WebSocket Gateway 骨架

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / FE
- 依赖：P1-003、P0-007
- 任务内容：实现前端与 Go 后端的 WebSocket 通道。
- 交付物：WebSocket Hub。
- 完成目标效果：前端可以实时收到 session 状态、考官消息、计时、ASR、评分进度。
- 验收标准：
  - WebSocket 鉴权可用。
  - 支持按 session_id 广播。
  - 支持断线重连基础策略。

## P1-010 实现 Model Call 审计表

- 状态：DONE
- 优先级：P1
- 负责人：BE-Go / AI/Agent
- 依赖：P1-001
- 任务内容：记录模型调用的模型名、用途、延迟、token、错误。
- 交付物：model_calls 表和写入 API。
- 完成目标效果：能够统计成本、排查质量问题、定位慢请求。
- 验收标准：
  - 每次关键模型调用有 run_id/session_id。
  - 错误有 error_code/error_message。
  - 敏感输入不明文记录或做脱敏。

---

# Phase 2：Agent Harness 骨架

## P2-001 初始化 Agent Harness 服务

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / DevOps
- 依赖：P0-003、P0-005
- 任务内容：创建 Python FastAPI 服务，接入 Microsoft Agent Framework。已完成：FastAPI Agent Harness、确定性工作流、`agent-framework-core` 依赖与 Microsoft Agent Framework runtime adapter 边界已落地；深度 workflow graph 迁移作为后续增强，不影响 MVP 主链路验收。
- 交付物：agent-harness 服务骨架。已完成：`services/agent-harness`、`app.core.runtime.AgentRuntime`、`docs/agent_runtime_boundary.md`。
- 完成目标效果：Go 后端可以调用 Agent 服务健康检查和基础接口。已完成：Go 可调用 `/healthz`、session plan/consume-asr/next-turn/score、run summary、trace、cancel 与 metrics。
- 验收标准：
  - `/healthz` 可用。已验证：返回 `status=ok`，包含模型、ASR/TTS、Knowledge Service 与 runtime adapter 摘要。
  - Docker 可启动。已验证：agent-harness 容器可构建并 health=healthy。
  - 日志格式统一。已验证：HTTP middleware 输出 request_id、session_id、method、path、status_code、latency_ms 结构化日志字段。

## P2-002 封装 MiMoChatClient

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P2-001、P0-006
- 任务内容：封装 MiMo OpenAI-compatible/Anthropic-compatible 调用。
- 交付物：models/mimo_client.py。
- 完成目标效果：Agent 代码不直接依赖底层 HTTP 细节，可以统一切换模型和参数。
- 验收标准：
  - 支持 mimo-v2.5-pro。
  - 支持流式/非流式文本。
  - 支持 tool call 或结构化输出适配。
  - 支持超时、重试、错误分类。

## P2-003 实现 Model Router

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent
- 依赖：P2-002
- 任务内容：按任务类型选择模型，如评分、组卷、反馈、低成本任务。
- 交付物：model_router.py。
- 完成目标效果：不同任务可独立调整模型，不影响工作流代码。
- 验收标准：
  - 支持通过配置切换模型。
  - 支持 fallback 模型。
  - 支持为不同任务设置 temperature、max_tokens。

## P2-004 定义 Agent Run 数据结构

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / BE-Go
- 依赖：P0-007
- 任务内容：定义 agent_run、agent_step、tool_call、workflow_node 的结构。
- 交付物：Agent Run Schema。
- 完成目标效果：每次 Agent 执行都可追踪、可复盘、可定位问题。
- 验收标准：
  - run_id 可贯穿 Go、Agent、前端事件。
  - 每个节点记录输入摘要、输出摘要、耗时、错误。
  - 支持写入 Langfuse 或内部审计。

## P2-005 实现 ExamWorkflow 最小版本

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P2-002、P2-004
- 任务内容：实现最小考试工作流，先用 mock question 和 mock user answer。
- 交付物：exam_workflow.py。
- 完成目标效果：Harness 能控制一次简化口语流程。
- 验收标准：
  - 能输出 examiner.message 事件。
  - 能接收 asr_text。
  - 能决定 next_question 或 finish。

## P2-006 实现 PracticeWorkflow 最小版本

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent
- 依赖：P2-005
- 任务内容：实现 Part 单项练习与 topic_practice 基础流程。
- 交付物：practice_workflow.py。
- 完成目标效果：系统可以只练 Part 1、Part 2 或 Part 3。
- 验收标准：
  - 支持 mode 参数。
  - 支持练习模式显示提示。
  - 不影响考试模式严肃流程。

## P2-007 实现 Agent API

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / BE-Go
- 依赖：P2-005
- 任务内容：实现 `/agent/sessions/{id}/plan`、`/next-turn`、`/consume-asr`。
- 交付物：Agent HTTP API。
- 完成目标效果：Go 后端可以把用户会话推进请求交给 Agent Harness。
- 验收标准：
  - 请求/响应符合 schema。
  - 错误返回可被 Go 网关识别。
  - 每次调用都有 run_id。

## P2-008 实现 AG-UI 风格事件适配器

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / FE / BE-Go
- 依赖：P0-007、P2-005
- 任务内容：把工作流节点输出转换成前端可理解事件。
- 交付物：protocols/ag_ui_events.py。
- 完成目标效果：Agent 内部流程变化不直接影响前端 UI。
- 验收标准：
  - 支持 examiner.message、timer.started、part.started、scoring.started 等事件。
  - 事件 payload 可校验。
  - Go Backend 可直接转发。

## P2-009 接入 Langfuse Trace 初版

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent / DevOps
- 依赖：P2-004
- 任务内容：记录模型调用、Prompt 版本、工具调用、工作流节点耗时。
- 交付物：Langfuse 集成。
- 完成目标效果：AI 质量问题可以通过 Trace 定位。
- 验收标准：
  - 每次 Agent API 调用在 Langfuse 有 trace。
  - trace 包含 session_id/run_id。
  - 敏感信息有脱敏策略。

## P2-010 实现结构化输出校验

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P2-002、P0-007
- 任务内容：使用 Pydantic/JSON Schema 校验模型输出。
- 交付物：structured_output.py。
- 完成目标效果：评分、追问、报告等关键输出不会因模型格式漂移导致系统崩溃。
- 验收标准：
  - 输出不合法时自动重试或返回 recoverable error。
  - 所有关键 Agent 输出有 schema。
  - 错误被记录到 trace。

---

# Phase 3：MCP 与 RAG 知识库

## P3-001 初始化 LlamaIndex Knowledge Service

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P1-002、P2-001
- 任务内容：构建 LlamaIndex 服务，连接 pgvector。
- 交付物：llamaindex_service.py。
- 完成目标效果：Agent 可以通过统一接口检索题库、Rubric、用户背景。
- 验收标准：
  - 支持 ingest documents。
  - 支持 retrieve Top K。
  - 支持 metadata filter。

## P3-002 设计知识 Chunk 规范

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / Content/Ops
- 依赖：P3-001
- 任务内容：定义题库、Rubric、主题知识、用户背景的 chunk 粒度与 metadata。
- 交付物：Knowledge Chunk Spec。
- 完成目标效果：检索结果可控、可解释、可过滤。
- 验收标准：
  - question chunk 包含 season、part、topic、source_type。
  - rubric chunk 包含 criterion、band、descriptor。
  - user chunk 包含 privacy_level、allowed_usage。

## P3-003 实现题库索引任务

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / BE-Go
- 依赖：P1-005、P3-002
- 任务内容：把题库同步到 question_bank_index。
- 交付物：embedding job。
- 完成目标效果：Agent 可以按 Part、主题、季度检索题目。
- 验收标准：
  - 新增/更新题目后可重新索引。
  - 支持按 active season 检索。
  - 检索结果返回 question_id。

## P3-004 实现 Rubric 索引任务

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / Content/Ops
- 依赖：P3-002
- 任务内容：录入四维评分标准、内部评分说明、anchor examples。
- 交付物：rubric_index。
- 完成目标效果：评分 Agent 可检索相关评分标准和示例。
- 验收标准：
  - 可按 criterion 检索。
  - 可按 band 范围检索。
  - anchor examples 可被评分工作流引用。

## P3-005 实现用户背景索引任务

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / BE-Go
- 依赖：P1-004、P3-002
- 任务内容：将背景问卷转成可检索事实。
- 交付物：user_profile_index。
- 完成目标效果：系统可基于用户背景生成更自然问题和参考答案。
- 验收标准：
  - 禁用字段不会进入 Agent 可用上下文。
  - 背景事实可按 topic 检索。
  - 用户更新问卷后索引可更新。

## P3-006 实现 question-bank-mcp

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / BE-Go
- 依赖：P3-003
- 任务内容：暴露题库相关工具。
- 交付物：question-bank-mcp 工具边界。
- 完成目标效果：Agent 通过标准工具访问题库，不直接访问数据库。
- 验收标准：
  - search_questions 可用。已完成：复用 QuestionBankIndexer，支持 active season、Part、topic、Top K，并返回 source doc/chunk。
  - get_cue_card 可用。已完成：基于结构化 metadata 返回 Part 2 cue card prompt、bullet points、准备/回答时长。
  - get_followup_templates 可用。已完成：返回 active follow-up templates，并支持按 Part 过滤。
  - 工具有 user/session scope。已完成：McpToolContext 强制 `user_id/session_id`，并校验 `question_bank:read` scope 与 `allowed_tools`。

## P3-007 实现 profile-mcp

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / BE-Go
- 依赖：P3-005
- 任务内容：暴露用户背景检索工具。
- 交付物：profile-mcp 工具边界。
- 完成目标效果：Agent 能获得允许使用的用户背景事实。
- 验收标准：
  - get_user_background_summary 可用。已完成：按 `topic`、`allowed_usage` 与 Top K 检索当前用户允许使用的背景事实，并返回摘要和 source doc/chunk。
  - get_privacy_exclusions 可用。已完成：通过 `ProfilePrivacySource` / `PostgresProfilePrivacySource` 读取最新背景问卷的 privacy exclusions。
  - 工具不允许越权查询其他用户。已完成：工具方法不接受外部 `user_id`，只使用 `McpToolContext.user_id`；测试覆盖跨用户事实不会返回。

## P3-008 实现 rubric-mcp

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P3-004
- 任务内容：暴露评分标准检索工具。
- 交付物：rubric-mcp 工具边界。
- 完成目标效果：评分 Agent 可以引用标准和内部校准规则。
- 验收标准：
  - retrieve_speaking_band_descriptor 可用。已完成：支持 criterion、band range、band list、policy type 与 Top K。
  - get_anchor_samples 可用。已完成：默认限定 `policy_type=anchor_example`，支持 criterion、band 与 anchor_sample_id 过滤。
  - 输出包含 source/chunk_id。已完成：返回 `source_ref.doc_id`、`source_ref.chunk_id` 与 `source_ref.source`。

## P3-009 实现 speech-metrics-mcp

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent / BE-Go
- 依赖：P1-008、P1-007
- 任务内容：暴露语音指标工具，如 WPM、长停顿、回答时长。
- 交付物：speech-metrics-mcp 工具边界。
- 完成目标效果：评分 Agent 能结合客观语音指标判断 fluency 和 pronunciation。
- 验收标准：
  - compute_wpm 可用。已完成：支持 `duration_ms + words_count` 或 `duration_ms + transcript` 计算 WPM。
  - detect_long_pauses 可用。已完成：支持 pause segments、阈值、长停顿数量、总停顿时长与平均长停顿。
  - 返回指标包含 confidence。已完成：WPM、长停顿、filler ratio、ASR confidence 与 turn audio metrics 均返回 confidence。

## P3-010 实现 report-mcp

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent / BE-Go
- 依赖：P1-007
- 任务内容：暴露保存评分、反馈、参考答案的工具。
- 交付物：report-mcp 工具边界。
- 完成目标效果：Agent 生成的报告可以通过工具持久化。
- 验收标准：
  - save_score_report 可用。已完成：保存 score report、四维 criterion scores 与 next practice plan，并校验 session scope、四维 criteria 与官方免责声明。
  - save_feedback 可用。已完成：保存 feedback item，并通过 report ownership 校验归属。
  - 工具调用写审计日志。已完成：每次成功写入通过 `ReportAuditSink` 记录 user_id、session_id、tool_name、request_id、target_id。

## P3-011 增加 MCP 权限与审计

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / BE-Go / DevOps
- 依赖：P3-006 至 P3-010
- 任务内容：为 MCP 工具调用增加 allowlist、scope、审计日志。
- 交付物：MCP security middleware。已完成：`app.mcp.security` 提供 `McpToolContext`、`authorize_tool_call()`、`McpAuditRecord`、`McpAuditSink`、默认内存审计 sink 与用户 ID 哈希。
- 完成目标效果：Agent 工具调用不会越权，不会绕过业务权限。
- 验收标准：
  - 每次工具调用记录 user_id_hash、session_id、tool_name。已完成：允许与拒绝调用均写入工具调用级审计记录，并记录 request_id、status、reason、required scopes 与 granted scopes。
  - 未授权工具调用被拒绝。已完成：缺失 scope、未在 `allowed_tools` allowlist、命中 `disabled_tools` 均抛出 `McpAuthorizationError`。
  - 高风险工具可配置禁用。已完成：`disable_high_risk_tools=true` 可禁用 report 写入类工具，显式 `high_risk_tools=None` 会回退默认高风险清单，避免配置绕过。

---

# Phase 4：Live 口语交互闭环

## P4-001 实现前端项目骨架

- 状态：DONE
- 优先级：P0
- 负责人：FE
- 依赖：P0-003
- 任务内容：初始化 Next.js + TypeScript + Tailwind + shadcn/ui。
- 交付物：apps/web。
- 完成目标效果：前端基础页面和组件体系可开发。
- 验收标准：
  - 本地可启动。
  - 路由结构清晰。
  - UI 组件库可用。

## P4-002 实现登录与基础布局

- 状态：DONE
- 优先级：P0
- 负责人：FE / BE-Go
- 依赖：P1-003、P4-001
- 任务内容：登录页、主布局、用户状态、路由保护。
- 交付物：Auth UI。
- 完成目标效果：用户可登录后进入练习首页。
- 验收标准：
  - 未登录访问练习页会跳转登录。
  - 登录状态刷新后保持。
  - 移动端布局可用。

## P4-003 实现背景问卷页面

- 状态：DONE
- 优先级：P0
- 负责人：FE / BE-Go
- 依赖：P1-004、P4-002
- 任务内容：实现结构化问卷、隐私排除、保存提示。
- 交付物：Background Profile UI。
- 完成目标效果：用户可以完成个性化练习所需背景资料。
- 验收标准：
  - 支持保存和编辑。
  - 支持不愿使用信息标记。
  - 表单在移动端可用。

## P4-004 实现模式选择页

- 状态：DONE
- 优先级：P0
- 负责人：FE / PM
- 依赖：P4-002
- 任务内容：提供完整模拟、Part 单练、主题练习入口。
- 交付物：Practice Mode UI。
- 完成目标效果：用户可清楚选择练习目标。
- 验收标准：
  - 展示每种模式说明。
  - 可选择 Part 和主题。
  - 创建 session 成功后进入 Live 页面。

## P4-005 实现 Live 页面基础布局

- 状态：DONE
- 优先级：P0
- 负责人：FE
- 依赖：P4-001、P0-007
- 任务内容：实现 Live 口语页面布局。
- 交付物：Live Speaking UI。
- 完成目标效果：页面结构能承载考官、字幕、录音、倒计时、题卡和操作按钮。
- 验收标准：
  - 桌面端和移动端均可用。
  - 有 Part 进度、题目区域、录音区域、操作栏。
  - 支持考试模式隐藏提示。

## P4-006 实现前端 WebSocket Client

- 状态：DONE
- 优先级：P0
- 负责人：FE / BE-Go
- 依赖：P1-009、P0-007
- 任务内容：连接 WebSocket，处理 session 事件。
- 交付物：useSessionSocket。
- 完成目标效果：前端可以实时响应后端/Agent 事件。
- 验收标准：
  - 支持连接、断线、重连。
  - 支持事件 schema 校验或类型约束。
  - 事件可驱动 UI 状态变化。

## P4-007 实现浏览器录音

- 状态：DONE
- 优先级：P0
- 负责人：FE
- 依赖：P4-005
- 任务内容：使用 MediaRecorder 获取麦克风、录音、停止、上传。
- 交付物：Audio Recorder Module。
- 完成目标效果：用户可以在浏览器完成回答录音。
- 验收标准：
  - 首次使用有麦克风授权提示。
  - 支持录音开始/暂停/结束。
  - 录音文件可上传到后端。

## P4-008 实现本地静音检测 MVP

- 状态：DONE
- 优先级：P1
- 负责人：FE
- 依赖：P4-007
- 任务内容：基于 Web Audio API 检测音量和长时间静音。
- 交付物：VAD MVP。
- 完成目标效果：用户停顿过久时系统可以提示或自动准备提交。
- 验收标准：
  - 能检测连续静音。
  - 阈值可配置。
  - 不会频繁误触发。

## P4-009 实现倒计时组件

- 状态：DONE
- 优先级：P0
- 负责人：FE
- 依赖：P4-005
- 任务内容：支持 Part 1/2/3 的建议用时、准备倒计时、警告提示。
- 交付物：Timer Component。
- 完成目标效果：用户能感知考试节奏。
- 验收标准：
  - Part 2 支持 60 秒准备。
  - 支持 60/30/10 秒提醒。
  - 练习模式和考试模式提示样式不同。

## P4-010 实现 TTS 音频播放

- 状态：DONE
- 优先级：P0
- 负责人：FE / BE-Go
- 依赖：P1-008、P4-005
- 任务内容：前端播放考官 TTS 音频，支持重听和打断。
- 交付物：Examiner Audio Player。
- 完成目标效果：考官问题以语音形式播出。
- 验收标准：
  - 收到 examiner.audio_ready 后播放。
  - 支持打断播放。
  - 支持重听当前问题。

## P4-011 实现 Live2D Avatar MVP

- 状态：DONE
- 优先级：P2
- 负责人：FE
- 依赖：P4-010
- 任务内容：接入 Live2D 模型，支持 speaking/listening/idle 状态。
- 交付物：Avatar Component。
- 完成目标效果：提升真实考官临场感，但不影响核心考试流程。
- 验收标准：
  - 考官说话时 Avatar 有口型或状态变化。
  - 用户回答时 Avatar 进入 listening 状态。
  - 低性能设备可关闭 Avatar。

## P4-012 打通单轮问答闭环

- 状态：DONE
- 优先级：P0
- 负责人：FE / BE-Go / AI/Agent
- 依赖：P2-007、P4-006、P4-007、P4-010
- 任务内容：从创建 session 到考官提问、用户录音、上传、ASR、下一题事件。
- 交付物：Single Turn E2E Demo。
- 完成目标效果：项目具备最小 Live 语音交互闭环。
- 验收标准：
  - 用户能听到问题。
  - 用户能录音并提交。
  - ASR 结果能回显。
  - Agent 能返回下一步事件。

---

# Phase 5：完整考试与练习模式

## P5-001 实现 QuestionSetPlannerAgent

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P3-006、P3-007
- 任务内容：根据模式、题库、用户背景、目标分数生成题组。
- 交付物：question_planner_agent.py。已完成：新增 `app.agents.question_planner_agent.QuestionSetPlannerAgent`、`QuestionSetPlan`、`QuestionPartPlan`、`PlannedQuestion`，并接入 `ExamWorkflow` 与 `PracticeWorkflow`。
- 完成目标效果：系统能自动生成合理的 Part 1/2/3 题组。
- 验收标准：
  - full_exam 包含 Part 1/2/3。已完成：默认生成 Part 1/2/3 题组，MVP 题量为 4/1/2。
  - part_practice 只生成指定 Part。已完成：`part_practice` 只规划请求中的目标 Part，`topic_practice` 支持指定 Part 或 Part 1 -> Part 2 -> Part 3。
  - 不重复抽取高度相似问题。已完成：按 `question_id` 和题面 token Jaccard 相似度去重，避免同题或高度相似题进入同一题组。

## P5-002 实现 ExaminerAgent

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P5-001、P2-010
- 任务内容：生成符合 IELTS 考官风格的问题和过渡语。
- 交付物：examiner_agent.py。已完成：新增 `app.agents.examiner_agent.ExaminerAgent`、`ExaminerTurnInput`、`ExaminerUtterance`，并接入 `ExamWorkflow` 与 `PracticeWorkflow`。
- 完成目标效果：考官自然、克制、简洁，不像普通聊天机器人。
- 验收标准：
  - 考试模式不主动给答题建议。已完成：`full_exam` 禁止 `practice_mode`，练习提示只在练习工作流的 `practice_hints` 字段输出。
  - 问题长度适合口语考试。已完成：输出统一压缩空白并限制最大长度，Part 1/3 简洁提问，Part 2 只追加真实考试式 long-turn 引导。
  - 不泄露评分规则和内部 Prompt。已完成：基础过滤 `system prompt`、`rubric`、`scoring rule` 等内部术语，后续 GuardrailAgent 接入前先保住话术边界。

## P5-003 实现 FollowupPlannerAgent

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P5-002、P3-006、P3-007
- 任务内容：根据用户回答规划追问。
- 交付物：followup_planner_agent.py。已完成：新增 `app.agents.followup_planner_agent.FollowupPlannerAgent`、`FollowupPlannerInput` 和 `FollowupPlan`，并接入 `ExamWorkflow.consume_asr` 与 `PracticeWorkflow.consume_asr`。
- 完成目标效果：系统能根据回答动态追问，而不是机械读题。
- 验收标准：
  - Part 3 追问更抽象。已完成：Part 3 短回答追问使用更泛化的社会/人群视角问题。
  - 回答过短时可以自然追问。已完成：按 Part 设置最小词数阈值，短回答直接返回追问 `examiner.message`。
  - 不过度追问私人敏感信息。已完成：邮箱、手机号、地址、薪资、证件、密码、工作地点等敏感线索触发 privacy guard，跳过私人追问并进入下一题。

## P5-004 完成 Part 1 流程

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / FE / BE-Go
- 依赖：P5-001、P5-002、P4-012
- 任务内容：实现 Part 1 多题问答流程。
- 交付物：Part 1 Workflow。已完成：Part 1 默认 4 题，支持多话题题组、每题建议时间、Part 时间盒和自动进入下一 Part。
- 完成目标效果：用户能完成 4-5 分钟左右的 Part 1 模拟。
- 验收标准：
  - 多个日常话题自然切换。已完成：fallback 题组覆盖 hometown、work/study、daily routine、free time，并在事件 payload 中返回 topic。
  - 每题建议用时正常。已完成：Part 1 每题 `suggested_seconds=30`，Part 时间盒 `timebox_seconds=300`。
  - 到时间可收束进入下一 Part。已完成：`part_elapsed_seconds >= timebox_seconds` 或题目问完时输出 `part.completed`，并自动进入 Part 2。

## P5-005 完成 Part 2 流程

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / FE / BE-Go
- 依赖：P5-001、P4-009、P4-012
- 任务内容：实现 cue card、1 分钟准备、1-2 分钟回答。
- 交付物：Part 2 Workflow。已完成：Part 2 事件输出 cue card、准备倒计时、回答倒计时、提醒节点和 180 秒 Part 时间盒。
- 完成目标效果：用户能体验真实 Part 2 长轮次考试。
- 验收标准：
  - 显示 cue card。已完成：`examiner.message.payload.cue_card` 输出 prompt、bullet points、preparation/speaking seconds。
  - 准备倒计时准确。已完成：`part.started` 与 `timer.started` 输出 `preparation_seconds=60`。
  - 回答倒计时和提醒准确。已完成：`speaking_seconds=120`，`warning_seconds=[60,30,10]`，`timer.started.phase=prepare_then_speak`。

## P5-006 完成 Part 3 流程

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / FE / BE-Go
- 依赖：P5-003、P5-005
- 任务内容：实现与 Part 2 主题相关的抽象讨论。
- 交付物：Part 3 Workflow。已完成：Part 3 题组继承 Part 2 cue card 上下文，并在事件 payload 中输出抽象讨论 metadata。
- 完成目标效果：Part 3 问题能从个人经历上升到社会和抽象观点。
- 验收标准：
  - 问题与 Part 2 主题相关。已完成：`QuestionSetPlannerAgent` 为 Part 3 写入 `linked_part2_question_id`、`linked_part2_topic`，fallback 题目会围绕 Part 2 主题上升到公共空间、城市生活或对应社会议题。
  - 追问具有讨论深度。已完成：Part 3 题目和事件 payload 带 `discussion_level`、`discussion_focus`，`FollowupPlannerAgent` 保持社会/人群视角的抽象追问。
  - 不生成过长或写作化问题。已完成：新增回归测试约束 Part 3 题面保持简短口语化，`ExaminerAgent` 输出克制的 Part 3 考官话术。

## P5-007 完成 full_exam 模式

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / FE / BE-Go
- 依赖：P5-004、P5-005、P5-006
- 任务内容：串联 Part 1/2/3。
- 交付物：Full Exam Mode。已完成：`ExamWorkflow` 可从 Part 1 自动推进到 Part 2、Part 3，并在完整考试结束后进入 scoring。
- 完成目标效果：用户可以完成一次完整模拟考试。
- 验收标准：
  - 从 Part 1 到 Part 3 自动推进。已完成：`next-turn` 按题目数量或 Part 时间盒输出 `part.completed`，并依次进入 Part 2、Part 3。
  - 中间状态能持久化。已完成：`plan` 初始化 `state.status=in_progress`，`consume-asr` 将 turn、Part、题目、ASR 文本、音频资产、置信度和追问决策追加进 `state.answers`，调用方可持久化返回 state。
  - 结束后进入 scoring 状态。已完成：Part 3 完成后输出 `session.completed` 与 `scoring.started`，`state.status=scoring`，`next_action=score_session`。

## P5-008 完成 part_practice 模式

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent / FE / BE-Go
- 依赖：P5-004、P5-005、P5-006
- 任务内容：支持单独练 Part 1/2/3。
- 交付物：Part Practice Mode。已完成：`PracticeWorkflow` 支持按请求 `part` 单练 Part 1、Part 2 或 Part 3，练习完成后进入 scoring。
- 完成目标效果：用户能针对薄弱部分训练。
- 验收标准：
  - 用户可选择 Part。已完成：`part_practice` 会设置 `target_parts=[part]`、`current_part=part`，并仅规划目标 Part 题组。
  - 练习模式可显示提示。已完成：`part.started`、`examiner.message`、`timer.started` 均标记 `practice_mode=true`，`part.started` 和 `examiner.message` 输出 `practice_hints`；Part 2 输出 cue card，Part 3 输出讨论 metadata。
  - 练习结束后也可评分和复盘。已完成：目标 Part 完成后输出 `session.completed` 与 `scoring.started`，`state.status=scoring`，`next_action=score_session`；`consume-asr` 会把回答写入 `state.answers` 供后续报告使用。

## P5-009 完成 topic_practice 模式

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent / FE / BE-Go
- 依赖：P3-003、P5-001
- 任务内容：支持按主题练习，如 hometown、technology、travel。
- 交付物：Topic Practice Mode。已完成：`PracticeWorkflow` 支持按 `topic_ids` 进入主题练习，并生成主题词汇、可用表达和反馈关注点。
- 完成目标效果：用户可围绕当季高频主题进行针对训练。
- 验收标准：
  - 可选择主题。已完成：`topic_practice` 保留 `topic_ids`，不指定 Part 时按 Part 1 -> Part 2 -> Part 3 推进，指定 Part 时只练目标 Part。
  - 题目来自对应 topic。已完成：fallback 题组会把 `selected topic` 占位文案渲染为具体主题，题目 metadata 保留对应 topic。
  - 反馈中包含主题词汇与表达建议。已完成：`state.topic_guidance` 和事件 payload 携带主题词汇、可用表达和 `feedback_focus`，`state.answers`、`session.completed`、`scoring.started` 均保留该反馈种子，供后续 FeedbackWorkflow 生成主题反馈。

## P5-010 实现考试/练习模式差异控制

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / FE
- 依赖：P5-007、P5-008
- 任务内容：通过 mode_policy 控制提示、参考答案、追问、评分严格度。
- 交付物：Mode Policy。已完成：新增 `app.workflows.mode_policy`，并接入 `ExamWorkflow` 与 `PracticeWorkflow` 的 state 和关键事件。
- 完成目标效果：考试模式真实，练习模式可教学。
- 验收标准：
  - 考试模式不显示中文策略提示。已完成：`full_exam` 的 `mode_policy` 禁用 `practice_hints`、结构建议、参考答案、topic guidance 和中文策略提示，并新增测试阻止考试事件 payload 出现练习字段或中文策略提示。
  - 练习模式允许显示结构建议。已完成：`part_practice` / `topic_practice` 的 `mode_policy` 使用 `coach_practice`，允许 `practice_hints`、结构建议、参考答案和诊断式评分。
  - Prompt 层和 UI 层都遵守模式策略。已完成：`mode_policy` 写入 workflow state，并随 `session.started`、`part.started`、`examiner.message`、`timer.started`、`session.completed`、`scoring.started` 等关键事件透出，后续 Prompt、UI、Scoring、Feedback 节点可统一消费。

---

# Phase 6：ASR、TTS 与音频服务

## P6-001 实现 ASR 调用服务

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / AI/Agent
- 依赖：P1-008、P2-002
- 任务内容：调用 mimo-v2.5-asr，对用户录音转写。已完成：新增 `app.audio.asr_service.AsrService` 与 `POST /agent/audio/transcribe`。
- 交付物：ASR Service。已完成：mock provider、MiMo ASR provider 边界、结构化错误处理、共享协议 schema 与 README。
- 完成目标效果：用户回答音频可以转成文本供 Agent 和报告使用。
- 验收标准：
  - 支持 wav/mp3/webm 转换或兼容处理。已完成：支持 `audio/wav`、`audio/x-wav`、`audio/mpeg`、`audio/mp3`、`audio/webm`，并规范化浏览器 codec MIME。
  - 返回 asr_text、language、confidence 或可用元信息。已完成：返回 `asr_text`、`language`、`confidence`、`provider`、`model`、`duration_ms` 与 metadata。
  - 失败时可重试或提示用户。已完成：不支持格式 415、真实模式缺少音频源 422、上游可重试错误 503，并返回 `retryable`。

## P6-002 实现 ASR 结果持久化

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go
- 依赖：P6-001、P1-007
- 任务内容：保存每个 turn 的 ASR 结果。已完成：`POST /api/sessions/:id/turns/:turn_id/asr-results` 写入 `asr_results`，并同步用户 turn 的 `answer_text`。
- 交付物：asr_results 数据写入。已完成：新增 `000002_asr_result_corrections.sql`、人工修正接口、raw response 脱敏保存和 turn/audio 归属校验。
- 完成目标效果：报告、评分和复盘都可以使用同一份转写。
- 验收标准：
  - ASR 与 audio_asset、turn 关联。已完成：保存时校验 `audio_asset_id` 必须属于当前 turn，`GetSession` 返回 turn 下 ASR 结果。
  - 支持人工修正字段。已完成：支持 `corrected_transcript`、`corrected_by_user_id`、`corrected_at`，并提供 correction API。
  - 原始响应可脱敏保存。已完成：支持 `raw_response` 输入并递归脱敏保存为 `raw_response_redacted`。

## P6-003 实现 TTS 调用服务

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / AI/Agent
- 依赖：P1-008、P2-002
- 任务内容：调用 mimo-v2.5-tts 生成考官音频。已完成：新增 `app.audio.tts_service.TTSService`、`POST /agent/audio/synthesize` 与 Go `POST /api/audio/tts` 保存链路。
- 交付物：TTS Service。已完成：Agent Harness TTS provider 边界、mock wav 生成、Go AgentHarnessTTSClient、对象存储保存和协议 schema。
- 完成目标效果：考官消息可以转换成自然语音。
- 验收标准：
  - 支持 voice 参数。已完成：支持 `voice_id` 并透传到 Agent Harness TTS。
  - 支持语速/情绪/风格配置。已完成：支持 `speaking_rate`、`emotion`、`style`。
  - 输出音频保存到对象存储。已完成：Go `POST /api/audio/tts` 将 TTS `audio_base64` 解码后以 `examiner_tts` 类型保存到 MinIO/S3，并通过真实链路 smoke 验证。

## P6-004 实现 TTS 缓存

- 状态：DONE
- 优先级：P1
- 负责人：BE-Go
- 依赖：P6-003
- 任务内容：按 text+voice+style hash 缓存考官音频。已完成：按 `text + voice_id + speaking_rate + emotion + style` 生成 cache key，命中时复用缓存音频 payload。
- 交付物：tts_cache。已完成：新增 `000003_tts_cache.sql`、Postgres cache store、Service cache hit/miss 逻辑和过期清理接口。
- 完成目标效果：重复题目播放更快，降低模型调用成本。
- 验收标准：
  - 命中缓存时不重复调用 TTS。已完成：缓存 hit 不调用 Agent Harness TTS provider，测试和 smoke 均覆盖。
  - 缓存记录可过期。已完成：`tts_cache.expires_at` 默认 7 天 TTL，并按 `expires_at > now` 判断命中。
  - 支持后台清理。已完成：`DELETE /api/audio/tts/cache/expired` 可删除过期缓存记录。

## P6-005 实现语音指标提取 MVP

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent / BE-Go
- 依赖：P6-002
- 任务内容：计算回答时长、词数、WPM、停顿估计、填充词比例。已完成：Go API 可从请求、当前 turn 录音时长和最新 ASR / 人工修正文案自动推导 duration、words、WPM、pause、filler 指标。
- 交付物：speech_metrics。已完成：新增 `000004_speech_metrics_mvp.sql`，持久化 `duration_ms`、`words_count`、`filler_count`、`mean_pause_ms`、`total_pause_ms`，并更新 API 类型、Postgres Store、handler 测试与 `speech-metrics-mcp` 字段映射。
- 完成目标效果：评分不只依赖文本，也能参考流利度客观指标。已完成：MCP 可读取 turn 级客观指标，后续 ScoringWorkflow 可引用同一份 evidence。
- 验收标准：
  - 每个 turn 有 duration_ms。已完成：请求可显式传入，也可从当前 turn 的 `user_recording` audio asset 推导；smoke 返回 `duration_ms=18000`。
  - 有 words_count、wpm。已完成：可从 transcript 或最新 ASR / 人工修正文案推导；smoke 返回 `words_count=11`、`wpm=36.67`。
  - 可记录长停顿数量或估计值。已完成：`pause_segments` + `long_pause_threshold_ms` 可推导长停顿数量、平均长停顿和长停顿总时长；smoke 返回 `long_pause_count=1`、`mean_pause_ms=1600`、`total_pause_ms=1600`。

## P6-006 实现音频回放能力

- 状态：DONE
- 优先级：P1
- 负责人：FE / BE-Go
- 依赖：P1-008、P6-002
- 任务内容：复盘页播放用户录音和考官音频。已完成：`/report/[sessionId]` 读取 session turns/audio assets，并用 `ReplayAudioPanel` 按 turn 展示用户录音、考官 TTS 和参考音频。
- 交付物：Replay Audio Component。已完成：新增 `apps/web/components/ReplayAudioPanel.tsx`，并修正 `AudioPlayer` 使用 Go API 的 `signed_url` 字段。
- 完成目标效果：用户可以听回自己的回答。已完成：报告页可基于 `audio_assets` 获取短期签名 URL 并播放。
- 验收标准：
  - 支持按 turn 播放。已完成：组件按 turn 分组展示 `user_recording`、`examiner_tts` 和 `reference`。
  - 支持播放进度。已完成：组件显示当前时间、总时长和可拖动进度条。
  - 支持签名 URL 过期重取。已完成：播放前获取短期 URL，临近过期、手动刷新或播放错误时重新请求 signed URL；后端 handler 测试覆盖 `expires_seconds=300`。

## P6-007 设计开源 Speech Assessment Service

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent / BE-Go / DevOps
- 依赖：P6-001、P6-002、P7-001
- 任务内容：设计独立 Python `speech-assessment-service`，负责音频质量、ASR 时间戳、VAD、流利度指标、发音证据提取。已完成：新增独立 FastAPI 语音 evidence 服务骨架，当前使用 deterministic extractor 输出可测试 evidence，后续 P6-008/P6-009 接入 WhisperX/GOPT adapter。
- 交付物：Speech Assessment Service ADR、API schema、Docker 服务骨架。已完成：`docs/speech_assessment_service_adr.md`、`packages/protocol/schemas/speech-assessment.schema.json`、`services/speech-assessment`、Dockerfile、Compose service、staging override 与 smoke tests。
- 完成目标效果：评分系统拥有可替换、可校准、可观测的开源语音证据层，避免把开源模型直接当 IELTS 分数器。已完成：response policy 强制 `ielts_band_output_allowed=false`，Protocol 反例校验禁止 direct band 字段进入 speech evidence response。
- 验收标准：
  - 明确自由口语考试与 Pronunciation Drill 两条链路。已完成：`mode=mock_exam` 与 `mode=pronunciation_drill` 分离；ADR 明确自由口语和固定文本 drill 的不同消费边界。
  - 输出包含 `audio_quality`、`fluency`、`pronunciation`、`confidence`。已完成：`POST /speech/assess` 返回四类 evidence，并通过 Pydantic 与 JSON Schema 校验。
  - Agent Harness 只消费 evidence，不直接信任开源模型给出的 IELTS band。已完成：schema 和测试禁止 direct IELTS band output，文档要求 ScoringWorkflow 仅把该服务作为 evidence source。

## P6-008 接入 WhisperX / faster-whisper 时间戳与对齐

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent / BE-Go
- 依赖：P6-007
- 任务内容：接入 WhisperX 或 faster-whisper，提供 transcript、word timestamps、可选 alignment。已完成：Speech Assessment Service 新增 `/speech/transcribe-timestamps`，默认 deterministic provider 输出稳定词级时间戳，并接入 `provider=faster_whisper` 懒加载 adapter。
- 交付物：ASR timestamp adapter。已完成：`services/speech-assessment/app/timestamps.py`、`TimestampTranscriptionRequest/Response`、共享 schema、测试和 Docker 依赖 `faster-whisper>=1.1,<2.0`。
- 完成目标效果：复盘页可做音频文本高亮，流利度指标可基于词级时间戳计算。已完成：接口返回 `segments`、`word_timestamps`、`asr_confidence`、`alignment_confidence`、`downstream_confidence` 与 `audio_quality_label`，可供复盘高亮和下游评分降权使用。
- 验收标准：
  - 返回 word-level timestamps。已完成：deterministic 和 faster-whisper adapter 均输出 `word_timestamps`；容器 smoke 返回 5 个词级时间戳。
  - 支持 ASR confidence 或可替代稳定性指标。已完成：返回 `asr_confidence`、`alignment_confidence` 与 segment/word confidence。
  - 低质量音频会降低 downstream confidence。已完成：`downstream_confidence_for()` 会对短音频/低 alignment confidence 降权，并输出 `audio_quality_label`。

## P6-009 实现开源 Fluency Metrics 与 GOPT evidence

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent
- 依赖：P6-007、P6-008
- 任务内容：实现 VAD + pause / WPM / filler / repetition / self-correction 指标，并接入 GOPT sentence-level pronunciation evidence。已完成：`/speech/assess` 支持 `vad_segments` 与 `word_timestamps`，并输出 deterministic GOPT-compatible sentence evidence。
- 交付物：fluency_metrics.py、gopt_scorer.py、speech evidence schema。已完成：`services/speech-assessment/app/fluency_metrics.py`、`services/speech-assessment/app/gopt_scorer.py`、`packages/protocol/schemas/speech-assessment.schema.json`。
- 完成目标效果：Fluency 与 Pronunciation 评分具备客观语音证据。已完成：response 包含 fluency metrics 和 `pronunciation.gopt`，ScoringWorkflow 可作为 evidence 消费，不直接映射 IELTS band。
- 验收标准：
  - 输出 `duration_sec`、`speech_duration_sec`、`silence_ratio`、`wpm`、`long_pause_count`、`mean_pause_ms`、`filler_count`、`repetition_count`、`self_correction_count`。已完成：VAD smoke 返回 `speech_duration_sec=1.6`、`silence_ratio=0.84`、`long_pause_count=2`、`filler_count=3`。
  - 输出 GOPT sentence-level pronunciation、accuracy、fluency、prosody 和 confidence。已完成：`pronunciation.gopt` 输出 `sentence_score`、`accuracy`、`fluency`、`prosody`、`confidence`、`provider=deterministic_gopt`。
  - ScoringWorkflow 可引用 evidence 但不直接把 GOPT 分映射为 IELTS band。已完成：`policy.ielts_band_output_allowed=false`，GOPT `calibration_note` 明确禁止直接映射 IELTS band。

## P6-010 规划 MFA / Kaldi GOP Pronunciation Drill

- 状态：DONE
- 优先级：P2
- 负责人：AI/Agent / Content/Ops
- 依赖：P6-007
- 任务内容：为固定文本跟读设计 MFA / Kaldi GOP 发音专项训练链路。已完成：独立 `/speech/pronunciation-drill` API、`deterministic_mfa_kaldi_gop` adapter boundary、真实 MFA / Kaldi GOP provider 预留。
- 交付物：Pronunciation Drill 技术方案与样例 API。已完成：`services/speech-assessment/app/pronunciation_drill.py`、`docs/pronunciation_drill_mfa_kaldi_gop.md`、`packages/protocol/schemas/speech-assessment.schema.json` drill request/response。
- 完成目标效果：自由口语考试只做保守发音 evidence，固定文本训练提供更细的词级、音素级、重音反馈。已完成：Mock Exam 继续走 `/speech/assess` sentence-level evidence；Fixed Text Drill 单独走 `/speech/pronunciation-drill`。
- 验收标准：
  - 支持目标文本输入。已完成：`PronunciationDrillRequest.target_text` 必填，API 无 `mock_exam` mode。
  - 返回 word-level / phoneme-level feedback。已完成：响应包含 `word_feedback`、`phoneme_feedback`、alignment confidence、timing/stress/status。
  - 与 IELTS Mock Exam 评分链路明确分离。已完成：独立 endpoint、独立 response schema，`policy.ielts_band_output_allowed=false` 且 direct band 字段被协议反例禁止。

### 2026-06-08 P6-010 Pronunciation Drill 验证记录

- 新增 `POST /speech/pronunciation-drill`，返回 `mode=pronunciation_drill`、`provider=deterministic_mfa_kaldi_gop`、`model=mfa-kaldi-gop-drill-v0`、word-level GOP-compatible feedback、phoneme-level feedback 与 alignment 统计。
- 新增 `docs/pronunciation_drill_mfa_kaldi_gop.md`，明确 Mock Exam / Free Speaking 与 Pronunciation Drill / Fixed Text 的链路分离、API 示例、adapter 替换点和风险控制。
- 协议层新增 `PronunciationDrillRequest`、`PronunciationDrillResponse`、word/phoneme feedback schema 和 direct IELTS band 反例。
- Service / Protocol verification：`python -m pytest services/speech-assessment/tests` 通过，10 passed；`pnpm --filter @ielts-speaking/protocol validate` 通过。
- Unified verification：`python -m pytest services/agent-harness/tests` 通过，213 passed；`go test ./...` 通过；`docker compose config --quiet` 与 `docker compose -f docker-compose.yml -f docker-compose.staging.yml config --quiet` 均通过；`pnpm --filter @ielts-speaking/web lint`、`typecheck`、`build` 均通过。
- Docker / smoke：`docker compose build --pull=false speech-assessment` 通过；`docker compose up -d speech-assessment` 后 `/healthz` 返回 `status=ok`，`POST /speech/pronunciation-drill` smoke 返回 `target_word_count=3`、`substituted_word_count=1`、`word_feedback_count=3`、`phoneme_feedback_count=24`、`confidence=0.83`、`policy.ielts_band_output_allowed=false`。
- Local web：已恢复 `http://127.0.0.1:3000/practice`，HTTP 200。

### 2026-06-08 Speech Assessment Service 验证记录

- 新增独立服务 `services/speech-assessment`，包含 FastAPI `/healthz`、`/metrics`、`POST /speech/assess`，默认监听 `8010`。
- 新增 `packages/protocol/schemas/speech-assessment.schema.json`，覆盖 request、audio quality、fluency、pronunciation evidence、policy 和 response；协议校验新增合法样例与 `overall_band` 反例，确保 speech evidence 不直接输出 IELTS band。
- 新增 `docs/speech_assessment_service_adr.md`，明确 Mock Exam / Free Speaking 与 Pronunciation Drill / Fixed Text 两条链路，后续 WhisperX、GOPT、MFA/Kaldi GOP 作为 adapter 逐步接入。
- 新增 Docker Compose `speech-assessment` 服务，并在 `.env.example`、`.env.staging.example`、`docker-compose.staging.yml` 中补充 `SPEECH_ASSESSMENT_*` 配置；Go API 与 Agent Harness 环境预留 `SPEECH_ASSESSMENT_URL`。
- Service tests：`python -m pytest services/speech-assessment/tests` 通过，4 passed，覆盖健康检查、mock_exam evidence、Pronunciation Drill target_text 校验和 word/phoneme feedback。
- Unified tests：`python -m pytest services/agent-harness/tests` 通过，213 passed；`go test ./...` 通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`docker compose config --quiet` 与 staging compose config 均通过；`pnpm --filter @ielts-speaking/web lint`、`typecheck`、`build` 均通过。
- Docker / smoke：`docker compose build --pull=false speech-assessment` 通过；`docker compose up -d speech-assessment` 后 `/healthz` 返回 `status=ok`、`policy.ielts_band_output_allowed=false`，`POST /speech/assess` 返回 `evidence_id`、fluency WPM、sentence-level pronunciation evidence 和 `response.policy.ielts_band_output_allowed=false`。

### 2026-06-08 ASR Timestamp Adapter 验证记录

- 新增 `services/speech-assessment/app/timestamps.py`，提供 deterministic timestamp provider 与 `provider=faster_whisper` adapter；faster-whisper 使用懒加载 `WhisperModel`，支持 `audio_path` 或 `audio_base64`，并输出 word timestamps、segments、ASR confidence、alignment confidence 与 downstream confidence。
- `services/speech-assessment/requirements.txt` 已加入 `faster-whisper>=1.1,<2.0`；Docker build 验证其 Linux 依赖可安装。
- 新增 `POST /speech/transcribe-timestamps`，response schema 纳入 `packages/protocol/schemas/speech-assessment.schema.json`；协议校验新增 timestamp 合法样例。
- Service tests：`python -m pytest services/speech-assessment/tests` 通过，7 passed；新增用例覆盖 deterministic timestamp 输出、短音频 downstream confidence 降权和缺少 transcript 的 422。
- Unified tests：`python -m pytest services/agent-harness/tests` 通过，213 passed；`go test ./...` 通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`docker compose config --quiet` 与 staging compose config 均通过；`pnpm --filter @ielts-speaking/web lint`、`typecheck`、`build` 均通过。
- Docker / smoke：`docker compose build --pull=false speech-assessment` 通过；`docker compose up -d speech-assessment` 后 `/healthz` 返回 `timestamp_provider=deterministic`、`features.faster_whisper=optional`；`POST /speech/transcribe-timestamps` 返回 5 个 word timestamps、首词 `technology`、`downstream_confidence=0.81` 和 `audio_quality_label=usable`。
- Local dev：Web dev server 已恢复，`http://127.0.0.1:3000/practice` 返回 200。

### 2026-06-08 Fluency Metrics 与 GOPT Evidence 验证记录

- 新增 `services/speech-assessment/app/fluency_metrics.py`，从 transcript、duration、VAD segments 和 word timestamps 计算 duration、speech duration、silence ratio、WPM、long pause、mean pause、filler、repetition、self-correction 与 confidence。
- 新增 `services/speech-assessment/app/gopt_scorer.py`，输出 deterministic GOPT-compatible sentence-level evidence，包含 `sentence_score`、`accuracy`、`fluency`、`prosody`、`confidence`、`provider=deterministic_gopt` 和禁止 direct IELTS band 映射的 `calibration_note`。
- `SpeechAssessmentRequest` 新增 `vad_segments`；`PronunciationEvidence` 新增 `gopt`；共享 `speech-assessment.schema.json` 已同步 VAD 与 GOPT evidence 字段。
- Service tests：`python -m pytest services/speech-assessment/tests` 通过，8 passed；新增用例覆盖 VAD 驱动 fluency metrics、GOPT evidence 字段与 direct band 禁止策略。
- Unified tests：`python -m pytest services/agent-harness/tests` 通过，213 passed；`go test ./...` 通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`docker compose config --quiet` 与 staging compose config 均通过；`pnpm --filter @ielts-speaking/web lint`、`typecheck`、`build` 均通过。
- Docker / smoke：`docker compose build --pull=false speech-assessment` 通过；`docker compose up -d speech-assessment` 后 `POST /speech/assess` 返回 `speech_duration_sec=1.6`、`silence_ratio=0.84`、`long_pause_count=2`、`filler_count=3`、`pronunciation.gopt.provider=deterministic_gopt`、`gopt_sentence=0.67`、`policy.ielts_band_output_allowed=false`。
- Local dev：Web dev server 已恢复，`http://127.0.0.1:3000/practice` 返回 200。

---

# Phase 7：评分与复盘报告

## P7-001 定义评分报告 Schema

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / BE-Go / FE / PM
- 依赖：P0-007
- 任务内容：定义 overall_band、criteria、evidence、suggestions、confidence、next_practice_plan。已完成：共享 schema 已覆盖总体分、四维评分、证据、建议、置信度、下一步练习计划、reviewer notes、官方免责声明和报告版本号。
- 交付物：scoring-report.schema.json。已完成：`packages/protocol/schemas/scoring-report.schema.json` 已通过 Ajv 2020 编译和 scoring-report 样例/反例校验。
- 完成目标效果：评分输出可持久化、可展示、可评测。已完成：schema 与 `ReportMCP` / `score_reports.version` 字段保持一致，Report MCP raw report 摘要写入 version/status。
- 验收标准：
  - 四维字段完整。已完成：`fluency_coherence`、`lexical_resource`、`grammatical_range_accuracy`、`pronunciation` 均为必填。
  - 每维必须包含 band、confidence、evidence、suggestions。已完成：每个 `CriterionScore` 均要求这些字段。
  - 支持报告版本号。已完成：schema 必填 `version >= 1`，校验脚本确认缺少版本号会失败。

## P7-002 实现 FluencyCoherenceScorer

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P3-008、P6-005、P7-001
- 任务内容：基于转写、语音指标、Rubric 进行流利度与连贯性评分。已完成：实现确定性 `FluencyCoherenceScorerAgent` baseline，综合 transcript、turn 级 speech metrics、rubric descriptors 与 anchor sample ids 输出四维报告可消费的结构化评分。
- 交付物：fluency_scorer_agent.py。已完成：`services/agent-harness/app/agents/fluency_scorer_agent.py` 与 `services/agent-harness/tests/test_fluency_scorer_agent.py` 已落地。
- 完成目标效果：用户能看到流利度、停顿、逻辑展开相关评分证据。已完成：evidence 可引用具体 turn、回答片段、WPM、长停顿和连接标记；suggestions 聚焦连续表达、连接推进和 filler 控制。
- 验收标准：
  - 输出 band 和 confidence。已完成：`FluencyCoherenceScorerOutput` 输出 half-band 分数和 0-1 confidence，并可转换为 `CriterionScoreInput`。
  - evidence 引用具体回答或指标。已完成：evidence 引用 turn_id、短回答 quote、WPM、长停顿和连接标记等可解释证据。
  - 不把语法错误主要归入 fluency。已完成：`dimension_boundary=fluency_coherence_only_no_grammar_penalty`，测试覆盖 grammar/tense/subject-verb 不进入 fluency 主要证据或建议。

## P7-003 实现 LexicalResourceScorer

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P3-008、P7-001
- 任务内容：评估词汇多样性、准确性、搭配、话题词。已完成：实现确定性 `LexicalResourceScorerAgent` baseline，综合 transcript、topic keywords、rubric descriptors 与 anchor sample ids 输出结构化词汇评分。
- 交付物：lexical_scorer_agent.py。已完成：`services/agent-harness/app/agents/lexical_scorer_agent.py` 与 `services/agent-harness/tests/test_lexical_scorer_agent.py` 已落地。
- 完成目标效果：用户能知道词汇使用是否重复、空泛或不自然。已完成：evidence 可引用重复内容词、低效表达、话题词命中与具体回答片段；suggestions 给出自然替代表达。
- 验收标准：
  - 输出具体重复词或低效表达。已完成：`repeated_words` 与 `low_value_expressions` 会进入 raw feature summary 和 evidence。
  - 给出可替换表达。已完成：针对 good、nice、bad、thing、stuff、interesting、important、very、a lot 等低效表达给出自然替换。
  - 不鼓励堆砌生僻词。已完成：`dimension_boundary=lexical_resource_only_no_rare_word_stuffing`，话题词建议强调服务于具体例子，不鼓励 rare/advanced word stuffing。

## P7-004 实现 GrammarScorer

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P3-008、P7-001
- 任务内容：评估语法范围与准确性。已完成：实现确定性 `GrammarScorerAgent` baseline，综合 transcript、rubric descriptors 与 anchor sample ids 输出结构化语法评分。
- 交付物：grammar_scorer_agent.py。已完成：`services/agent-harness/app/agents/grammar_scorer_agent.py` 与 `services/agent-harness/tests/test_grammar_scorer_agent.py` 已落地。
- 完成目标效果：用户能看到主要语法问题和可升级句型。已完成：evidence 覆盖复杂结构标记、重大语法错误、轻微冠词问题和自然口语改写提示。
- 验收标准：
  - evidence 包含具体错误或句子。已完成：evidence 引用 turn_id、回答片段、具体错误 quote 和 rewrite hint。
  - 区分小错误和影响理解的错误。已完成：raw feature summary 区分 `major_error_count` 与 `minor_error_count`，规则包含主谓一致/时态等 major 与冠词缺失 minor。
  - 给出自然改写，不生成过度书面句。已完成：suggestions 强调口语清楚，测试覆盖不输出 formal/academic 导向改写。

## P7-005 实现 PronunciationScorer

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P3-008、P6-005、P7-001
- 任务内容：基于语音指标、ASR 困难片段、节奏停顿保守评估发音。已完成：实现确定性 `PronunciationScorerAgent` baseline，综合 speech metrics、ASR confidence、不可识别片段、可选 pronunciation/prosody evidence 与 audio quality 输出结构化发音评分。
- 交付物：pronunciation_scorer_agent.py。已完成：`services/agent-harness/app/agents/pronunciation_scorer_agent.py` 与 `services/agent-harness/tests/test_pronunciation_scorer_agent.py` 已落地。
- 完成目标效果：给出谨慎的发音反馈，不因口音误扣分。已完成：评分 evidence 聚焦可懂度、ASR 困难片段、节奏、重音和停顿分块，明确不把 non-native accent 视作错误。
- 验收标准：
  - 置信度低时明确提示限制。已完成：低 ASR confidence、poor audio quality 或不可识别片段较多时降低 confidence，并提示录音质量/ASR/不可识别片段限制。
  - 不把非母语口音直接视为错误。已完成：`dimension_boundary=pronunciation_only_intelligibility_rhythm_stress_no_accent_penalty`，测试覆盖 non-native accent 不作为扣分证据。
  - 建议聚焦可懂度、重音、节奏和停顿分块。已完成：suggestions 聚焦关键词清晰度、meaning chunks、重音、语调和停顿分块。

## P7-006 实现 ScoreReviewerAgent

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P7-002 至 P7-005
- 任务内容：复核四维分数，检查证据不足、维度混淆、过度扣分。已完成：实现确定性 `ScoreReviewerAgent`，审计四维 `CriterionScoreInput` 的证据数量、维度边界、维度词对齐和高置信风险。
- 交付物：score_reviewer_agent.py。已完成：`services/agent-harness/app/agents/score_reviewer_agent.py` 与 `services/agent-harness/tests/test_score_reviewer_agent.py` 已落地。
- 完成目标效果：评分更稳定、更公平、更可信。已完成：复核输出 `findings`、`reviewed_criteria` 和 `reviewer_notes`，可让 ScoringWorkflow 对严重问题触发重评，对轻微证据不足保守降置信。
- 验收标准：
  - 能标记证据不足维度。已完成：`insufficient_evidence` 与 `high_confidence_with_minimal_evidence` finding 会记录具体 criterion 和 reviewer note。
  - 能要求重新评分或降低 confidence。已完成：严重证据不足或 dimension_boundary 错配输出 `request_rescore`；证据刚够但置信过高输出 `lower_confidence` 并更新 reviewed criteria。
  - 能输出 reviewer_notes。已完成：每个 finding 生成中文 reviewer note，全部通过时输出自动复核通过说明。

## P7-007 实现 ScoreCalibrator

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent / Content/Ops
- 依赖：P7-006、P10-001
- 任务内容：基于 anchor samples 做分数校准。已完成：实现确定性 `ScoreCalibrator`，按 criterion 聚合相似 anchor，计算偏差并保守校准四维 `CriterionScoreInput`。
- 交付物：score_calibrator.py。已完成：`services/agent-harness/app/agents/score_calibrator.py` 与 `services/agent-harness/tests/test_score_calibrator.py` 已落地。
- 完成目标效果：不同版本 Prompt/模型下评分不会大幅漂移。已完成：每次校准最多移动 0.5 band，并记录 anchor 均值、偏差、调整方向和原因，避免少量 anchor 造成过度校准。
- 验收标准：
  - 与 anchor set 偏差可计算。已完成：`ScoreCalibrationAdjustment` 输出 `anchor_mean_band` 与 `deviation`，并按 `min_similarity` 过滤可用 anchor。
  - 可输出校准前后分数。已完成：每个 criterion 输出 `before_band`、`after_band`，并写入 `raw_output.calibration`。
  - 分数调整有原因记录。已完成：每个 adjustment 记录中文 `reason`、`action` 与 anchor_sample_ids；anchor 不足时明确 `insufficient_anchors`。

## P7-008 实现 ScoringWorkflow

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P7-002 至 P7-007
- 任务内容：编排四维评分、复核、总体分生成。已完成：`ScoringWorkflow` 串联四维 scorer、Reviewer 与 Calibrator，从 `session_state.answers` 生成四维模拟评分报告。
- 交付物：scoring_workflow.py。已完成：`services/agent-harness/app/workflows/scoring_workflow.py`、`services/agent-harness/tests/test_scoring_workflow.py` 与 `POST /agent/sessions/{session_id}/score` 已落地。
- 完成目标效果：完整考试结束后可自动生成评分报告。已完成：评分端点返回 `report.ready` 事件和 `state.score_report`，报告兼容 `ScoreReportInput`，包含官方练习免责声明。
- 验收标准：
  - 输入 session_id 后可生成报告。已完成：`POST /agent/sessions/{session_id}/score` 接收 `session_state` 并输出 report-ready AgentResponse。
  - 报告符合 schema。已完成：测试使用 `ScoreReportInput.model_validate()` 校验生成报告，包含四维 criteria、overall_band、confidence、reviewer_notes 和 disclaimer。
  - 失败节点可重试。已完成：无可评分回答或 Reviewer 要求重评时返回 `error.recoverable` 和 `next_action=retry_current_node`，state 保留 `scoring_error`。

## P7-009 实现 FeedbackCoachAgent

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent
- 依赖：P7-008、P3-007
- 任务内容：生成指导性建议、answer skeleton、参考答案、训练计划。已完成：`FeedbackCoachAgent` 基于四维评分、evidence、用户回答和可用背景事实生成 `feedback_items`、`reference_answers` 与 `next_practice_plan`。
- 交付物：feedback_coach_agent.py。已完成：`services/agent-harness/app/agents/feedback_coach_agent.py`、`services/agent-harness/tests/test_feedback_coach_agent.py`，并已接入 `ScoringWorkflow` 与 `/agent/sessions/{session_id}/score`。
- 完成目标效果：用户知道下一步怎么改，而不是只看到分数。已完成：评分响应中的 `state.score_report.next_practice_plan`、`state.feedback_items`、`state.reference_answers` 可直接供报告页和持久化 API 使用。
- 验收标准：
  - 建议具体、可执行。已完成：按最低分维度生成优先级、标题、正文、evidence refs 与练习任务。
  - 参考答案结合用户背景但不生硬。已完成：可读取 `agent_facts` / profile 中的安全背景提示，并作为可替换示例融入参考答案。
  - 不鼓励全文背诵。已完成：`personalization_notes` 明确标注参考答案是 flexible model，不建议逐句背诵。

## P7-010 实现报告持久化

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / AI/Agent
- 依赖：P7-008、P3-010
- 任务内容：保存 score_reports、criterion_scores、feedback_items、reference_answers。已完成：新增 Go `internal/report` 模块，支持 `POST /api/sessions/:session_id/report` 持久化报告、四维分、反馈、参考答案和训练计划，支持 `GET /api/sessions/:session_id/report` 查询最新报告。
- 交付物：Report persistence。已完成：`services/api-go/internal/report/*`、router 注册、handler 测试；Python `report-mcp` 同步增强，避免临时 `model_run_id` / 非 UUID `turn_id` 导致整份报告写入失败。
- 完成目标效果：用户可以之后反复查看历史复盘。已完成：报告按 session/version upsert，读取时返回 criteria、feedback_items、reference_answers、study_plans 与 raw_report。
- 验收标准：
  - 报告与 session 关联。已完成：Go store 保存前校验 session ownership，查询也按当前用户和 session 过滤。
  - 支持版本号。已完成：沿用 `(session_id, version)` 唯一约束，重复写入同版本会更新报告和子表。
  - 写入失败不会丢失 Agent 输出。已完成：`raw_report` 保留 reviewer notes、feedback、reference_answers、next_practice_plan、model_run_id 等原始 Agent 输出；不存在的 `model_run_id` 不阻断保存。

## P7-011 实现复盘报告页面

- 状态：DONE
- 优先级：P0
- 负责人：FE / BE-Go
- 依赖：P7-010、P6-006
- 任务内容：展示总体分、四维分、证据、建议、参考答案、回放。已完成：`/report/[sessionId]` 同时读取 session replay 与最新 persisted report，展示 overall band、雷达图、四维 criteria、evidence、建议、feedback、study plan、reference answer 和音频回放入口。
- 交付物：Review Report UI。已完成：`apps/web/app/report/[sessionId]/page.tsx` 与可复用 `RadarChart` 动态分数输入。
- 完成目标效果：用户能完整复盘一次练习或考试。已完成：报告页可在报告未生成时降级显示 replay；报告生成后完整展示评分、证据、反馈、参考答案与免责声明。
- 验收标准：
  - 四维评分清晰。已完成：整体分、置信度、四维分卡片和 Recharts 雷达图均接入真实 report 数据。
  - evidence 与原回答关联。已完成：evidence 中的 `turn_id` 会映射到 session turn，展示 quote、reason 与 Original answer。
  - 支持录音回放和转写查看。已完成：保留 `ReplayAudioPanel`，并在证据区显示对应转写/原回答。

## P7-012 实现历史报告列表

- 状态：DONE
- 优先级：P1
- 负责人：FE / BE-Go
- 依赖：P7-010
- 任务内容：用户可查看历史练习记录。已完成：新增 `GET /api/reports` 历史报告列表 API，前端新增 `/history` 页面，并在 Practice Dashboard 增加 History 入口。
- 交付物：History UI。已完成：`apps/web/app/history/page.tsx` 提供筛选表单、overall band SVG 趋势图、历史报告列表和复盘入口；Go `internal/report` 已扩展 `ReportHistoryFilter` / `ReportHistoryItem` 与 PostgreSQL 查询。
- 完成目标效果：用户能长期追踪学习进步。已完成：历史页按最新报告倒序展示练习/考试记录，显示 latest/average/delta、criteria 摘要与报告状态，并可跳转单次复盘。
- 验收标准：
  - 可按日期、模式、Part 过滤。已完成：API 支持 `from`/`to`、`mode`、`part` 查询；UI 提供 Date、Mode、Part 控件和 Apply/Reset。
  - 显示 overall band 趋势。已完成：历史页顶部以轻量 SVG 趋势图展示 overall band 变化，并展示 latest、average、delta 指标。
  - 可进入单次复盘。已完成：每条历史报告提供 `Open review`，跳转 `/report/[sessionId]`，浏览器自动化已验证可进入 Session Report。

---

# Phase 8：管理后台与内容运营

## P8-001 实现后台权限模型

- 状态：DONE
- 优先级：P1
- 负责人：BE-Go / FE
- 依赖：P1-003
- 任务内容：区分普通用户、运营、管理员。已完成：复用 `users.role`，后台题库路由通过 `auth.RequireRoles("operator", "admin")` 校验；前端后台页面基于 hydrated user role 控制访问。
- 交付物：Admin RBAC。已完成：Go admin route RBAC、前端 Access denied、operator/admin 入口控制、`admin_audit_logs` 持久化审计。
- 完成目标效果：题库和知识库管理不暴露给普通用户。已完成：普通 user 访问后台题库接口返回 403，普通用户不会看到 `/practice` 的 `Question Admin` 入口。
- 验收标准：
  - 后台接口有角色校验。已完成：`/api/admin/question-bank/*` 需要 Bearer token 且角色为 operator/admin。
  - 未授权用户无法访问管理页面。已完成：未登录用户跳转登录，普通用户显示 Access denied。
  - 管理操作有审计。已完成：operator 成功操作和 user 403 越权操作均写入 `admin_audit_logs`。

## P8-002 实现题库管理页面

- 状态：DONE
- 优先级：P1
- 负责人：FE / BE-Go / Content/Ops
- 依赖：P1-005、P8-001
- 任务内容：题目列表、编辑、审核、上下架、导入。已完成：`/admin/questions` 支持题目列表、创建、编辑、状态流转、Archive 和批量 JSON 导入。
- 交付物：Question Admin UI。已完成：`apps/web/app/admin/questions/page.tsx`，并在 `/practice` 为 operator/admin 增加入口。
- 完成目标效果：运营可以维护季度题库。已完成：operator 真实浏览器链路可创建题目、改为 reviewing、导入题目并归档测试题。
- 验收标准：
  - 支持筛选 season、part、topic、status。已完成：Filters 区支持 season/topic/part/status 查询。
  - 支持批量导入。已完成：Batch Import 接受 QuestionPayload JSON 数组并逐条创建。
  - 支持审核状态流转。已完成：题目列表内可在 draft/reviewing/active/archived 间更新 review_status，Archive 会下架并软删除。

## P8-003 实现知识库管理页面

- 状态：DONE
- 优先级：P2
- 负责人：FE / BE-Go / AI/Agent
- 依赖：P3-001、P8-001
- 任务内容：上传知识文档、查看索引状态、触发重建。已完成：`/api/admin/knowledge/docs` 支持上传、列表、状态更新、reindex 和归档；`/admin/knowledge` 提供对应 UI。
- 交付物：Knowledge Admin UI。已完成：`apps/web/app/admin/knowledge/page.tsx`，并在 `/practice` 增加 Knowledge 入口。
- 完成目标效果：非研发也能维护主题知识和评分材料。已完成：operator 可上传 topic_knowledge/rubric/review_history 文档，查看 chunk_count/token_count/index_status/embedding_model，并触发重建。
- 验收标准：
  - 可上传文档。已完成：创建文档会写入 `knowledge_docs` 和 `knowledge_chunks`。
  - 可查看 chunk 数量和索引状态。已完成：列表展示 chunk_count、token_count、content_hash、index_status 和 embedding_model。
  - 可触发重新索引。已完成：Reindex 会基于当前 chunks 重建 hash embedding chunks 并写入审计。

## P8-004 实现 Prompt 版本管理后台 MVP

- 状态：DONE
- 优先级：P2
- 负责人：AI/Agent / FE
- 依赖：P2-009
- 任务内容：展示当前 Prompt 版本、用途、发布时间、回滚信息。已完成：`/api/admin/prompts/versions` 返回 agent、purpose、version、hash、active、created_at 和 redacted metadata；`/admin/prompts` 展示。
- 交付物：Prompt Version UI。已完成：`apps/web/app/admin/prompts/page.tsx`，并在 `/practice` 增加 Prompts 入口。
- 完成目标效果：Prompt 变更可追踪。已完成：迁移 seed 首批 5 个 Prompt 版本元信息，后续可通过同表追加历史版本。
- 验收标准：
  - 每个 Agent 有 prompt_version。已完成：ExamWorkflow、PracticeWorkflow、FollowupPlannerAgent、ScoringWorkflow、FeedbackCoachAgent 均有 active 版本元信息。
  - 可查看历史版本元信息。已完成：列表支持 agent/purpose/active 过滤，展示 content_hash、summary 和 rollback 元信息。
  - 不在前端暴露敏感系统提示全文给无权限用户。已完成：API/UI 只暴露 redacted metadata 和 hash，不返回 prompt body。

## P8-005 实现内容审核流程

- 状态：DONE
- 优先级：P1
- 负责人：Content/Ops / BE-Go
- 依赖：P8-002
- 任务内容：定义题目、参考答案、主题知识的审核状态和发布流程。已完成：题目、knowledge_docs、reference_answers 均进入 draft/reviewing/active/archived 流程。
- 交付物：Content Review Workflow。已完成：Question Admin、Knowledge Admin 与 Review Board 共同覆盖题目、主题知识和参考答案审核。
- 完成目标效果：上线内容可控，避免未审核内容进入正式练习。已完成：公开题库查询和 RAG pgvector 检索均只消费 active 内容；reference answers 默认 draft，需运营发布。
- 验收标准：
  - draft/reviewing/active/archived 状态清晰。已完成：三类内容统一使用 `content_status`。
  - active 内容才进入用户练习。已完成：`/api/questions` 与 Agent Harness pgvector retrieve 均过滤 active；Knowledge Admin active 状态写入 `knowledge_docs.status`。
  - 操作有审核记录。已完成：question_bank、knowledge_base、prompt_versions、content_review 后台操作均写入 `admin_audit_logs`。

---

# Phase 9：评测、观测与质量保障

## P9-001 建立 Langfuse 观测体系

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / DevOps
- 依赖：P2-009
- 任务内容：完善 Trace、Prompt、模型调用、工具调用记录。已完成：TraceStep 补充 tokens 估算、retrieved_chunks、structured_output_validity、scoring_result、error_type，并接入 MCP audit sink 形成工具调用链路。
- 交付物：Langfuse Dashboard。已完成：新增 `GET /agent/observability/summary`、`GET /agent/observability/alerts` 与 `/metrics`，本地等效 dashboard 数据源可按 run/session 聚合。
- 完成目标效果：每次会话可追踪到 Agent 节点和模型输出。已完成：`/agent/runs/{run_id}/trace` 保留单 run 明细，summary 提供跨 run 延迟、错误率、节点和工具统计。
- 验收标准：
  - 可按 session_id/run_id 查询。
  - 可查看工具调用链路。
  - 可统计延迟和错误率。

## P9-002 建立 DeepEval 回归测试

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent / QA
- 依赖：P7-008
- 任务内容：为组卷、追问、评分、反馈建立自动评测。已完成：新增本地确定性 DeepEval-like runner，覆盖 question_planning、followup、scoring、feedback。
- 交付物：deepeval_tests。已完成：`services/agent-harness/app/evals/deepeval_regression.py` 与 `tests/test_phase9_evals.py`。
- 完成目标效果：Prompt 和模型调整后可以发现质量回退。已完成：默认 30+ 样本可生成 Markdown 报告，失败项进入 improvement_items，高风险失败阻塞发布。
- 验收标准：
  - 至少覆盖 30 个样本。
  - CI 可运行核心测试。
  - 失败报告可读。

## P9-003 建立 Ragas RAG 评估

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent / QA
- 依赖：P3-001、P3-003、P3-004
- 任务内容：评估题库和 Rubric 检索质量。已完成：新增本地 Ragas-like RAG evaluator，使用 query + expected_doc_ids + metadata filters 评估检索。
- 交付物：ragas_tests。已完成：`services/agent-harness/app/evals/ragas_rag_eval.py`。
- 完成目标效果：检索不是黑盒，能量化相关性与遗漏问题。已完成：输出 precision/recall、missing_doc_ids，失败样本进入 improvement_items。
- 验收标准：
  - 有问题-期望文档对。
  - 输出 retrieval precision/recall 或等效指标。
  - 检索失败样本进入改进列表。

## P9-004 建立 Promptfoo 安全红队测试

- 状态：DONE
- 优先级：P1
- 负责人：AI/Agent / QA / Security
- 依赖：P5-002、P7-009
- 任务内容：测试 Prompt 注入、越权请求、隐私提取、系统提示泄露。已完成：新增本地 Promptfoo-like red-team runner，覆盖考试模式和练习模式。
- 交付物：promptfoo red-team config。已完成：`services/agent-harness/evals/promptfoo-redteam.yaml` 与 `app/evals/promptfoo_redteam.py`。
- 完成目标效果：减少 Agent 被诱导泄露或越权调用工具的风险。已完成：Examiner 内部术语与高风险敏感指令脱敏，MCP 高风险写入工具可被禁用并阻塞发布。
- 验收标准：
  - 覆盖考试模式和练习模式。
  - 覆盖工具调用注入。
  - 高风险失败必须阻塞发布。

## P9-005 建立端到端测试

- 状态：DONE
- 优先级：P0
- 负责人：QA / FE / BE-Go
- 依赖：P4-012、P5-007、P7-011
- 任务内容：自动化测试创建会话、完成问答、生成报告。已完成：新增 API E2E happy path，覆盖 full_exam、part_practice、报告生成与观测 summary。
- 交付物：E2E Tests。已完成：`services/agent-harness/tests/test_phase9_e2e.py`。
- 完成目标效果：核心用户路径有自动化保护。已完成：Agent Harness 测试集中跑通 203 个用例，核心路径纳入回归。
- 验收标准：
  - full_exam happy path 可跑通。
  - part_practice happy path 可跑通。
  - 报告生成可验证。

## P9-006 建立性能基线

- 状态：DONE
- 优先级：P1
- 负责人：DevOps / BE-Go / FE / AI-Agent
- 依赖：P5-007、P7-008
- 任务内容：测试 Live 延迟、ASR 时间、TTS 时间、评分时间、报告生成时间。已完成：新增性能基线 runner，覆盖 live_turn、asr、tts、scoring、report_generation、agent_node。
- 交付物：Performance Baseline Report。已完成：`services/agent-harness/app/evals/performance_baseline.py`，支持 Markdown 报告。
- 完成目标效果：明确瓶颈，避免体验不可控。已完成：输出整体和组件维度 p50/p95、错误率、TTS cache hit rate 与 bottlenecks。
- 验收标准：
  - 记录 p50/p95 延迟。
  - 记录 TTS 缓存命中率。
  - 记录 Agent 节点耗时。

## P9-007 建立错误恢复机制

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / AI-Agent / FE
- 依赖：P4-012、P5-007
- 任务内容：处理 ASR 失败、TTS 失败、Agent 输出不合法、WebSocket 断线。已完成：新增 RecoveryPolicy，前端 WebSocket 自动重连并保留 session 状态。
- 交付物：Error Recovery Policy。已完成：`services/agent-harness/app/recovery/error_policy.py` 与 `POST /agent/recovery/directive`，文档见 `docs/phase9_quality_gate.md`。
- 完成目标效果：用户不会因为单点错误直接丢失整场考试。已完成：ASR 可重试/手动输入，TTS 可文本降级，Agent 结构化失败可重试/安全兜底，WebSocket 支持指数退避重连。
- 验收标准：
  - ASR 失败可重试或手动输入。
  - TTS 失败可显示文字题目。
  - Agent 失败可重试当前节点。
  - 前端断线重连后恢复 session 状态。

## P9-008 建立日志与告警

- 状态：DONE
- 优先级：P1
- 负责人：DevOps / BE-Go
- 依赖：P0-005
- 任务内容：接入 Prometheus、Grafana、Loki 或等效方案。已完成：Agent Harness 输出 JSON request logs、Prometheus 风格 `/metrics` 与 in-memory alert policy。
- 交付物：Monitoring Dashboard。已完成：`GET /agent/observability/summary`、`GET /agent/observability/alerts`、`GET /metrics` 可作为本地 dashboard 数据源。
- 完成目标效果：线上问题可以被及时发现。已完成：服务健康、错误率、延迟、工具成功率和 workflow node 延迟均可查询，关键失败生成告警。
- 验收标准：
  - 服务健康、错误率、延迟有监控。
  - 关键失败有告警。
  - 日志可按 request_id/session_id 检索。

### 2026-06-08 Phase 9 统一验证记录

- Agent Harness：`python -m pytest services/agent-harness/tests` 通过，203 passed；新增 Phase 9 用例覆盖观测 summary/alerts/metrics、DeepEval-like 回归、Ragas-like 检索评估、Promptfoo-like 红队、E2E happy path、性能基线与恢复策略。
- Go API：`go test ./...` 通过；本阶段未新增 Go 业务迁移，现有 API 回归保持通过。
- Protocol：`pnpm --filter @ielts-speaking/protocol validate` 通过，agent-api、agent-run、scoring-report、session-event schema 与示例均 OK。
- Web：`pnpm --filter @ielts-speaking/web lint`、`pnpm --filter @ielts-speaking/web typecheck`、`pnpm --filter @ielts-speaking/web build` 均通过。
- Docker：`docker compose config --quiet` 通过；`docker compose build --pull=false agent-harness` 通过；`docker compose up -d agent-harness` 后容器 health=healthy。
- Smoke：Agent Harness `/agent/sessions/{session_id}/plan`、`/agent/observability/summary`、`/metrics`、`/agent/recovery/directive` 验证通过；Go API `/healthz` 返回 ok。
- Browser：重新启动 Web dev server 后，`http://127.0.0.1:3000/practice` 桌面与移动视口加载正常，无新增 console error/warn，无横向溢出。

### 2026-06-08 Observability 与 Calibration 后端复核补齐记录

- Observability 复核结论：后端已真实实现 Trace、run 查询、单 run trace、summary、alerts、Prometheus 风格 `/metrics`、request_id/session_id 结构化日志、敏感信息脱敏、Langfuse exporter 与 MCP tool calls 汇总，符合规划中 session/run、workflow node、prompt/model、tokens、retrieved chunks、structured validity、scoring result、error type、latency/error/tool success 追踪要求。
- Calibration 缺口修复：原有 `ScoreCalibrator`、speech calibration runner 与 MultiPA runner 已真实存在，但主要依赖 CLI/测试；本轮新增 `services/agent-harness/app/calibration_api.py` 与 Agent Harness 后端 API，补齐后台/后端可调用面。
- 新增 Calibration API：`GET /agent/calibration/anchor-samples`、`POST /agent/calibration/score`、`POST /agent/calibration/speech-regression`、`POST /agent/calibration/multipa-experiment`、`POST /agent/calibration/quality-gate`。
- API 能力边界：支持 anchor samples audit、四维评分校准、speech calibration MAE/max error/release gate、MultiPA vs GOPT baseline 对比、DeepEval/Ragas/Promptfoo/performance/speech/MultiPA 聚合质量门禁；API 仅接收结构化样本或显式 contract samples，不读取任意本地 manifest 路径。
- Verification：`python -m pytest services/agent-harness/tests/test_calibration_api.py services/agent-harness/tests/test_phase9_observability.py services/agent-harness/tests/test_phase10_content_quality.py services/agent-harness/tests/test_score_calibrator.py` 通过，26 passed；`python -m pytest services/agent-harness/tests` 通过，224 passed。
- 状态说明：功能性后端已补齐；P10-006 / P10-007 仍保留 DEFERRED，仅因为真实 SpeechOcean762 授权样本、自有双人标注样本和真实 MultiPA adapter 输出尚未提供，不能把 contract samples 当成生产验收。

### 2026-06-08 Observability 与 Calibration 二次验收补齐记录

- Observability 后端补齐：`ObservabilitySummary` 新增 `structured_output_validity_rate`、structured output 计数、input/output token 汇总与 `estimated_model_cost_usd`；`TraceStep` 与 Langfuse metadata 同步 `estimated_cost_usd`；`/metrics` 新增结构化输出有效率、token 与成本指标。
- Observability 配置补齐：新增 `MIMO_INPUT_COST_USD_PER_1K_TOKENS`、`MIMO_OUTPUT_COST_USD_PER_1K_TOKENS`，默认 0；配置真实 token 单价后可在 trace、summary 与 Prometheus 中输出模型成本估算。
- Calibration 后端补齐：speech regression case metadata 新增 Part、accent group、recording quality、confidence 与 transcript excerpt，支撑后台样本筛选、明细表与错误排查。
- Calibration / Observability 产品化补齐：新增 `/admin/calibration`，已接入 `GET /agent/calibration/anchor-samples`、`POST /agent/calibration/score`、`POST /agent/calibration/speech-regression`、`POST /agent/calibration/multipa-experiment`、`POST /agent/calibration/quality-gate`；`/admin/observability` 指标卡改为展示 P95 latency、tool success、structured validity、model cost。
- Web BFF 修复：新增并验证 `/api/agent-harness/[...path]` 代理；调整 `apps/web/next.config.mjs`，将 Go API `/api/:path*` rewrite 移至 fallback，避免吞掉 Next route handler；Docker / staging Web service 均配置 `AGENT_HARNESS_URL`。
- Verification：`python -m pytest services/agent-harness/tests/test_calibration_api.py services/agent-harness/tests/test_phase9_observability.py services/agent-harness/tests/test_score_calibrator.py` 通过，16 passed；显式 mock 测试环境下 `python -m pytest services/agent-harness/tests` 通过，225 passed；`pnpm --filter @ielts-speaking/web lint`、`pnpm --filter @ielts-speaking/web typecheck`、`pnpm --filter @ielts-speaking/web build` 通过；`pnpm eval:speech-calibration:contract` 输出 `passed=True samples=12 mae=0.333 max_error=1.000 issues=0`；`pnpm eval:multipa:contract` 输出 `status=passed samples=12 block_release=false risks=0`；`docker compose config --quiet` 与 `pnpm compose:staging:config` 通过。
- Smoke：`http://127.0.0.1:3000/practice` 返回 200；`/api/agent-harness/agent/calibration/anchor-samples` 带 Authorization 返回 200；`/api/agent-harness/agent/calibration/quality-gate` 带 Authorization 返回 200 且 status passed；in-app browser 验证 `/admin/calibration` 显示 `Quality Gate: passed`、MAE 与样本覆盖，随后已恢复到 `/practice`。
- 状态说明：Observability 与 Calibration 的功能性后端、BFF 与后台页面已按规划补齐；P10-006 / P10-007 仍保留 DEFERRED，仅因真实 SpeechOcean762 授权样本、自有双人标注样本和真实 MultiPA adapter 输出未提供；P12-003 仍保留 REVIEW，等待真实 staging URL、HTTPS 证书、MiMo staging key 与 Langfuse staging 实例。

### 2026-06-08 UI/UX 规划状态同步记录

- 文档同步：`docs/ui_ux_gpt_image_prompts_and_interactions.md` 已将 `/practice/setup/full`、`/practice/setup/part`、`/practice/setup/topic`、`/pronunciation`、`/admin/observability`、`/admin/calibration`、`/admin` 从旧的“规划新增/后续 API”状态同步为已实现状态。
- 接口同步：`/admin/observability` 与 `/admin/calibration` 的页面-后端联动表已更新为 Web BFF `/api/agent-harness/*` 与 Agent Harness `/agent/observability/*`、`/agent/runs/*`、`/agent/calibration/*` 的真实接入关系。
- Verification：`rg` 未再命中旧的 `规划新增`、`Coming Soon`、`后续 API`、`/admin/calibration.*后续`、`/admin/observability.*可经` 等滞后描述；`pnpm --filter @ielts-speaking/web typecheck` 通过；`http://127.0.0.1:3000/practice` 与 `http://127.0.0.1:3000/admin/calibration` 均返回 200。
- 状态说明：本轮为规划与实现状态同步，不改变 DONE 110、REVIEW 1、DEFERRED 2 的任务计数；剩余非 DONE 项仍受真实外部数据和真实 staging 环境约束。

### 2026-06-08 前端危险操作与根路径状态收口记录

- History 删除体验补齐：`apps/web/app/history/page.tsx` 已移除 `window.confirm`，改为页面内确认对话框；删除报告和录音前必须输入 `DELETE_MY_DATA`，与隐私/数据删除语义保持一致。
- 根路径规划同步：`docs/ui_ux_gpt_image_prompts_and_interactions.md` 的 P19 已从“根路径视觉预览页”更新为“根路径入口页”，状态为未登录跳 `/login`、已登录跳 `/practice`；前端迭代建议同步移除已完成的 setup、pronunciation、observability、calibration 与根路径迁移事项。
- Verification：`rg "window\\.confirm|confirm\\(" apps/web/app apps/web/components` 无命中；`rg` 未命中旧的根路径视觉预览/后续 API 状态描述；`pnpm --filter @ielts-speaking/web lint`、`pnpm --filter @ielts-speaking/web typecheck`、`pnpm --filter @ielts-speaking/web build` 均通过，build 路由表包含 `/history`；in-app browser 打开 `/history` 后在未登录会话下按预期跳转 `/login`，未出现可见 404。
- 状态说明：本轮继续收口非外部依赖的产品化与规划一致性问题，不改变 DONE 110、REVIEW 1、DEFERRED 2 的任务计数。

---

# Phase 10：评分样本与内容质量建设

## P10-001 建立 Anchor Samples 数据集

- 状态：DONE
- 优先级：P0
- 负责人：Content/Ops / AI/Agent / QA
- 依赖：P7-001
- 任务内容：收集并标注不同分数段的口语样本。已完成：内置 Band 4-8 synthetic internal anchor samples，包含样本、四维分、校准转换与数据集审计。
- 交付物：anchor_samples。已完成：`services/agent-harness/app/content/anchor_samples.py`。
- 完成目标效果：评分系统有校准依据。已完成：可输出 calibration anchor samples，并通过 coverage/compliance audit。
- 验收标准：
  - 覆盖 Band 4-8 常见水平。
  - 每个样本有四维分与解释。
  - 样本来源合规。

## P10-002 建立题库审核标准

- 状态：DONE
- 优先级：P1
- 负责人：Content/Ops / PM
- 依赖：P8-005
- 任务内容：定义题目来源、难度、重复、版权、语言风格审核规则。已完成：题目审核规则覆盖来源/授权、Part 风格、重复度、内部术语泄漏与发布 checklist。
- 交付物：Question Review Guideline。已完成：`docs/question_review_guideline.md` 与 `services/agent-harness/app/content/question_review.py`。
- 完成目标效果：题库质量稳定，不依赖个人主观判断。已完成：每道题可由 deterministic review policy 输出 pass/fail 与处理建议。
- 验收标准：
  - 每道题可按标准审核。
  - 不合规题目有处理流程。
  - 题库版本发布有 checklist。

## P10-003 建立参考答案风格规范

- 状态：DONE
- 优先级：P1
- 负责人：Content/Ops / AI/Agent
- 依赖：P7-009
- 任务内容：定义参考答案长度、难度、自然度、背诵风险控制。已完成：Band 5/6/7 风格 profile、answer skeleton 要求、自然口语与背诵风险校验。
- 交付物：Reference Answer Style Guide。已完成：`docs/reference_answer_style_guide.md` 与 `services/agent-harness/app/content/reference_answer_style.py`。
- 完成目标效果：系统生成的参考答案更自然，更适合口语训练。已完成：参考答案可按目标 Band 做风格校验并强制 skeleton。
- 验收标准：
  - 不生成过度书面化答案。
  - 区分 Band 5/6/7 示例。
  - 强制包含 answer skeleton。

## P10-004 建立主题知识库

- 状态：DONE
- 优先级：P1
- 负责人：Content/Ops / AI/Agent
- 依赖：P3-002
- 任务内容：为常见主题整理观点、例子、词汇、表达。已完成：technology/travel/hometown/work_or_study/public_places 首批主题知识文档。
- 交付物：topic_knowledge_index。已完成：`services/agent-harness/app/content/topic_knowledge.py`，可 ingest 到现有 knowledge/RAG 服务。
- 完成目标效果：Part 3 和参考答案质量提升。已完成：主题知识包含观点、例子、词汇并可检索。
- 验收标准：
  - 覆盖首批核心主题。
  - 每个主题包含观点、例子、词汇。
  - 可通过 RAG 检索。

## P10-005 建立用户反馈收集机制

- 状态：DONE
- 优先级：P2
- 负责人：PM / FE / BE-Go
- 依赖：P7-011
- 任务内容：用户可对评分、建议、参考答案反馈是否有用。已完成：报告页 overall 文本反馈，评分项/建议项/参考答案 thumbs up/down。
- 交付物：Feedback Collection。已完成：`report_user_feedback` 迁移、Go API `POST /api/reports/:report_id/feedback`、operator/admin `GET /api/reports/feedback/export`、报告页与后台 Review Board UI。
- 完成目标效果：后续可基于真实用户反馈优化 Agent。已完成：反馈与 report/session/user/target 关联，后台可查看并导出 JSON。
- 验收标准：
  - 报告页支持 thumbs up/down 或文本反馈。
  - 反馈与 session/report 关联。
  - 后台可导出反馈。

## P10-006 建立 SpeechOcean762 + 自有样本语音校准集

- 状态：DEFERRED
- 优先级：P1
- 负责人：Content/Ops / AI/Agent / QA
- 依赖：P7-008、P10-001、P6-009
- 任务内容：使用 SpeechOcean762 与自有 200-500 条人工标注 IELTS 口语样本校准开源语音 evidence 到内部模拟评分区间。工程准备已完成：manifest schema、授权校验、覆盖率审计、回归 MAE harness、报告 CLI、合成 contract tests 与 Agent Harness 后端 API；真实授权数据与人工标注仍待 Content/Ops 接入。
- 交付物：speech calibration dataset、校准评测报告。工程交付已完成：`services/agent-harness/app/evals/speech_calibration.py`、`services/agent-harness/app/evals/speech_eval_cli.py`、`services/agent-harness/app/calibration_api.py`、`services/agent-harness/evals/speech_calibration_manifest.example.jsonl`、`docs/speech_calibration_and_multipa_eval.md`；生产校准集本体仍需真实数据。
- 完成目标效果：GOPT / Fluency Metrics 输出能与目标用户群体和 IELTS 模拟评分更稳定对齐。当前达到 engineering-ready：可在真实数据到位后通过 CLI 或 `POST /agent/calibration/speech-regression` 生成授权、覆盖、回归门禁报告；尚未完成真实人群校准。
- 验收标准：
  - 样本来源与授权合规。工程门禁已完成：SpeechOcean762 要求 `source_license_id`，自有样本要求 `consent_record_id` 与至少 2 名标注者；真实授权样本仍待接入。
  - 覆盖不同 band、口音、录音质量和 Part 类型。工程审计已完成：覆盖 band buckets、Part 1/2/3、accent groups、good/fair/poor；真实覆盖仍待数据证明。
  - 每次 scoring prompt 或 speech model 变更可跑回归评测。已完成：`SpeechCalibrationRegressionRunner`、`python -m app.evals.speech_eval_cli calibration` 与 `POST /agent/calibration/speech-regression` 均可输出 case error、MAE、max error、release gate、JSON/Markdown 或 API 报告；合成 contract 样本只用于 CI/本地门禁，不通过生产门禁。

## P10-007 实验 MultiPA 开放回答发音评估

- 状态：DEFERRED
- 优先级：P3
- 负责人：AI/Agent
- 依赖：P6-009、P10-006
- 任务内容：在 `exp/multipa-open-response` 分支验证 MultiPA 对 IELTS Part 2/3 开放回答 pronunciation assessment 的效果。工程准备已完成：固定 benchmark 对比 runner、MultiPA adapter output 合约、GOPT baseline 对比、延迟/成本/部署复杂度报告、JSONL output loader、报告 CLI 与 Agent Harness 后端 API；真实 MultiPA 输出仍待实验环境接入。
- 交付物：实验报告、推理成本评估、与 GOPT / Kaldi GOP baseline 对比。工程交付已完成：`services/agent-harness/app/evals/multipa_open_response.py`、`services/agent-harness/app/evals/speech_eval_cli.py`、`services/agent-harness/app/calibration_api.py`、`services/agent-harness/evals/multipa_outputs.example.jsonl` 与 `docs/speech_calibration_and_multipa_eval.md`；正式实验报告需真实 benchmark 与 adapter 输出。
- 完成目标效果：为后续开放式发音评估保留实验路线，但不影响 MVP 主链路稳定性。已完成：runner 默认在缺少 MultiPA 输出时返回 `not_configured`，不会进入主评分链路。
- 验收标准：
  - 有固定 benchmark 与人工标注对比。工程合约已完成：复用 P10-006 calibration samples；真实人工标注 benchmark 仍待数据接入。
  - 明确部署复杂度、延迟和成本。已完成：`ProviderComparison`、`python -m app.evals.speech_eval_cli multipa` 与 `POST /agent/calibration/multipa-experiment` 输出 MAE、max error、p95 latency、estimated total cost、deployment complexity、JSON/Markdown 或 API 报告。
  - 未通过稳定性验证前不进入主评分链路。已完成：`MultiPAOpenResponseExperimentRunner` 缺少真实 adapter 输出时为 `not_configured`，通过后也只建议 feature-flagged experiment。

### 2026-06-08 Phase 10 语音校准与 MultiPA 工程准备记录

- 新增 `app.evals.speech_calibration`：支持 JSONL manifest 加载、SpeechOcean762 / 自有样本授权字段校验、band/Part/accent/recording quality 覆盖审计、内部 pronunciation evidence 回归 MAE 报告，并禁止把 speech model 输出当作 direct IELTS band 发布。
- 新增 `app.evals.multipa_open_response`：支持固定 benchmark 上 GOPT baseline 与 MultiPA adapter output 对比，输出 MAE、max error、p95 latency、estimated cost 与 deployment complexity；缺少真实 adapter 输出时保持 `not_configured`。
- 新增 `app.evals.speech_eval_cli`：支持 `calibration` 与 `multipa` 两个子命令，可加载真实 JSONL manifest / MultiPA outputs，输出 JSON 与 Markdown 报告，并用退出码表达 release gate。
- 新增 `app.calibration_api`：将 anchor audit、ScoreCalibrator、speech calibration regression、MultiPA experiment 和聚合 quality gate 暴露为 Agent Harness 后端 API，便于后台或 Go BFF 调用。
- 新增 `docs/speech_calibration_and_multipa_eval.md`、`services/agent-harness/evals/speech_calibration_manifest.example.jsonl` 与 `services/agent-harness/evals/multipa_outputs.example.jsonl`，说明真实生产门禁和合成 contract 样本边界。
- Targeted verification：`python -m pytest services/agent-harness/tests/test_phase10_content_quality.py` 通过，11 passed；`python -m app.evals.speech_eval_cli calibration --contract-samples --allow-synthetic-contract --min-production-samples 0 --stdout-format summary` 通过，输出 `mae=0.333`、`max_error=1.000`；`python -m app.evals.speech_eval_cli multipa --contract-samples --contract-multipa-outputs --stdout-format summary` 通过，输出 `status=passed`。
- Unified verification：`python -m pytest services/agent-harness/tests` 通过，219 passed；`python -m pytest services/speech-assessment/tests` 通过，10 passed；`go test ./...` 通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`docker compose config --quiet` 与 staging compose config 均通过；`pnpm --filter @ielts-speaking/web lint`、`typecheck`、`build` 均通过。
- Docker / smoke：`docker compose build --pull=false agent-harness` 通过；`docker compose up -d agent-harness` 后 `/healthz` 返回 `status=ok`、`adapter=microsoft-agent-framework`、`adapter_installed=true`；容器内 `python -m app.evals.speech_eval_cli calibration --contract-samples --allow-synthetic-contract --min-production-samples 0 --stdout-format summary` 通过，输出 `mae=0.333`、`max_error=1.000`。
- Local web：已恢复 `http://127.0.0.1:3000/practice`，HTTP 200。
- 状态说明：P10-006 / P10-007 保留 DEFERRED，因为真实 SpeechOcean762 授权样本、自有 200-500 条双人标注样本、真实 MultiPA adapter 输出和正式实验报告尚未由外部数据/实验环境提供。

### 2026-06-08 Phase 10 统一验证记录

- Agent Harness：`python -m pytest services/agent-harness/tests` 通过，208 passed；新增 Phase 10 用例覆盖 anchor samples、题库审核、参考答案风格与主题知识 RAG。
- Go API：`go test ./...` 通过；新增 report feedback handler/export 测试，DB migration 测试通过；本地 `report_user_feedback` 迁移成功到 version 7。
- Protocol：`pnpm --filter @ielts-speaking/protocol validate` 通过，所有 schema 与 scoring-report examples OK。
- Web：`pnpm --filter @ielts-speaking/web lint`、`pnpm --filter @ielts-speaking/web typecheck`、`pnpm --filter @ielts-speaking/web build` 均通过。
- Docker：`docker compose config --quiet` 通过；`docker compose build --pull=false api-go agent-harness` 通过；`docker compose up -d api-go agent-harness` 后两个容器 health=healthy。
- Smoke：Go `/healthz`、Agent Harness `/healthz` 与 `/metrics` 正常；本地 operator smoke 账号提交 report feedback 入库，`/api/reports/feedback/export` 可按 report 导出。
- Browser：重新启动 Web dev server 后，`/practice`、`/report/{sessionId}`、`/admin/review` 桌面与移动视口加载正常；报告页反馈保存成功，后台 User Feedback 可见；无新增 console error/warn，无横向溢出。

---

# Phase 11：安全、隐私与合规

## P11-001 实现录音授权与隐私提示

- 状态：DONE
- 优先级：P0
- 负责人：FE / PM / BE-Go
- 依赖：P4-007
- 任务内容：首次录音前展示用途、保存策略、删除方式。已完成：Live 页录音 consent 卡片，API consent 保存/查询，音频上传服务端二次校验。
- 交付物：Consent UI + consent_records。已完成：`POST /api/privacy/consents`、`GET /api/privacy/consents`、Live Session consent UI。
- 完成目标效果：用户明确知道录音如何被使用。已完成：文案说明录音用于转写、AI 评分、反馈、回放和报告，并提示可删除。
- 验收标准：
  - 未授权不能录音。
  - 授权记录可查询。
  - 文案明确说明 AI 处理用途。

## P11-002 实现用户数据删除能力

- 状态：DONE
- 优先级：P1
- 负责人：BE-Go / FE
- 依赖：P1-008、P7-010
- 任务内容：支持删除历史录音、报告、背景资料。已完成：session/report/audio 软删除与背景资料删除，均要求确认短语。
- 交付物：Data Deletion API/UI。已完成：`POST /api/privacy/data-deletion`、History 删除本次录音与报告、Background 隐私控制删除背景资料。
- 完成目标效果：用户可控制自己的数据。已完成：删除 session 后报告 API 不可访问；音频 signed URL 排除 deleted asset。
- 验收标准：
  - 删除录音会删除对象存储文件或标记清理。
  - 删除报告后不可访问。
  - 删除操作有确认流程。

## P11-003 实现敏感信息最小化传输

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / AI-Agent
- 依赖：P1-004、P3-007
- 任务内容：Agent 请求中只传必要背景，不传完整用户资料。已完成：Agent Harness Privacy Filter 排除 private/is_excluded/privacy_exclusions facts，并补充 Trace redaction。
- 交付物：Privacy Filter。已完成：`services/agent-harness/app/privacy/filters.py` 与 `docs/privacy_compliance_controls.md`。
- 完成目标效果：降低模型调用中的隐私暴露风险。已完成：禁用字段不进入 prompt facts，Trace payload 仅保留脱敏摘要。
- 验收标准：
  - 禁用字段不会进入 prompt。
  - Trace 中敏感信息脱敏。
  - 工具调用结果可按 privacy_level 过滤。

## P11-004 实现 Voice Clone 合规限制

- 状态：DONE
- 优先级：P2
- 负责人：PM / BE-Go / FE
- 依赖：P6-003
- 任务内容：如果使用 voiceclone，必须增加授权、声明和审核流程。已完成：MVP 默认禁用 voice clone，TTS voiceclone/clone voice_id 在未启用时被服务端阻断。
- 交付物：Voice Clone Policy。已完成：`docs/voice_clone_policy.md`、`app_settings.voice_clone_policy`、admin compliance API 与后台开关。
- 完成目标效果：避免仿冒声音和未授权声音复刻。已完成：operator/admin 可查看和禁用策略，默认 disabled。
- 验收标准：
  - 未授权不能上传声音复刻。
  - 明确禁止使用他人声音。
  - 管理后台可禁用 voiceclone 功能。

## P11-005 实现题库版权字段和下架机制

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / Content/Ops
- 依赖：P1-005、P8-002
- 任务内容：记录 source_type、license、review_status，支持下架。已完成：题库 schema、Go API、后台 UI 和 RAG indexer 均使用 source_type/license/review_status/deleted_at。
- 交付物：Content Compliance Fields。已完成：Question Bank 管理页字段、归档删除、public query 仅返回 active。
- 完成目标效果：题库来源可追溯，可处理版权风险。已完成：未审核/已归档题不进入公开题库和 active RAG 索引。
- 验收标准：
  - 每道题有来源类型。
  - 未审核题不进入 active。
  - 下架后不会被检索到。

## P11-006 实现 Prompt Injection 防护

- 状态：DONE
- 优先级：P0
- 负责人：AI/Agent / QA
- 依赖：P9-004
- 任务内容：在 Examiner、Scoring、Feedback、MCP 工具调用前后增加防护策略。已完成：GuardrailAgent 检测 prompt injection、system prompt leak、privacy exfiltration、tool override，并提供输出净化。
- 交付物：GuardrailAgent + tests。已完成：`services/agent-harness/app/agents/guardrail_agent.py` 与 Phase 11 privacy/guardrail tests。
- 完成目标效果：用户无法通过回答诱导系统泄露内部提示或越权调用工具。已完成：常见注入样本被 block，工具越权和用户控制参数被拒绝。
- 验收标准：
  - 常见注入样本测试通过。
  - Agent 不输出系统提示。
  - 工具调用参数不由用户文本直接决定。

### 2026-06-08 Phase 11 统一验证记录

- Agent Harness：`python -m pytest services/agent-harness/tests` 通过，213 passed；新增 Phase 11 用例覆盖 Privacy Filter、Trace redaction、GuardrailAgent 注入/泄露/工具越权防护。
- Go API：`go test ./...` 通过；新增 compliance handler 测试、audio consent/voiceclone service 测试，DB migration 测试通过；本地迁移成功到 version 8。
- Protocol：`pnpm --filter @ielts-speaking/protocol validate` 通过，所有 schema 与 scoring-report examples OK。
- Web：`pnpm --filter @ielts-speaking/web lint`、`pnpm --filter @ielts-speaking/web typecheck`、`pnpm --filter @ielts-speaking/web build` 均通过。
- Docker：`docker compose config --quiet` 通过；`docker compose build --pull=false api-go agent-harness` 通过；`docker compose up -d api-go agent-harness` 后两个容器 health=healthy。
- Smoke：Go `/healthz`、Agent Harness `/healthz` 正常；本地 API smoke 验证 recording consent 保存/查询、数据删除后 report 返回 404、operator voice clone policy 保持 disabled。
- Browser：重新启动 Web dev server 后，`/practice`、`/background`、`/history`、`/admin/review`、`/live/{sessionId}` 桌面与移动视口加载正常；Privacy Controls、Delete、Voice Clone Policy、Recording Consent 可见；无新增 console error/warn，无横向溢出。

---

# Phase 12：部署、CI/CD 与发布

## P12-001 建立 CI Pipeline

- 状态：DONE
- 优先级：P0
- 负责人：DevOps / Tech Lead
- 依赖：P0-003
- 任务内容：配置 lint、unit test、type check、build。已完成：GitHub Actions quality gate 覆盖 protocol、Web lint/typecheck/build、Go test、Agent test、Docker compose config、migration audit、staging readiness example、release record example 与镜像构建。
- 交付物：CI Workflow。已完成：`.github/workflows/ci.yml`。
- 完成目标效果：合并前自动检查基础质量。已完成：PR/push 到 main 自动执行基础质量门禁。
- 验收标准：
  - 前端 typecheck 运行。
  - Go test 运行。
  - Agent test 运行。
  - Docker build 可验证。

## P12-002 建立数据库迁移流程

- 状态：DONE
- 优先级：P0
- 负责人：BE-Go / DevOps
- 依赖：P1-001
- 任务内容：选择并配置 Goose/Atlas/Ent migration。已完成：Goose SQL migrations 已嵌入 API 二进制，Docker/本地/CI/staging 使用同一迁移集，并可生成发布前后 migration status evidence JSON。
- 交付物：Migration Pipeline。已完成：`docs/migration_pipeline.md`。
- 完成目标效果：数据库变更可版本化、可回滚。已完成：迁移文件进入代码库，发布前后可执行 status/up/down，并将 status 输出封装进发布证据。
- 验收标准：
  - 本地和 dev 可执行迁移。
  - migration 文件进入代码库。
  - 破坏性变更需 Review。

## P12-003 建立 Staging 环境

- 状态：REVIEW
- 优先级：P1
- 负责人：DevOps
- 依赖：P0-005、P12-001
- 任务内容：部署接近生产的测试环境。已完成：staging compose override、`.env.staging.example`、staging readiness gate；待部署平台接入实际 HTTPS URL。
- 交付物：Staging URL。已完成配置交付：`docker-compose.staging.yml`、`.env.staging.example`、`docs/staging_environment.md`、`scripts/verify_staging_readiness.ps1`；实际 URL 由目标部署环境提供。
- 完成目标效果：内测前可在稳定环境验证。当前达到 REVIEW：配置与 readiness gate 可校验，真实 URL/证书/观测实例需在部署平台落地。
- 验收标准：
  - 使用真实 MiMo API 或可控 mock。
  - HTTPS 可用。
  - 日志和监控可用。

## P12-004 建立备份与恢复策略

- 状态：DONE
- 优先级：P1
- 负责人：DevOps / BE-Go
- 依赖：P1-001、P1-008
- 任务内容：数据库和对象存储备份、恢复演练。已完成：PostgreSQL dump 与 MinIO mirror 备份/恢复脚本，恢复脚本需要显式确认短语，并可生成备份 manifest 完整性证据。
- 交付物：Backup Policy。已完成：`docs/backup_recovery_policy.md`、`scripts/backup_local.ps1`、`scripts/restore_local.ps1`、`scripts/verify_backup_manifest.ps1`。
- 完成目标效果：数据风险可控。已完成：备份范围、频率、恢复演练步骤、manifest 校验和发布前备份完整性门禁明确。
- 验收标准：
  - PostgreSQL 定时备份。
  - MinIO/S3 备份策略明确。
  - 至少完成一次恢复演练。

## P12-005 准备生产发布 Checklist

- 状态：DONE
- 优先级：P1
- 负责人：PM / Tech Lead / QA / DevOps
- 依赖：P9-005、P9-008、P11-001
- 任务内容：制定上线前检查项。已完成：功能、安全隐私、迁移、监控、回滚和发布记录 checklist，并将 migration audit、migration status、staging readiness、backup manifest 与 backup integrity evidence 聚合进机器可读 release record。
- 交付物：Release Checklist。已完成：`docs/release_checklist.md`。
- 完成目标效果：发布前质量、安全、合规、运维检查明确。已完成：上线门禁和回滚责任项可逐条勾选。
- 验收标准：
  - 包含功能验收。
  - 包含隐私和合规检查。
  - 包含回滚方案。
  - 包含监控告警检查。

### 2026-06-08 Phase 12 统一验证记录

- CI/CD：新增 `.github/workflows/ci.yml`，覆盖 protocol validate、Web lint/typecheck/build、Go test、Agent Harness pytest、Phase 10 speech calibration / MultiPA contract gates、Speech Assessment pytest、Docker compose config、staging compose config、staging readiness example gate，以及 api-go/agent-harness/speech-assessment/web 镜像构建。
- Migration：新增 `docs/migration_pipeline.md`，本地 `go test ./...` 中 migration 测试通过；当前数据库已在 Phase 11 迁移到 version 8。
- Staging：新增 `.env.staging.example`、`docker-compose.staging.yml`、`docs/staging_environment.md`；`docker compose -f docker-compose.yml -f docker-compose.staging.yml config --quiet` 通过；实际 HTTPS URL 等待部署平台接入。
- Backup/Restore：新增 `docs/backup_recovery_policy.md`、`scripts/backup_local.ps1`、`scripts/restore_local.ps1`，覆盖 PostgreSQL dump、MinIO mirror 与显式确认恢复流程。
- Release：新增 `docs/release_checklist.md`，包含功能验收、安全隐私、迁移、监控告警、回滚和发布记录。
- Unified tests：`python -m pytest services/agent-harness/tests` 通过，213 passed；`go test ./...` 通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`pnpm --filter @ielts-speaking/web lint`、`typecheck`、`build` 均通过；`docker compose build --pull=false web` 通过。后续 CI 门禁加固已补充 Speech Assessment tests、Phase 10 合约评测、staging readiness example gate 与四个服务镜像逐步构建验证。

### 2026-06-08 Phase 12 收口补充验证记录

- Checklist audit：P0-005 Docker Compose 基线已由 REVIEW 同步为 DONE；P2-001 Agent Harness 服务骨架已由 IN_PROGRESS 同步为 DONE；P12-003 Staging 环境保留 REVIEW，因为真实 HTTPS URL、证书与外部观测实例需要部署平台提供。
- Agent Runtime：新增 `docs/agent_runtime_boundary.md`，说明当前确定性工作流、Microsoft Agent Framework core 适配边界与后续深度 graph migration 验收条件；`services/agent-harness/requirements.txt` 已加入 `agent-framework-core>=1.0,<2.0`。
- Runtime smoke：`docker compose build --pull=false agent-harness` 通过；`docker compose up -d agent-harness` 后 `GET http://127.0.0.1:8000/healthz` 返回 `runtime.adapter=microsoft-agent-framework`、`runtime.adapter_package=agent-framework-core`、`runtime.adapter_installed=true`、`runtime.adapter_version=1.8.0`、`framework=deterministic-workflow`。
- Unified retest：`python -m pytest services/agent-harness/tests` 通过，213 passed；`go test ./...` 通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`docker compose config --quiet` 与 `docker compose -f docker-compose.yml -f docker-compose.staging.yml config --quiet` 均通过；`pnpm --filter @ielts-speaking/web lint`、`typecheck`、`build` 均通过。
- Local dev：Web dev server 已恢复，`http://127.0.0.1:3000/practice` 返回 200。

### 2026-06-08 Phase 12 Staging Readiness Gate 补充记录

- 新增 `scripts/verify_staging_readiness.ps1`，检查 `.env.staging` 必填项、占位符、HTTPS public URL、staging compose config，并可对 Web/API/Agent/Speech 公网 URL 执行 health/metrics smoke。
- `.env.staging.example` 新增 `AGENT_HARNESS_PUBLIC_URL` 与 `SPEECH_ASSESSMENT_PUBLIC_URL`，便于部署平台暴露服务后纳入统一 staging smoke。
- `docs/staging_environment.md` 补充 readiness gate 使用方式：部署前可 `-SkipRemoteChecks` 做静态门禁，部署后执行完整远程门禁。
- Verification：`powershell -ExecutionPolicy Bypass -File scripts\verify_staging_readiness.ps1 -EnvFile .env.staging.example -AllowExamplePlaceholders -SkipRemoteChecks` 通过，返回 `compose_config_passed=true`、`issue_count=0`、`passed=true`。
- 状态说明：P12-003 仍保留 REVIEW，因为真实 Staging URL、HTTPS 证书、MiMo staging key 和 Langfuse staging 实例必须由目标部署平台提供后才能完成最终验收。

### 2026-06-08 Phase 12 CI 门禁加固与逐步镜像构建验证记录

- CI 已补齐 Phase 10 语音校准合约门禁、MultiPA 合约门禁、Speech Assessment 依赖安装与测试、staging compose config、staging readiness example gate，以及 speech-assessment 镜像构建。
- Docker 镜像构建在 CI 中拆分为 `docker compose build --pull=false api-go`、`agent-harness`、`speech-assessment`、`web` 四个独立 step，避免并发导出镜像时受 Docker Desktop I/O 抖动影响。
- Phase 10 contract gates：`pnpm eval:speech-calibration:contract` 通过，summary 显示 `mae=0.333`、`max_error=1.000`；`pnpm eval:multipa:contract` 通过，`status=passed`。
- Speech Assessment：`python -m pytest services/speech-assessment/tests` 通过，10 passed。
- Staging gates：`pnpm compose:staging:config` 与 `pnpm staging:readiness:example` 均通过，readiness example 返回 `passed=true`。
- Unified regression：`python -m pytest services/agent-harness/tests` 通过，219 passed；`go test ./...` 通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`pnpm --filter @ielts-speaking/web lint`、`typecheck`、`build` 均通过；`docker compose config --quiet` 通过。
- Image build verification：`docker compose build --pull=false api-go`、`agent-harness`、`speech-assessment`、`web` 已逐个通过。
- Local dev recovery：Web dev server 已恢复到 `http://127.0.0.1:3000`；`Invoke-WebRequest http://127.0.0.1:3000/practice` 返回 200；应用内浏览器确认 `/practice` 渲染 `Dashboard`、`Full Mock Exam`、`Part Practice`、`Topic Practice`，console 无 error/warn。
- 状态说明：当前任务状态仍为 DONE 110、REVIEW 1、DEFERRED 2；P10-006 / P10-007 等待真实授权语音样本、双人标注样本与 MultiPA adapter 输出，P12-003 等待真实 staging URL、HTTPS 证书、MiMo staging key 与 Langfuse staging 实例。

### 2026-06-08 Observability / Calibration 后端二次确认记录

- Observability 复核：`/agent/runs/{run_id}`、`/agent/runs/{run_id}/trace`、`/agent/observability/summary`、`/agent/observability/alerts` 和 `/metrics` 已由 Agent Harness 主应用真实暴露；Trace 覆盖 workflow node、prompt version、模型名、token 估算、成本估算、结构化输出合法性、评分摘要、MCP tool calls、错误类型、敏感信息脱敏和 Langfuse ingestion payload。
- Observability 契约补齐：`TraceRecorder.record_agent_call()` 的 traceable request 类型边界已补齐评分请求 Protocol，避免 `score_session` 已接入但类型契约仍只覆盖 plan/ASR/next-turn。
- Calibration 复核：`/agent/calibration/anchor-samples`、`/agent/calibration/score`、`/agent/calibration/speech-regression`、`/agent/calibration/multipa-experiment` 和 `/agent/calibration/quality-gate` 已由 Agent Harness 主应用真实暴露；后端覆盖 anchor audit、ScoreCalibrator、DeepEval/Ragas/Promptfoo/performance gate、speech calibration regression 与 MultiPA fixed benchmark comparison。
- Targeted verification：`python -m pytest services/agent-harness/tests/test_phase9_observability.py services/agent-harness/tests/test_langfuse_trace.py services/agent-harness/tests/test_calibration_api.py services/agent-harness/tests/test_score_calibrator.py` 通过，20 passed。
- Unified backend verification：显式 mock 环境下 `$env:MOCK_MODEL_ENABLED='true'; $env:LANGFUSE_ENABLED='false'; $env:KNOWLEDGE_STORE_BACKEND='memory'; python -m pytest services/agent-harness/tests` 通过，225 passed。
- Phase 10 contract gates：`pnpm eval:speech-calibration:contract` 通过，`passed=True samples=12 mae=0.333 max_error=1.000 issues=0`；`pnpm eval:multipa:contract` 通过，`status=passed samples=12 block_release=false risks=0`。
- 结论：规划里的 Observability 与 Calibration 后端功能性需求已真实实现并完成二次验收；P10-006 / P10-007 的生产验收状态仍保持 DEFERRED，仅等待真实 SpeechOcean762 授权样本、自有双人标注样本和真实 MultiPA adapter 输出。

### 2026-06-08 Observability / Calibration 后端第三次复核记录

- 规划对齐复核：按 `ielts_speaking_agent_harness_plan.md` 的 Evaluation / Observability、Agent API、Trace 字段和 P10 校准要求反查代码，确认 Observability 不是文档占位；主应用真实挂载 run summary、trace、summary、alerts、Prometheus metrics、Langfuse exporter、结构化日志和脱敏逻辑。
- Prompt 管理边界：当前项目以 Go 后台 `prompt_versions` 管理 Prompt 元数据和内容哈希，Agent trace 记录 `prompt_version` 并可导出 Langfuse；未把 Langfuse Prompt Registry 作为本地运行时强依赖，符合当前任务清单已落地边界。
- 接口 smoke：FastAPI TestClient 创建 `part_practice` run 后，`GET /agent/runs/{run_id}/trace` 返回 `completed`，trace step 包含 `workflow_node`、`prompt_version`、`model_name`、`input_tokens`、`output_tokens`、`estimated_cost_usd`、`retrieved_chunks`、`structured_output_validity`、`scoring_result`、`tool_calls`；`GET /agent/observability/summary` 返回 `run_count=1`、`structured_output_validity_rate=1.0`；`GET /metrics` 包含 `agent_harness_estimated_model_cost_usd`。
- Calibration smoke：`GET /agent/calibration/anchor-samples?include_samples=false` 返回 `audit.passed=true`；`POST /agent/calibration/quality-gate` 返回 `status=passed`，checks 覆盖 `anchor_samples`、`deepeval_regression`、`ragas_rag`、`promptfoo_redteam`、`performance_baseline`、`speech_calibration_contract`、`multipa_contract`。
- Verification：专项测试 `python -m pytest services/agent-harness/tests/test_phase9_observability.py services/agent-harness/tests/test_langfuse_trace.py services/agent-harness/tests/test_calibration_api.py services/agent-harness/tests/test_score_calibrator.py` 通过，20 passed；Agent Harness 全量 mock 后端测试 `python -m pytest services/agent-harness/tests` 通过，225 passed；`pnpm eval:speech-calibration:contract` 与 `pnpm eval:multipa:contract` 通过。
- 状态同步：Observability 与 Calibration 的后端功能性需求确认已真实实现；任务状态不变，仍为 DONE 110、REVIEW 1、DEFERRED 2，P10-006 / P10-007 不因合成 contract 样本改为 DONE。

### 2026-06-08 Live 会话恢复态补齐验证记录

- Live upload recovery：`apps/web/app/live/[sessionId]/page.tsx` 已在录音上传失败时保留本地 audio blob，展示 Recovery 面板，并提供 `Retry upload` 与 `Continue without audio` 两条恢复路径；后者要求输入手动文本并以 `manual_text_fallback` 事件继续本轮，避免用户因单次上传失败丢失回答。
- Silence feedback：VAD 静音触发后会立即显示 `Silence detected, processing your answer...`，并继续走停止录音与上传流程，降低用户对录音是否丢失的误判。
- UI/UX 文档同步：`docs/ui_ux_gpt_image_prompts_and_interactions.md` 已同步登录/注册视觉统一状态，以及 Live 静音提示、Retry upload、Continue without audio 和录音上传失败错误态处理。
- Verification：`pnpm --filter @ielts-speaking/web lint` 通过；`pnpm --filter @ielts-speaking/web typecheck` 通过；`pnpm --filter @ielts-speaking/web build` 通过，路由表包含 `/live/[sessionId]`、`/background`、`/login`、`/register`。
- Browser smoke：本地 Web dev server 已恢复到 `http://127.0.0.1:3000`；未登录访问 `/live/smoke-live-recovery` 正确跳 `/login`；本地测试账号登录后访问真实 session `/live/dc5b3ea0-1006-4fcb-a8ae-536d02a67ece`，桌面与移动视口均显示 Live Session、Recording Consent、Session Timeline / Progress、Examiner Stage、Replay / Start speaking / Reconnect 控件，控制台无 error/warn，移动端未发现横向溢出。
- 状态说明：本轮为 Phase 4 / Phase 11 前端可靠性收口，当前任务状态仍为 DONE 110、REVIEW 1、DEFERRED 2；剩余 P10-006、P10-007、P12-003 仍仅受外部真实数据和 staging 环境门禁限制。

### 2026-06-08 Phase 12 Staging Observability Gate 加固记录

- Staging readiness gate 加固：`scripts/verify_staging_readiness.ps1` 已将 `LANGFUSE_ENABLED`、`AGENT_HARNESS_PUBLIC_URL`、`SPEECH_ASSESSMENT_PUBLIC_URL` 纳入必填项；静态门禁会校验 Agent Harness / Speech Assessment public URL 必须为 HTTPS，避免 staging 配置缺少可观测服务入口。
- 观测实例 smoke：完整远程门禁现在会检查 `LANGFUSE_HOST` 可访问性，同时继续检查 Web、Go API `/healthz`/`/readyz`、Agent Harness `/healthz`/`/metrics`、Speech Assessment `/healthz`/`/metrics`，更贴近 P12-003 “日志和监控可用”的验收标准。
- 文档同步：`docs/staging_environment.md` 已同步新的 readiness gate 行为，明确 Web / API / MinIO / Agent Harness / Speech Assessment / Langfuse public endpoint HTTPS 要求，以及 `LANGFUSE_ENABLED=true` 和 Langfuse host 可达性检查。
- Phase 12 targeted verification：`pnpm staging:readiness:example` 通过，返回 `compose_config_passed=true`、`issue_count=0`、`passed=true`；`pnpm compose:staging:config` 通过；`docker compose config --quiet` 通过。
- Cross-service regression：`pnpm --filter @ielts-speaking/protocol validate` 通过；`go test ./...` 通过；显式 mock 环境下 `python -m pytest services/agent-harness/tests` 通过，225 passed；`python -m pytest services/speech-assessment/tests` 通过，10 passed。
- 状态说明：本轮继续收口 P12-003 的工程可验收面，但真实 Staging URL、HTTPS 证书、MiMo staging key 与 Langfuse staging 实例仍需部署平台提供；当前任务状态保持 DONE 110、REVIEW 1、DEFERRED 2。

### 2026-06-08 Phase 12 Speech Assessment Remote Smoke 加固记录

- Staging speech smoke 加固：`scripts/verify_staging_readiness.ps1` 的完整远程门禁已从浅层 `/healthz`、`/metrics` 扩展到 deterministic POST smoke：`/speech/transcribe-timestamps` 会验证词级时间戳与 downstream confidence，`/speech/assess` 会验证 evidence 响应结构。
- 语音评分边界门禁：`/speech/assess` smoke 会确认 `policy.ielts_band_output_allowed=false`，并递归检查响应中不存在 `overall_band`、`predicted_band` 或直接 `band` 字段，防止 staging 发布时把 Speech Assessment 误用为直接 IELTS 分数器。
- 文档同步：`docs/staging_environment.md` 已更新验证脚本说明，明确 Speech Assessment timestamp / assess POST smoke 与 direct band 字段禁止规则。
- Verification：`pnpm staging:readiness:example` 通过；`pnpm compose:staging:config` 通过；PowerShell scriptblock 语法检查通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`python -m pytest services/speech-assessment/tests` 通过，10 passed；`go test ./...` 通过；显式 mock 环境下 `python -m pytest services/agent-harness/tests` 通过，225 passed。
- 状态说明：本轮继续强化 P12-003 在真实 staging 接入后的自动验收能力；P12-003 仍保持 REVIEW，等待真实公网 HTTPS 与 Langfuse staging 实例。

### 2026-06-08 Phase 12 Agent Observability / Quality Gate Remote Smoke 加固记录

- Agent remote smoke 加固：`scripts/verify_staging_readiness.ps1` 的完整远程门禁已新增 `GET /agent/observability/summary` 与 `GET /agent/observability/alerts` 检查，验证 summary 核心字段存在，并在出现 critical alert 时阻止 readiness 通过。
- Agent quality gate 加固：完整远程门禁新增 `POST /agent/calibration/quality-gate`，覆盖 DeepEval-like regression、Ragas-like RAG eval、Promptfoo-like redteam、performance baseline、speech calibration contract 与 MultiPA contract；若返回 `blocked` 或任一 check `block_release=true`，staging readiness 会失败。
- 文档同步：`docs/staging_environment.md` 已补充 Agent Harness observability summary/alerts 和 calibration quality gate 的完整远程门禁说明，和 `docs/release_checklist.md` 中“观测 summary、alerts、Prompt injection/RAG/性能门禁”的发布要求对齐。
- Verification：`pnpm staging:readiness:example` 通过；`pnpm compose:staging:config` 通过；PowerShell scriptblock 语法检查通过；专项 `python -m pytest services/agent-harness/tests/test_phase9_observability.py services/agent-harness/tests/test_calibration_api.py` 通过，12 passed；`pnpm --filter @ielts-speaking/protocol validate` 通过；`python -m pytest services/speech-assessment/tests` 通过，10 passed；`go test ./...` 通过；显式 mock 环境下 `python -m pytest services/agent-harness/tests` 通过，225 passed。
- 状态说明：本轮继续强化 P12-003 在真实 staging 接入后的自动验收能力；P12-003 仍保持 REVIEW，等待真实公网 HTTPS、MiMo staging key 与 Langfuse staging 实例。

### 2026-06-08 Phase 12 Readiness Evidence 输出加固记录

- 发布留痕加固：`scripts/verify_staging_readiness.ps1` 新增 `-OutputFile` 参数，可把 readiness JSON 保存为发布证据文件；输出新增 `generated_at` 与 `gate_version=staging-readiness-v3`，用于记录 staging 验证时间和门禁版本。
- 文档同步：`docs/staging_environment.md` 已将静态门禁和完整门禁示例改为带 `-OutputFile`，并说明输出 JSON 可直接作为发布记录附件；`docs/release_checklist.md` 的发布记录新增 `Staging readiness evidence JSON` 字段。
- Verification：PowerShell scriptblock 语法检查通过；`pnpm staging:readiness:example` 通过，输出包含 `generated_at`、`gate_version`、`passed=true`；`pnpm compose:staging:config` 通过；`-OutputFile tmp/staging-readiness-outputfile-test.json` 实际写入验证通过，测试文件已清理；`pnpm --filter @ielts-speaking/protocol validate` 通过；`go test ./...` 通过；`python -m pytest services/speech-assessment/tests` 通过，10 passed；显式 mock 环境下 `python -m pytest services/agent-harness/tests` 通过，225 passed。
- 状态说明：本轮继续强化 P12-003 在真实 staging 接入后的发布证据留存能力；P12-003 仍保持 REVIEW，等待真实公网 HTTPS、MiMo staging key 与 Langfuse staging 实例。

### 2026-06-08 Phase 12 Backup Manifest / Restore Integrity 加固记录

- 备份证据加固：`scripts/backup_local.ps1` 已在每次备份目录生成 `manifest.json`，记录 `generated_at`、`backup_version=ielts-speaking-backup-v1`、PostgreSQL dump 与 MinIO archive 的路径、文件大小和 SHA-256，用于发布前备份证据留存。
- 恢复安全加固：`scripts/restore_local.ps1` 默认要求 `manifest.json`，并在执行 `pg_restore` / MinIO mirror 前校验 dump 和 archive 的大小与 SHA-256；缺少 manifest 会阻断恢复，只有显式 `-AllowMissingManifest` 才允许旧备份继续走人工校验路径。
- 文档同步：`docs/backup_recovery_policy.md` 已补充 manifest 与恢复前校验要求；`docs/release_checklist.md` 已新增备份 manifest 字段和 SHA-256 校验确认项。
- 非破坏性 guard verification：PowerShell scriptblock 语法检查通过；恢复脚本缺 manifest 阻断测试通过；错误确认短语阻断测试通过；manifest 文件大小/校验不匹配阻断测试通过。
- Unified verification：`pnpm staging:readiness:example` 通过；`pnpm compose:staging:config` 通过；`docker compose config --quiet` 通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`go test ./...` 通过；`python -m pytest services/speech-assessment/tests` 通过，10 passed；显式 mock 环境下 `python -m pytest services/agent-harness/tests` 通过，225 passed。
- 状态说明：本轮继续强化 P12-004 的数据风险控制和发布证据留存；P12-003 仍保持 REVIEW，等待真实公网 HTTPS、MiMo staging key 与 Langfuse staging 实例。

### 2026-06-08 Phase 12 Migration Audit Evidence 加固记录

- 迁移静态审计：新增 `scripts/audit_migrations.ps1`，检查迁移文件名格式、版本连续性、重复版本、`-- +goose Up` / `-- +goose Down` 是否齐全，并输出每个 SQL 文件的大小与 SHA-256。
- 发布审查证据：迁移审计输出 `audit_version=migration-audit-v1`、`latest_version`、`issue_count`、`review_items`、`passed`；潜在破坏性 Up SQL 会进入 `review_items`，用于发布负责人审查。
- 脚本兼容性：`audit_migrations.ps1`、`backup_local.ps1`、`restore_local.ps1` 已统一使用 `Get-FileHash` + .NET SHA-256 fallback，避免部分 `powershell` 执行环境缺少 `Get-FileHash` 时发布脚本失败。
- 文档同步：`package.json` 新增 `pnpm migration:audit`；`docs/migration_pipeline.md` 已补充 migration audit 命令与发布规则；`docs/release_checklist.md` 已新增 migration audit JSON 记录字段。
- Verification：PowerShell scriptblock 语法检查通过；`pnpm migration:audit` 通过，当前 `migration_count=8`、`latest_version=8`、`issue_count=0`、`review_item_count=0`、`passed=true`；`-OutputFile tmp/migration-audit-outputfile-test.json` 实际写入验证通过，测试文件已清理。
- Unified verification：`pnpm staging:readiness:example` 通过；`pnpm compose:staging:config` 通过；`docker compose config --quiet` 通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`go test ./...` 通过；`python -m pytest services/speech-assessment/tests` 通过，10 passed；显式 mock 环境下 `python -m pytest services/agent-harness/tests` 通过，227 passed。
- 状态说明：本轮继续强化 P12-002 / P12-005 的迁移发布证据留存；P12-003 仍保持 REVIEW，等待真实公网 HTTPS、MiMo staging key 与 Langfuse staging 实例。

### 2026-06-08 Observability / Calibration 后端第四次严格复核与 Trace 字段补齐记录

- 规划缺口复核：按 `ielts_speaking_agent_harness_plan.md` 14.1 Trace 字段逐项反查，发现 `part` 与 `question_id` 原先只存在于事件/state 业务 payload，未作为 Agent Run Trace 的结构化观测字段返回。
- Observability 后端补齐：`AgentRunTrace`、`TraceStep`、`ObservabilityRunSummary` 新增可选 `part`、`question_id`；`TraceRecorder` 会从请求 `session_state` 或响应 `examiner.message` / state 中提取当前题目上下文，并同步写入 Langfuse ingestion metadata。
- 协议与后台同步：`packages/protocol/schemas/agent-run.schema.json` 已同步当前真实 Trace 字段，包括 `part`、`question_id`、tokens、成本、retrieved chunks、structured validity、scoring result 与 error_type；`/admin/observability` 的 step detail payload 已可展示新字段。
- Calibration 复核结论：未发现新的后端功能缺口；`/agent/calibration/anchor-samples`、`/score`、`/speech-regression`、`/multipa-experiment`、`/quality-gate` 仍真实可用，并继续保留合成 contract 样本与生产验收样本的边界。
- Verification：专项 `python -m pytest services/agent-harness/tests/test_agent_api.py services/agent-harness/tests/test_phase9_observability.py services/agent-harness/tests/test_langfuse_trace.py services/agent-harness/tests/test_calibration_api.py services/agent-harness/tests/test_score_calibrator.py services/agent-harness/tests/test_phase10_content_quality.py` 通过，55 passed。
- Unified verification：显式 mock 环境下 `python -m pytest services/agent-harness/tests` 通过，227 passed；`pnpm --filter @ielts-speaking/protocol validate` 通过；`pnpm --filter @ielts-speaking/web typecheck` 通过；`pnpm eval:speech-calibration:contract` 通过，`passed=True samples=12 mae=0.333 max_error=1.000 issues=0`；`pnpm eval:multipa:contract` 通过，`status=passed samples=12 block_release=false risks=0`。
- 状态说明：Observability 与 Calibration 的后端功能性需求现在按规划字段完整补齐；任务状态仍保持 DONE 110、REVIEW 1、DEFERRED 2，P10-006 / P10-007 不因合成 contract 样本转 DONE，P12-003 仍等待真实 staging 输入。

### 2026-06-09 Phase 12 Release Record Example Gate 加固记录

- 发布记录门禁：新增 `scripts/verify_release_record_example.ps1`，自动生成临时 migration audit、staging readiness example、mock backup manifest，并调用 `scripts/generate_release_record.ps1` 生成 release record。
- 门禁校验范围：断言 `record_version=release-record-v1`、`passed=true`、`issue_count=0`，并检查 migration audit、staging readiness、backup manifest 三类 evidence 文件均带 SHA-256；输出目录限制在工作区 `tmp/` 下，运行后默认清理临时文件。
- CI/CD 同步：`package.json` 新增 `pnpm release:record:example`；`.github/workflows/ci.yml` 新增 `Audit migrations` 与 `Validate release record example`，避免发布证据脚本只停留在手工文档层。
- 文档同步：`docs/release_checklist.md` 已补充 release record example gate 命令；P12-001 CI Pipeline 描述同步为覆盖 migration audit、staging readiness example 与 release record example。
- Verification：PowerShell scriptblock 语法检查通过；`pnpm release:record:example` 通过，输出 `status=passed`、`record_version=release-record-v1`、`issue_count=0`；`pnpm migration:audit` 通过，`migration_count=8`、`latest_version=8`、`issue_count=0`、`review_item_count=0`、`passed=true`。
- Unified verification：`pnpm staging:readiness:example` 通过，`gate_version=staging-readiness-v3`、`passed=true`；`pnpm compose:staging:config` 通过；`docker compose config --quiet` 通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`go test ./...` 通过；`python -m pytest services/speech-assessment/tests` 通过，10 passed；显式 mock 环境下 `python -m pytest services/agent-harness/tests` 通过，227 passed；`pnpm --filter @ielts-speaking/web lint`、`pnpm --filter @ielts-speaking/web build`、build 后串行 `pnpm --filter @ielts-speaking/web typecheck` 均通过。
- 状态说明：本轮继续强化 P12-001 / P12-005 的 CI 与发布记录证据闭环；当前任务状态仍保持 DONE 110、REVIEW 1、DEFERRED 2，P12-003 仍等待真实公网 HTTPS、MiMo staging key 与 Langfuse staging 实例。

### 2026-06-09 Phase 12 Migration Status Evidence / Release Record 加固记录

- 迁移状态证据：新增 `scripts/capture_migration_status.ps1`，可通过 Docker Compose、local Go、raw file 或 raw text 捕获 `migrate status` 输出，生成 `migration-status-evidence-v1` JSON，包含 phase、command、exit_code、applied/pending count、latest seen/applied version、rows、raw_stdout 和 issues。
- 发布前后门禁：`pre` phase 默认允许 pending migration；`post` phase 若仍有 pending migration 会失败。新增负向 smoke 验证发布后 pending migration 会阻断。
- Release record 强化：`scripts/generate_release_record.ps1` 现在强制要求 `MigrationStatusBeforeJson` 与 `MigrationStatusAfterJson`，校验 evidence version、phase、exit_code、raw stdout、post pending count，并确认 post latest applied version 不低于 migration audit latest version。
- Example gate 同步：`scripts/verify_release_record_example.ps1` 改为动态读取 migration audit 生成 pre/post status raw evidence，再通过 `capture_migration_status.ps1` 和 `generate_release_record.ps1` 聚合，避免未来新增 migration 时示例门禁硬编码失效。
- 文档与脚本入口：`package.json` 新增 `pnpm migration:status:evidence`；`docs/migration_pipeline.md` 和 `docs/release_checklist.md` 已补充发布前后 migration status evidence JSON 与 release record 参数。
- 测试预期同步：Agent Harness 观测测试从旧的 `tool_calls == []` 更新为验证 `search_questions` / `get_followup_templates` 工具链路成功记录；Question Planner fake 工具 allowlist 断言同步为包含 search / cue card / followup templates，匹配真实题库规划权限模型。
- Verification：`capture_migration_status.ps1` pre raw-text smoke 通过，pending count 为 1 且 `passed=true`；post raw-text smoke 通过，pending count 为 0；post pending negative gate 通过，确认 pending migration 会失败；`pnpm release:record:example` 通过，`record_version=release-record-v1`、`issue_count=0`；`pnpm migration:audit` 通过，`migration_count=8`、`latest_version=8`、`issue_count=0`。
- Unified verification：`pnpm staging:readiness:example` 通过；`pnpm compose:staging:config` 通过；`docker compose config --quiet` 通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`go test ./...` 通过；`python -m pytest services/speech-assessment/tests` 通过，10 passed；显式 mock 环境下 `python -m pytest services/agent-harness/tests` 通过，227 passed；`pnpm --filter @ielts-speaking/web lint`、`pnpm --filter @ielts-speaking/web build`、build 后串行 `pnpm --filter @ielts-speaking/web typecheck` 均通过。
- 状态说明：本轮继续强化 P12-002 / P12-005 的迁移状态留档和发布记录硬门禁；当前任务状态仍保持 DONE 110、REVIEW 1、DEFERRED 2，P12-003 仍等待真实公网 HTTPS、MiMo staging key 与 Langfuse staging 实例。

### 2026-06-09 Phase 12 Backup Integrity Evidence / Release Record 加固记录

- 备份完整性证据：新增 `scripts/verify_backup_manifest.ps1`，只读校验 `manifest.json`、PostgreSQL dump 和 MinIO archive，生成 `backup-integrity-evidence-v1` JSON，包含 manifest 路径、backup version、backup dir、file checks、verified file count、issues 和 passed 状态。
- 校验规则：脚本会验证 manifest 版本、备份目录、dump/archive 记录存在，并确认实际文件存在、大小匹配、SHA-256 匹配；任一缺失、大小不符或 hash 不符都会退出失败。
- Release record 强化：`scripts/generate_release_record.ps1` 现在强制要求 `BackupIntegrityJson`，并校验 evidence version、`passed=true`、`issue_count=0`、至少 2 个文件通过验证，以及 integrity evidence 对应同一个 backup manifest。
- Example gate 同步：`scripts/verify_release_record_example.ps1` 现在会创建真实小型 mock `postgres.dump` / `minio.tgz` 文件，计算实际 SHA-256，生成 backup manifest，再运行 `verify_backup_manifest.ps1` 后聚合进 release record。
- 文档与脚本入口：`package.json` 新增 `pnpm backup:verify`；`docs/backup_recovery_policy.md` 补充发布前 backup integrity evidence 命令；`docs/release_checklist.md` 补充 `BackupIntegrityJson` 参数和 checklist 字段。
- Verification：PowerShell scriptblock 语法检查通过；backup integrity 正向 smoke 通过；篡改 `postgres.dump` 后负向 smoke 通过，确认 hash mismatch 会阻断；`pnpm release:record:example` 通过，输出 `record_version=release-record-v1`、`issue_count=0`；`pnpm migration:audit` 通过，`migration_count=8`、`latest_version=8`、`issue_count=0`。
- Unified verification：`pnpm staging:readiness:example` 通过；`pnpm compose:staging:config` 通过；`docker compose config --quiet` 通过；`pnpm --filter @ielts-speaking/protocol validate` 通过；`go test ./...` 通过；`python -m pytest services/speech-assessment/tests` 通过，10 passed；显式 mock 环境下 `python -m pytest services/agent-harness/tests` 通过，227 passed；`pnpm --filter @ielts-speaking/web lint`、`pnpm --filter @ielts-speaking/web build`、build 后串行 `pnpm --filter @ielts-speaking/web typecheck` 均通过。
- 状态说明：本轮继续强化 P12-004 / P12-005 的备份文件完整性和发布记录硬门禁；当前任务状态仍保持 DONE 110、REVIEW 1、DEFERRED 2，P12-003 仍等待真实公网 HTTPS、MiMo staging key 与 Langfuse staging 实例。

### 2026-06-09 Observability / Calibration 后端复核与本地服务状态记录

- Observability 复核结论：按规划的 `session_id`、`user_id_hash`、`mode`、`part`、`question_id`、`agent_run_id`、`workflow_node`、`prompt_version`、`model_name`、latency、tokens、tool calls、retrieved chunks、structured validity、scoring result 和 error type 逐项反查，Agent Harness 后端仍真实暴露 `/agent/runs/{run_id}`、`/agent/runs/{run_id}/trace`、`/agent/observability/summary`、`/agent/observability/alerts` 与 `/metrics`，并可生成 Langfuse ingestion payload。
- Calibration 复核结论：`/agent/calibration/anchor-samples`、`/agent/calibration/score`、`/agent/calibration/speech-regression`、`/agent/calibration/multipa-experiment`、`/agent/calibration/quality-gate` 仍真实调用 anchor audit、`ScoreCalibrator`、speech calibration regression、MultiPA benchmark comparison 和聚合质量门禁；合成 contract 样本仅用于本地/CI 门禁，生产语音校准仍要求真实授权样本。
- Verification：`pnpm --filter @ielts-speaking/protocol validate` 通过；显式 mock + memory knowledge backend 环境下专项 `python -m pytest services/agent-harness/tests/test_agent_api.py services/agent-harness/tests/test_phase9_observability.py services/agent-harness/tests/test_langfuse_trace.py services/agent-harness/tests/test_calibration_api.py services/agent-harness/tests/test_score_calibrator.py services/agent-harness/tests/test_phase10_content_quality.py` 通过，55 passed；`pnpm eval:speech-calibration:contract` 通过，`passed=True samples=12 mae=0.333 max_error=1.000 issues=0`；`pnpm eval:multipa:contract` 通过，`status=passed samples=12 block_release=false risks=0`。
- 本地服务状态：Docker 后端保持运行，`agent-harness`、`api-go`、`speech-assessment`、`postgres`、`redis`、`minio` 均为 healthy；`http://127.0.0.1:8000/healthz`、`http://127.0.0.1:8010/healthz` 与项目 Go API `http://127.0.0.1:18080/healthz` 均返回 200。
- 前端运行状态：发现 3000 旧 Next dev server 因 `.next` 生成产物不一致返回 500；已停止旧进程、校验并清理 `apps/web/.next` 后重新启动 `pnpm exec next dev --hostname 127.0.0.1 --port 3000`，`http://127.0.0.1:3000/practice` 返回 200。内置浏览器刷新后未出现 Next error 或控制台 error，未登录状态按业务流程跳转到 `/login`。
- 状态说明：Observability 与 Calibration 的后端功能性需求确认已按规划真实实现；当前任务状态仍保持 DONE 110、REVIEW 1、DEFERRED 2，P10-006 / P10-007 等待真实授权语音样本、双人标注样本与 MultiPA adapter 输出，P12-003 等待真实公网 HTTPS、MiMo staging key 与 Langfuse staging 实例。

---

# 5. MVP 验收总标准

MVP 可以进入内测的最低标准：

1. 用户可以注册/登录。
2. 用户可以填写背景问卷。
3. 管理员可以导入并激活一批题库。
4. 用户可以选择完整考试或单项练习。
5. 前端可以完成考官提问、TTS 播放、用户录音、上传、ASR 转写。
6. Agent 可以按 Part 1/2/3 推进流程。
7. 完整考试结束后能生成四维模拟评分。
8. 报告页能展示分数、证据、建议、参考答案和录音回放。
9. Agent 调用、工具调用、模型调用有 Trace。
10. 核心路径有端到端测试。
11. 用户录音和隐私处理有授权与删除机制。
12. Docker Compose 能启动本地完整环境。

---

# 6. 高风险任务清单

| 风险任务 | 风险点 | 应对策略 |
|---|---|---|
| ASR/TTS 链路 | 延迟、格式兼容、失败重试 | 先做回合制，失败时文字兜底，TTS 缓存 |
| 评分系统 | 分数不稳定、用户不信任 | 四维独立评分、Reviewer、Anchor Set、置信度 |
| Agent 工具调用 | 越权、Prompt 注入 | MCP allowlist、scope、审计、Promptfoo 红队 |
| 题库内容 | 版权、质量不稳定 | source_type、license、review_status、审核流程 |
| Live 体验 | 前后端状态不同步 | 统一 AG-UI 风格事件、WebSocket 状态恢复 |
| 移动端录音 | 浏览器兼容差异 | 早期做 iOS/Android 真机测试 |
| Avatar | 性能影响主流程 | MVP 可关闭，先用 Live2D 轻量方案 |

---

# 7. 建议排期顺序

建议按以下并行方式推进：

```text
第 1 组：Go Backend
  Phase 1 -> Phase 6 -> Phase 7 persistence -> Phase 11

第 2 组：Agent Harness
  Phase 2 -> Phase 3 -> Phase 5 -> Phase 7 -> Phase 9

第 3 组：Frontend
  Phase 4 -> Phase 5 UI -> Phase 7 report -> Phase 8 admin

第 4 组：Content / QA / DevOps
  Phase 0 -> Phase 3 content -> Phase 9 -> Phase 10 -> Phase 12
```

最重要的路径是：

```text
P0-005 Docker 基线
  -> P1-007 会话 API
  -> P2-005 ExamWorkflow
  -> P3-006 question-bank-mcp
  -> P4-012 单轮问答闭环
  -> P5-007 full_exam
  -> P7-008 ScoringWorkflow
  -> P7-011 报告页
  -> P9-005 E2E 测试
```

只要这条路径打通，项目就从“架构设想”进入“可持续优化的真实产品”。
