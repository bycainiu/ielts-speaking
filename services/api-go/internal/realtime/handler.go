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
	requestHost := strings.ToLower(r.Host)
	originHost := strings.ToLower(parsed.Host)
	if originHost == requestHost {
		return true
	}
	return isLocalHost(originHost) && isLocalHost(requestHost)
}

func isLocalHost(host string) bool {
	host = strings.TrimPrefix(host, "[")
	host = strings.TrimSuffix(host, "]")
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
