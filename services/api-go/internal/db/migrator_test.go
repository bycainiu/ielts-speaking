package db

import "testing"

func TestValidateMigrationCommand(t *testing.T) {
	for _, command := range []string{"up", "down", "redo", "status", "version"} {
		if err := ValidateMigrationCommand(command); err != nil {
			t.Fatalf("ValidateMigrationCommand(%q) error = %v", command, err)
		}
	}
}

func TestValidateMigrationCommandRejectsUnknownCommand(t *testing.T) {
	if err := ValidateMigrationCommand("drop-all"); err == nil {
		t.Fatal("expected unsupported migration command error")
	}
}
