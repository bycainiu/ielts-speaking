package realtime

import (
	"errors"
	"net/http"
	"net/url"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
)

type Handler struct {
	hub           *Hub
	access        SessionAccessStore
	authenticator auth.Authenticator
	upgrader      websocket.Upgrader
}

func NewHandler(hub *Hub, access SessionAccessStore, authenticator auth.Authenticator) Handler {
	return Handler{
		hub:           hub,
		access:        access,
		authenticator: authenticator,
		upgrader: websocket.Upgrader{
			ReadBufferSize:  1024,
			WriteBufferSize: 1024,
			CheckOrigin:     checkOrigin,
		},
	}
}

func (h Handler) RegisterRoutes(api *gin.RouterGroup) {
	api.GET("/ws/sessions/:id", h.ConnectSession)
}

func (h Handler) ConnectSession(c *gin.Context) {
	user, err := h.authenticate(c)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "unauthorized", "message": "请先登录"})
		return
	}

	sessionID := c.Param("id")
	if err := h.access.EnsureSessionAccess(c.Request.Context(), user.ID, sessionID); err != nil {
		if errors.Is(err, ErrSessionNotFound) {
			c.JSON(http.StatusNotFound, gin.H{"error": "not_found", "message": "会话资源不存在"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
		return
	}

	conn, err := h.upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		return
	}

	client := h.hub.NewClient(sessionID, user.ID)
	client.attach(conn)
	h.hub.Register(client)
	go client.writePump()
	client.readPump()
}

func (h Handler) authenticate(c *gin.Context) (auth.AuthenticatedUser, error) {
	header := c.GetHeader("Authorization")
	if strings.TrimSpace(header) == "" {
		if token := strings.TrimSpace(c.Query("access_token")); token != "" {
			header = "Bearer " + token
		}
	}
	if strings.TrimSpace(header) == "" {
		return auth.AuthenticatedUser{}, ErrUnauthorized
	}
	return h.authenticator.AuthenticateBearer(c.Request.Context(), header)
}

func checkOrigin(r *http.Request) bool {
	origin := strings.TrimSpace(r.Header.Get("Origin"))
	if origin == "" {
		return true
	}
	parsed, err := url.Parse(origin)
	if err != nil || parsed.Host == "" {
		return false
	}
	originHost := strings.ToLower(parsed.Host)

	for _, requestHost := range requestOriginHosts(r) {
		if originMatchesRequestHost(originHost, requestHost) {
			return true
		}
	}

	return false
}

func originMatchesRequestHost(originHost string, requestHost string) bool {
	requestHost = strings.ToLower(strings.TrimSpace(requestHost))
	if requestHost == "" {
		return false
	}
	if originHost == requestHost {
		return true
	}
	if sameHostname(originHost, requestHost) {
		return true
	}
	return isLocalHost(originHost) && isLocalHost(requestHost)
}

func requestOriginHosts(r *http.Request) []string {
	hosts := make([]string, 0, 4)
	hosts = appendHostCandidates(hosts, r.Host)
	hosts = appendHostCandidates(hosts, r.Header.Get("X-Forwarded-Host"))
	hosts = appendHostCandidates(hosts, r.Header.Get("X-Original-Host"))
	hosts = appendForwardedHostCandidates(hosts, r.Header.Get("Forwarded"))
	return hosts
}

func appendHostCandidates(hosts []string, value string) []string {
	for _, part := range strings.Split(value, ",") {
		host := strings.TrimSpace(part)
		if host != "" {
			hosts = append(hosts, host)
		}
	}
	return hosts
}

func appendForwardedHostCandidates(hosts []string, value string) []string {
	for _, forwarded := range strings.Split(value, ",") {
		for _, parameter := range strings.Split(forwarded, ";") {
			key, rawValue, ok := strings.Cut(strings.TrimSpace(parameter), "=")
			if !ok || !strings.EqualFold(strings.TrimSpace(key), "host") {
				continue
			}
			host := strings.Trim(strings.TrimSpace(rawValue), `"`)
			if host != "" {
				hosts = append(hosts, host)
			}
		}
	}
	return hosts
}

func sameHostname(leftHost string, rightHost string) bool {
	leftName, err := hostnameFromHost(leftHost)
	if err != nil || leftName == "" {
		return false
	}
	rightName, err := hostnameFromHost(rightHost)
	if err != nil || rightName == "" {
		return false
	}
	return strings.EqualFold(leftName, rightName)
}

func hostnameFromHost(host string) (string, error) {
	parsed := host
	if !strings.Contains(parsed, "://") {
		parsed = "http://" + parsed
	}
	url, err := url.Parse(parsed)
	if err != nil {
		return "", err
	}
	hostname := strings.TrimSpace(url.Hostname())
	if hostname == "" {
		return "", nil
	}
	return strings.Trim(strings.ToLower(hostname), "[]"), nil
}

func isLocalHost(host string) bool {
	hostname, err := hostnameFromHost(host)
	if err == nil && hostname != "" {
		return hostname == "localhost" || hostname == "127.0.0.1" || hostname == "::1"
	}
	host = strings.Trim(strings.ToLower(strings.TrimSpace(host)), "[]")
	if strings.HasPrefix(host, "localhost:") || host == "localhost" {
		return true
	}
	if strings.HasPrefix(host, "127.0.0.1:") || host == "127.0.0.1" {
		return true
	}
	if strings.HasPrefix(host, "::1:") || host == "::1" {
		return true
	}
	return false
}
