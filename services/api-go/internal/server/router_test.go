package server

import (
	"database/sql"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ielts-speaking/platform/services/api-go/internal/config"
	_ "github.com/jackc/pgx/v5/stdlib"
)

func TestHealthz(t *testing.T) {
	router := NewRouter(config.Config{AppEnv: "test", HTTPPort: "8080"})
	request := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	response := httptest.NewRecorder()

	router.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusOK)
	}
}

func TestRouterWithDBRegistersSessionReportRoutes(t *testing.T) {
	db, err := sql.Open("pgx", "postgres://ielts:ielts@127.0.0.1:5432/ielts_speaking?sslmode=disable")
	if err != nil {
		t.Fatalf("sql.Open() error = %v", err)
	}
	defer db.Close()

	router := NewRouterWithDB(config.Config{
		AppEnv:             "test",
		HTTPPort:           "8080",
		JWTSecret:          "test-secret-must-be-at-least-32-bytes",
		AgentHarnessURL:    "http://127.0.0.1:8000",
		S3Endpoint:         "http://127.0.0.1:9000",
		S3PublicEndpoint:   "http://127.0.0.1:9000",
		S3AccessKey:        "minioadmin",
		S3SecretKey:        "minioadmin",
		S3Region:           "local",
		S3Bucket:           "ielts-speaking-local",
		AudioMaxBytes:      25 * 1024 * 1024,
		AudioMaxDurationMS: 10 * 60 * 1000,
		KnowledgeMaxUploadBytes: 20 * 1024 * 1024,
	}, db)

	request := httptest.NewRequest(http.MethodGet, "/api/sessions/session_001/report", nil)
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)

	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusUnauthorized)
	}

	historyRequest := httptest.NewRequest(http.MethodGet, "/api/reports", nil)
	historyResponse := httptest.NewRecorder()
	router.ServeHTTP(historyResponse, historyRequest)

	if historyResponse.Code != http.StatusUnauthorized {
		t.Fatalf("history status = %d, want %d", historyResponse.Code, http.StatusUnauthorized)
	}

	adminKnowledgeRequest := httptest.NewRequest(http.MethodGet, "/api/admin/knowledge/docs", nil)
	adminKnowledgeResponse := httptest.NewRecorder()
	router.ServeHTTP(adminKnowledgeResponse, adminKnowledgeRequest)

	if adminKnowledgeResponse.Code != http.StatusUnauthorized {
		t.Fatalf("admin knowledge status = %d, want %d", adminKnowledgeResponse.Code, http.StatusUnauthorized)
	}

	adminPromptRequest := httptest.NewRequest(http.MethodGet, "/api/admin/prompts/versions", nil)
	adminPromptResponse := httptest.NewRecorder()
	router.ServeHTTP(adminPromptResponse, adminPromptRequest)

	if adminPromptResponse.Code != http.StatusUnauthorized {
		t.Fatalf("admin prompt status = %d, want %d", adminPromptResponse.Code, http.StatusUnauthorized)
	}

	billingPlansRequest := httptest.NewRequest(http.MethodGet, "/api/billing/plans", nil)
	billingPlansResponse := httptest.NewRecorder()
	router.ServeHTTP(billingPlansResponse, billingPlansRequest)
	if billingPlansResponse.Code != http.StatusOK && billingPlansResponse.Code != http.StatusInternalServerError {
		t.Fatalf("billing plans status = %d", billingPlansResponse.Code)
	}

	knowledgeUploadRequest := httptest.NewRequest(http.MethodGet, "/api/knowledge/uploads", nil)
	knowledgeUploadResponse := httptest.NewRecorder()
	router.ServeHTTP(knowledgeUploadResponse, knowledgeUploadRequest)

	if knowledgeUploadResponse.Code != http.StatusUnauthorized {
		t.Fatalf("knowledge upload status = %d, want %d", knowledgeUploadResponse.Code, http.StatusUnauthorized)
	}

	protectedRoutes := []struct {
		name   string
		method string
		path   string
	}{
		{name: "me", method: http.MethodGet, path: "/api/me"},
		{name: "sessions", method: http.MethodPost, path: "/api/sessions"},
		{name: "billing subscription", method: http.MethodGet, path: "/api/billing/subscription"},
		{name: "audio upload", method: http.MethodPost, path: "/api/audio/upload"},
		{name: "admin users", method: http.MethodGet, path: "/api/admin/users"},
		{name: "admin audit", method: http.MethodGet, path: "/api/admin/audit/logs"},
		{name: "privacy consents", method: http.MethodGet, path: "/api/privacy/consents"},
		{name: "profile background", method: http.MethodGet, path: "/api/me/background"},
	}

	for _, route := range protectedRoutes {
		request := httptest.NewRequest(route.method, route.path, nil)
		response := httptest.NewRecorder()
		router.ServeHTTP(response, request)

		if response.Code != http.StatusUnauthorized {
			t.Fatalf("%s status = %d, want %d", route.name, response.Code, http.StatusUnauthorized)
		}
	}

	publicRoutes := []struct {
		name   string
		method string
		path   string
	}{
		{name: "active season", method: http.MethodGet, path: "/api/seasons/active"},
		{name: "public topics", method: http.MethodGet, path: "/api/topics"},
		{name: "public questions", method: http.MethodGet, path: "/api/questions"},
	}

	for _, route := range publicRoutes {
		request := httptest.NewRequest(route.method, route.path, nil)
		response := httptest.NewRecorder()
		router.ServeHTTP(response, request)

		if response.Code == http.StatusUnauthorized {
			t.Fatalf("%s should be public but returned 401", route.name)
		}
	}
}
