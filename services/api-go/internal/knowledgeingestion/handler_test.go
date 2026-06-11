package knowledgeingestion

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
)

type fakeStore struct {
	job    KnowledgeImportJobDetail
	policy RuntimePolicy
}

func newFakeStore() *fakeStore {
	now := time.Now().UTC()
	job := KnowledgeImportJobDetail{
		KnowledgeImportJobSummary: KnowledgeImportJobSummary{
			ID:                  "11111111-1111-1111-1111-111111111111",
			OwnerUserID:         "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
			RequestedVisibility: VisibilityPrivate,
			RequestedAction:     PurposeKnowledge,
			Status:              JobStatusCompleted,
			Stage:               "materialized",
			ProgressPct:         100,
			QueuedAt:            now,
			UpdatedAt:           now,
			SourceFile: KnowledgeSourceFile{
				ID:               "22222222-2222-2222-2222-222222222222",
				OwnerUserID:      "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
				Visibility:       VisibilityPrivate,
				UploadPurpose:    PurposeKnowledge,
				Title:            "Resume",
				OriginalFilename: "resume.docx",
				Extension:        ".docx",
				MimeType:         "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
				SizeBytes:        2048,
				ChecksumSHA256:   "sha256:test",
				StorageBucket:    "ielts-speaking-local",
				StorageKey:       "knowledge/test/resume.docx",
				Metadata:         map[string]any{"uploaded_via": "api_go"},
				CreatedAt:        now,
			},
			CandidateCounts: map[string]int{
				CandidateKindKnowledge:  1,
				CandidateKindBackground: 1,
			},
		},
		Candidates: []KnowledgeIngestionCandidate{
			{
				ID:                  "33333333-3333-3333-3333-333333333333",
				JobID:               "11111111-1111-1111-1111-111111111111",
				CandidateKind:       CandidateKindKnowledge,
				Title:               "Resume knowledge",
				Content:             "Candidate content",
				CandidateStatus:     CandidateStatusApproved,
				NormalizedPayload:   map[string]any{"title": "Resume knowledge"},
				MaterializationPlan: map[string]any{"tables": []string{"knowledge_docs", "knowledge_chunks"}},
				Metadata:            map[string]any{},
				CreatedAt:           now,
				UpdatedAt:           now,
			},
		},
		Artifacts: []KnowledgeIngestionArtifact{
			{
				ID:            "44444444-4444-4444-4444-444444444444",
				JobID:         "11111111-1111-1111-1111-111111111111",
				ArtifactKind:  ArtifactKindOriginal,
				Title:         "resume.docx",
				ContentType:   "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
				StorageBucket: stringPtr("ielts-speaking-local"),
				StorageKey:    stringPtr("knowledge/test/resume.docx"),
				Metadata:      map[string]any{},
				CreatedAt:     now,
			},
		},
	}
	return &fakeStore{
		job: job,
		policy: RuntimePolicy{
			PolicyKey:      "document_ingestion",
			MaxConcurrency: 2,
			Paused:         false,
			Raw:            map[string]any{"max_concurrency": 2, "paused": false},
			UpdatedAt:      now,
		},
	}
}

func (s *fakeStore) CreateUpload(context.Context, CreateUploadRecordInput) (KnowledgeImportJobDetail, error) {
	return s.job, nil
}

func (s *fakeStore) ListUserJobs(context.Context, string, UserJobFilter) ([]KnowledgeImportJobSummary, error) {
	return []KnowledgeImportJobSummary{s.job.KnowledgeImportJobSummary}, nil
}

func (s *fakeStore) ListAdminJobs(context.Context, AdminJobFilter) ([]KnowledgeImportJobSummary, error) {
	return []KnowledgeImportJobSummary{s.job.KnowledgeImportJobSummary}, nil
}

func (s *fakeStore) GetJobDetail(context.Context, string) (KnowledgeImportJobDetail, error) {
	return s.job, nil
}

func (s *fakeStore) ConfirmBackgroundCandidates(context.Context, string, string, ConfirmBackgroundInput) (KnowledgeImportJobDetail, error) {
	job := s.job
	job.Status = JobStatusCompleted
	return job, nil
}

func (s *fakeStore) ReviewJob(context.Context, string, string, string, AdminReviewInput) (KnowledgeImportJobDetail, error) {
	return s.job, nil
}

func (s *fakeStore) CancelJob(context.Context, string, string, string) (KnowledgeImportJobDetail, error) {
	job := s.job
	job.Status = JobStatusCancelled
	return job, nil
}

func (s *fakeStore) RetryJob(context.Context, string, string, string) (KnowledgeImportJobDetail, error) {
	job := s.job
	job.Status = JobStatusQueued
	return job, nil
}

func (s *fakeStore) GetRuntimePolicy(context.Context) (RuntimePolicy, error) {
	return s.policy, nil
}

func (s *fakeStore) UpdateRuntimePolicy(context.Context, string, RuntimePolicyUpdateInput) (RuntimePolicy, error) {
	return s.policy, nil
}

func (s *fakeStore) GetArtifact(context.Context, string) (KnowledgeIngestionArtifact, error) {
	return s.job.Artifacts[0], nil
}

type fakeObjectStore struct{}

func (fakeObjectStore) EnsureBucket(context.Context, string) error { return nil }
func (fakeObjectStore) PutObject(context.Context, string, string, io.Reader, int64, string) error {
	return nil
}
func (fakeObjectStore) PresignedGetObject(context.Context, string, string, time.Duration, string) (string, error) {
	return "http://localhost:9000/signed-url", nil
}

func TestUserRoutesWorkForKnowledgeIngestion(t *testing.T) {
	router, token := testRouter(t, "user")

	response := performJSON(router, http.MethodGet, "/api/knowledge/uploads", nil, token)
	if response.Code != http.StatusOK {
		t.Fatalf("list jobs status = %d, body = %s", response.Code, response.Body.String())
	}
	if !bytes.Contains(response.Body.Bytes(), []byte(`"jobs"`)) {
		t.Fatalf("list jobs body = %s", response.Body.String())
	}

	response = performJSON(router, http.MethodGet, "/api/knowledge/uploads/11111111-1111-1111-1111-111111111111", nil, token)
	if response.Code != http.StatusOK {
		t.Fatalf("job detail status = %d, body = %s", response.Code, response.Body.String())
	}

	response = performJSON(router, http.MethodPost, "/api/knowledge/uploads/11111111-1111-1111-1111-111111111111/confirm-background", map[string]any{
		"candidate_ids": []string{"33333333-3333-3333-3333-333333333333"},
	}, token)
	if response.Code != http.StatusOK {
		t.Fatalf("confirm background status = %d, body = %s", response.Code, response.Body.String())
	}

	response = performJSON(router, http.MethodPost, "/api/knowledge/uploads/11111111-1111-1111-1111-111111111111/cancel", nil, token)
	if response.Code != http.StatusOK {
		t.Fatalf("user cancel status = %d, body = %s", response.Code, response.Body.String())
	}

	response = performJSON(router, http.MethodPost, "/api/knowledge/uploads/11111111-1111-1111-1111-111111111111/retry", nil, token)
	if response.Code != http.StatusOK {
		t.Fatalf("user retry status = %d, body = %s", response.Code, response.Body.String())
	}

	response = performJSON(router, http.MethodGet, "/api/knowledge/uploads/11111111-1111-1111-1111-111111111111/artifacts/44444444-4444-4444-4444-444444444444/preview", nil, token)
	if response.Code != http.StatusOK {
		t.Fatalf("preview status = %d, body = %s", response.Code, response.Body.String())
	}
	if !bytes.Contains(response.Body.Bytes(), []byte(`"signed_url"`)) {
		t.Fatalf("preview body = %s", response.Body.String())
	}
}

func TestUploadAcceptsMultipartDocument(t *testing.T) {
	router, token := testRouter(t, "user")

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	_ = writer.WriteField("visibility", VisibilityPrivate)
	_ = writer.WriteField("purpose", PurposeKnowledge)
	_ = writer.WriteField("title", "Resume")
	fileWriter, err := writer.CreateFormFile("file", "resume.docx")
	if err != nil {
		t.Fatalf("CreateFormFile() error = %v", err)
	}
	_, _ = fileWriter.Write([]byte("fake-docx-content"))
	_ = writer.Close()

	request := httptest.NewRequest(http.MethodPost, "/api/knowledge/uploads", body)
	request.Header.Set("Content-Type", writer.FormDataContentType())
	request.Header.Set("Authorization", token)
	response := httptest.NewRecorder()

	router.ServeHTTP(response, request)
	if response.Code != http.StatusCreated {
		t.Fatalf("upload status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestAdminRoutesRequireOperatorOrAdmin(t *testing.T) {
	router, token := testRouter(t, "operator")

	response := performJSON(router, http.MethodGet, "/api/admin/knowledge/imports", nil, token)
	if response.Code != http.StatusOK {
		t.Fatalf("admin list status = %d, body = %s", response.Code, response.Body.String())
	}

	response = performJSON(router, http.MethodPut, "/api/admin/agent-runtime/document-ingestion", map[string]any{
		"max_concurrency": 2,
		"paused":          false,
	}, token)
	if response.Code != http.StatusOK {
		t.Fatalf("policy update status = %d, body = %s", response.Code, response.Body.String())
	}

	response = performJSON(router, http.MethodPost, "/api/admin/knowledge/imports/11111111-1111-1111-1111-111111111111/review", map[string]any{
		"decision": "approve",
	}, token)
	if response.Code != http.StatusOK {
		t.Fatalf("review status = %d, body = %s", response.Code, response.Body.String())
	}
}

func testRouter(t *testing.T, role string) (http.Handler, string) {
	t.Helper()
	gin.SetMode(gin.TestMode)
	router := gin.New()
	api := router.Group("/api")

	tokenService, err := auth.NewTokenService(auth.TokenServiceConfig{
		Secret: "test-secret-must-be-at-least-32-bytes",
	})
	if err != nil {
		t.Fatalf("NewTokenService() error = %v", err)
	}
	user := auth.User{
		ID:        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		Email:     "tester@example.com",
		Role:      role,
		Status:    "active",
		CreatedAt: time.Now().UTC(),
	}
	pair, err := tokenService.GeneratePair(user)
	if err != nil {
		t.Fatalf("GeneratePair() error = %v", err)
	}
	authStore := newAuthStoreForTests(user)
	authenticator := auth.NewAuthenticator(authStore, tokenService)
	knowledgeStore := newFakeStore()
	service := NewService(knowledgeStore, fakeObjectStore{}, "ielts-speaking-local", defaultMaxUploadBytes)
	NewHandler(service, defaultMaxUploadBytes).RegisterRoutes(api, authenticator)
	return router, "Bearer " + pair.AccessToken
}

func performJSON(router http.Handler, method string, path string, body any, authHeader string) *httptest.ResponseRecorder {
	var payload bytes.Buffer
	if body != nil {
		encoder := json.NewEncoder(&payload)
		_ = encoder.Encode(body)
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

type authStoreForTests struct {
	user auth.User
}

func newAuthStoreForTests(user auth.User) authStoreForTests {
	return authStoreForTests{user: user}
}

func (s authStoreForTests) CreateUser(context.Context, auth.CreateUserParams) (auth.User, error) {
	return s.user, nil
}

func (s authStoreForTests) GetUserByEmail(context.Context, string) (auth.UserWithPassword, error) {
	return auth.UserWithPassword{User: s.user, PasswordHash: "hashed"}, nil
}

func (s authStoreForTests) GetUserByID(context.Context, string) (auth.User, error) {
	return s.user, nil
}

func (s authStoreForTests) UpdateLastLogin(context.Context, string) error {
	return nil
}
