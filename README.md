# IELTS Speaking Platform

雅思口语练习网站的 monorepo 工程基线。当前版本已落地 Phase 0 的项目骨架、协议约定、Docker 本地环境，以及 Agent Harness / Go API / Web 前端的最小可运行服务；Go API 已推进到鉴权、背景问卷、题库、会话、WebSocket Gateway 和音频资产服务。

## 目录结构

```text
apps/
  web/                     # Next.js 前端
services/
  api-go/                  # Go + Gin 业务 API / BFF
  agent-harness/           # Python FastAPI Agent Harness
  speech-assessment/       # Python FastAPI 语音 evidence 服务
  worker/                  # 异步任务预留目录
packages/
  protocol/                # 前后端与 Agent 共享协议 schema
infra/                     # 部署与基础设施配置预留目录
docs/                      # 架构、配置、范围与 ADR
```

## 本地启动

1. 复制环境变量：

```powershell
Copy-Item .env.example .env
```

2. 启动本地环境：

```powershell
docker compose up --build
```

3. 访问服务：

```text
Web:            http://localhost:3000
Go API:         http://localhost:8080/healthz
Agent Harness: http://localhost:8000/healthz
Speech Evidence: http://localhost:8010/healthz
MinIO Console: http://localhost:9001
```

## 常用校验

```powershell
docker compose config
cd services/api-go; go test ./...
cd services/agent-harness; .\.venv\Scripts\python.exe -m pytest tests
cd services/speech-assessment; python -m pytest tests
pnpm --filter @ielts-speaking/protocol validate
```

## 数据库迁移

```powershell
cd services/api-go
go run ./cmd/api migrate up
go run ./cmd/api migrate status
```

## 当前工程状态

- Phase 0 的 MVP 范围、架构基线、monorepo、协作规范、Docker 基线、环境变量规范、通用协议 schema 已建立。
- PostgreSQL / pgvector 核心 schema 已建立，迁移文件通过 Go 二进制嵌入执行。
- Go API 已提供注册、登录、刷新 token、当前用户信息、Bearer 鉴权中间件和 WebSocket 鉴权。
- 背景问卷 API 已支持用户 profile、结构化 answers、自由补充、privacy exclusions 和 Agent 安全 facts 视图。
- 题库 API 已支持 season、topic、question CRUD，覆盖 Part 1 / Part 2 cue card / Part 3 题型结构。
- 会话 API 已支持 full_exam、part_practice、topic_practice，能够记录 turn、audio metadata、ASR 和 speech metrics。
- WebSocket Gateway 已支持 `/api/ws/sessions/:id`，可按 session 广播共享协议事件并支持断线后使用同一 token/session 重连。
- 音频资产服务已接入 MinIO/S3，支持录音上传、`audio_assets` 持久化、签名 URL 回放，以及文件类型、大小、时长限制。
- Agent Harness 提供 `/healthz`、`/metrics` 与 `/agent/sessions/{id}` 流程接口，已封装 MiMoChatClient、RAG、MCP、Trace、评分与反馈工作流；当前主链路使用确定性工作流保障回归稳定，并已建立 Microsoft Agent Framework core 适配边界。
- Speech Assessment Service 提供独立语音 evidence 层，输出 ASR word timestamps、audio quality、fluency、pronunciation evidence 和 confidence；协议禁止直接输出 IELTS band。
- Go API 提供 Gin 服务骨架与健康检查。
- Web 前端提供 Live 练习控制台骨架，后续接入真实 WebSocket、录音、ASR、TTS 与报告页。
