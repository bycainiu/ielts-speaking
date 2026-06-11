package audio

import (
	"errors"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
)

type Handler struct {
	service  Service
	maxBytes int64
}

func NewHandler(service Service, maxBytes int64) Handler {
	if maxBytes == 0 {
		maxBytes = DefaultMaxUploadBytes
	}
	return Handler{service: service, maxBytes: maxBytes}
}

func (h Handler) RegisterRoutes(api *gin.RouterGroup, authenticator auth.Authenticator) {
	group := api.Group("/audio")
	group.Use(auth.AuthMiddleware(authenticator))
	group.POST("/upload", h.Upload)
	group.POST("/tts", h.SynthesizeTTS)
	group.DELETE("/tts/cache/expired", h.CleanupExpiredTTSCache)
	group.GET("/:id/signed-url", h.SignedURL)
}

func (h Handler) Upload(c *gin.Context) {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, h.maxBytes+1024*1024)
	file, header, err := c.Request.FormFile("file")
	if err != nil {
		var maxBytesError *http.MaxBytesError
		if errors.As(err, &maxBytesError) {
			writeError(c, ErrFileTooLarge)
			return
		}
		writeError(c, ErrInvalidInput)
		return
	}
	defer file.Close()

	durationMS, ok := requiredPositiveInt(c.PostForm("duration_ms"))
	if !ok {
		writeError(c, ErrInvalidInput)
		return
	}

	result, err := h.service.Upload(c.Request.Context(), UploadInput{
		UserID:     auth.CurrentUserID(c),
		SessionID:  c.PostForm("session_id"),
		TurnID:     c.PostForm("turn_id"),
		Kind:       c.PostForm("kind"),
		FileName:   header.Filename,
		MimeType:   header.Header.Get("Content-Type"),
		SizeBytes:  header.Size,
		DurationMS: durationMS,
		Content:    file,
	})
	if err != nil {
		writeError(c, err)
		return
	}

	c.JSON(http.StatusCreated, result)
}

func (h Handler) SynthesizeTTS(c *gin.Context) {
	var request SynthesizeTTSInput
	if !bindJSON(c, &request) {
		return
	}
	request.UserID = auth.CurrentUserID(c)

	result, err := h.service.SynthesizeTTS(c.Request.Context(), request)
	if err != nil {
		writeError(c, err)
		return
	}

	c.JSON(http.StatusCreated, result)
}

func (h Handler) CleanupExpiredTTSCache(c *gin.Context) {
	result, err := h.service.CleanupExpiredTTSCache(c.Request.Context())
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, result)
}

func (h Handler) SignedURL(c *gin.Context) {
	expires := intQuery(c.Query("expires_seconds"), DefaultSignedURLSeconds)
	result, err := h.service.SignedURL(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"), expires, requestPublicHostname(c.Request))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, result)
}

func requestPublicHostname(r *http.Request) string {
	for _, candidate := range playbackHostCandidates(r) {
		hostname, err := hostnameFromValue(candidate)
		if err == nil && hostname != "" {
			return hostname
		}
	}
	return ""
}

func playbackHostCandidates(r *http.Request) []string {
	candidates := make([]string, 0, 6)
	candidates = appendHostHeaderValues(candidates, r.Header.Get("X-Forwarded-Host"))
	candidates = appendHostHeaderValues(candidates, r.Header.Get("X-Original-Host"))
	candidates = appendForwardedHeaderHosts(candidates, r.Header.Get("Forwarded"))
	if origin := strings.TrimSpace(r.Header.Get("Origin")); origin != "" {
		candidates = append(candidates, origin)
	}
	candidates = appendHostHeaderValues(candidates, r.Host)
	return candidates
}

func appendHostHeaderValues(items []string, value string) []string {
	for _, part := range strings.Split(value, ",") {
		host := strings.TrimSpace(part)
		if host != "" {
			items = append(items, host)
		}
	}
	return items
}

func appendForwardedHeaderHosts(items []string, value string) []string {
	for _, forwarded := range strings.Split(value, ",") {
		for _, segment := range strings.Split(forwarded, ";") {
			key, rawValue, ok := strings.Cut(strings.TrimSpace(segment), "=")
			if !ok || !strings.EqualFold(strings.TrimSpace(key), "host") {
				continue
			}
			host := strings.Trim(strings.TrimSpace(rawValue), `"`)
			if host != "" {
				items = append(items, host)
			}
		}
	}
	return items
}

func hostnameFromValue(value string) (string, error) {
	normalized := strings.TrimSpace(value)
	if normalized == "" {
		return "", nil
	}
	if !strings.Contains(normalized, "://") {
		normalized = "http://" + normalized
	}
	parsed, err := url.Parse(normalized)
	if err != nil {
		return "", err
	}
	hostname := strings.TrimSpace(parsed.Hostname())
	if hostname == "" {
		return "", nil
	}
	return strings.Trim(strings.ToLower(hostname), "[]"), nil
}

func shouldRewritePlaybackHost(hostname string) bool {
	normalized := strings.Trim(strings.ToLower(strings.TrimSpace(hostname)), "[]")
	if normalized == "" {
		return false
	}
	if isLoopbackHostname(normalized) {
		return true
	}
	if normalized == "minio" {
		return true
	}
	return !strings.Contains(normalized, ".") && net.ParseIP(normalized) == nil
}

func isLoopbackHostname(hostname string) bool {
	return hostname == "localhost" || hostname == "127.0.0.1" || hostname == "::1"
}

func requiredPositiveInt(value string) (*int, bool) {
	if value == "" {
		return nil, false
	}
	parsed, err := strconv.Atoi(value)
	if err != nil || parsed <= 0 {
		return nil, false
	}
	return &parsed, true
}

func bindJSON(c *gin.Context, target any) bool {
	if err := c.ShouldBindJSON(target); err != nil {
		writeError(c, ErrInvalidInput)
		return false
	}
	return true
}

func intQuery(value string, fallback int) int {
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func writeError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, ErrNotFound):
		c.JSON(http.StatusNotFound, gin.H{"error": "audio_asset_not_found", "message": "音频资产不存在"})
	case errors.Is(err, ErrInvalidInput):
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_audio_input", "message": "音频上传参数不合法"})
	case errors.Is(err, ErrFileTooLarge):
		c.JSON(http.StatusRequestEntityTooLarge, gin.H{"error": "audio_file_too_large", "message": "音频文件过大"})
	case errors.Is(err, ErrDurationTooLong):
		c.JSON(http.StatusBadRequest, gin.H{"error": "audio_duration_too_long", "message": "音频时长超过限制"})
	case errors.Is(err, ErrUnsupportedType):
		c.JSON(http.StatusUnsupportedMediaType, gin.H{"error": "unsupported_audio_type", "message": "不支持的音频文件类型"})
	case errors.Is(err, ErrDuplicateAsset):
		c.JSON(http.StatusConflict, gin.H{"error": "duplicate_audio_asset", "message": "音频资产已存在"})
	case errors.Is(err, ErrStorageUnavailable):
		c.JSON(http.StatusBadGateway, gin.H{"error": "audio_storage_unavailable", "message": "音频存储暂时不可用"})
	case errors.Is(err, ErrConsentRequired):
		c.JSON(http.StatusForbidden, gin.H{"error": "recording_consent_required", "message": "请先授权录音与 AI 处理用途"})
	case errors.Is(err, ErrVoiceCloneDisabled):
		c.JSON(http.StatusForbidden, gin.H{"error": "voice_clone_disabled", "message": "当前未启用授权声音复刻"})
	default:
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
	}
}
