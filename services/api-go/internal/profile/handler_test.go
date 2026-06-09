package profile

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

func TestHandlerSaveBackgroundFiltersAgentFacts(t *testing.T) {
	router, token, store := testRouter(t)

	response := performJSON(router, http.MethodPut, "/api/me/background", map[string]any{
		"profile": map[string]any{
			"display_name":        "Learner",
			"timezone":            "Asia/Shanghai",
			"target_band":         7,
			"current_band":        6,
			"preferred_exam_date": "2026-08-01",
		},
		"answers": map[string]any{
			"hometown":  "Hangzhou",
			"free_note": "I prefer technology and education topics.",
		},
		"privacy_exclusions": []string{"workplace"},
		"facts": []map[string]any{
			{"topic": "personal", "fact_key": "hometown", "fact_value": "Hangzhou"},
			{"topic": "work", "fact_key": "workplace", "fact_value": "A private company"},
		},
		"submitted": true,
	}, token)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if store.saved.Profile == nil || *store.saved.Profile.DisplayName != "Learner" {
		t.Fatalf("profile input was not saved: %#v", store.saved.Profile)
	}

	var body struct {
		Background Background `json:"background"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}
	if len(body.Background.Facts) != 2 {
		t.Fatalf("facts length = %d, want 2", len(body.Background.Facts))
	}
	if len(body.Background.AgentFacts) != 1 {
		t.Fatalf("agent_facts length = %d, want 1", len(body.Background.AgentFacts))
	}
	if body.Background.AgentFacts[0].FactKey != "hometown" {
		t.Fatalf("agent fact = %q, want hometown", body.Background.AgentFacts[0].FactKey)
	}
}

func TestHandlerGetBackgroundRequiresAuthentication(t *testing.T) {
	router, _, _ := testRouter(t)

	response := performJSON(router, http.MethodGet, "/api/me/background", nil, "")
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusUnauthorized)
	}
}

func TestHandlerRejectsInvalidFact(t *testing.T) {
	router, token, _ := testRouter(t)

	response := performJSON(router, http.MethodPut, "/api/me/background", map[string]any{
		"facts": []map[string]any{
			{"fact_value": "missing key"},
		},
	}, token)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusBadRequest, response.Body.String())
	}
}

func TestNormalizeBackgroundInputDeduplicatesPrivacyExclusions(t *testing.T) {
	got := normalizeBackgroundInput(BackgroundInput{
		PrivacyExclusions: []string{" hometown ", "hometown", ""},
		Facts: []FactInput{
			{FactKey: " city ", FactValue: " Hangzhou "},
		},
	})

	if len(got.PrivacyExclusions) != 1 || got.PrivacyExclusions[0] != "hometown" {
		t.Fatalf("privacy exclusions = %#v, want [hometown]", got.PrivacyExclusions)
	}
	if got.Facts[0].FactKey != "city" || got.Facts[0].FactValue != "Hangzhou" {
		t.Fatalf("fact = %#v", got.Facts[0])
	}
	if got.Facts[0].PrivacyLevel != PrivacyNormal {
		t.Fatalf("privacy level = %q, want normal", got.Facts[0].PrivacyLevel)
	}
}

func testRouter(t *testing.T) (http.Handler, string, *fakeStore) {
	t.Helper()
	gin.SetMode(gin.TestMode)

	tokens, err := auth.NewTokenService(auth.TokenServiceConfig{Secret: "test-secret-must-be-at-least-32-bytes"})
	if err != nil {
		t.Fatalf("NewTokenService() error = %v", err)
	}
	user := auth.User{ID: "user_001", Email: "learner@example.com", Role: "user", Status: "active", CreatedAt: time.Now().UTC()}
	pair, err := tokens.GeneratePair(user)
	if err != nil {
		t.Fatalf("GeneratePair() error = %v", err)
	}

	store := newFakeStore()
	router := gin.New()
	NewHandler(store).RegisterRoutes(router.Group("/api"), auth.NewAuthenticator(profileAuthStore{}, tokens))
	return router, "Bearer " + pair.AccessToken, store
}

type fakeStore struct {
	saved      BackgroundInput
	background Background
}

func newFakeStore() *fakeStore {
	now := time.Now().UTC()
	return &fakeStore{
		background: Background{
			Profile: UserProfile{
				ID:        "profile_001",
				UserID:    "user_001",
				Timezone:  DefaultTimezone,
				CreatedAt: now,
				UpdatedAt: now,
			},
			Facts:      []BackgroundFact{},
			AgentFacts: []BackgroundFact{},
		},
	}
}

func (s *fakeStore) GetBackground(context.Context, string) (Background, error) {
	return s.background, nil
}

func (s *fakeStore) SaveBackground(_ context.Context, userID string, input BackgroundInput) (Background, error) {
	input = normalizeBackgroundInput(input)
	if err := validateBackgroundInput(input); err != nil {
		return Background{}, err
	}
	s.saved = input

	now := time.Now().UTC()
	profile := s.background.Profile
	if input.Profile != nil && input.Profile.DisplayName != nil {
		profile.DisplayName = input.Profile.DisplayName
	}
	questionnaire := &Questionnaire{
		ID:                "questionnaire_001",
		UserID:            userID,
		Version:           1,
		Answers:           mapToRawJSON(input.Answers),
		PrivacyExclusions: input.PrivacyExclusions,
		SubmittedAt:       &now,
		CreatedAt:         now,
		UpdatedAt:         now,
	}

	exclusions := privacyExclusionSet(input.PrivacyExclusions)
	facts := []BackgroundFact{}
	for _, item := range input.Facts {
		topic := item.Topic
		facts = append(facts, BackgroundFact{
			ID:              "fact_" + item.FactKey,
			UserID:          userID,
			QuestionnaireID: &questionnaire.ID,
			Topic:           topic,
			FactKey:         item.FactKey,
			FactValue:       item.FactValue,
			PrivacyLevel:    item.PrivacyLevel,
			AllowedUsage:    item.AllowedUsage,
			IsExcluded:      item.IsExcluded || factExcluded(item, exclusions),
			CreatedAt:       now,
			UpdatedAt:       now,
		})
	}

	s.background = Background{
		Profile:       profile,
		Questionnaire: questionnaire,
		Facts:         facts,
		AgentFacts:    filterAgentFacts(facts),
	}
	return s.background, nil
}

type profileAuthStore struct{}

func (profileAuthStore) CreateUser(context.Context, auth.CreateUserParams) (auth.User, error) {
	return auth.User{}, nil
}

func (profileAuthStore) GetUserByEmail(context.Context, string) (auth.UserWithPassword, error) {
	return auth.UserWithPassword{}, auth.ErrUserNotFound
}

func (profileAuthStore) GetUserByID(context.Context, string) (auth.User, error) {
	return auth.User{ID: "user_001", Email: "learner@example.com", Role: "user", Status: "active", CreatedAt: time.Now().UTC()}, nil
}

func (profileAuthStore) UpdateLastLogin(context.Context, string) error {
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
