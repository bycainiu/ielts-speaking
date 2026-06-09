package config

import "testing"

func TestLoadUsesDefaults(t *testing.T) {
	t.Setenv("APP_ENV", "")
	t.Setenv("API_HTTP_PORT", "")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.HTTPPort != "8080" {
		t.Fatalf("HTTPPort = %q, want 8080", cfg.HTTPPort)
	}
	if cfg.AudioMaxDurationMS != 600000 {
		t.Fatalf("AudioMaxDurationMS = %d, want 600000", cfg.AudioMaxDurationMS)
	}
}

func TestLoadRejectsShortProductionJWTSecret(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	t.Setenv("JWT_SECRET", "short")

	_, err := Load()
	if err == nil {
		t.Fatal("Load() expected error for short production JWT secret")
	}
}

func TestLoadRejectsInvalidAudioDurationLimit(t *testing.T) {
	t.Setenv("AUDIO_MAX_DURATION_MS", "0")

	_, err := Load()
	if err == nil {
		t.Fatal("Load() expected error for invalid audio duration limit")
	}
}
