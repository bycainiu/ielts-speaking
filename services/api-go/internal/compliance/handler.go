package compliance

import (
	"errors"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
)

type Handler struct {
	store Store
}

func NewHandler(store Store) Handler {
	return Handler{store: store}
}

func (h Handler) RegisterRoutes(api *gin.RouterGroup, authenticator auth.Authenticator) {
	privacy := api.Group("/privacy")
	privacy.Use(auth.AuthMiddleware(authenticator))
	privacy.GET("/consents", h.ListConsents)
	privacy.POST("/consents", h.SaveConsent)
	privacy.POST("/data-deletion", h.DeleteData)
	privacy.GET("/voice-clone-policy", h.GetVoiceClonePolicy)

	admin := api.Group("/admin/compliance")
	admin.Use(auth.AuthMiddleware(authenticator), auth.RequireRoles("operator", "admin"))
	admin.GET("/voice-clone-policy", h.GetVoiceClonePolicy)
	admin.PUT("/voice-clone-policy", h.UpdateVoiceClonePolicy)
}

func (h Handler) ListConsents(c *gin.Context) {
	consentType := strings.TrimSpace(c.Query("consent_type"))
	items, err := h.store.ListConsents(c.Request.Context(), auth.CurrentUserID(c), consentType)
	if err != nil {
		writeError(c, err)
		return
	}
	var latest *ConsentRecord
	if len(items) > 0 {
		latest = &items[0]
	}
	c.JSON(http.StatusOK, gin.H{"consents": items, "latest": latest})
}

func (h Handler) SaveConsent(c *gin.Context) {
	var request SaveConsentInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.SaveConsent(c.Request.Context(), auth.CurrentUserID(c), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"consent": item})
}

func (h Handler) DeleteData(c *gin.Context) {
	var request DataDeletionInput
	if !bind(c, &request) {
		return
	}
	result, err := h.store.DeleteUserData(c.Request.Context(), auth.CurrentUserID(c), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"deletion": result})
}

func (h Handler) GetVoiceClonePolicy(c *gin.Context) {
	policy, err := h.store.GetVoiceClonePolicy(c.Request.Context())
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"policy": policy})
}

func (h Handler) UpdateVoiceClonePolicy(c *gin.Context) {
	var request UpdateVoiceClonePolicyInput
	if !bind(c, &request) {
		return
	}
	policy, err := h.store.UpdateVoiceClonePolicy(c.Request.Context(), auth.CurrentUserID(c), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"policy": policy})
}

func bind(c *gin.Context, target any) bool {
	if err := c.ShouldBindJSON(target); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_request", "message": "请求体格式或字段不合法"})
		return false
	}
	return true
}

func writeError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, ErrNotFound):
		c.JSON(http.StatusNotFound, gin.H{"error": "not_found", "message": "合规资源不存在"})
	case errors.Is(err, ErrInvalidInput):
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_compliance_input", "message": err.Error()})
	default:
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
	}
}
