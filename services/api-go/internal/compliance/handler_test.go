package compliance

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

func TestHandlerSavesAndListsRecordingConsent(t *testing.T) {
	router, token, store := testRouter(t, "user")

	response := performJSON(router, http.MethodPost, "/api/privacy/consents", map[string]any{
		"consent_type": "recording",
		"accepted":     true,
		"metadata": map[string]any{
			"surface": "live_session",
		},
	}, token)
	if response.Code != http.StatusCreated {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if len(store.consents) != 1 || !store.consents[0].Accepted {
		t.Fatalf("consents = %+v", store.consents)
	}

	list := performJSON(router, http.MethodGet, "/api/privacy/consents?consent_type=recording", nil, token)
	if list.Code != http.StatusOK {
		t.Fatalf("list status = %d, body = %s", list.Code, list.Body.String())
	}
	var body struct {
		Consents []ConsentRecord `json:"consents"`
		Latest   *ConsentRecord  `json:"latest"`
	}
	if err := json.Unmarshal(list.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode list: %v", err)
	}
	if len(body.Consents) != 1 || body.Latest == nil || body.Latest.ConsentType != "recording" {
		t.Fatalf("list body = %+v", body)
	}
}

func TestHandlerDeleteDataRequiresConfirmation(t *testing.T) {
	router, token, _ := testRouter(t, "user")

	response := performJSON(router, http.MethodPost, "/api/privacy/data-deletion", map[string]any{
		"delete_background": true,
		"confirmation":      "WRONG",
	}, token)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestHandlerDeletesUserData(t *testing.T) {
	router, token, store := testRouter(t, "user")

	response := performJSON(router, http.MethodPost, "/api/privacy/data-deletion", map[string]any{
		"session_id":        "11111111-1111-1111-1111-111111111111",
		"delete_recordings": true,
		"delete_reports":    true,
		"delete_background": true,
		"confirmation":      DataDeletionConfirmation,
	}, token)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if store.lastDeletion.SessionID == nil || *store.lastDeletion.SessionID == "" {
		t.Fatalf("deletion input = %+v", store.lastDeletion)
	}
	var body struct {
		Deletion DataDeletionResult `json:"deletion"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode deletion: %v", err)
	}
	if body.Deletion.SessionsDeleted != 1 || body.Deletion.AudioAssetsDeleted != 2 || body.Deletion.BackgroundItemsDeleted != 3 {
		t.Fatalf("deletion = %+v", body.Deletion)
	}
}

func TestHandlerUpdatesVoiceClonePolicyForOperator(t *testing.T) {
	router, token, store := testRouter(t, "operator")

	response := performJSON(router, http.MethodPut, "/api/admin/compliance/voice-clone-policy", map[string]any{
		"enabled": true,
	}, token)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if !store.policy.Enabled {
		t.Fatalf("policy = %+v", store.policy)
	}
}

func TestHandlerRejectsVoiceClonePolicyUpdateForUser(t *testing.T) {
	router, token, _ := testRouter(t, "user")

	response := performJSON(router, http.MethodPut, "/api/admin/compliance/voice-clone-policy", map[string]any{
		"enabled": true,
	}, token)
	if response.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusForbidden)
	}
}

func testRouter(t *testing.T, role string) (http.Handler, string, *fakeStore) {
	t.Helper()
	gin.SetMode(gin.TestMode)

	tokenService, err := auth.NewTokenService(auth.TokenServiceConfig{Secret: "test-secret-must-be-at-least-32-bytes"})
	if err != nil {
		t.Fatalf("NewTokenService() error = %v", err)
	}
	user := auth.User{ID: "user_001", Email: "learner@example.com", Role: role, Status: "active", CreatedAt: time.Now().UTC()}
	pair, err := tokenService.GeneratePair(user)
	if err != nil {
		t.Fatalf("GeneratePair() error = %v", err)
	}
	store := &fakeStore{policy: defaultVoiceClonePolicy(time.Now().UTC())}
	router := gin.New()
	NewHandler(store).RegisterRoutes(router.Group("/api"), auth.NewAuthenticator(authStore{user: user}, tokenService))
	return router, "Bearer " + pair.AccessToken, store
}

type fakeStore struct {
	consents     []ConsentRecord
	lastDeletion DataDeletionInput
	policy       VoiceClonePolicy
}

func (s *fakeStore) SaveConsent(_ context.Context, userID string, input SaveConsentInput) (ConsentRecord, error) {
	input.Normalize()
	if err := input.Validate(); err != nil {
		return ConsentRecord{}, err
	}
	metadata, _ := marshalObject(input.Metadata)
	now := time.Now().UTC()
	item := ConsentRecord{
		ID:          "consent_001",
		UserID:      userID,
		ConsentType: input.ConsentType,
		Version:     input.Version,
		Accepted:    input.Accepted,
		Metadata:    json.RawMessage(metadata),
		CreatedAt:   now,
	}
	if input.Accepted {
		item.AcceptedAt = &now
	}
	s.consents = append([]ConsentRecord{item}, s.consents...)
	return item, nil
}

func (s *fakeStore) ListConsents(_ context.Context, _ string, consentType string) ([]ConsentRecord, error) {
	if consentType == "" {
		return s.consents, nil
	}
	items := []ConsentRecord{}
	for _, item := range s.consents {
		if item.ConsentType == consentType {
			items = append(items, item)
		}
	}
	return items, nil
}

func (s *fakeStore) DeleteUserData(_ context.Context, _ string, input DataDeletionInput) (DataDeletionResult, error) {
	input.Normalize()
	if err := input.Validate(); err != nil {
		return DataDeletionResult{}, err
	}
	s.lastDeletion = input
	return DataDeletionResult{SessionsDeleted: 1, AudioAssetsDeleted: 2, BackgroundItemsDeleted: 3}, nil
}

func (s *fakeStore) GetVoiceClonePolicy(context.Context) (VoiceClonePolicy, error) {
	return s.policy, nil
}

func (s *fakeStore) UpdateVoiceClonePolicy(_ context.Context, actorUserID string, input UpdateVoiceClonePolicyInput) (VoiceClonePolicy, error) {
	input.Normalize()
	if err := input.Validate(); err != nil {
		return VoiceClonePolicy{}, err
	}
	requiresConsent := true
	if input.RequiresExplicitConsent != nil {
		requiresConsent = *input.RequiresExplicitConsent
	}
	now := time.Now().UTC()
	s.policy = VoiceClonePolicy{
		Enabled:                 input.Enabled,
		Version:                 input.Version,
		RequiresExplicitConsent: requiresConsent,
		UpdatedBy:               &actorUserID,
		UpdatedAt:               now,
	}
	return s.policy, nil
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

type authStore struct {
	user auth.User
}

func (authStore) CreateUser(context.Context, auth.CreateUserParams) (auth.User, error) {
	return auth.User{}, nil
}

func (authStore) GetUserByEmail(context.Context, string) (auth.UserWithPassword, error) {
	return auth.UserWithPassword{}, auth.ErrUserNotFound
}

func (s authStore) GetUserByID(context.Context, string) (auth.User, error) {
	return s.user, nil
}

func (authStore) UpdateLastLogin(context.Context, string) error {
	return nil
}
