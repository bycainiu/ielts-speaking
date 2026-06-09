# Go API Service

Go + Gin 业务 API / BFF 服务。当前版本提供配置加载、健康检查和基础路由，后续承载用户鉴权、会话、WebSocket Gateway、音频资产、Agent Harness Client 和持久化访问。

## 本地运行

```powershell
cd services/api-go
go mod tidy
go run ./cmd/api
```

## 数据库迁移

```powershell
go run ./cmd/api migrate up
go run ./cmd/api migrate status
go run ./cmd/api migrate down
```

迁移使用 `DATABASE_URL`，默认适配本地 Docker Compose 的 PostgreSQL + pgvector。

## 测试

```powershell
go test ./...
```

## 接口

- `GET /healthz`
- `GET /readyz`
- `GET /api/version`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/me`
- `GET /api/me/background`
- `PUT /api/me/background`
- `GET /api/seasons/active`
- `GET /api/topics`
- `GET /api/questions`
- `GET /api/questions/:id`
- `POST /api/admin/question-bank/seasons`
- `GET /api/admin/question-bank/seasons`
- `PUT /api/admin/question-bank/seasons/:id`
- `POST /api/admin/question-bank/seasons/:id/activate`
- `DELETE /api/admin/question-bank/seasons/:id`
- `POST /api/admin/question-bank/topics`
- `GET /api/admin/question-bank/topics`
- `PUT /api/admin/question-bank/topics/:id`
- `DELETE /api/admin/question-bank/topics/:id`
- `POST /api/admin/question-bank/questions`
- `GET /api/admin/question-bank/questions`
- `GET /api/admin/question-bank/questions/:id`
- `PUT /api/admin/question-bank/questions/:id`
- `DELETE /api/admin/question-bank/questions/:id`
- `POST /api/sessions`
- `GET /api/sessions`
- `GET /api/sessions/:id`
- `POST /api/sessions/:id/start`
- `POST /api/sessions/:id/parts/:part/complete`
- `POST /api/sessions/:id/finish`
- `POST /api/sessions/:id/cancel`
- `POST /api/sessions/:id/turns`
- `PATCH /api/sessions/:id/turns/:turn_id`
- `POST /api/sessions/:id/turns/:turn_id/audio-assets`
- `POST /api/sessions/:id/turns/:turn_id/asr-results`
- `PATCH /api/sessions/:id/turns/:turn_id/asr-results/:asr_result_id/correction`
- `POST /api/sessions/:id/turns/:turn_id/speech-metrics`
- `GET /api/ws/sessions/:id`
- `POST /api/audio/upload`
- `POST /api/audio/tts`
- `GET /api/audio/:id/signed-url`

## Auth API 示例

注册：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/auth/register `
  -ContentType application/json `
  -Body '{"email":"learner@example.com","password":"secret-password","display_name":"Learner"}'
```

登录后访问当前用户：

```powershell
$login = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/auth/login `
  -ContentType application/json `
  -Body '{"email":"learner@example.com","password":"secret-password"}'

Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8080/api/me `
  -Headers @{ Authorization = "Bearer $($login.token.access_token)" }
```

## Background API

查询当前用户背景资料：

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8080/api/me/background `
  -Headers @{ Authorization = "Bearer $accessToken" }
```

保存或更新背景问卷、隐私排除字段和结构化 facts：

```powershell
Invoke-RestMethod -Method Put -Uri http://127.0.0.1:8080/api/me/background `
  -Headers @{ Authorization = "Bearer $accessToken" } `
  -ContentType application/json `
  -Body '{
    "profile": {
      "display_name": "Learner",
      "timezone": "Asia/Shanghai",
      "target_band": 7.0,
      "current_band": 6.0,
      "preferred_exam_date": "2026-08-01"
    },
    "answers": {
      "hometown": "Hangzhou",
      "study_goal": "Improve Part 3 answers",
      "free_note": "I prefer technology and education topics."
    },
    "privacy_exclusions": ["workplace"],
    "facts": [
      {"topic": "personal", "fact_key": "hometown", "fact_value": "Hangzhou"},
      {"topic": "work", "fact_key": "workplace", "fact_value": "Private employer", "privacy_level": "sensitive"}
    ],
    "submitted": true
  }'
```

响应中的 `facts` 会返回用户自己的完整事实列表，`agent_facts` 只返回未被排除的 facts，供后续 MCP/Profile 工具复用。省略 `facts` 会保留旧 facts，显式传入 `"facts": []` 会清空当前问卷 facts。

## Question Bank API

公开题库查询只返回 active 内容：

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/api/questions?part=1&limit=20"
```

后台题库 CRUD 需要 `operator` 或 `admin` 角色：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/admin/question-bank/questions `
  -Headers @{ Authorization = "Bearer $accessToken" } `
  -ContentType application/json `
  -Body '{
    "part": 2,
    "text": "Describe a place in your city that you enjoy visiting.",
    "source_type": "original",
    "review_status": "draft",
    "cue_card": {
      "prompt": "Describe a place in your city that you enjoy visiting.",
      "bullet_points": ["where it is", "what you do there", "why you like it"]
    }
  }'
```

Part 2 题目必须带 `cue_card`；Part 1 / Part 3 不允许带 `cue_card`，可使用 `followup_templates` 管理追问。

## Session API

创建完整考试会话：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/sessions `
  -Headers @{ Authorization = "Bearer $accessToken" } `
  -ContentType application/json `
  -Body '{"mode":"full_exam","season_id":"<season-id>"}'
```

创建单项练习：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/sessions `
  -Headers @{ Authorization = "Bearer $accessToken" } `
  -ContentType application/json `
  -Body '{"mode":"part_practice","target_part":2}'
```

记录用户回答、ASR 和语音指标：

```powershell
$turn = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/sessions/$sessionId/turns" `
  -Headers @{ Authorization = "Bearer $accessToken" } `
  -ContentType application/json `
  -Body '{"part":1,"speaker":"user","status":"recording","answer_text":"I come from Hangzhou."}'

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/sessions/$sessionId/turns/$($turn.turn.id)/asr-results" `
  -Headers @{ Authorization = "Bearer $accessToken" } `
  -ContentType application/json `
  -Body '{"provider":"mock_asr","model":"mimo-v2.5-asr","transcript":"I come from Hangzhou.","confidence":0.93,"raw_response":{"provider_request_id":"mock_001","audio_base64":"redacted-before-save"}}'

Invoke-RestMethod -Method Patch -Uri "http://127.0.0.1:8080/api/sessions/$sessionId/turns/$($turn.turn.id)/asr-results/$asrResultId/correction" `
  -Headers @{ Authorization = "Bearer $accessToken" } `
  -ContentType application/json `
  -Body '{"corrected_transcript":"I come from Hangzhou, a city in eastern China."}'
```

ASR 持久化会校验 `audio_asset_id` 必须属于当前 turn；`raw_response` 入库前会脱敏保存为 `raw_response_redacted`；用户人工修正会写入 `corrected_transcript`、`corrected_by_user_id` 和 `corrected_at`。

保存语音指标：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/sessions/$sessionId/turns/$($turn.turn.id)/speech-metrics" `
  -Headers @{ Authorization = "Bearer $accessToken" } `
  -ContentType application/json `
  -Body '{"audio_asset_id":"'$audioAssetId'","long_pause_threshold_ms":1000,"pause_segments":[{"start_ms":1000,"end_ms":1600},{"start_ms":3000,"end_ms":4600}],"asr_confidence":0.93}'
```

`speech-metrics` 可以显式接收 `duration_ms`、`transcript`、`words_count`、`wpm`、`long_pause_count`、`mean_pause_ms`、`total_pause_ms`、`filler_count` 和 `filler_ratio`。省略这些字段时，服务会优先从当前 turn 的用户录音 `duration_ms` 与最新 ASR / 人工修正文案推导 `words_count`、`wpm`、填充词数量和填充词比例；传入 `pause_segments` 时会按 `long_pause_threshold_ms` 估算长停顿数量、平均长停顿和长停顿总时长。`audio_asset_id` 仍会校验必须属于当前 turn。

合成并保存考官 TTS 音频：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/audio/tts" `
  -Headers @{ Authorization = "Bearer $accessToken" } `
  -ContentType application/json `
  -Body '{"session_id":"'$sessionId'","turn_id":"'$turnId'","text":"Let''s talk about your hometown.","voice_id":"ielts_examiner_default","speaking_rate":1.0,"emotion":"neutral","style":"examiner"}'
```

该接口会调用 Agent Harness 的 `POST /agent/audio/synthesize`，再以 `examiner_tts` 类型保存到 MinIO/S3，并返回 `audio_asset` 与 TTS provider/model/voice 元信息。

TTS 会按 `text + voice_id + speaking_rate + emotion + style` 生成缓存 key；命中缓存时不会再次调用 Agent Harness TTS provider，但仍会为当前 turn 保存独立的 `examiner_tts` 音频资产，避免跨用户复用 `audio_asset` 权限。响应中的 `tts.cache_hit` 可用于观察缓存效果。

清理过期 TTS 缓存：

```powershell
Invoke-RestMethod -Method Delete -Uri "http://127.0.0.1:8080/api/audio/tts/cache/expired" `
  -Headers @{ Authorization = "Bearer $accessToken" }
```

`POST /api/sessions/:id/finish` 会把会话推进到 `scoring`，为后续 ScoringWorkflow 接管留出状态边界。

## WebSocket Gateway

连接指定会话的实时事件通道：

```text
ws://127.0.0.1:8080/api/ws/sessions/<session-id>?access_token=<access-token>
```

服务端也支持通过 WebSocket 握手请求的 `Authorization: Bearer <access-token>` 传 token；浏览器原生 `WebSocket` 通常无法设置自定义 header，因此前端可使用 `access_token` 查询参数。连接前会校验 access token 和 session 归属，跨用户 session 不能连接。

客户端发送和接收的消息使用 `packages/protocol/schemas/session-event.schema.json` 中定义的 `SessionEvent` 结构：

```json
{
  "type": "timer.tick",
  "session_id": "<session-id>",
  "run_id": "run_001",
  "payload": {
    "remaining_seconds": 45
  },
  "created_at": "2026-06-07T14:08:42Z"
}
```

Gateway 会按 `session_id` 广播事件；同一 session 下多个连接会收到同一事件，断线后用同一个有效 token 和 session URL 重新连接即可恢复实时通道。

## Audio API

上传用户录音到对象存储，并写入 `audio_assets`：

```powershell
$upload = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/audio/upload `
  -Headers @{ Authorization = "Bearer $accessToken" } `
  -Form @{
    session_id = $sessionId
    turn_id = $turnId
    duration_ms = "18000"
    file = Get-Item ".\answer.webm"
  }
```

获取回放用签名 URL：

```powershell
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8080/api/audio/$($upload.audio_asset.id)/signed-url?expires_seconds=300" `
  -Headers @{ Authorization = "Bearer $accessToken" }
```

响应包含 `audio_asset`、`signed_url` 和 `expires_at`。前端复盘页应在播放前获取短期 `signed_url`，播放失败或临近过期时重新请求该接口，不应缓存或展示永久对象地址。

上传接口会校验当前用户是否拥有对应 session/turn，并限制音频类型、文件大小和 `duration_ms`。默认允许 `audio/webm`、`audio/wav`、`audio/mpeg`、`audio/mp4`、`audio/ogg`，默认最大 25MB、10 分钟；当 multipart 客户端只发送 `application/octet-stream` 时，会按受控文件扩展名推断 MIME。

在 Docker Compose 中，`S3_ENDPOINT` 用于 API 容器访问 MinIO，`S3_PUBLIC_ENDPOINT` 用于生成浏览器可访问的签名 URL，例如 `http://localhost:9000`。

## Report API

保存 Agent Harness 生成的评分报告、四维分、反馈项、参考答案和下一轮训练计划：

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8080/api/sessions/$sessionId/report" `
  -Headers @{ Authorization = "Bearer $accessToken" } `
  -Body ($scoreReportPayload | ConvertTo-Json -Depth 20) `
  -ContentType "application/json"
```

读取当前 session 最新版本报告：

```powershell
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8080/api/sessions/$sessionId/report" `
  -Headers @{ Authorization = "Bearer $accessToken" }
```

报告保存前会校验 session 归属，按 `(session_id, version)` 幂等更新，并返回 `criteria`、`feedback_items`、`reference_answers` 和 `study_plans`。如果 Agent 返回的 `model_run_id` 尚未写入 `agent_runs`，服务会把外键字段置空，但仍在 `raw_report` 中保留原始 Agent 输出，避免整份报告因为观测链路暂未落库而丢失。

## Web 回放页

- `apps/web/components/ReplayAudioPanel.tsx` 会按 turn 聚合 `user_recording`、`examiner_tts` 和 `reference` 音频资产。
- `/report/[sessionId]` 会读取 `GET /api/sessions/:id` 返回的 turn/audio asset 列表和 `GET /api/sessions/:id/report` 返回的最新评分报告，展示四维分、evidence、建议、参考答案和训练计划，并把音频交给 `ReplayAudioPanel` 播放。
- 回放控件显示当前播放进度，支持拖动进度条；每次播放前会获取短期签名 URL，点击刷新或播放失败时会重新拉取签名 URL。

## 命令

- `api migrate up`：执行所有待执行迁移。
- `api migrate down`：回滚最近一次迁移。
- `api migrate status`：查看迁移状态。
- `api healthcheck`：Docker 健康检查入口。
