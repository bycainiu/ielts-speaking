package profile

import (
	"errors"
	"net/http"

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
	group := api.Group("/me/background")
	group.Use(auth.AuthMiddleware(authenticator))
	group.GET("", h.GetBackground)
	group.PUT("", h.SaveBackground)
}

func (h Handler) GetBackground(c *gin.Context) {
	item, err := h.store.GetBackground(c.Request.Context(), auth.CurrentUserID(c))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"background": item})
}

func (h Handler) SaveBackground(c *gin.Context) {
	var request BackgroundInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.SaveBackground(c.Request.Context(), auth.CurrentUserID(c), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"background": item})
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
		c.JSON(http.StatusNotFound, gin.H{"error": "not_found", "message": "背景资料不存在"})
	case errors.Is(err, ErrInvalidInput):
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_background_input", "message": "背景问卷参数不合法"})
	default:
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
	}
}
