package adminops

import (
	"errors"
	"net/http"
	"strconv"

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
	knowledge := api.Group("/admin/knowledge")
	knowledge.Use(auth.AuthMiddleware(authenticator), h.auditAdminAction("knowledge_base"), auth.RequireRoles("operator", "admin"))
	knowledge.GET("/docs", h.ListKnowledgeDocs)
	knowledge.POST("/docs", h.CreateKnowledgeDoc)
	knowledge.PUT("/docs/:id", h.UpdateKnowledgeDoc)
	knowledge.POST("/docs/:id/reindex", h.ReindexKnowledgeDoc)
	knowledge.DELETE("/docs/:id", h.ArchiveKnowledgeDoc)

	prompts := api.Group("/admin/prompts")
	prompts.Use(auth.AuthMiddleware(authenticator), h.auditAdminAction("prompt_versions"), auth.RequireRoles("operator", "admin"))
	prompts.GET("/versions", h.ListPromptVersions)

	review := api.Group("/admin/content-review")
	review.Use(auth.AuthMiddleware(authenticator), h.auditAdminAction("content_review"), auth.RequireRoles("operator", "admin"))
	review.GET("/summary", h.ContentReviewSummary)
	review.GET("/reference-answers", h.ListReferenceAnswers)
	review.PUT("/reference-answers/:id/status", h.UpdateReferenceAnswerStatus)
}

func (h Handler) auditAdminAction(resource string) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Next()

		route := c.FullPath()
		if route == "" {
			route = c.Request.URL.Path
		}
		statusCode := c.Writer.Status()
		if statusCode == 0 {
			statusCode = http.StatusOK
		}
		_ = h.store.RecordAdminAudit(c.Request.Context(), AdminAuditInput{
			ActorUserID: auth.CurrentUserID(c),
			ActorRole:   auth.CurrentRole(c),
			Action:      c.Request.Method + " " + route,
			Resource:    resource,
			Method:      c.Request.Method,
			Path:        route,
			StatusCode:  statusCode,
			Metadata: map[string]any{
				"request_path": c.Request.URL.Path,
				"route":        route,
			},
		})
	}
}

func (h Handler) CreateKnowledgeDoc(c *gin.Context) {
	var request KnowledgeDocInput
	if !bind(c, &request) {
		return
	}
	doc, err := h.store.CreateKnowledgeDoc(c.Request.Context(), request, auth.CurrentUserID(c))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"doc": doc})
}

func (h Handler) ListKnowledgeDocs(c *gin.Context) {
	docs, err := h.store.ListKnowledgeDocs(c.Request.Context(), KnowledgeDocFilter{
		DocType: c.Query("doc_type"),
		Status:  c.Query("status"),
		Limit:   intQuery(c, "limit", 80),
		Offset:  intQuery(c, "offset", 0),
	})
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"docs": docs})
}

func (h Handler) UpdateKnowledgeDoc(c *gin.Context) {
	var request KnowledgeDocUpdateInput
	if !bind(c, &request) {
		return
	}
	doc, err := h.store.UpdateKnowledgeDoc(c.Request.Context(), c.Param("id"), request, auth.CurrentUserID(c))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"doc": doc})
}

func (h Handler) ReindexKnowledgeDoc(c *gin.Context) {
	doc, err := h.store.ReindexKnowledgeDoc(c.Request.Context(), c.Param("id"), auth.CurrentUserID(c))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"doc": doc})
}

func (h Handler) ArchiveKnowledgeDoc(c *gin.Context) {
	if err := h.store.ArchiveKnowledgeDoc(c.Request.Context(), c.Param("id")); err != nil {
		writeError(c, err)
		return
	}
	c.Status(http.StatusNoContent)
}

func (h Handler) ListPromptVersions(c *gin.Context) {
	filter := PromptVersionFilter{
		AgentName: c.Query("agent_name"),
		Purpose:   c.Query("purpose"),
		Limit:     intQuery(c, "limit", 80),
		Offset:    intQuery(c, "offset", 0),
	}
	if value := c.Query("active"); value != "" {
		active := value == "true" || value == "1"
		filter.Active = &active
	}
	versions, err := h.store.ListPromptVersions(c.Request.Context(), filter)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"versions": versions})
}

func (h Handler) ContentReviewSummary(c *gin.Context) {
	items, err := h.store.ContentReviewSummary(c.Request.Context())
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"summary": items})
}

func (h Handler) ListReferenceAnswers(c *gin.Context) {
	items, err := h.store.ListReferenceAnswers(c.Request.Context(), ReferenceAnswerFilter{
		Status: c.Query("status"),
		Limit:  intQuery(c, "limit", 60),
		Offset: intQuery(c, "offset", 0),
	})
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"reference_answers": items})
}

func (h Handler) UpdateReferenceAnswerStatus(c *gin.Context) {
	var request StatusUpdateInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.UpdateReferenceAnswerStatus(c.Request.Context(), c.Param("id"), request.Status)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"reference_answer": item})
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

func writeError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, ErrNotFound):
		c.JSON(http.StatusNotFound, gin.H{"error": "not_found", "message": "运营内容资源不存在"})
	case errors.Is(err, ErrInvalidInput):
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_admin_content_input", "message": err.Error()})
	default:
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
	}
}
