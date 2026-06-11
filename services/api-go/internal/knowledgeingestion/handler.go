package knowledgeingestion

import (
	"errors"
	"io"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
)

type Handler struct {
	service  Service
	maxBytes int64
}

func NewHandler(service Service, maxBytes int64) Handler {
	if maxBytes <= 0 {
		maxBytes = defaultMaxUploadBytes
	}
	return Handler{service: service, maxBytes: maxBytes}
}

func (h Handler) RegisterRoutes(api *gin.RouterGroup, authenticator auth.Authenticator) {
	userGroup := api.Group("/knowledge")
	userGroup.Use(auth.AuthMiddleware(authenticator))
	userGroup.POST("/uploads", h.Upload)
	userGroup.GET("/uploads", h.ListUserJobs)
	userGroup.GET("/uploads/:jobId", h.GetUserJobDetail)
	userGroup.POST("/uploads/:jobId/confirm-background", h.ConfirmBackground)
	userGroup.POST("/uploads/:jobId/cancel", h.CancelJob)
	userGroup.POST("/uploads/:jobId/retry", h.RetryJob)
	userGroup.GET("/uploads/:jobId/artifacts/:artifactId/preview", h.PreviewArtifact)

	adminGroup := api.Group("/admin/knowledge")
	adminGroup.Use(auth.AuthMiddleware(authenticator), auth.RequireRoles("operator", "admin"))
	adminGroup.GET("/imports", h.ListAdminJobs)
	adminGroup.GET("/imports/:jobId", h.GetAdminJobDetail)
	adminGroup.POST("/imports/:jobId/review", h.ReviewJob)
	adminGroup.POST("/imports/:jobId/cancel", h.CancelJob)
	adminGroup.POST("/imports/:jobId/retry", h.RetryJob)
	adminGroup.GET("/imports/:jobId/stream", h.StreamJob)

	runtimeGroup := api.Group("/admin/agent-runtime")
	runtimeGroup.Use(auth.AuthMiddleware(authenticator), auth.RequireRoles("operator", "admin"))
	runtimeGroup.GET("/document-ingestion", h.GetRuntimePolicy)
	runtimeGroup.PUT("/document-ingestion", h.UpdateRuntimePolicy)
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

	reader, ok := file.(ReadSeekCloser)
	if !ok {
		writeError(c, ErrInvalidInput)
		return
	}

	detail, err := h.service.Upload(c.Request.Context(), CreateUploadInput{
		UserID:     auth.CurrentUserID(c),
		Visibility: c.PostForm("visibility"),
		Purpose:    c.PostForm("purpose"),
		Title:      c.PostForm("title"),
		FileName:   header.Filename,
		MimeType:   header.Header.Get("Content-Type"),
		SizeBytes:  header.Size,
		Content:    reader,
	})
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"job": detail})
}

func (h Handler) ListUserJobs(c *gin.Context) {
	items, err := h.service.ListUserJobs(c.Request.Context(), auth.CurrentUserID(c), UserJobFilter{
		Status: c.Query("status"),
		Limit:  intQuery(c.Query("limit"), 40),
		Offset: intQuery(c.Query("offset"), 0),
	})
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"jobs": items})
}

func (h Handler) GetUserJobDetail(c *gin.Context) {
	item, err := h.service.GetJobDetail(c.Request.Context(), auth.CurrentUserID(c), auth.CurrentRole(c), c.Param("jobId"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"job": item})
}

func (h Handler) ConfirmBackground(c *gin.Context) {
	var request ConfirmBackgroundInput
	if !bindJSON(c, &request) {
		return
	}
	item, err := h.service.ConfirmBackgroundCandidates(c.Request.Context(), auth.CurrentUserID(c), c.Param("jobId"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"job": item})
}

func (h Handler) PreviewArtifact(c *gin.Context) {
	preview, err := h.service.PreviewArtifact(c.Request.Context(), auth.CurrentUserID(c), auth.CurrentRole(c), c.Param("jobId"), c.Param("artifactId"), requestPublicHostname(c.Request))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, preview)
}

func (h Handler) ListAdminJobs(c *gin.Context) {
	items, err := h.service.ListAdminJobs(c.Request.Context(), AdminJobFilter{
		Status:      c.Query("status"),
		Visibility:  c.Query("visibility"),
		OwnerUserID: c.Query("owner_user_id"),
		Limit:       intQuery(c.Query("limit"), 80),
		Offset:      intQuery(c.Query("offset"), 0),
	})
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"jobs": items})
}

func (h Handler) GetAdminJobDetail(c *gin.Context) {
	item, err := h.service.GetJobDetail(c.Request.Context(), auth.CurrentUserID(c), auth.CurrentRole(c), c.Param("jobId"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"job": item})
}

func (h Handler) ReviewJob(c *gin.Context) {
	var request AdminReviewInput
	if !bindJSON(c, &request) {
		return
	}
	item, err := h.service.ReviewJob(c.Request.Context(), auth.CurrentUserID(c), auth.CurrentRole(c), c.Param("jobId"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"job": item})
}

func (h Handler) CancelJob(c *gin.Context) {
	item, err := h.service.CancelJob(c.Request.Context(), auth.CurrentUserID(c), auth.CurrentRole(c), c.Param("jobId"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"job": item})
}

func (h Handler) RetryJob(c *gin.Context) {
	item, err := h.service.RetryJob(c.Request.Context(), auth.CurrentUserID(c), auth.CurrentRole(c), c.Param("jobId"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"job": item})
}

func (h Handler) StreamJob(c *gin.Context) {
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()
	c.Stream(func(w io.Writer) bool {
		item, err := h.service.GetJobDetail(c.Request.Context(), auth.CurrentUserID(c), auth.CurrentRole(c), c.Param("jobId"))
		if err != nil {
			c.SSEvent("error", gin.H{"message": "知识导入任务读取失败"})
			return false
		}
		payload := map[string]any{
			"job":       item,
			"run":       item.Run,
			"artifacts": item.Artifacts,
		}
		c.SSEvent("snapshot", payload)
		if isSettledJobStatus(item.Status) {
			c.SSEvent("done", map[string]any{"job_id": item.ID, "status": item.Status})
			return false
		}
		select {
		case <-c.Request.Context().Done():
			return false
		case <-ticker.C:
			return true
		}
	})
}

func (h Handler) GetRuntimePolicy(c *gin.Context) {
	policy, err := h.service.GetRuntimePolicy(c.Request.Context())
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"policy": policy})
}

func (h Handler) UpdateRuntimePolicy(c *gin.Context) {
	var request RuntimePolicyUpdateInput
	if !bindJSON(c, &request) {
		return
	}
	policy, err := h.service.UpdateRuntimePolicy(c.Request.Context(), auth.CurrentUserID(c), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"policy": policy})
}

func bindJSON(c *gin.Context, target any) bool {
	if err := c.ShouldBindJSON(target); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_request", "message": "请求体格式或字段不合法"})
		return false
	}
	return true
}

func writeError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, ErrNotFound):
		c.JSON(http.StatusNotFound, gin.H{"error": "knowledge_ingestion_not_found", "message": "知识导入任务不存在"})
	case errors.Is(err, ErrInvalidInput):
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_knowledge_ingestion_input", "message": "知识导入参数不合法"})
	case errors.Is(err, ErrForbidden):
		c.JSON(http.StatusForbidden, gin.H{"error": "knowledge_ingestion_forbidden", "message": "没有权限访问该知识导入任务"})
	case errors.Is(err, ErrConflict):
		c.JSON(http.StatusConflict, gin.H{"error": "knowledge_ingestion_conflict", "message": "当前知识导入状态不允许执行此操作"})
	case errors.Is(err, ErrUnsupportedType):
		c.JSON(http.StatusUnsupportedMediaType, gin.H{"error": "knowledge_ingestion_unsupported_type", "message": "暂不支持该文档格式"})
	case errors.Is(err, ErrFileTooLarge):
		c.JSON(http.StatusRequestEntityTooLarge, gin.H{"error": "knowledge_ingestion_file_too_large", "message": "上传文档超过大小限制"})
	case errors.Is(err, ErrStorageUnavailable):
		c.JSON(http.StatusBadGateway, gin.H{"error": "knowledge_ingestion_storage_unavailable", "message": "对象存储暂时不可用"})
	case errors.Is(err, ErrProcessingPending):
		c.JSON(http.StatusAccepted, gin.H{"error": "knowledge_ingestion_processing_pending", "message": "任务仍在处理中"})
	default:
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
	}
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

func isSettledJobStatus(status string) bool {
	switch status {
	case JobStatusAwaitingReview, JobStatusAwaitingUserConfirm, JobStatusCompleted, JobStatusFailed, JobStatusCancelled, JobStatusRejected:
		return true
	default:
		return false
	}
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
	if normalized == "localhost" || normalized == "127.0.0.1" || normalized == "::1" {
		return true
	}
	if normalized == "minio" {
		return true
	}
	return !strings.Contains(normalized, ".") && net.ParseIP(normalized) == nil
}
