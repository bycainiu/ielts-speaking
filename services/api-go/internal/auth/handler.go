package auth

import (
	"context"
	"errors"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
)

type Handler struct {
	service           Service
	authenticator     Authenticator
	captchaStore      *CaptchaStore
	emailVerification *EmailVerificationService
	onUserRegistered  func(ctx context.Context, userID string) error
}

type HandlerOption func(*Handler)

func NewHandler(service Service, authenticator Authenticator, options ...HandlerOption) Handler {
	handler := Handler{service: service, authenticator: authenticator}
	for _, option := range options {
		option(&handler)
	}
	return handler
}

func WithCaptchaStore(store *CaptchaStore) HandlerOption {
	return func(handler *Handler) {
		handler.captchaStore = store
	}
}

func WithEmailVerification(service *EmailVerificationService) HandlerOption {
	return func(handler *Handler) {
		handler.emailVerification = service
	}
}

func WithUserRegisteredHook(hook func(ctx context.Context, userID string) error) HandlerOption {
	return func(handler *Handler) {
		handler.onUserRegistered = hook
	}
}

type registerRequest struct {
	Email                 string `json:"email" binding:"required,email"`
	Password              string `json:"password" binding:"required,min=8,max=128"`
	DisplayName           string `json:"display_name" binding:"omitempty,max=80"`
	EmailVerificationCode string `json:"email_verification_code" binding:"omitempty,len=6,numeric"`
}

type loginRequest struct {
	Email         string `json:"email" binding:"required,email"`
	Password      string `json:"password" binding:"required,max=128"`
	CaptchaID     string `json:"captcha_id" binding:"omitempty,max=120"`
	CaptchaAnswer string `json:"captcha_answer" binding:"omitempty,max=16"`
}

type refreshRequest struct {
	RefreshToken string `json:"refresh_token" binding:"required"`
}

type sendRegisterEmailCodeRequest struct {
	Email         string `json:"email" binding:"required,email"`
	CaptchaID     string `json:"captcha_id" binding:"required,max=120"`
	CaptchaAnswer string `json:"captcha_answer" binding:"required,max=16"`
}

func (h Handler) RegisterRoutes(api *gin.RouterGroup) {
	api.GET("/auth/captcha", h.Captcha)
	api.POST("/auth/register/email-code", h.SendRegisterEmailCode)
	api.POST("/auth/register", h.Register)
	api.POST("/auth/login", h.Login)
	api.POST("/auth/refresh", h.Refresh)

	protected := api.Group("")
	protected.Use(AuthMiddleware(h.authenticator))
	protected.GET("/me", h.Me)
}

func (h Handler) Captcha(c *gin.Context) {
	if h.captchaStore == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "captcha_unavailable", "message": "图形验证码暂不可用"})
		return
	}

	challenge, err := h.captchaStore.NewChallenge()
	if err != nil {
		writeAuthError(c, err)
		return
	}

	c.JSON(http.StatusOK, challenge)
}

func (h Handler) SendRegisterEmailCode(c *gin.Context) {
	if h.emailVerification == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "email_verification_unavailable", "message": "邮箱验证码暂不可用"})
		return
	}

	var request sendRegisterEmailCodeRequest
	if !bindJSON(c, &request) {
		return
	}

	if !h.verifyCaptcha(request.CaptchaID, request.CaptchaAnswer) {
		writeAuthError(c, ErrInvalidCaptcha)
		return
	}

	response, err := h.emailVerification.RequestCode(c.Request.Context(), request.Email)
	if err != nil {
		writeAuthError(c, err)
		return
	}

	c.JSON(http.StatusOK, response)
}

func (h Handler) Register(c *gin.Context) {
	var request registerRequest
	if !bindJSON(c, &request) {
		return
	}

	if h.emailVerification != nil {
		if err := h.emailVerification.Verify(request.Email, request.EmailVerificationCode); err != nil {
			writeAuthError(c, err)
			return
		}
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

	if h.onUserRegistered != nil {
		if hookErr := h.onUserRegistered(c.Request.Context(), response.User.ID); hookErr != nil {
			writeAuthError(c, hookErr)
			return
		}
	}

	c.JSON(http.StatusCreated, response)
}

func (h Handler) Login(c *gin.Context) {
	var request loginRequest
	if !bindJSON(c, &request) {
		return
	}

	if !h.verifyCaptcha(request.CaptchaID, request.CaptchaAnswer) {
		writeAuthError(c, ErrInvalidCaptcha)
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

func (h Handler) verifyCaptcha(id string, answer string) bool {
	if h.captchaStore == nil {
		return true
	}
	return h.captchaStore.Verify(id, answer)
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
	case errors.Is(err, ErrInvalidCaptcha):
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_captcha", "message": "图形验证码不正确或已过期"})
	case errors.Is(err, ErrInvalidEmailCode):
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_email_verification_code", "message": "邮箱验证码不正确或已过期"})
	case errors.Is(err, ErrEmailCodeSendFailed):
		c.JSON(http.StatusBadGateway, gin.H{"error": "email_verification_send_failed", "message": "邮箱验证码发送失败，请稍后重试"})
	default:
		if cooldown, ok := IsEmailCodeCooldown(err); ok {
			c.JSON(http.StatusTooManyRequests, gin.H{
				"error":               "email_verification_cooldown",
				"message":             "邮箱验证码发送过于频繁，请稍后再试",
				"retry_after_seconds": secondsCeil(cooldown.RetryAfter),
			})
			return
		}
		if strings.TrimSpace(err.Error()) == "" {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
	}
}
