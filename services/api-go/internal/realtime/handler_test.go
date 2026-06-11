package realtime

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
)

func TestConnectSessionRequiresAuthentication(t *testing.T) {
	server, _ := newTestServer(t, fakeAccessStore{})
	defer server.Close()

	_, response, err := websocket.DefaultDialer.Dial(wsURL(server.URL, "/api/ws/sessions/session_001"), nil)
	if err == nil {
		t.Fatal("Dial() expected authentication error")
	}
	if response == nil || response.StatusCode != http.StatusUnauthorized {
		t.Fatalf("status = %v, want %d", statusCode(response), http.StatusUnauthorized)
	}
}

func TestConnectSessionRequiresSessionAccess(t *testing.T) {
	server, token := newTestServer(t, fakeAccessStore{err: ErrSessionNotFound})
	defer server.Close()

	_, response, err := websocket.DefaultDialer.Dial(wsURL(server.URL, "/api/ws/sessions/session_404?access_token="+token), nil)
	if err == nil {
		t.Fatal("Dial() expected session access error")
	}
	if response == nil || response.StatusCode != http.StatusNotFound {
		t.Fatalf("status = %v, want %d", statusCode(response), http.StatusNotFound)
	}
}

func TestConnectSessionWithQueryTokenBroadcastsEvent(t *testing.T) {
	server, token := newTestServer(t, fakeAccessStore{})
	defer server.Close()

	conn, response, err := websocket.DefaultDialer.Dial(wsURL(server.URL, "/api/ws/sessions/session_001?access_token="+token), nil)
	if err != nil {
		t.Fatalf("Dial() error = %v, status = %v", err, statusCode(response))
	}
	defer conn.Close()

	event := SessionEvent{
		Type:      EventTimerTick,
		SessionID: "session_001",
		RunID:     "run_001",
		Payload:   json.RawMessage(`{"remaining_seconds":45}`),
		CreatedAt: time.Now().UTC().Format(time.RFC3339Nano),
	}
	if err := conn.WriteJSON(event); err != nil {
		t.Fatalf("WriteJSON() error = %v", err)
	}

	var received SessionEvent
	conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	if err := conn.ReadJSON(&received); err != nil {
		t.Fatalf("ReadJSON() error = %v", err)
	}
	if received.Type != EventTimerTick || received.SessionID != "session_001" {
		t.Fatalf("received event = %#v", received)
	}
}

func TestCheckOriginAllowsSameHostDifferentPorts(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "http://192.168.1.100:18080/api/ws/sessions/session_001", nil)
	request.Header.Set("Origin", "http://192.168.1.100:3000")

	if !checkOrigin(request) {
		t.Fatal("checkOrigin() rejected same hostname with different dev ports")
	}
}

func TestCheckOriginAllowsForwardedHostFromWebProxy(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "http://localhost:18080/api/ws/sessions/session_001", nil)
	request.Header.Set("Origin", "http://192.168.1.100:3000")
	request.Header.Set("X-Forwarded-Host", "192.168.1.100:3000")

	if !checkOrigin(request) {
		t.Fatal("checkOrigin() rejected matching forwarded host from web proxy")
	}
}

func TestCheckOriginAllowsForwardedHeaderHostFromWebProxy(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "http://api-go:8080/api/ws/sessions/session_001", nil)
	request.Header.Set("Origin", "https://exam.local")
	request.Header.Set("Forwarded", `for=10.0.0.2;proto=https;host="exam.local"`)

	if !checkOrigin(request) {
		t.Fatal("checkOrigin() rejected matching Forwarded host")
	}
}

func TestCheckOriginRejectsDifferentHosts(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "http://192.168.1.100:18080/api/ws/sessions/session_001", nil)
	request.Header.Set("Origin", "http://192.168.1.50:3000")

	if checkOrigin(request) {
		t.Fatal("checkOrigin() accepted different hostnames")
	}
}

func TestCheckOriginRejectsDifferentForwardedHosts(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "http://localhost:18080/api/ws/sessions/session_001", nil)
	request.Header.Set("Origin", "http://192.168.1.50:3000")
	request.Header.Set("X-Forwarded-Host", "192.168.1.100:3000")

	if checkOrigin(request) {
		t.Fatal("checkOrigin() accepted different forwarded hostname")
	}
}

func newTestServer(t *testing.T, access SessionAccessStore) (*httptest.Server, string) {
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

	router := gin.New()
	NewHandler(NewHub(), access, auth.NewAuthenticator(realtimeAuthStore{}, tokens)).RegisterRoutes(router.Group("/api"))
	return httptest.NewServer(router), pair.AccessToken
}

type fakeAccessStore struct {
	err error
}

func (s fakeAccessStore) EnsureSessionAccess(context.Context, string, string) error {
	return s.err
}

type realtimeAuthStore struct{}

func (realtimeAuthStore) CreateUser(context.Context, auth.CreateUserParams) (auth.User, error) {
	return auth.User{}, nil
}

func (realtimeAuthStore) GetUserByEmail(context.Context, string) (auth.UserWithPassword, error) {
	return auth.UserWithPassword{}, auth.ErrUserNotFound
}

func (realtimeAuthStore) GetUserByID(context.Context, string) (auth.User, error) {
	return auth.User{ID: "user_001", Email: "learner@example.com", Role: "user", Status: "active", CreatedAt: time.Now().UTC()}, nil
}

func (realtimeAuthStore) UpdateLastLogin(context.Context, string) error {
	return nil
}

func wsURL(base string, path string) string {
	return "ws" + strings.TrimPrefix(base, "http") + path
}

func statusCode(response *http.Response) int {
	if response == nil {
		return 0
	}
	return response.StatusCode
}
