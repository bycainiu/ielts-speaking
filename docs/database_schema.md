# 数据库 Schema 基线

## 迁移工具

Go API 使用 Goose 管理数据库迁移，迁移文件位于：

```text
services/api-go/internal/db/migrations
```

迁移文件通过 `go:embed` 打进 Go 二进制，保证本地、Docker 和后续 CI 使用同一份 SQL。

## 执行迁移

```powershell
cd services/api-go
go run ./cmd/api migrate up
go run ./cmd/api migrate status
go run ./cmd/api migrate down
```

迁移默认读取 `DATABASE_URL`。本地 Docker Compose 的默认连接串为：

```text
postgres://ielts:ielts@localhost:5432/ielts_speaking?sslmode=disable
```

## 当前核心表

### 用户与隐私

- `users`
- `user_profiles`
- `background_questionnaires`
- `background_facts`
- `consent_records`

这些表支撑登录身份、背景问卷、隐私排除字段和录音授权记录。`background_facts.is_excluded` 用于保证 Agent 检索时不返回用户禁用的信息。

### 题库与内容

- `seasons`
- `topic_categories`
- `topics`
- `questions`
- `cue_cards`
- `followup_templates`
- `question_versions`

题目保留 `source_type`、`license`、`review_status`，满足版权与审核追踪要求。只有后续业务层筛选出的 `active` 内容应进入正式练习。

### 知识库与向量检索

- `knowledge_docs`
- `knowledge_chunks`

`knowledge_chunks.embedding` 使用 `vector(1536)`，并建立 cosine ivfflat 索引。metadata 使用 GIN 索引，并额外为 `part`、`season_id` 建表达式索引，服务题库与 Rubric 检索过滤。

### 会话、音频与 ASR

- `practice_sessions`
- `session_parts`
- `session_turns`
- `audio_assets`
- `asr_results`
- `speech_metrics`

这些表支撑 full exam、单项练习、回合记录、录音资产、ASR 转写和语音指标。

`asr_results` 会同时保存原始转写、可选人工修正文案、ASR 置信度、segments，以及脱敏后的供应商原始响应摘要；写入时 `audio_asset_id` 必须属于当前 turn，避免跨会话误关联。

`speech_metrics` 保存每个用户回答 turn 的客观流利度指标，包括 `duration_ms`、`words_count`、`wpm`、`long_pause_count`、`mean_pause_ms`、`total_pause_ms`、`filler_count`、`filler_ratio`、`asr_confidence` 和 `raw_metrics`。当前 MVP 支持从用户录音时长和最新 ASR / 人工修正文案推导词数、WPM、填充词指标，并根据传入的 pause segments 估算长停顿，供后续 ScoringWorkflow 作为证据使用。

`tts_cache` 按 `text_hash + voice_id + speaking_rate + emotion + style` 的稳定缓存 key 保存考官 TTS 音频 payload、provider/model 元信息和 `expires_at`。缓存命中用于跳过重复 TTS 模型调用；具体会话仍会生成自己的 `examiner_tts` audio asset，保证对象权限边界清晰。

### Agent、模型审计与报告

- `agent_runs`
- `agent_steps`
- `model_calls`
- `score_reports`
- `criterion_scores`
- `feedback_items`
- `reference_answers`
- `study_plans`
- `prompt_versions`
- `eval_runs`

评分报告固定包含官方免责声明字段：`AI 模拟评分仅用于练习参考，不代表 IELTS 官方成绩。`

## 设计原则

- 所有核心业务表都有 `created_at`，可变业务表有 `updated_at`。
- 软删除使用 `deleted_at`，避免用户历史复盘和审计链路断裂。
- Agent Run 使用文本 ID，以便与 Python Agent Harness 的 `run_xxx` ID 直接对齐。
- 模型调用表只保存脱敏输入和输出摘要，不保存完整敏感 prompt。
