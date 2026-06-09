# 数据库迁移流程

Go API 使用 Goose 管理 SQL 迁移，并通过 `go:embed` 将迁移文件打进二进制。本地、Docker Compose、CI、staging 使用同一套 migration。

## 常用命令

```powershell
cd services/api-go
go run ./cmd/api migrate status
go run ./cmd/api migrate up
go run ./cmd/api migrate down
```

静态审计：

```powershell
pnpm migration:audit
powershell -ExecutionPolicy Bypass -File scripts/audit_migrations.ps1 -OutputFile tmp/migration-audit.json
```

发布前后状态证据：

```powershell
pnpm migration:status:evidence -- -Phase pre -Mode DockerCompose -OutputFile tmp/migration-status-before.json
docker compose run --rm api-go migrate up
pnpm migration:status:evidence -- -Phase post -Mode DockerCompose -OutputFile tmp/migration-status-after.json
```

Docker：

```powershell
docker compose run --rm api-go migrate status
docker compose run --rm api-go migrate up
```

## 规则

- 迁移文件存放在 `services/api-go/internal/db/migrations`。
- 文件名必须单调递增，例如 `000001_name.sql`、`000002_name.sql`。
- 每个迁移必须包含 `-- +goose Up` 与 `-- +goose Down`。
- 破坏性迁移必须在 PR 中写明影响范围，并在发布 checklist 中写明回滚或 forward-fix 方案。
- 数据回填必须可重复执行，或使用明确条件避免重复写入。
- 发布前必须保存 migration audit JSON，确认文件名、版本连续性和 Goose Up/Down 均通过；`review_items` 中的破坏性 Up SQL 必须由发布负责人确认。
- 发布前后必须保存 migration status evidence JSON；发布后证据必须无 pending migration，且 latest applied version 不低于 migration audit 的 latest version。
- CI 必须运行 Go migration 测试；staging 必须在 `migrate up` 前后记录 `migrate status`。

## 回滚

`migrate down` 只用于最近一次迁移，并且必须由发布负责人确认不会破坏已产生数据。涉及数据破坏时，优先使用 forward-fix migration。
