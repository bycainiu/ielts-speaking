# Staging 环境

Staging 使用与本地 Docker Compose 相同的服务拓扑，但必须替换为接近生产的密钥、模型路由、对象存储和观测配置。

## 配置

1. 将 `.env.staging.example` 复制到部署平台的密钥管理或环境变量配置中。
2. 替换所有 `change-me` 和 `replace-with-*` 值。
3. 设置 `APP_ENV=staging`。
4. 真实模型联调时设置 `MOCK_MODEL_ENABLED=false`；只跑确定性回归时才允许临时设为 `true`。
5. 设置 `LANGFUSE_ENABLED=true`，并指向 staging 观测实例。

## 启动

```powershell
docker compose --env-file .env.staging -f docker-compose.yml -f docker-compose.staging.yml config --quiet
docker compose --env-file .env.staging -f docker-compose.yml -f docker-compose.staging.yml up -d --build
docker compose --env-file .env.staging -f docker-compose.yml -f docker-compose.staging.yml run --rm api-go migrate up
```

## 验证脚本

部署前先运行静态门禁：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_staging_readiness.ps1 -EnvFile .env.staging -SkipRemoteChecks -OutputFile tmp/staging-readiness-static.json
```

部署并暴露公网 HTTPS URL 后运行完整门禁：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_staging_readiness.ps1 -EnvFile .env.staging -OutputFile tmp/staging-readiness-full.json
```

`-OutputFile` 会保存与终端输出一致的 JSON，包含 `generated_at`、`gate_version`、remote checks、issues 和最终 `passed` 状态，可直接作为发布记录附件。

脚本会检查：

- `.env.staging` 必填项是否存在。
- 是否仍存在 `change-me`、`replace-with-*`、`example.com` 占位符。
- Web / API / MinIO / Agent Harness / Speech Assessment / Langfuse public endpoint 是否使用 HTTPS。
- `LANGFUSE_ENABLED=true` 是否开启，避免 staging 缺失 Trace 观测。
- Staging compose config 是否可解析。
- `STAGING_WEB_URL`、`NEXT_PUBLIC_API_BASE_URL/healthz`、`/readyz` 是否可访问。
- `AGENT_HARNESS_PUBLIC_URL` 的 `/healthz`、`/metrics`、`/agent/observability/summary`、`/agent/observability/alerts` 是否可访问，且无 critical alert。
- `AGENT_HARNESS_PUBLIC_URL/agent/calibration/quality-gate` 是否可运行，且没有 release-blocking check。
- `SPEECH_ASSESSMENT_PUBLIC_URL` 的 `/healthz` 与 `/metrics` 是否可访问。
- `SPEECH_ASSESSMENT_PUBLIC_URL/speech/transcribe-timestamps` 是否能返回词级时间戳。
- `SPEECH_ASSESSMENT_PUBLIC_URL/speech/assess` 是否返回 evidence，并确认 `policy.ielts_band_output_allowed=false` 且响应中没有 `overall_band`、`predicted_band` 或直接 `band` 字段。
- `LANGFUSE_HOST` 是否可访问，用于确认 staging 观测实例已接入。

## 健康检查

- Web：`STAGING_WEB_URL`
- Go API：`/healthz` 与 `/readyz`
- Agent Harness：`/healthz` 与 `/metrics`
- Speech Assessment：`/healthz`、`/metrics`、`/speech/transcribe-timestamps` 与 `/speech/assess`
- PostgreSQL、Redis、MinIO 必须在 `docker compose ps` 中显示 healthy。

## HTTPS

HTTPS 由平台负载均衡、反向代理或 ingress 终止。Staging 中的 `NEXT_PUBLIC_API_BASE_URL` 与 `S3_PUBLIC_ENDPOINT` 必须使用 HTTPS URL。

## 发布门禁

Staging 进入内测前必须满足：CI 通过、迁移干净执行、Phase 9/10/11 smoke checks 在 staging 环境通过，并确认 Speech Assessment response policy 中 `ielts_band_output_allowed=false`。
