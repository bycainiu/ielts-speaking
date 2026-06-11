package adminops

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
)

type fakeStore struct {
	doc          KnowledgeDoc
	prompts      []PromptVersion
	references   []ReferenceAnswerReview
	auditLogs    []AdminAuditLog
	auditRecords []AdminAuditInput
	lastAuditLogFilter AdminAuditLogFilter
}

func newFakeStore() *fakeStore {
	now := time.Now().UTC()
	doc := KnowledgeDoc{
		ID:             "11111111-1111-1111-1111-111111111111",
		DocType:        "topic_knowledge",
		Title:          "City Life Vocabulary",
		ContentHash:    "sha256:test",
		Metadata:       map[string]any{"index_status": "indexed"},
		Status:         StatusDraft,
		ChunkCount:     1,
		TokenCount:     12,
		EmbeddingModel: stringPtr(embeddingModel),
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	prompts := []PromptVersion{
		{
			ID:          "22222222-2222-2222-2222-222222222222",
			AgentName:   "ExamWorkflow",
			Purpose:     "full_exam_flow",
			Version:     "mock.exam_workflow.v1",
			ContentHash: "sha256:redacted",
			Metadata:    map[string]any{"prompt_body_redacted": true, "summary": "Formal exam flow"},
			Active:      true,
			CreatedAt:   now,
		},
	}
	references := []ReferenceAnswerReview{
		{
			ID:           "33333333-3333-3333-3333-333333333333",
			ReportID:     "44444444-4444-4444-4444-444444444444",
			Skeleton:     map[string]any{},
			AnswerText:   "A concise sample answer.",
			ReviewStatus: StatusDraft,
			CreatedAt:    now,
		},
	}
	auditLogs := []AdminAuditLog{
		{
			ID:         "55555555-5555-5555-5555-555555555555",
			ActorRole:  "operator",
			Action:     "GET /api/admin/prompts/versions",
			Resource:   "prompt_versions",
			Method:     http.MethodGet,
			Path:       "/api/admin/prompts/versions",
			StatusCode: http.StatusOK,
			Metadata:   map[string]any{"route": "/api/admin/prompts/versions"},
			CreatedAt:  now,
		},
	}
	return &fakeStore{doc: doc, prompts: prompts, references: references, auditLogs: auditLogs}
}

func (s *fakeStore) RecordAdminAudit(_ context.Context, input AdminAuditInput) error {
	s.auditRecords = append(s.auditRecords, input)
	return nil
}

func (s *fakeStore) ListAdminAudits(_ context.Context, filter AdminAuditLogFilter) ([]AdminAuditLog, error) {
	s.lastAuditLogFilter = normalizeAdminAuditLogFilter(filter)
	return s.auditLogs, nil
}

func (s *fakeStore) CreateKnowledgeDoc(_ context.Context, input KnowledgeDocInput, actorUserID string) (KnowledgeDoc, error) {
	doc := s.doc
	doc.DocType = input.DocType
	doc.Title = input.Title
	doc.Status = input.Status
	doc.Metadata = map[string]any{"index_status": "indexed", "updated_by": actorUserID}
	doc.ChunkCount = len(splitText(input.Content, chunkMaxChars, chunkOverlapChars))
	s.doc = doc
	return doc, nil
}

func (s *fakeStore) ListKnowledgeDocs(context.Context, KnowledgeDocFilter) ([]KnowledgeDoc, error) {
	return []KnowledgeDoc{s.doc}, nil
}

func (s *fakeStore) UpdateKnowledgeDoc(_ context.Context, _ string, input KnowledgeDocUpdateInput, _ string) (KnowledgeDoc, error) {
	s.doc.Title = input.Title
	s.doc.Status = input.Status
	return s.doc, nil
}

func (s *fakeStore) ReindexKnowledgeDoc(context.Context, string, string) (KnowledgeDoc, error) {
	s.doc.Metadata["index_status"] = "indexed"
	return s.doc, nil
}

func (s *fakeStore) ArchiveKnowledgeDoc(context.Context, string) error {
	s.doc.Status = StatusArchived
	return nil
}

func (s *fakeStore) ListPromptVersions(context.Context, PromptVersionFilter) ([]PromptVersion, error) {
	return s.prompts, nil
}

func (s *fakeStore) ContentReviewSummary(context.Context) ([]ContentReviewSummaryItem, error) {
	return []ContentReviewSummaryItem{
		{ContentType: "question", Status: StatusDraft, Count: 2},
		{ContentType: "knowledge_doc", Status: StatusActive, Count: 1},
		{ContentType: "reference_answer", Status: StatusDraft, Count: 1},
	}, nil
}

func (s *fakeStore) ListReferenceAnswers(context.Context, ReferenceAnswerFilter) ([]ReferenceAnswerReview, error) {
	return s.references, nil
}

func (s *fakeStore) UpdateReferenceAnswerStatus(_ context.Context, _ string, status string) (ReferenceAnswerReview, error) {
	s.references[0].ReviewStatus = status
	return s.references[0], nil
}

func TestAdminOpsRoutesRequireOperatorOrAdminAndAuditForbidden(t *testing.T) {
	router, token, store := testRouterWithStore(t, "user")

	response := performJSON(router, http.MethodGet, "/api/admin/prompts/versions", nil, token)

	if response.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusForbidden, response.Body.String())
	}
	if len(store.auditRecords) != 1 {
		t.Fatalf("audit records = %d, want 1", len(store.auditRecords))
	}
	record := store.auditRecords[0]
	if record.Resource != "prompt_versions" || record.StatusCode != http.StatusForbidden || record.ActorRole != "user" {
		t.Fatalf("audit record = %+v", record)
	}
}

func TestAdminCanListAuditLogs(t *testing.T) {
	router, token, _ := testRouterWithStore(t, "admin")

	response := performJSON(router, http.MethodGet, "/api/admin/audit/logs?resource=prompt_versions&status_class=2", nil, token)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusOK, response.Body.String())
	}
	body := response.Body.String()
	if !strings.Contains(body, `"logs"`) || !strings.Contains(body, `"prompt_versions"`) {
		t.Fatalf("unexpected audit log body: %s", body)
	}
}

func TestAdminAuditLogFiltersAreParsed(t *testing.T) {
	router, token, store := testRouterWithStore(t, "admin")

	response := performJSON(
		router,
		http.MethodGet,
		"/api/admin/audit/logs?resource=prompt_versions&actor_role=operator&method=post&status_class=4&q=versions&limit=25&offset=10",
		nil,
		token,
	)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusOK, response.Body.String())
	}
	if store.lastAuditLogFilter.Resource != "prompt_versions" {
		t.Fatalf("resource filter = %q", store.lastAuditLogFilter.Resource)
	}
	if store.lastAuditLogFilter.ActorRole != "operator" {
		t.Fatalf("actor role filter = %q", store.lastAuditLogFilter.ActorRole)
	}
	if store.lastAuditLogFilter.Method != "POST" {
		t.Fatalf("method filter = %q", store.lastAuditLogFilter.Method)
	}
	if store.lastAuditLogFilter.StatusClass != 4 {
		t.Fatalf("status class filter = %d", store.lastAuditLogFilter.StatusClass)
	}
	if store.lastAuditLogFilter.Query != "versions" {
		t.Fatalf("query filter = %q", store.lastAuditLogFilter.Query)
	}
	if store.lastAuditLogFilter.Limit != 25 || store.lastAuditLogFilter.Offset != 10 {
		t.Fatalf("pagination = %+v", store.lastAuditLogFilter)
	}
}

func TestOperatorCanManageKnowledgeDoc(t *testing.T) {
	router, token, store := testRouterWithStore(t, "operator")
	response := performJSON(router, http.MethodPost, "/api/admin/knowledge/docs", map[string]any{
		"doc_type": "topic_knowledge",
		"title":    "City life vocabulary",
		"content":  "Public transport, community spaces, commute, neighbourhood and urban planning vocabulary.",
		"status":   StatusReviewing,
		"metadata": map[string]any{"knowledge_type": "vocabulary"},
	}, token)

	if response.Code != http.StatusCreated {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusCreated, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), `"chunk_count":1`) {
		t.Fatalf("response missing chunk_count: %s", response.Body.String())
	}

	response = performJSON(router, http.MethodPost, "/api/admin/knowledge/docs/11111111-1111-1111-1111-111111111111/reindex", nil, token)
	if response.Code != http.StatusOK {
		t.Fatalf("reindex status = %d, body = %s", response.Code, response.Body.String())
	}

	response = performJSON(router, http.MethodDelete, "/api/admin/knowledge/docs/11111111-1111-1111-1111-111111111111", nil, token)
	if response.Code != http.StatusNoContent {
		t.Fatalf("archive status = %d, body = %s", response.Code, response.Body.String())
	}
	if store.doc.Status != StatusArchived {
		t.Fatalf("doc status = %s, want archived", store.doc.Status)
	}
	if len(store.auditRecords) != 3 {
		t.Fatalf("audit records = %d, want 3", len(store.auditRecords))
	}
}

func TestPromptVersionsDoNotExposePromptBody(t *testing.T) {
	router, token, _ := testRouterWithStore(t, "admin")
	response := performJSON(router, http.MethodGet, "/api/admin/prompts/versions", nil, token)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusOK, response.Body.String())
	}
	body := response.Body.String()
	if !strings.Contains(body, `"prompt_body_redacted":true`) {
		t.Fatalf("expected redacted metadata, body = %s", body)
	}
	if strings.Contains(body, "system prompt") || strings.Contains(body, "hidden instruction") {
		t.Fatalf("prompt body leaked: %s", body)
	}
}

func TestContentReviewCanUpdateReferenceAnswerStatus(t *testing.T) {
	router, token, store := testRouterWithStore(t, "operator")

	response := performJSON(router, http.MethodPut, "/api/admin/content-review/reference-answers/33333333-3333-3333-3333-333333333333/status", map[string]string{
		"status": StatusActive,
	}, token)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusOK, response.Body.String())
	}
	if store.references[0].ReviewStatus != StatusActive {
		t.Fatalf("reference status = %s, want active", store.references[0].ReviewStatus)
	}
}

func testRouterWithStore(t *testing.T, role string) (http.Handler, string, *fakeStore) {
	t.Helper()
	gin.SetMode(gin.TestMode)

	tokens := testTokenService()
	pair, err := tokens.GeneratePair(auth.User{ID: "user_001", Email: "operator@example.com", Role: role, Status: "active", CreatedAt: time.Now().UTC()})
	if err != nil {
		t.Fatalf("GeneratePair() error = %v", err)
	}

	router := gin.New()
	api := router.Group("/api")
	store := newFakeStore()
	NewHandler(store).RegisterRoutes(api, auth.NewAuthenticator(authStore{role: role}, tokens))
	return router, "Bearer " + pair.AccessToken, store
}

func testTokenService() auth.TokenService {
	tokens, err := auth.NewTokenService(auth.TokenServiceConfig{Secret: "test-secret-must-be-at-least-32-bytes"})
	if err != nil {
		panic(err)
	}
	return tokens
}

type authStore struct {
	role string
}

func (s authStore) CreateUser(context.Context, auth.CreateUserParams) (auth.User, error) {
	return auth.User{}, nil
}

func (s authStore) GetUserByEmail(context.Context, string) (auth.UserWithPassword, error) {
	return auth.UserWithPassword{}, auth.ErrUserNotFound
}

func (s authStore) GetUserByID(context.Context, string) (auth.User, error) {
	return auth.User{ID: "user_001", Email: "operator@example.com", Role: s.role, Status: "active", CreatedAt: time.Now().UTC()}, nil
}

func (s authStore) UpdateLastLogin(context.Context, string) error {
	return nil
}

func performJSON(router http.Handler, method string, path string, body any, authHeader string) *httptest.ResponseRecorder {
	var payload bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&payload).Encode(body); err != nil {
			panic(err)
		}
	}
	request := httptest.NewRequest(method, path, &payload)
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if authHeader != "" {
		request.Header.Set("Authorization", authHeader)
	}
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	return response
}

func stringPtr(value string) *string {
	return &value
}
