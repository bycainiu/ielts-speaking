package session

import (
	"context"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
	"github.com/ielts-speaking/platform/services/api-go/internal/quota"
)

type QuotaStore interface {
	AssertCanStart(ctx context.Context, userID, mode string) error
	ConsumeCredits(ctx context.Context, userID, sessionID, mode string) error
}

type Handler struct {
	store Store
	quota QuotaStore
}

type HandlerOption func(*Handler)

func NewHandler(store Store, options ...HandlerOption) Handler {
	handler := Handler{store: store}
	for _, option := range options {
		option(&handler)
	}
	return handler
}

func WithQuotaStore(quota QuotaStore) HandlerOption {
	return func(handler *Handler) {
		handler.quota = quota
	}
}

func (h Handler) RegisterRoutes(api *gin.RouterGroup, authenticator auth.Authenticator) {
	group := api.Group("/sessions")
	group.Use(auth.AuthMiddleware(authenticator))
	group.GET("", h.ListSessions)
	group.POST("", h.CreateSession)
	group.GET("/:id", h.GetSession)
	group.POST("/:id/start", h.StartSession)
	group.POST("/:id/pause", h.PauseSession)
	group.POST("/:id/resume", h.ResumeSession)
	group.PATCH("/:id/state", h.UpdateSessionState)
	group.POST("/:id/parts/:part/complete", h.CompletePart)
	group.POST("/:id/finish", h.FinishSession)
	group.POST("/:id/cancel", h.CancelSession)
	group.POST("/:id/turns", h.CreateTurn)
	group.PATCH("/:id/turns/:turn_id", h.UpdateTurn)
	group.POST("/:id/turns/:turn_id/audio-assets", h.AttachAudioAsset)
	group.POST("/:id/turns/:turn_id/asr-results", h.SaveASRResult)
	group.PATCH("/:id/turns/:turn_id/asr-results/:asr_result_id/correction", h.CorrectASRResult)
	group.POST("/:id/turns/:turn_id/speech-metrics", h.SaveSpeechMetrics)

	admin := api.Group("/admin/sessions")
	admin.Use(auth.AuthMiddleware(authenticator), auth.RequireRoles("operator", "admin"))
	admin.GET("/contexts", h.AdminGetSessionContexts)
	admin.GET("/user-contexts", h.AdminGetUserContexts)
	admin.GET("/:id", h.AdminGetSession)
}

func (h Handler) CreateSession(c *gin.Context) {
	var request CreateSessionInput
	if !bind(c, &request) {
		return
	}
	userID := auth.CurrentUserID(c)
	if h.quota != nil && !quota.IsPrivilegedRole(auth.CurrentRole(c)) {
		if err := h.quota.AssertCanStart(c.Request.Context(), userID, request.Mode); err != nil {
			writeBillingError(c, err)
			return
		}
	}
	item, err := h.store.CreateSession(c.Request.Context(), userID, request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"session": item})
}

func (h Handler) ListSessions(c *gin.Context) {
	items, err := h.store.ListSessions(c.Request.Context(), auth.CurrentUserID(c), SessionFilter{
		Mode:   c.Query("mode"),
		Status: c.Query("status"),
		Limit:  intQuery(c, "limit", 50),
		Offset: intQuery(c, "offset", 0),
	})
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"sessions": items})
}

func (h Handler) GetSession(c *gin.Context) {
	item, err := h.store.GetSession(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"session": item})
}

func (h Handler) AdminGetSession(c *gin.Context) {
	item, err := h.store.GetSessionForAdmin(c.Request.Context(), c.Param("id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"session": item})
}

func (h Handler) AdminGetSessionContexts(c *gin.Context) {
	items, err := h.store.GetSessionContextsForAdmin(c.Request.Context(), csvQuery(c, "ids"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"contexts": items})
}

func (h Handler) AdminGetUserContexts(c *gin.Context) {
	items, err := h.store.GetUserContextsByHashForAdmin(c.Request.Context(), csvQuery(c, "hashes"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"contexts": items})
}

func (h Handler) StartSession(c *gin.Context) {
	item, err := h.store.StartSession(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"session": item})
}

func (h Handler) PauseSession(c *gin.Context) {
	item, err := h.store.PauseSession(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"session": item})
}

func (h Handler) ResumeSession(c *gin.Context) {
	item, err := h.store.ResumeSession(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"session": item})
}

func (h Handler) UpdateSessionState(c *gin.Context) {
	var request UpdateSessionStateInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.UpdateSessionState(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"session": item})
}

func (h Handler) CompletePart(c *gin.Context) {
	part, err := strconv.Atoi(c.Param("part"))
	if err != nil || part < 1 || part > 3 {
		writeError(c, ErrInvalidInput)
		return
	}
	item, err := h.store.CompletePart(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"), part)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"session": item})
}

func (h Handler) FinishSession(c *gin.Context) {
	userID := auth.CurrentUserID(c)
	sessionID := c.Param("id")
	item, err := h.store.FinishSession(c.Request.Context(), userID, sessionID)
	if err != nil {
		writeError(c, err)
		return
	}
	if h.quota != nil && !quota.IsPrivilegedRole(auth.CurrentRole(c)) {
		if err := h.quota.ConsumeCredits(c.Request.Context(), userID, sessionID, item.Mode); err != nil {
			writeBillingError(c, err)
			return
		}
	}
	c.JSON(http.StatusOK, gin.H{"session": item})
}

func (h Handler) CancelSession(c *gin.Context) {
	item, err := h.store.CancelSession(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"session": item})
}

func (h Handler) CreateTurn(c *gin.Context) {
	var request CreateTurnInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.CreateTurn(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"turn": item})
}

func (h Handler) UpdateTurn(c *gin.Context) {
	var request UpdateTurnInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.UpdateTurn(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"), c.Param("turn_id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"turn": item})
}

func (h Handler) AttachAudioAsset(c *gin.Context) {
	var request AudioAssetInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.AttachAudioAsset(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"), c.Param("turn_id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"audio_asset": item})
}

func (h Handler) SaveASRResult(c *gin.Context) {
	var request ASRResultInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.SaveASRResult(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"), c.Param("turn_id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"asr_result": item})
}

func (h Handler) CorrectASRResult(c *gin.Context) {
	var request CorrectASRResultInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.CorrectASRResult(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"), c.Param("turn_id"), c.Param("asr_result_id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"asr_result": item})
}

func (h Handler) SaveSpeechMetrics(c *gin.Context) {
	var request SpeechMetricsInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.SaveSpeechMetrics(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"), c.Param("turn_id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"speech_metrics": item})
}

func bind(c *gin.Context, target any) bool {
	if err := c.ShouldBindJSON(target); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_request", "message": "请求体格式或字段不合法"})
		return false
	}
	return true
}

func intQuery(c *gin.Context, key string, fallback int) int {
	value := c.Query(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func csvQuery(c *gin.Context, key string) []string {
	raw := strings.TrimSpace(c.Query(key))
	if raw == "" {
		return []string{}
	}
	parts := strings.Split(raw, ",")
	items := make([]string, 0, len(parts))
	seen := make(map[string]struct{}, len(parts))
	for _, part := range parts {
		normalized := strings.TrimSpace(part)
		if normalized == "" {
			continue
		}
		if _, exists := seen[normalized]; exists {
			continue
		}
		seen[normalized] = struct{}{}
		items = append(items, normalized)
		if len(items) >= 200 {
			break
		}
	}
	return items
}

func writeBillingError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, quota.ErrQuotaExceeded):
		if details, ok := quota.ExceededDetailsFrom(err); ok {
			c.JSON(http.StatusPaymentRequired, gin.H{
				"error":     "quota_exceeded",
				"message":   "练习额度不足，请升级套餐",
				"required":  details.Required,
				"remaining": details.Remaining,
				"plan":      details.PlanSlug,
			})
			return
		}
		c.JSON(http.StatusPaymentRequired, gin.H{"error": "quota_exceeded", "message": "练习额度不足，请升级套餐"})
	case errors.Is(err, quota.ErrSubscriptionExpired):
		c.JSON(http.StatusPaymentRequired, gin.H{"error": "subscription_expired", "message": "订阅已过期，请续费"})
	default:
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
	}
}

func writeError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, ErrNotFound):
		c.JSON(http.StatusNotFound, gin.H{"error": "not_found", "message": "会话资源不存在"})
	case errors.Is(err, ErrInvalidInput):
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_session_input", "message": err.Error()})
	case errors.Is(err, ErrInvalidStatusFlow):
		c.JSON(http.StatusConflict, gin.H{"error": "invalid_status_flow", "message": "当前会话状态不允许执行该操作"})
	case errors.Is(err, ErrDuplicateTurnIndex):
		c.JSON(http.StatusConflict, gin.H{"error": "duplicate_turn_index", "message": "会话轮次序号重复"})
	case errors.Is(err, ErrDuplicateAudioAsset):
		c.JSON(http.StatusConflict, gin.H{"error": "duplicate_audio_asset", "message": "音频资产已存在"})
	default:
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
	}
}
