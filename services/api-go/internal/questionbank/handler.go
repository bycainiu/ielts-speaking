package questionbank

import (
	"context"
	"errors"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
)

type Handler struct {
	store      Store
	auditStore AdminAuditStore
}

type AdminAuditStore interface {
	RecordAdminAudit(ctx context.Context, input AdminAuditInput) error
}

type noopAdminAuditStore struct{}

func (noopAdminAuditStore) RecordAdminAudit(context.Context, AdminAuditInput) error {
	return nil
}

func NewHandler(store Store, auditStores ...AdminAuditStore) Handler {
	auditStore := AdminAuditStore(noopAdminAuditStore{})
	if len(auditStores) > 0 && auditStores[0] != nil {
		auditStore = auditStores[0]
	}
	return Handler{store: store, auditStore: auditStore}
}

func (h Handler) RegisterRoutes(api *gin.RouterGroup, authenticator auth.Authenticator) {
	api.GET("/seasons/active", h.GetActiveSeason)
	api.GET("/topics", h.ListPublicTopics)
	api.GET("/questions", h.ListPublicQuestions)
	api.GET("/questions/:id", h.GetPublicQuestion)

	admin := api.Group("/admin/question-bank")
	admin.Use(auth.AuthMiddleware(authenticator), h.auditAdminAction("question_bank"), auth.RequireRoles("operator", "admin"))
	admin.POST("/seasons", h.CreateSeason)
	admin.GET("/seasons", h.ListAdminSeasons)
	admin.PUT("/seasons/:id", h.UpdateSeason)
	admin.POST("/seasons/:id/activate", h.ActivateSeason)
	admin.DELETE("/seasons/:id", h.ArchiveSeason)

	admin.POST("/topics", h.CreateTopic)
	admin.GET("/topics", h.ListAdminTopics)
	admin.PUT("/topics/:id", h.UpdateTopic)
	admin.DELETE("/topics/:id", h.ArchiveTopic)

	admin.POST("/questions", h.CreateQuestion)
	admin.GET("/questions", h.ListAdminQuestions)
	admin.GET("/questions/:id", h.GetAdminQuestion)
	admin.PUT("/questions/:id", h.UpdateQuestion)
	admin.DELETE("/questions/:id", h.ArchiveQuestion)
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
		_ = h.auditStore.RecordAdminAudit(c.Request.Context(), AdminAuditInput{
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

func (h Handler) GetActiveSeason(c *gin.Context) {
	season, err := h.store.GetActiveSeason(c.Request.Context())
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"season": season})
}

func (h Handler) ListPublicTopics(c *gin.Context) {
	topics, err := h.store.ListTopics(c.Request.Context(), false)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"topics": topics})
}

func (h Handler) ListPublicQuestions(c *gin.Context) {
	questions, err := h.store.ListQuestions(c.Request.Context(), parseQuestionFilter(c, false))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"questions": questions})
}

func (h Handler) GetPublicQuestion(c *gin.Context) {
	question, err := h.store.GetQuestion(c.Request.Context(), c.Param("id"))
	if err != nil {
		writeError(c, err)
		return
	}
	if question.ReviewStatus != StatusActive {
		writeError(c, ErrNotFound)
		return
	}
	c.JSON(http.StatusOK, gin.H{"question": question})
}

func (h Handler) CreateSeason(c *gin.Context) {
	var request SeasonInput
	if !bind(c, &request) {
		return
	}
	season, err := h.store.CreateSeason(c.Request.Context(), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"season": season})
}

func (h Handler) ListAdminSeasons(c *gin.Context) {
	seasons, err := h.store.ListSeasons(c.Request.Context(), true)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"seasons": seasons})
}

func (h Handler) UpdateSeason(c *gin.Context) {
	var request SeasonInput
	if !bind(c, &request) {
		return
	}
	season, err := h.store.UpdateSeason(c.Request.Context(), c.Param("id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"season": season})
}

func (h Handler) ActivateSeason(c *gin.Context) {
	season, err := h.store.ActivateSeason(c.Request.Context(), c.Param("id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"season": season})
}

func (h Handler) ArchiveSeason(c *gin.Context) {
	if err := h.store.ArchiveSeason(c.Request.Context(), c.Param("id")); err != nil {
		writeError(c, err)
		return
	}
	c.Status(http.StatusNoContent)
}

func (h Handler) CreateTopic(c *gin.Context) {
	var request TopicInput
	if !bind(c, &request) {
		return
	}
	topic, err := h.store.CreateTopic(c.Request.Context(), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"topic": topic})
}

func (h Handler) ListAdminTopics(c *gin.Context) {
	topics, err := h.store.ListTopics(c.Request.Context(), true)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"topics": topics})
}

func (h Handler) UpdateTopic(c *gin.Context) {
	var request TopicInput
	if !bind(c, &request) {
		return
	}
	topic, err := h.store.UpdateTopic(c.Request.Context(), c.Param("id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"topic": topic})
}

func (h Handler) ArchiveTopic(c *gin.Context) {
	if err := h.store.ArchiveTopic(c.Request.Context(), c.Param("id")); err != nil {
		writeError(c, err)
		return
	}
	c.Status(http.StatusNoContent)
}

func (h Handler) CreateQuestion(c *gin.Context) {
	var request QuestionInput
	if !bind(c, &request) {
		return
	}
	question, err := h.store.CreateQuestion(c.Request.Context(), request, auth.CurrentUserID(c))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"question": question})
}

func (h Handler) ListAdminQuestions(c *gin.Context) {
	questions, err := h.store.ListQuestions(c.Request.Context(), parseQuestionFilter(c, true))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"questions": questions})
}

func (h Handler) GetAdminQuestion(c *gin.Context) {
	question, err := h.store.GetQuestion(c.Request.Context(), c.Param("id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"question": question})
}

func (h Handler) UpdateQuestion(c *gin.Context) {
	var request QuestionInput
	if !bind(c, &request) {
		return
	}
	question, err := h.store.UpdateQuestion(c.Request.Context(), c.Param("id"), request, auth.CurrentUserID(c))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"question": question})
}

func (h Handler) ArchiveQuestion(c *gin.Context) {
	if err := h.store.ArchiveQuestion(c.Request.Context(), c.Param("id")); err != nil {
		writeError(c, err)
		return
	}
	c.Status(http.StatusNoContent)
}

func bind(c *gin.Context, target any) bool {
	if err := c.ShouldBindJSON(target); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_request", "message": "请求体格式或字段不合法"})
		return false
	}
	return true
}

func parseQuestionFilter(c *gin.Context, includeDraft bool) QuestionFilter {
	filter := QuestionFilter{
		SeasonID:     c.Query("season_id"),
		TopicID:      c.Query("topic_id"),
		ReviewStatus: c.Query("review_status"),
		IncludeDraft: includeDraft,
		Limit:        intQuery(c, "limit", 50),
		Offset:       intQuery(c, "offset", 0),
	}

	if value := c.Query("part"); value != "" {
		part, err := strconv.Atoi(value)
		if err == nil {
			filter.Part = &part
		}
	}

	return filter
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
		c.JSON(http.StatusNotFound, gin.H{"error": "not_found", "message": "题库资源不存在"})
	case errors.Is(err, ErrDuplicateResource):
		c.JSON(http.StatusConflict, gin.H{"error": "duplicate_resource", "message": "题库资源已存在"})
	case errors.Is(err, ErrInvalidInput):
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_question_bank_input", "message": err.Error()})
	default:
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
	}
}
