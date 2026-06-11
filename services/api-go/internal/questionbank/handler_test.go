package questionbank

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
)

type fakeStore struct {
	seasons      []Season
	topics       []Topic
	question     Question
	auditRecords []AdminAuditInput
}

func newFakeStore() *fakeStore {
	now := time.Now().UTC()
	season := Season{ID: "season_001", Code: "2026-Q2", Title: "2026 Q2", Status: StatusActive, IsActive: true, CreatedAt: now, UpdatedAt: now}
	topic := Topic{ID: "topic_001", Name: "Hometown", Slug: "hometown", Status: StatusActive, CreatedAt: now, UpdatedAt: now}
	question := Question{
		ID:           "question_001",
		Part:         1,
		Text:         "Where is your hometown?",
		SourceType:   SourceOriginal,
		ReviewStatus: StatusActive,
		Metadata:     json.RawMessage(`{}`),
		Followups:    []FollowupTemplate{},
		CreatedAt:    now,
		UpdatedAt:    now,
	}
	return &fakeStore{seasons: []Season{season}, topics: []Topic{topic}, question: question}
}

func (s *fakeStore) CreateSeason(_ context.Context, input SeasonInput) (Season, error) {
	season := s.seasons[0]
	season.Code = input.Code
	season.Title = input.Title
	season.Status = input.Status
	if season.Status == "" {
		season.Status = StatusDraft
	}
	return season, nil
}

func (s *fakeStore) ListSeasons(context.Context, bool) ([]Season, error) { return s.seasons, nil }
func (s *fakeStore) GetActiveSeason(context.Context) (Season, error)     { return s.seasons[0], nil }
func (s *fakeStore) UpdateSeason(_ context.Context, _ string, input SeasonInput) (Season, error) {
	return s.CreateSeason(context.Background(), input)
}
func (s *fakeStore) ActivateSeason(context.Context, string) (Season, error) { return s.seasons[0], nil }
func (s *fakeStore) ArchiveSeason(context.Context, string) error            { return nil }

func (s *fakeStore) CreateTopic(_ context.Context, input TopicInput) (Topic, error) {
	topic := s.topics[0]
	topic.Name = input.Name
	topic.Slug = input.Slug
	topic.Status = input.Status
	return topic, nil
}

func (s *fakeStore) ListTopics(context.Context, bool) ([]Topic, error) { return s.topics, nil }
func (s *fakeStore) UpdateTopic(_ context.Context, _ string, input TopicInput) (Topic, error) {
	return s.CreateTopic(context.Background(), input)
}
func (s *fakeStore) ArchiveTopic(context.Context, string) error { return nil }

func (s *fakeStore) CreateQuestion(_ context.Context, input QuestionInput, createdBy string) (Question, error) {
	if err := validateQuestionInput(normalizeQuestionInput(input)); err != nil {
		return Question{}, err
	}
	question := s.question
	question.Part = input.Part
	question.Text = input.Text
	question.CreatedBy = &createdBy
	if input.CueCard != nil {
		question.CueCard = &CueCard{ID: "cue_001", QuestionID: question.ID, Prompt: input.CueCard.Prompt, BulletPoints: input.CueCard.BulletPoints}
	}
	return question, nil
}

func (s *fakeStore) ListQuestions(context.Context, QuestionFilter) ([]Question, error) {
	return []Question{s.question}, nil
}

func (s *fakeStore) GetQuestion(context.Context, string) (Question, error) { return s.question, nil }
func (s *fakeStore) UpdateQuestion(_ context.Context, _ string, input QuestionInput, createdBy string) (Question, error) {
	return s.CreateQuestion(context.Background(), input, createdBy)
}
func (s *fakeStore) ArchiveQuestion(context.Context, string) error { return nil }

func (s *fakeStore) RecordAdminAudit(_ context.Context, input AdminAuditInput) error {
	s.auditRecords = append(s.auditRecords, input)
	return nil
}

func TestPublicRoutesListActiveContent(t *testing.T) {
	router, _ := testRouter(t, "operator")

	response := performJSON(router, http.MethodGet, "/api/topics", nil, "")
	if response.Code != http.StatusOK {
		t.Fatalf("topics status = %d, body = %s", response.Code, response.Body.String())
	}

	response = performJSON(router, http.MethodGet, "/api/questions", nil, "")
	if response.Code != http.StatusOK {
		t.Fatalf("questions status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestAdminRoutesRequireOperatorOrAdmin(t *testing.T) {
	router, token, store := testRouterWithStore(t, "user")
	response := performJSON(router, http.MethodPost, "/api/admin/question-bank/topics", map[string]string{
		"name":   "Hometown",
		"slug":   "hometown",
		"status": StatusActive,
	}, token)

	if response.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusForbidden, response.Body.String())
	}
	if len(store.auditRecords) != 1 || store.auditRecords[0].StatusCode != http.StatusForbidden {
		t.Fatalf("audit records = %+v", store.auditRecords)
	}
}

func TestAdminCanCreatePart2QuestionWithCueCard(t *testing.T) {
	router, token, store := testRouterWithStore(t, "operator")
	response := performJSON(router, http.MethodPost, "/api/admin/question-bank/questions", map[string]any{
		"part":   2,
		"text":   "Describe a place in your city that you enjoy visiting.",
		"status": StatusDraft,
		"cue_card": map[string]any{
			"prompt":        "Describe a place in your city that you enjoy visiting.",
			"bullet_points": []string{"where it is", "what you do there"},
		},
	}, token)

	if response.Code != http.StatusCreated {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusCreated, response.Body.String())
	}
	if len(store.auditRecords) != 1 {
		t.Fatalf("audit records = %d, want 1", len(store.auditRecords))
	}
	if store.auditRecords[0].ActorRole != "operator" || store.auditRecords[0].StatusCode != http.StatusCreated {
		t.Fatalf("audit record = %+v", store.auditRecords[0])
	}
}

func TestPart2QuestionRequiresCueCard(t *testing.T) {
	router, token := testRouter(t, "operator")
	response := performJSON(router, http.MethodPost, "/api/admin/question-bank/questions", map[string]any{
		"part": 2,
		"text": "Describe a place in your city that you enjoy visiting.",
	}, token)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusBadRequest, response.Body.String())
	}
}

func TestQuestionRejectsPlaceholderFollowupText(t *testing.T) {
	router, token := testRouter(t, "operator")
	response := performJSON(router, http.MethodPost, "/api/admin/question-bank/questions", map[string]any{
		"part": 2,
		"text": "Describe a place in your city that you enjoy visiting.",
		"cue_card": map[string]any{
			"prompt":        "Describe a place in your city that you enjoy visiting.",
			"bullet_points": []string{"where it is", "what you do there"},
		},
		"followup_templates": []map[string]any{
			{
				"part": 3,
				"text": "待补充",
			},
		},
	}, token)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusBadRequest, response.Body.String())
	}
}

func testRouter(t *testing.T, role string) (http.Handler, string) {
	router, token, _ := testRouterWithStore(t, role)
	return router, token
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
	handler := NewHandler(store, store)
	handler.RegisterRoutes(api, auth.NewAuthenticator(authStore{role: role}, tokens))
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
	request.Header.Set("Content-Type", "application/json")
	if authHeader != "" {
		request.Header.Set("Authorization", authHeader)
	}

	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	return response
}
