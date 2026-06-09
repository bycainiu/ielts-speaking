# 环境变量与密钥管理

## 基本原则

- 仓库只提交 `.env.example`，不提交真实 `.env`。
- 本地环境允许使用 mock 模型和开发密钥，生产环境必须显式配置真实密钥。
- 服务启动时应对生产环境关键配置做校验，缺失时返回明确错误。
- Trace、日志和审计记录不得明文保存高敏感用户资料。

## 关键配置

| 配置 | 用途 |
|---|---|
| `DATABASE_URL` | Go API 连接 PostgreSQL |
| `REDIS_URL` | Go API 连接 Redis |
| `JWT_SECRET` | 用户鉴权签名密钥 |
| `AGENT_HARNESS_URL` | Go API 与 Web BFF 调用 Agent Harness |
| `MIMO_API_KEY` | Agent Harness 调用 MiMo 模型 |
| `MIMO_BASE_URL` | MiMo OpenAI-compatible / Anthropic-compatible API 地址 |
| `MIMO_DEFAULT_MODEL` | 默认模型，当前为 `mimo-v2.5-pro` |
| `MIMO_API_FORMAT` | 模型 API 格式，支持 `openai` 或 `anthropic` |
| `MIMO_TIMEOUT_SECONDS` | 单次模型请求超时时间 |
| `MIMO_MAX_RETRIES` | 可重试模型错误的最大重试次数 |
| `MIMO_MODEL_ROUTES_JSON` | Agent Harness 任务级模型路由配置 |
| `MIMO_INPUT_COST_USD_PER_1K_TOKENS` | Observability 估算输入 token 成本 |
| `MIMO_OUTPUT_COST_USD_PER_1K_TOKENS` | Observability 估算输出 token 成本 |
| `MIMO_AVAILABLE_MODELS_JSON` | 当前供应商可用 MiMo 模型清单，供后续真实测试、ASR/TTS 与路由校验引用 |
| `MOCK_MODEL_ENABLED` | 本地是否启用 mock 模型 |
| `KNOWLEDGE_STORE_BACKEND` | Knowledge Service 后端，支持 `memory` 或 `pgvector` |
| `KNOWLEDGE_DATABASE_URL` | Knowledge Service 连接 PostgreSQL/pgvector 的地址 |
| `KNOWLEDGE_EMBEDDING_MODEL` | Knowledge Service 使用的 embedding 模型名 |
| `KNOWLEDGE_EMBEDDING_DIMENSION` | embedding 维度，pgvector 表当前为 1536 |
| `KNOWLEDGE_CHUNK_MAX_CHARS` | 知识文档切片最大字符数 |
| `KNOWLEDGE_CHUNK_OVERLAP_CHARS` | 相邻 chunk 的重叠字符数 |
| `S3_ENDPOINT` | 对象存储地址 |
| `S3_PUBLIC_ENDPOINT` | 生成签名 URL 时对浏览器暴露的对象存储地址 |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | 对象存储访问密钥 |
| `S3_REGION` | S3 区域，本地 MinIO 可使用 `local` |
| `S3_USE_SSL` | S3 端点是否使用 HTTPS |
| `MINIO_BUCKET` | 音频资产默认存储桶 |
| `AUDIO_MAX_UPLOAD_BYTES` | 单个音频上传最大字节数，默认 25MB |
| `AUDIO_MAX_DURATION_MS` | 单个音频上传最大时长，默认 10 分钟 |
| `LANGFUSE_ENABLED` | Agent Harness 是否向 Langfuse 导出 trace |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Langfuse API 密钥 |
| `LANGFUSE_HOST` | Langfuse 服务地址 |
| `LANGFUSE_TIMEOUT_SECONDS` | Langfuse 导出请求超时时间 |
| `TRACE_USER_HASH_SALT` | Trace 中 user_id 哈希盐 |
| `TRACE_STORE_LIMIT` | Agent Harness 本地内存 trace 保留数量 |

## JWT 配置要求

- `JWT_SECRET` 至少 32 个字符。
- 本地可以使用 `.env.example` 中的开发密钥。
- 生产环境必须使用随机生成的高强度密钥，并通过密钥管理系统注入。
- Access token 用于普通 API 鉴权，refresh token 只允许调用刷新接口。

## MiMo 模型配置

- `MIMO_DEFAULT_MODEL` 默认使用 `mimo-v2.5-pro`，用于组卷、追问、评分、反馈等高推理任务。
- `MIMO_API_FORMAT=openai` 时，Agent Harness 调用 `/chat/completions`，支持 `tools` 和 `response_format`。
- `MIMO_API_FORMAT=anthropic` 时，Agent Harness 调用 `/messages`，会将 system message、tool use 和 token usage 转换为内部统一结构。
- `MIMO_TIMEOUT_SECONDS` 和 `MIMO_MAX_RETRIES` 用于控制模型调用的超时和可重试错误；生产环境应结合上游 SLA 和用户实时体验设置。
- `MIMO_MODEL_ROUTES_JSON` 是 JSON 对象，用于按任务覆盖模型、fallback 模型、`temperature` 和 `max_tokens`。内置任务包括 `question_planning`、`examiner`、`followup_planning`、`scoring`、`feedback`、`cheap` 和 `default`。
- `MIMO_AVAILABLE_MODELS_JSON` 记录当前模型供应商允许使用的模型清单，当前包含 `mimo-v2.5-pro`、`mimo-v2.5`、`mimo-v2.5-asr`、`mimo-v2.5-tts-voiceclone`、`mimo-v2.5-tts-voicedesign`、`mimo-v2.5-tts`、`mimo-v2-pro`、`mimo-v2-omni`、`mimo-v2-tts`。
- `MIMO_INPUT_COST_USD_PER_1K_TOKENS` 与 `MIMO_OUTPUT_COST_USD_PER_1K_TOKENS` 默认为 0；配置真实单价后，Agent Harness trace、summary 和 Prometheus metrics 会输出估算模型成本。
- 本地真实供应商凭据只写入未提交的 `.env`，仓库中的 `.env.example` 只保留占位值和模型清单，不保存真实 API key。
- fallback 模型只在可重试错误上使用，例如上游 5xx、429、网络错误或超时；401/403 等鉴权错误不会 fallback，避免掩盖密钥或权限配置问题。
- `MOCK_MODEL_ENABLED=true` 时工作流仍可使用确定性 mock 输出；真实模型接入由后续工作流节点逐步切换到 `MiMoChatClient`。

示例：

```json
{
  "scoring": {
    "model": "mimo-v2.5-pro",
    "fallback_model": "mimo-v2.5",
    "temperature": 0.0,
    "max_tokens": 1800
  },
  "feedback": {
    "model": "mimo-v2.5-pro",
    "temperature": 0.4,
    "max_tokens": 1800
  },
  "cheap": {
    "model": "mimo-v2.5",
    "temperature": 0.2,
    "max_tokens": 512
  }
}
```

## 音频与对象存储配置

- 本地 Docker Compose 使用 MinIO，默认 API 地址为 `http://minio:9000`，控制台为 `http://localhost:9001`。
- Go API 通过 `S3_ENDPOINT`、`S3_ACCESS_KEY`、`S3_SECRET_KEY`、`S3_REGION`、`S3_USE_SSL` 连接对象存储。
- Docker Compose 中 `S3_ENDPOINT` 使用容器内地址 `http://minio:9000`；`S3_PUBLIC_ENDPOINT` 默认使用宿主机可访问的 `http://localhost:9000`，用于生成浏览器可直接访问的签名 URL。
- `MINIO_BUCKET` 是音频上传落桶名称，服务会在上传时确认 bucket 存在，不存在则创建。
- `AUDIO_MAX_UPLOAD_BYTES` 和 `AUDIO_MAX_DURATION_MS` 是上传安全边界；前端展示限制时应和这两个配置保持一致。
- 回放必须通过 `GET /api/audio/:id/signed-url` 获取短期签名 URL，不应直接暴露永久对象地址；前端播放失败或 URL 临近过期时应重新获取签名 URL。

## Knowledge Service 配置

- `KNOWLEDGE_STORE_BACKEND=memory` 是本地默认值，使用确定性 hash embedding 和内存索引，适合单元测试和 mock 工作流。
- `KNOWLEDGE_STORE_BACKEND=pgvector` 时，Agent Harness 使用 `KNOWLEDGE_DATABASE_URL` 连接 PostgreSQL，并写入既有 `knowledge_docs`、`knowledge_chunks` 表。
- 当前数据库迁移中 `knowledge_chunks.embedding` 是 `vector(1536)`，因此 pgvector 后端要求 `KNOWLEDGE_EMBEDDING_DIMENSION=1536`。
- `KNOWLEDGE_EMBEDDING_MODEL=hash-embedding-v1` 是可重复的本地基线；后续接入真实 embedding 模型时，需要保持写入的 `embedding_model` 可追踪。
- `KNOWLEDGE_CHUNK_MAX_CHARS` 和 `KNOWLEDGE_CHUNK_OVERLAP_CHARS` 控制切片粒度。题库、Rubric、用户背景、主题知识和历史复盘的 metadata 规范已在 `docs/knowledge_chunk_spec.md` 固化，并由 Agent Harness ingest 边界校验。
- `/healthz` 会返回 Knowledge Service 后端摘要，便于确认当前运行环境使用 memory 还是 pgvector。

## Trace 与 Langfuse 配置

- `LANGFUSE_ENABLED=false` 时，Agent Harness 仍会在本地内存记录 Agent Run Trace，供 `GET /agent/runs/:run_id/trace` 查询，便于本地开发和测试。
- `LANGFUSE_ENABLED=true` 时，Agent Harness 会尝试向 `LANGFUSE_HOST/api/public/ingestion` 导出 trace；此时必须配置 `LANGFUSE_PUBLIC_KEY` 和 `LANGFUSE_SECRET_KEY`。
- Trace 必须包含 `session_id`、`run_id`、工作流节点、prompt version、模型名、工具调用摘要、节点耗时和状态。
- Trace 不保存原始 `user_id`，只保存使用 `TRACE_USER_HASH_SALT` 计算的 `user_id_hash`；生产环境必须配置非默认 salt。
- Trace 输入摘要不得保存完整 ASR 文本、密钥、Bearer token、邮箱等敏感内容；当前实现只记录 ASR 文本长度和必要状态字段。
- `TRACE_STORE_LIMIT` 只控制本地内存保留数量，不替代数据库审计表和 Langfuse 长期存储。

## 环境分层

- `local`：默认使用 mock 模型，Docker Compose 一键启动。
- `dev`：可接入真实 MiMo API 和 Langfuse。
- `staging`：接近生产配置，使用脱敏数据跑回归评测。
- `prod`：必须启用 HTTPS、真实密钥、备份、监控和告警。
