# 备份与恢复策略

## 范围

- PostgreSQL：用户、会话、题库、报告、合规记录、迁移版本。
- MinIO/S3：用户录音、TTS 缓存音频、回放资源。
- Redis 当前只作为缓存和实时辅助组件，不作为长期恢复源。

## 备份频率

- Staging：每日一次 PostgreSQL dump，每日一次 MinIO bucket mirror。
- 生产建议：PostgreSQL 每日全量、每小时 WAL 或托管 PITR；对象存储启用版本化和生命周期策略。

## 本地脚本

```powershell
./scripts/backup_local.ps1
./scripts/restore_local.ps1 -BackupDir tmp/backups/<timestamp> -Confirmation RESTORE_STAGING_DATA
```

备份脚本会在备份目录写入 `manifest.json`，记录生成时间、备份版本、PostgreSQL dump 和 MinIO archive 的文件大小与 SHA-256 校验和。恢复脚本必须显式传入确认短语，且默认会在执行恢复前校验 manifest，避免误恢复到错误环境或使用损坏备份。仅恢复旧备份时允许显式传入 `-AllowMissingManifest`，并且必须先人工完成校验。

发布前可先生成备份完整性证据，确认 manifest 指向的 dump/archive 文件仍存在且大小、SHA-256 一致：

```powershell
pnpm backup:verify -- -Manifest tmp/backups/<timestamp>/manifest.json -OutputFile tmp/backup-integrity.json
```

## 恢复演练

1. 在非生产环境执行备份。
2. 新建空环境或清空 staging 测试环境。
3. 执行恢复脚本。
4. 运行 `docker compose ps` 确认服务健康。
5. 验证 `/healthz`、登录、报告读取、录音 signed URL。
6. 记录恢复耗时、失败点和修复动作。

## 风险控制

- 备份文件不得提交到代码库。
- 含真实用户数据的备份必须加密存储。
- 恢复前必须确认目标环境、数据库名称和 bucket 名称。
- 恢复前必须确认 `manifest.json` 校验通过；旧备份缺少 manifest 时需要发布负责人书面确认后才可使用 `-AllowMissingManifest`。
- 破坏性迁移发布前必须先完成一次可恢复性检查。
