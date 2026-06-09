# 生产发布 Checklist

## 功能验收

- 注册、登录、刷新 token、当前用户信息正常。
- 背景问卷可保存，隐私排除字段生效。
- 题库 active 内容可检索，draft/reviewing/archived 不进入公开练习。
- Live 练习可完成录音授权、考官提问、录音、上传、ASR、评分与报告展示。
- 报告页可展示四维分、证据、建议、参考答案、回放和用户反馈。
- 后台可管理题库、知识库、Prompt、内容审核、用户反馈导出和 voice clone policy。

## 安全与隐私

- `JWT_SECRET`、`MIMO_API_KEY`、`S3_SECRET_KEY`、`TRACE_USER_HASH_SALT` 已替换为环境密钥。
- 录音前 consent 已启用，未授权不能上传用户录音。
- 数据删除 API/UI 已验证，删除报告后不可访问。
- Trace 中敏感信息脱敏，用户 private/excluded facts 不进入 Agent prompt。
- Voice clone policy 默认 disabled，未授权 voiceclone voice_id 被阻断。
- Prompt injection / system prompt leak / tool override 红队用例通过。

## 数据库与迁移

- `docker compose run --rm api-go migrate status` 发布前后均已记录。
- `pnpm migration:audit` 已通过，migration audit JSON 已保存。
- `pnpm migration:status:evidence` 发布前后 evidence JSON 已保存，发布后 pending migration 为 0。
- 本次发布包含的 migration 已审查 `Up` 和 `Down`。
- 破坏性迁移有回滚或 forward-fix 方案。
- 发布前已完成备份，备份文件位置已记录。
- 备份 `manifest.json` 已保存，并确认 PostgreSQL dump / MinIO archive 的 SHA-256 校验通过。
- `pnpm backup:verify` 已生成 backup integrity evidence JSON，确认 manifest 指向的备份文件存在且校验一致。

## 监控与告警

- Go API `/healthz`、`/readyz` 正常。
- Agent Harness `/healthz`、`/metrics` 正常。
- 观测 summary、alerts、request_id/session_id 日志可查询。
- 错误率、p95 延迟、工具成功率告警阈值已配置。

## 回滚方案

- 回滚镜像 tag 和 compose/env 版本已记录。
- 若迁移不可安全 down，使用 forward-fix migration。
- 回滚后重新跑 smoke：登录、练习入口、报告读取、Agent health、API health。

## 发布记录

可用以下命令生成机器可读发布记录：

```powershell
pnpm release:record -- `
  -ReleaseOwner "<name>" `
  -VersionTag "<image-or-git-tag>" `
  -RollbackDecisionOwner "<name>" `
  -RollbackImageTag "<previous-image-tag>" `
  -ComposeEnvVersion "<compose-env-version>" `
  -MigrationAuditJson tmp/migration-audit.json `
  -MigrationStatusBeforeJson tmp/migration-status-before.json `
  -MigrationStatusAfterJson tmp/migration-status-after.json `
  -StagingReadinessJson tmp/staging-readiness-full.json `
  -BackupManifest tmp/backups/<timestamp>/manifest.json `
  -BackupIntegrityJson tmp/backup-integrity.json `
  -OutputFile tmp/release-record.json
```

本地或 CI 可先运行示例证据链门禁，验证 migration audit、staging readiness、backup manifest 和 release record 聚合逻辑没有退化：

```powershell
pnpm release:record:example
```

- 发布负责人：
- 版本 / 镜像 tag：
- 迁移版本：
- Migration audit JSON：
- Migration status before JSON：
- Migration status after JSON：
- 备份 manifest：
- Backup integrity JSON：
- Staging 验证时间：
- Staging readiness evidence JSON：
- 生产发布时间：
- 监控观察窗口：
- 回滚决策人：
