package server

import (
	"context"
	"database/sql"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/ielts-speaking/platform/services/api-go/internal/adminops"
	"github.com/ielts-speaking/platform/services/api-go/internal/audio"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
	"github.com/ielts-speaking/platform/services/api-go/internal/billing"
	"github.com/ielts-speaking/platform/services/api-go/internal/compliance"
	"github.com/ielts-speaking/platform/services/api-go/internal/config"
	"github.com/ielts-speaking/platform/services/api-go/internal/knowledgeingestion"
	"github.com/ielts-speaking/platform/services/api-go/internal/objectstore"
	"github.com/ielts-speaking/platform/services/api-go/internal/profile"
	"github.com/ielts-speaking/platform/services/api-go/internal/questionbank"
	"github.com/ielts-speaking/platform/services/api-go/internal/realtime"
	"github.com/ielts-speaking/platform/services/api-go/internal/report"
	"github.com/ielts-speaking/platform/services/api-go/internal/session"
)

func NewRouter(cfg config.Config) http.Handler {
	return NewRouterWithDB(cfg, nil)
}

func NewRouterWithDB(cfg config.Config, database *sql.DB) http.Handler {
	if cfg.AppEnv == "prod" {
		gin.SetMode(gin.ReleaseMode)
	}

	router := gin.New()
	router.Use(gin.Recovery())

	router.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status":  "ok",
			"service": "api-go",
			"env":     cfg.AppEnv,
		})
	})

	router.GET("/readyz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status":            "ready",
			"database_url_set":  cfg.DatabaseURL != "",
			"redis_url_set":     cfg.RedisURL != "",
			"agent_harness_url": cfg.AgentHarnessURL,
		})
	})

	api := router.Group("/api")
	api.GET("/version", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"name":    "ielts-speaking-api",
			"version": "0.1.0",
		})
	})

	if database != nil {
		tokenService, err := auth.NewTokenService(auth.TokenServiceConfig{
			Secret: cfg.JWTSecret,
		})
		if err != nil {
			panic(err)
		}

		store := auth.NewPostgresStore(database)
		authenticator := auth.NewAuthenticator(store, tokenService)
		authService := auth.NewService(store, auth.NewBcryptPasswordHasher(), tokenService)
		captchaStore := auth.NewCaptchaStore(auth.CaptchaConfig{
			TTL: time.Duration(cfg.CaptchaTTLSeconds) * time.Second,
		})
		emailVerification := auth.NewEmailVerificationService(
			auth.NewMemoryEmailVerificationStore(),
			auth.NewEmailSender(auth.SMTPEmailSenderConfig{
				Host:     cfg.SMTPHost,
				Port:     cfg.SMTPPort,
				Username: cfg.SMTPUsername,
				Password: cfg.SMTPPassword,
				From:     cfg.SMTPFrom,
				UseTLS:   cfg.SMTPUseTLS,
			}),
			auth.EmailVerificationConfig{
				TTL:         time.Duration(cfg.EmailCodeTTLSeconds) * time.Second,
				Cooldown:    time.Duration(cfg.EmailCodeCooldownSeconds) * time.Second,
				MaxAttempts: cfg.EmailCodeMaxAttempts,
				DebugCode:   cfg.EmailCodeDebug,
			},
		)
		billingStore := billing.NewPostgresStore(database)
		billing.NewHandler(billingStore).RegisterRoutes(api, authenticator)

		auth.NewHandler(
			authService,
			authenticator,
			auth.WithCaptchaStore(captchaStore),
			auth.WithEmailVerification(emailVerification),
			auth.WithUserRegisteredHook(func(ctx context.Context, userID string) error {
				return billingStore.EnsureSignupSubscription(ctx, userID)
			}),
		).RegisterRoutes(api)

		profileStore := profile.NewPostgresStore(database)
		profile.NewHandler(profileStore).RegisterRoutes(api, authenticator)

		questionBankStore := questionbank.NewPostgresStore(database)
		questionbank.NewHandler(questionBankStore, questionBankStore).RegisterRoutes(api, authenticator)

		adminOpsStore := adminops.NewPostgresStore(database)
		adminops.NewHandler(adminOpsStore).RegisterRoutes(api, authenticator)

		complianceStore := compliance.NewPostgresStore(database)
		compliance.NewHandler(complianceStore).RegisterRoutes(api, authenticator)

		sessionStore := session.NewPostgresStore(database, cfg.TraceUserHashSalt)
		session.NewHandler(sessionStore, session.WithQuotaStore(billingStore)).RegisterRoutes(api, authenticator)

		reportStore := report.NewPostgresStore(database)
		report.NewHandler(reportStore).RegisterRoutes(api, authenticator)

		realtimeHub := realtime.NewHub()
		realtimeAccess := realtime.NewPostgresSessionAccessStore(database)
		realtime.NewHandler(realtimeHub, realtimeAccess, authenticator).RegisterRoutes(api)

		objectStore, err := objectstore.NewMinIOObjectStore(objectstore.MinIOConfig{
			Endpoint:       cfg.S3Endpoint,
			PublicEndpoint: cfg.S3PublicEndpoint,
			AccessKey:      cfg.S3AccessKey,
			SecretKey:      cfg.S3SecretKey,
			Region:         cfg.S3Region,
			UseSSL:         cfg.S3UseSSL,
		})
		if err != nil {
			panic(err)
		}
		audioStore := audio.NewPostgresStore(database)
		audioService := audio.NewService(audioStore, objectStore, audio.ServiceConfig{
			Bucket:        cfg.S3Bucket,
			MaxBytes:      cfg.AudioMaxBytes,
			MaxDurationMS: cfg.AudioMaxDurationMS,
			TTSProvider:   audio.NewAgentHarnessTTSClient(cfg.AgentHarnessURL),
		})
		audio.NewHandler(audioService, cfg.AudioMaxBytes).RegisterRoutes(api, authenticator)

		knowledgeStore := knowledgeingestion.NewPostgresStore(database)
		knowledgeService := knowledgeingestion.NewService(knowledgeStore, objectStore, cfg.S3Bucket, cfg.KnowledgeMaxUploadBytes)
		knowledgeingestion.NewHandler(knowledgeService, cfg.KnowledgeMaxUploadBytes).RegisterRoutes(api, authenticator)
	}

	return router
}
