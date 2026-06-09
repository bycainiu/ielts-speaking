package db

import (
	"database/sql"
	"errors"
	"fmt"

	"github.com/ielts-speaking/platform/services/api-go/internal/db/migrations"
	"github.com/pressly/goose/v3"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const migrationDir = "."

var supportedMigrationCommands = map[string]struct{}{
	"up":      {},
	"down":    {},
	"redo":    {},
	"status":  {},
	"version": {},
}

func ValidateMigrationCommand(command string) error {
	if command == "" {
		return errors.New("迁移命令不能为空")
	}

	if _, ok := supportedMigrationCommands[command]; !ok {
		return fmt.Errorf("不支持的迁移命令 %q，可用命令：up、down、redo、status、version", command)
	}

	return nil
}

func RunMigrations(databaseURL string, command string) error {
	if err := ValidateMigrationCommand(command); err != nil {
		return err
	}

	if databaseURL == "" {
		return errors.New("DATABASE_URL 不能为空")
	}

	conn, err := sql.Open("pgx", databaseURL)
	if err != nil {
		return fmt.Errorf("open database: %w", err)
	}
	defer conn.Close()

	if err := conn.Ping(); err != nil {
		return fmt.Errorf("ping database: %w", err)
	}

	goose.SetBaseFS(migrations.FS)
	if err := goose.SetDialect("postgres"); err != nil {
		return fmt.Errorf("set goose dialect: %w", err)
	}

	switch command {
	case "up":
		return goose.Up(conn, migrationDir)
	case "down":
		return goose.Down(conn, migrationDir)
	case "redo":
		return goose.Redo(conn, migrationDir)
	case "status":
		return goose.Status(conn, migrationDir)
	case "version":
		return goose.Version(conn, migrationDir)
	default:
		return ValidateMigrationCommand(command)
	}
}
