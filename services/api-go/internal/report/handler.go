package report

import (
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"

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
	reports := api.Group("/reports")
	reports.Use(auth.AuthMiddleware(authenticator))
	reports.GET("", h.ListReports)
	reports.GET("/feedback/export", auth.RequireRoles("operator", "admin"), h.ExportReportFeedback)
	reports.POST("/:report_id/feedback", h.SubmitReportFeedback)

	group := api.Group("/sessions/:id/report")
	group.Use(auth.AuthMiddleware(authenticator))
	group.GET("", h.GetLatestReport)
	group.POST("", h.SaveReport)
}

func (h Handler) ListReports(c *gin.Context) {
	filter, err := parseReportHistoryFilter(c)
	if err != nil {
		writeError(c, err)
		return
	}
	items, err := h.store.ListReports(c.Request.Context(), auth.CurrentUserID(c), filter)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"reports": items,
		"pagination": gin.H{
			"limit":  filter.Limit,
			"offset": filter.Offset,
		},
	})
}

func (h Handler) SubmitReportFeedback(c *gin.Context) {
	var request SubmitReportFeedbackInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.SubmitReportFeedback(c.Request.Context(), auth.CurrentUserID(c), c.Param("report_id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"feedback": item})
}

func (h Handler) ExportReportFeedback(c *gin.Context) {
	filter, err := parseReportFeedbackFilter(c)
	if err != nil {
		writeError(c, err)
		return
	}
	items, err := h.store.ListReportFeedback(c.Request.Context(), filter)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"feedback": items,
		"pagination": gin.H{
			"limit":  filter.Limit,
			"offset": filter.Offset,
		},
	})
}

func (h Handler) GetLatestReport(c *gin.Context) {
	item, err := h.store.GetLatestReport(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"report": item})
}

func (h Handler) SaveReport(c *gin.Context) {
	var request SaveReportInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.SaveReport(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"report": item})
}

func bind(c *gin.Context, target any) bool {
	if err := c.ShouldBindJSON(target); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_request", "message": "请求体格式或字段不合法"})
		return false
	}
	return true
}

func parseReportHistoryFilter(c *gin.Context) (ReportHistoryFilter, error) {
	mode := strings.TrimSpace(c.Query("mode"))
	if mode != "" && mode != "full_exam" && mode != "part_practice" && mode != "topic_practice" {
		return ReportHistoryFilter{}, ErrInvalidInput
	}

	var part *int
	if rawPart := strings.TrimSpace(c.Query("part")); rawPart != "" {
		parsed, err := strconv.Atoi(rawPart)
		if err != nil || parsed < 1 || parsed > 3 {
			return ReportHistoryFilter{}, ErrInvalidInput
		}
		part = &parsed
	}

	from, err := dateQuery(c, "from")
	if err != nil {
		return ReportHistoryFilter{}, err
	}
	to, err := dateQuery(c, "to")
	if err != nil {
		return ReportHistoryFilter{}, err
	}
	if to != nil {
		toExclusive := to.Add(24 * time.Hour)
		to = &toExclusive
	}
	if from != nil && to != nil && !from.Before(*to) {
		return ReportHistoryFilter{}, ErrInvalidInput
	}

	limit, err := boundedIntQuery(c, "limit", 30, 1, 100)
	if err != nil {
		return ReportHistoryFilter{}, err
	}
	offset, err := boundedIntQuery(c, "offset", 0, 0, 10000)
	if err != nil {
		return ReportHistoryFilter{}, err
	}

	return ReportHistoryFilter{
		Mode:   mode,
		Part:   part,
		From:   from,
		To:     to,
		Limit:  limit,
		Offset: offset,
	}, nil
}

func parseReportFeedbackFilter(c *gin.Context) (ReportFeedbackFilter, error) {
	targetType := strings.TrimSpace(c.Query("target_type"))
	if targetType != "" && !isKnownFeedbackTargetType(targetType) {
		return ReportFeedbackFilter{}, ErrInvalidInput
	}

	vote := strings.TrimSpace(c.Query("vote"))
	if vote != "" && vote != "up" && vote != "down" {
		return ReportFeedbackFilter{}, ErrInvalidInput
	}

	limit, err := boundedIntQuery(c, "limit", 100, 1, 500)
	if err != nil {
		return ReportFeedbackFilter{}, err
	}
	offset, err := boundedIntQuery(c, "offset", 0, 0, 10000)
	if err != nil {
		return ReportFeedbackFilter{}, err
	}

	return ReportFeedbackFilter{
		ReportID:   strings.TrimSpace(c.Query("report_id")),
		SessionID:  strings.TrimSpace(c.Query("session_id")),
		TargetType: targetType,
		Vote:       vote,
		Limit:      limit,
		Offset:     offset,
	}, nil
}

func dateQuery(c *gin.Context, key string) (*time.Time, error) {
	value := strings.TrimSpace(c.Query(key))
	if value == "" {
		return nil, nil
	}
	parsed, err := time.Parse("2006-01-02", value)
	if err != nil {
		return nil, ErrInvalidInput
	}
	return &parsed, nil
}

func boundedIntQuery(c *gin.Context, key string, fallback int, minValue int, maxValue int) (int, error) {
	value := strings.TrimSpace(c.Query(key))
	if value == "" {
		return fallback, nil
	}
	parsed, err := strconv.Atoi(value)
	if err != nil || parsed < minValue || parsed > maxValue {
		return 0, ErrInvalidInput
	}
	return parsed, nil
}

func writeError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, ErrNotFound):
		c.JSON(http.StatusNotFound, gin.H{"error": "not_found", "message": "报告资源不存在"})
	case errors.Is(err, ErrInvalidInput):
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_report_input", "message": err.Error()})
	default:
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
	}
}
