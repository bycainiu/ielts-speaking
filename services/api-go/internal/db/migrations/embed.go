package migrations

import "embed"

// FS 嵌入所有数据库迁移文件，保证 Docker 镜像和本地二进制使用同一套迁移。
//
//go:embed *.sql
var FS embed.FS
