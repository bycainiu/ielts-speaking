package config

import (
	"errors"
	"os"
	"strconv"
)

type Config struct {
	AppEnv                   string
	LogLevel                 string
	HTTPPort                 string
	DatabaseURL              string
	RedisURL                 string
	JWTSecret                string
	TraceUserHashSalt        string
	AgentHarnessURL          string
	S3Endpoint               string
	S3PublicEndpoint         string
	S3Region                 string
	S3Bucket                 string
	S3AccessKey              string
	S3SecretKey              string
	S3UseSSL                 bool
	AudioMaxBytes            int64
	AudioMaxDurationMS       int
	KnowledgeMaxUploadBytes  int64
	CaptchaTTLSeconds        int
	EmailCodeTTLSeconds      int
	EmailCodeCooldownSeconds int
	EmailCodeMaxAttempts     int
	EmailCodeDebug           bool
	SMTPHost                 string
	SMTPPort                 int
	SMTPUsername             string
	SMTPPassword             string
	SMTPFrom                 string
	SMTPUseTLS               bool
}

func Load() (Config, error) {
	appEnv := getEnv("APP_ENV", "local")
	cfg := Config{
		AppEnv:                   appEnv,
		LogLevel:                 getEnv("LOG_LEVEL", "info"),
		HTTPPort:                 getEnv("API_HTTP_PORT", "8080"),
		DatabaseURL:              getEnv("DATABASE_URL", "postgres://ielts:ielts@localhost:5432/ielts_speaking?sslmode=disable"),
		RedisURL:                 getEnv("REDIS_URL", "redis://localhost:6379/0"),
		JWTSecret:                getEnv("JWT_SECRET", "local-dev-change-me-minimum-32-chars"),
		TraceUserHashSalt:        getEnv("TRACE_USER_HASH_SALT", "local-trace-salt-change-me"),
		AgentHarnessURL:          getEnv("AGENT_HARNESS_URL", "http://localhost:8000"),
		S3Endpoint:               getEnv("S3_ENDPOINT", "http://localhost:9000"),
		S3PublicEndpoint:         getEnv("S3_PUBLIC_ENDPOINT", ""),
		S3Region:                 getEnv("S3_REGION", "local"),
		S3Bucket:                 getEnv("MINIO_BUCKET", "ielts-speaking-local"),
		S3AccessKey:              getEnv("S3_ACCESS_KEY", getEnv("MINIO_ROOT_USER", "minioadmin")),
		S3SecretKey:              getEnv("S3_SECRET_KEY", getEnv("MINIO_ROOT_PASSWORD", "minioadmin")),
		S3UseSSL:                 getBoolEnv("S3_USE_SSL", false),
		AudioMaxBytes:            getInt64Env("AUDIO_MAX_UPLOAD_BYTES", 25*1024*1024),
		AudioMaxDurationMS:       getIntEnv("AUDIO_MAX_DURATION_MS", 10*60*1000),
		KnowledgeMaxUploadBytes:  getInt64Env("KNOWLEDGE_MAX_UPLOAD_BYTES", 20*1024*1024),
		CaptchaTTLSeconds:        getIntEnv("AUTH_CAPTCHA_TTL_SECONDS", 180),
		EmailCodeTTLSeconds:      getIntEnv("AUTH_EMAIL_CODE_TTL_SECONDS", 600),
		EmailCodeCooldownSeconds: getIntEnv("AUTH_EMAIL_CODE_COOLDOWN_SECONDS", 60),
		EmailCodeMaxAttempts:     getIntEnv("AUTH_EMAIL_CODE_MAX_ATTEMPTS", 5),
		EmailCodeDebug:           getBoolEnv("AUTH_EMAIL_CODE_DEBUG", appEnv != "prod"),
		SMTPHost:                 getEnv("SMTP_HOST", ""),
		SMTPPort:                 getIntEnv("SMTP_PORT", 587),
		SMTPUsername:             getEnv("SMTP_USERNAME", ""),
		SMTPPassword:             getEnv("SMTP_PASSWORD", ""),
		SMTPFrom:                 getEnv("SMTP_FROM", "IELTS Speaking <no-reply@localhost>"),
		SMTPUseTLS:               getBoolEnv("SMTP_USE_TLS", false),
	}

	if cfg.AppEnv == "prod" && len(cfg.JWTSecret) < 32 {
		return Config{}, errors.New("生产环境 JWT_SECRET 长度不能少于 32 个字符")
	}

	if cfg.HTTPPort == "" {
		return Config{}, errors.New("API_HTTP_PORT 不能为空")
	}
	if cfg.AudioMaxBytes <= 0 {
		return Config{}, errors.New("AUDIO_MAX_UPLOAD_BYTES 必须大于 0")
	}
	if cfg.AudioMaxDurationMS <= 0 {
		return Config{}, errors.New("AUDIO_MAX_DURATION_MS 必须大于 0")
	}
	if cfg.KnowledgeMaxUploadBytes <= 0 {
		return Config{}, errors.New("KNOWLEDGE_MAX_UPLOAD_BYTES 必须大于 0")
	}
	if cfg.CaptchaTTLSeconds <= 0 {
		return Config{}, errors.New("AUTH_CAPTCHA_TTL_SECONDS 必须大于 0")
	}
	if cfg.EmailCodeTTLSeconds <= 0 {
		return Config{}, errors.New("AUTH_EMAIL_CODE_TTL_SECONDS 必须大于 0")
	}
	if cfg.EmailCodeCooldownSeconds <= 0 {
		return Config{}, errors.New("AUTH_EMAIL_CODE_COOLDOWN_SECONDS 必须大于 0")
	}
	if cfg.EmailCodeMaxAttempts <= 0 {
		return Config{}, errors.New("AUTH_EMAIL_CODE_MAX_ATTEMPTS 必须大于 0")
	}
	if cfg.SMTPPort <= 0 {
		return Config{}, errors.New("SMTP_PORT 必须大于 0")
	}

	return cfg, nil
}

func getEnv(key string, fallback string) string {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	return value
}

func getBoolEnv(key string, fallback bool) bool {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func getInt64Env(key string, fallback int64) int64 {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseInt(value, 10, 64)
	if err != nil {
		return fallback
	}
	return parsed
}

func getIntEnv(key string, fallback int) int {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}
