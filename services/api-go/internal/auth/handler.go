package auth

import (
	"errors"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
)

type Handler struct {
	service       Service
	authenticator Authenticator
}

func NewHandler(service Service, authenticator Authenticator) Handler {
	return Handler{service: service, authenticator: authenticator}
}

type registerRequest struct {
	Email       string `json:"email" binding:"required,email"`
	Password    string `json:"password" binding:"required,min=8,max=128"`
	DisplayName string `json:"display_name" binding:"omitempty,max=80"`
}

type loginRequest struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required,max=128"`
}

type refreshRequest struct {
	RefreshToken string `json:"refresh_token" binding:"required"`
}

func (h Handler) RegisterRoutes(api *gin.RouterGroup) {
	api.POST("/auth/register", h.Register)
	api.POST("/auth/login", h.Login)
	api.POST("/auth/refresh", h.Refresh)

	protected := api.Group("")
	protected.Use(AuthMiddleware(h.authenticator))
	protected.GET("/me", h.Me)
}

func (h Handler) Register(c *gin.Context) {
	var request registerRequest
	if !bindJSON(c, &request) {
		return
	}

	response, err := h.service.Register(c.Request.Context(), RegisterInput{
		Email:       request.Email,
		Password:    request.Password,
		DisplayName: request.DisplayName,
	})
	if err != nil {
		writeAuthError(c, err)
		return
	}

	c.JSON(http.StatusCreated, response)
}

func (h Handler) Login(c *gin.Context) {
	var request loginRequest
	if !bindJSON(c, &request) {
		return
	}

	response, err := h.service.Login(c.Request.Context(), LoginInput{
		Email:    request.Email,
		Password: request.Password,
	})
	if err != nil {
		writeAuthError(c, err)
		return
	}

	c.JSON(http.StatusOK, response)
}

func (h Handler) Refresh(c *gin.Context) {
	var request refreshRequest
	if !bindJSON(c, &request) {
		return
	}

	response, err := h.service.Refresh(c.Request.Context(), request.RefreshToken)
	if err != nil {
		writeAuthError(c, err)
		return
	}

	c.JSON(http.StatusOK, response)
}

func (h Handler) Me(c *gin.Context) {
	userID := CurrentUserID(c)
	user, err := h.service.CurrentUser(c.Request.Context(), userID)
	if err != nil {
		writeAuthError(c, err)
		return
	}

	c.JSON(http.StatusOK, gin.H{"user": user})
}

func bindJSON(c *gin.Context, target any) bool {
	if err := c.ShouldBindJSON(target); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"error":   "invalid_request",
			"message": "请求体格式或字段不合法",
		})
		return false
	}
	return true
}

func writeAuthError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, ErrEmailAlreadyRegistered):
		c.JSON(http.StatusConflict, gin.H{"error": "email_already_registered", "message": "该邮箱已注册"})
	case errors.Is(err, ErrInvalidCredentials):
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid_credentials", "message": "邮箱或密码不正确"})
	case errors.Is(err, ErrInvalidToken):
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid_token", "message": "登录状态无效或已过期"})
	case errors.Is(err, ErrForbiddenUserStatus):
		c.JSON(http.StatusForbidden, gin.H{"error": "forbidden_user_status", "message": "当前用户状态不允许访问"})
	case errors.Is(err, ErrUserNotFound):
		c.JSON(http.StatusNotFound, gin.H{"error": "user_not_found", "message": "用户不存在"})
	default:
		if strings.TrimSpace(err.Error()) == "" {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
	}
}
