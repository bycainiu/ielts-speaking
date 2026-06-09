package auth

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

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
