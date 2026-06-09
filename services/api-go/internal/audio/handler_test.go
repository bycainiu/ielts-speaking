package audio

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"net/textproto"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
)

func TestHandlerUploadRequiresAuthentication(t *testing.T) {
	router, _ := newAudioTestRouter(t, &fakeStore{}, &fakeObjectStore{})

	response := performMultipart(router, "/api/audio/upload", "", map[string]string{
		"session_id":  "session_001",
		"turn_id":     "turn_001",
		"duration_ms": "18000",
	}, []byte("fake-webm-audio"), "answer.webm", "audio/webm")

	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusUnauthorized)
	}
}

func TestHandlerUploadMultipartAudio(t *testing.T) {
	store := &fakeStore{}
	objects := &fakeObjectStore{}
	router, token := newAudioTestRouter(t, store, objects)

	response := performMultipart(router, "/api/audio/upload", token, map[string]string{
		"session_id":  "session_001",
		"turn_id":     "turn_001",
		"duration_ms": "18000",
	}, []byte("fake-webm-audio"), "answer.webm", "audio/webm")

	if response.Code != http.StatusCreated {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if objects.putCalls != 1 {
		t.Fatalf("putCalls = %d, want 1", objects.putCalls)
	}

	var body UploadResult
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}
	if body.AudioAsset.ID == "" {
		t.Fatal("response audio asset id is empty")
	}
}

func TestHandlerUploadRejectsInvalidDuration(t *testing.T) {
	store := &fakeStore{}
	objects := &fakeObjectStore{}
	router, token := newAudioTestRouter(t, store, objects)

	response := performMultipart(router, "/api/audio/upload", token, map[string]string{
		"session_id":  "session_001",
		"turn_id":     "turn_001",
		"duration_ms": "0",
	}, []byte("fake-webm-audio"), "answer.webm", "audio/webm")

	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusBadRequest, response.Body.String())
	}
	if objects.putCalls != 0 {
		t.Fatalf("putCalls = %d, want 0", objects.putCalls)
	}
}

func TestHandlerSynthesizeTTSStoresAudio(t *testing.T) {
	store := &fakeStore{}
	objects := &fakeObjectStore{}
	router, token := newAudioTestRouter(t, store, objects)

	response := performJSON(router, http.MethodPost, "/api/audio/tts", token, map[string]any{
		"session_id":    "session_001",
		"turn_id":       "turn_001",
		"text":          "Let's talk about your hometown.",
		"voice_id":      "examiner_voice_a",
		"speaking_rate": 1.05,
		"emotion":       "neutral",
		"style":         "examiner",
	})

	if response.Code != http.StatusCreated {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var body SynthesizeTTSResult
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}
	if body.AudioAsset.Kind != KindExaminerTTS {
		t.Fatalf("kind = %q, want %q", body.AudioAsset.Kind, KindExaminerTTS)
	}
	if body.TTS.Model != "mimo-v2.5-tts" || body.TTS.VoiceID != "examiner_voice_a" {
		t.Fatalf("tts brief = %+v", body.TTS)
	}
	if objects.putCalls != 1 {
		t.Fatalf("putCalls = %d, want 1", objects.putCalls)
	}
}

func TestHandlerCleanupExpiredTTSCache(t *testing.T) {
	store := &fakeStore{cleanupDeleted: 2}
	objects := &fakeObjectStore{}
	router, token := newAudioTestRouter(t, store, objects)

	response := performJSON(router, http.MethodDelete, "/api/audio/tts/cache/expired", token, nil)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var body CleanupTTSCacheResult
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}
	if body.DeletedCount != 2 {
		t.Fatalf("DeletedCount = %d, want 2", body.DeletedCount)
	}
}

func TestHandlerSignedURLReturnsReplayMetadata(t *testing.T) {
	durationMS := 18000
	store := &fakeStore{
		getAsset: Asset{
			ID:            "audio_001",
			Kind:          KindUserRecording,
			StorageBucket: "ielts-speaking-test",
			StorageKey:    "sessions/session_001/turns/turn_001/answer.webm",
			MimeType:      "audio/webm",
			DurationMS:    &durationMS,
		},
	}
	objects := &fakeObjectStore{}
	router, token := newAudioTestRouter(t, store, objects)

	response := performJSON(router, http.MethodGet, "/api/audio/audio_001/signed-url?expires_seconds=300", token, nil)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	var body SignedURLResult
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}
	if body.SignedURL == "" {
		t.Fatal("signed_url is empty")
	}
	if body.AudioAsset.DurationMS == nil || *body.AudioAsset.DurationMS != durationMS {
		t.Fatalf("duration_ms = %v", body.AudioAsset.DurationMS)
	}
	if objects.presignExpires != 300*time.Second {
		t.Fatalf("presign expires = %s, want 5m", objects.presignExpires)
	}
}

func newAudioTestRouter(t *testing.T, store Store, objects ObjectStore) (http.Handler, string) {
	t.Helper()
	gin.SetMode(gin.TestMode)

	tokenService, err := auth.NewTokenService(auth.TokenServiceConfig{Secret: "test-secret-must-be-at-least-32-bytes"})
	if err != nil {
		t.Fatalf("NewTokenService() error = %v", err)
	}
	user := auth.User{ID: "user_001", Email: "learner@example.com", Role: "user", Status: "active", CreatedAt: time.Now().UTC()}
	pair, err := tokenService.GeneratePair(user)
	if err != nil {
		t.Fatalf("GeneratePair() error = %v", err)
	}

	router := gin.New()
	service := NewService(store, objects, ServiceConfig{
		Bucket:        "ielts-speaking-test",
		MaxBytes:      1024 * 1024,
		MaxDurationMS: 60000,
		TTSProvider: &fakeTTSProvider{
			response: TTSProviderResponse{
				Text:        "Let's talk about your hometown.",
				AudioBase64: base64.StdEncoding.EncodeToString([]byte("fake-wav-audio")),
				MimeType:    "audio/wav",
				Provider:    "mock_tts",
				Model:       "mimo-v2.5-tts",
				VoiceID:     "examiner_voice_a",
				DurationMS:  intPtr(1200),
				Metadata:    map[string]any{"style": "examiner"},
			},
		},
	})
	NewHandler(service, 1024*1024).RegisterRoutes(router.Group("/api"), auth.NewAuthenticator(audioAuthStore{}, tokenService))
	return router, "Bearer " + pair.AccessToken
}

func performJSON(router http.Handler, method string, path string, authHeader string, body any) *httptest.ResponseRecorder {
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

func intPtr(value int) *int {
	return &value
}

type audioAuthStore struct{}

func (audioAuthStore) CreateUser(context.Context, auth.CreateUserParams) (auth.User, error) {
	return auth.User{}, nil
}

func (audioAuthStore) GetUserByEmail(context.Context, string) (auth.UserWithPassword, error) {
	return auth.UserWithPassword{}, auth.ErrUserNotFound
}

func (audioAuthStore) GetUserByID(context.Context, string) (auth.User, error) {
	return auth.User{ID: "user_001", Email: "learner@example.com", Role: "user", Status: "active", CreatedAt: time.Now().UTC()}, nil
}

func (audioAuthStore) UpdateLastLogin(context.Context, string) error {
	return nil
}

func performMultipart(router http.Handler, path string, authHeader string, fields map[string]string, file []byte, filename string, contentType string) *httptest.ResponseRecorder {
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	for key, value := range fields {
		if err := writer.WriteField(key, value); err != nil {
			panic(err)
		}
	}

	header := textproto.MIMEHeader{}
	header.Set("Content-Disposition", `form-data; name="file"; filename="`+filename+`"`)
	header.Set("Content-Type", contentType)
	part, err := writer.CreatePart(header)
	if err != nil {
		panic(err)
	}
	if _, err := part.Write(file); err != nil {
		panic(err)
	}
	if err := writer.Close(); err != nil {
		panic(err)
	}

	request := httptest.NewRequest(http.MethodPost, path, &body)
	request.Header.Set("Content-Type", writer.FormDataContentType())
	if authHeader != "" {
		request.Header.Set("Authorization", authHeader)
	}

	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	return response
}
