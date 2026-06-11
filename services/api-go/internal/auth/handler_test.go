package auth

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
)

func TestHandlerRegisterLoginAndMe(t *testing.T) {
	gin.SetMode(gin.TestMode)

	store := newFakeStore()
	tokens := testTokenService(t)
	service := NewService(store, fakeHasher{}, tokens)
	handler := NewHandler(service, NewAuthenticator(store, tokens))

	router := gin.New()
	api := router.Group("/api")
	handler.RegisterRoutes(api)

	registerBody := map[string]string{
		"email":        "learner@example.com",
		"password":     "secret-password",
		"display_name": "Learner",
	}
	registerResponse := performJSON(router, http.MethodPost, "/api/auth/register", registerBody, "")
	if registerResponse.Code != http.StatusCreated {
		t.Fatalf("register status = %d, body = %s", registerResponse.Code, registerResponse.Body.String())
	}

	loginResponse := performJSON(router, http.MethodPost, "/api/auth/login", map[string]string{
		"email":    "learner@example.com",
		"password": "secret-password",
	}, "")
	if loginResponse.Code != http.StatusOK {
		t.Fatalf("login status = %d, body = %s", loginResponse.Code, loginResponse.Body.String())
	}

	var body AuthResponse
	if err := json.Unmarshal(loginResponse.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal login response: %v", err)
	}

	meResponse := performJSON(router, http.MethodGet, "/api/me", nil, "Bearer "+body.Token.AccessToken)
	if meResponse.Code != http.StatusOK {
		t.Fatalf("me status = %d, body = %s", meResponse.Code, meResponse.Body.String())
	}
}

func TestHandlerRegisterAndLoginWithVerificationEnabled(t *testing.T) {
	gin.SetMode(gin.TestMode)

	store := newFakeStore()
	tokens := testTokenService(t)
	captchaStore := NewCaptchaStore(CaptchaConfig{TTL: time.Minute})
	emailVerification := NewEmailVerificationService(
		NewMemoryEmailVerificationStore(),
		LogEmailSender{Logger: log.New(io.Discard, "", 0)},
		EmailVerificationConfig{TTL: time.Minute, Cooldown: time.Second, DebugCode: true},
	)
	handler := NewHandler(
		NewService(store, fakeHasher{}, tokens),
		NewAuthenticator(store, tokens),
		WithCaptchaStore(captchaStore),
		WithEmailVerification(emailVerification),
	)

	router := gin.New()
	handler.RegisterRoutes(router.Group("/api"))

	captchaID, captchaAnswer := solvedCaptcha(t, captchaStore)
	emailCodeResponse := performJSON(router, http.MethodPost, "/api/auth/register/email-code", map[string]string{
		"email":          "learner@example.com",
		"captcha_id":     captchaID,
		"captcha_answer": captchaAnswer,
	}, "")
	if emailCodeResponse.Code != http.StatusOK {
		t.Fatalf("email code status = %d, body = %s", emailCodeResponse.Code, emailCodeResponse.Body.String())
	}

	var emailCodeBody EmailVerificationResult
	if err := json.Unmarshal(emailCodeResponse.Body.Bytes(), &emailCodeBody); err != nil {
		t.Fatalf("unmarshal email code response: %v", err)
	}
	if emailCodeBody.DebugCode == "" {
		t.Fatal("expected debug email code")
	}

	registerResponse := performJSON(router, http.MethodPost, "/api/auth/register", map[string]string{
		"email":                   "learner@example.com",
		"password":                "secret-password",
		"display_name":            "Learner",
		"email_verification_code": emailCodeBody.DebugCode,
	}, "")
	if registerResponse.Code != http.StatusCreated {
		t.Fatalf("register status = %d, body = %s", registerResponse.Code, registerResponse.Body.String())
	}

	loginCaptchaID, loginCaptchaAnswer := solvedCaptcha(t, captchaStore)
	loginResponse := performJSON(router, http.MethodPost, "/api/auth/login", map[string]string{
		"email":          "learner@example.com",
		"password":       "secret-password",
		"captcha_id":     loginCaptchaID,
		"captcha_answer": loginCaptchaAnswer,
	}, "")
	if loginResponse.Code != http.StatusOK {
		t.Fatalf("login status = %d, body = %s", loginResponse.Code, loginResponse.Body.String())
	}
}

func TestHandlerLoginRequiresCaptchaWhenEnabled(t *testing.T) {
	gin.SetMode(gin.TestMode)

	store := newFakeStore()
	tokens := testTokenService(t)
	if _, err := NewService(store, fakeHasher{}, tokens).Register(context.Background(), RegisterInput{Email: "learner@example.com", Password: "secret-password"}); err != nil {
		t.Fatalf("Register() error = %v", err)
	}

	handler := NewHandler(
		NewService(store, fakeHasher{}, tokens),
		NewAuthenticator(store, tokens),
		WithCaptchaStore(NewCaptchaStore(CaptchaConfig{TTL: time.Minute})),
	)

	router := gin.New()
	handler.RegisterRoutes(router.Group("/api"))

	response := performJSON(router, http.MethodPost, "/api/auth/login", map[string]string{
		"email":    "learner@example.com",
		"password": "secret-password",
	}, "")
	if response.Code != http.StatusBadRequest {
		t.Fatalf("login status = %d, want %d, body = %s", response.Code, http.StatusBadRequest, response.Body.String())
	}

	var body map[string]string
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal login response: %v", err)
	}
	if body["error"] != "invalid_captcha" {
		t.Fatalf("error = %q, want invalid_captcha", body["error"])
	}
}

func TestHandlerRefreshReturnsNestedTokenPayload(t *testing.T) {
	gin.SetMode(gin.TestMode)

	store := newFakeStore()
	tokens := testTokenService(t)
	service := NewService(store, fakeHasher{}, tokens)
	handler := NewHandler(service, NewAuthenticator(store, tokens))

	router := gin.New()
	handler.RegisterRoutes(router.Group("/api"))

	registerResponse := performJSON(router, http.MethodPost, "/api/auth/register", map[string]string{
		"email":    "learner@example.com",
		"password": "secret-password",
	}, "")
	if registerResponse.Code != http.StatusCreated {
		t.Fatalf("register status = %d, body = %s", registerResponse.Code, registerResponse.Body.String())
	}

	var registered AuthResponse
	if err := json.Unmarshal(registerResponse.Body.Bytes(), &registered); err != nil {
		t.Fatalf("unmarshal register response: %v", err)
	}

	refreshResponse := performJSON(router, http.MethodPost, "/api/auth/refresh", map[string]string{
		"refresh_token": registered.Token.RefreshToken,
	}, "")
	if refreshResponse.Code != http.StatusOK {
		t.Fatalf("refresh status = %d, body = %s", refreshResponse.Code, refreshResponse.Body.String())
	}

	var refreshed AuthResponse
	if err := json.Unmarshal(refreshResponse.Body.Bytes(), &refreshed); err != nil {
		t.Fatalf("unmarshal refresh response: %v", err)
	}
	if refreshed.Token.AccessToken == "" || refreshed.Token.RefreshToken == "" {
		t.Fatal("expected refreshed access and refresh tokens")
	}
	if refreshed.User.ID == "" {
		t.Fatal("expected refreshed user payload")
	}

	meResponse := performJSON(router, http.MethodGet, "/api/me", nil, "Bearer "+refreshed.Token.AccessToken)
	if meResponse.Code != http.StatusOK {
		t.Fatalf("me status = %d, body = %s", meResponse.Code, meResponse.Body.String())
	}
}

func TestHandlerMeRequiresAuth(t *testing.T) {
	gin.SetMode(gin.TestMode)

	store := newFakeStore()
	tokens := testTokenService(t)
	handler := NewHandler(NewService(store, fakeHasher{}, tokens), NewAuthenticator(store, tokens))

	router := gin.New()
	handler.RegisterRoutes(router.Group("/api"))

	response := performJSON(router, http.MethodGet, "/api/me", nil, "")
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusUnauthorized)
	}
}

func TestHandlerLoginShortWrongPasswordReturnsInvalidCredentials(t *testing.T) {
	gin.SetMode(gin.TestMode)

	store := newFakeStore()
	tokens := testTokenService(t)
	handler := NewHandler(NewService(store, fakeHasher{}, tokens), NewAuthenticator(store, tokens))

	router := gin.New()
	handler.RegisterRoutes(router.Group("/api"))

	registerResponse := performJSON(router, http.MethodPost, "/api/auth/register", map[string]string{
		"email":    "learner@example.com",
		"password": "secret-password",
	}, "")
	if registerResponse.Code != http.StatusCreated {
		t.Fatalf("register status = %d, body = %s", registerResponse.Code, registerResponse.Body.String())
	}

	response := performJSON(router, http.MethodPost, "/api/auth/login", map[string]string{
		"email":    "learner@example.com",
		"password": "bad",
	}, "")
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("login status = %d, want %d, body = %s", response.Code, http.StatusUnauthorized, response.Body.String())
	}

	var body map[string]string
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal login response: %v", err)
	}
	if body["error"] != "invalid_credentials" {
		t.Fatalf("error = %q, want invalid_credentials", body["error"])
	}
	if body["message"] != "邮箱或密码不正确" {
		t.Fatalf("message = %q, want 邮箱或密码不正确", body["message"])
	}
}

func solvedCaptcha(t *testing.T, store *CaptchaStore) (string, string) {
	t.Helper()

	challenge, err := store.NewChallenge()
	if err != nil {
		t.Fatalf("NewChallenge() error = %v", err)
	}

	store.mu.Lock()
	defer store.mu.Unlock()

	record, ok := store.records[challenge.ID]
	if !ok {
		t.Fatalf("captcha record %q not found", challenge.ID)
	}
	return challenge.ID, record.Answer
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
