package migrations

import (
	"io/fs"
	"testing"
)

func TestEmbeddedMigrations(t *testing.T) {
	files, err := fs.Glob(FS, "*.sql")
	if err != nil {
		t.Fatalf("glob migrations: %v", err)
	}

	if len(files) == 0 {
		t.Fatal("expected at least one embedded migration")
	}

	if files[0] != "000001_core_schema.sql" {
		t.Fatalf("first migration = %q, want 000001_core_schema.sql", files[0])
	}
}
