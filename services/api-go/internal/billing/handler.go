package billing

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

type Handler struct {
	store Store
}

func NewHandler(store Store) Handler {
	return Handler{store: store}
}

func (h Handler) RegisterRoutes(api *gin.RouterGroup, authenticator auth.Authenticator) {
	api.GET("/billing/plans", h.ListPublicPlans)

	billing := api.Group("/billing")
	billing.Use(auth.AuthMiddleware(authenticator))
	billing.GET("/subscription", h.GetSubscription)
	billing.GET("/orders", h.ListOrders)
	billing.POST("/checkout", h.CreateCheckout)
	billing.POST("/checkout/:id/confirm", h.ConfirmCheckout)
	billing.POST("/checkout/:id/cancel", h.CancelCheckout)

	adminPlans := api.Group("/admin/subscription-plans")
	adminPlans.Use(auth.AuthMiddleware(authenticator), auth.RequireRoles("operator", "admin"))
	adminPlans.GET("", h.ListAllPlans)
	adminPlans.POST("", h.CreatePlan)
	adminPlans.PATCH("/:id", h.UpdatePlan)

	adminUsers := api.Group("/admin/users")
	adminUsers.Use(auth.AuthMiddleware(authenticator), auth.RequireRoles("operator", "admin"))
	adminUsers.GET("", h.ListAdminUsers)
	adminUsers.GET("/:id", h.GetAdminUser)
	adminUsers.PATCH("/:id", h.PatchAdminUser)

	adminStats := api.Group("/admin/subscription-stats")
	adminStats.Use(auth.AuthMiddleware(authenticator), auth.RequireRoles("operator", "admin"))
	adminStats.GET("", h.GetSubscriptionStats)
}

func (h Handler) ListPublicPlans(c *gin.Context) {
	items, err := h.store.ListActivePlans(c.Request.Context())
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"plans": items})
}

func (h Handler) ListAllPlans(c *gin.Context) {
	items, err := h.store.ListAllPlans(c.Request.Context())
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"plans": items})
}

func (h Handler) CreatePlan(c *gin.Context) {
	var request PlanInput
	if !bind(c, &request) {
		return
	}
	item, err := h.store.CreatePlan(c.Request.Context(), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusCreated, gin.H{"plan": item})
}

func (h Handler) UpdatePlan(c *gin.Context) {
	var request PlanPatch
	if !bind(c, &request) {
		return
	}
	item, err := h.store.UpdatePlan(c.Request.Context(), c.Param("id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"plan": item})
}

func (h Handler) GetSubscription(c *gin.Context) {
	item, err := h.store.GetUserSubscriptionSummary(c.Request.Context(), auth.CurrentUserID(c))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"subscription": item})
}

func (h Handler) ListOrders(c *gin.Context) {
	items, err := h.store.ListOrders(c.Request.Context(), auth.CurrentUserID(c), intQuery(c, "limit", 20))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"orders": items})
}

func (h Handler) CreateCheckout(c *gin.Context) {
	var request CheckoutInput
	if !bind(c, &request) {
		return
	}
	plan, err := h.store.GetPlanBySlug(c.Request.Context(), request.PlanSlug)
	if err != nil {
		writeError(c, err)
		return
	}
	order, err := h.store.CreateOrder(c.Request.Context(), auth.CurrentUserID(c), plan.ID)
	if err != nil {
		writeError(c, err)
		return
	}
	order.Plan = &plan
	c.JSON(http.StatusCreated, gin.H{"order": order})
}

func (h Handler) ConfirmCheckout(c *gin.Context) {
	var request ConfirmCheckoutInput
	if !bind(c, &request) {
		return
	}
	method := strings.TrimSpace(request.PaymentMethod)
	if method == "" {
		method = "card"
	}
	order, err := h.store.ConfirmOrder(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"), method)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"order": order})
}

func (h Handler) CancelCheckout(c *gin.Context) {
	order, err := h.store.CancelOrder(c.Request.Context(), auth.CurrentUserID(c), c.Param("id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"order": order})
}

func (h Handler) ListAdminUsers(c *gin.Context) {
	items, err := h.store.ListAdminUsers(c.Request.Context(), AdminUserFilter{
		Query:    c.Query("q"),
		Role:     c.Query("role"),
		Status:   c.Query("status"),
		PlanSlug: c.Query("plan"),
		Limit:    intQuery(c, "limit", 50),
		Offset:   intQuery(c, "offset", 0),
	})
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"users": items,
		"pagination": gin.H{
			"limit":  intQuery(c, "limit", 50),
			"offset": intQuery(c, "offset", 0),
		},
	})
}

func (h Handler) GetAdminUser(c *gin.Context) {
	item, err := h.store.GetAdminUserDetail(c.Request.Context(), c.Param("id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, item)
}

func (h Handler) PatchAdminUser(c *gin.Context) {
	var request AdminUserPatch
	if !bind(c, &request) {
		return
	}
	item, err := h.store.UpdateAdminUser(c.Request.Context(), c.Param("id"), request)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"user": item})
}

func (h Handler) GetSubscriptionStats(c *gin.Context) {
	item, err := h.store.GetSubscriptionStats(c.Request.Context())
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, item)
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
		c.JSON(http.StatusNotFound, gin.H{"error": "not_found", "message": "资源不存在"})
	case errors.Is(err, ErrInvalidInput):
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_input", "message": "参数不合法"})
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
	case errors.Is(err, ErrOrderNotPending):
		c.JSON(http.StatusConflict, gin.H{"error": "order_not_pending", "message": "订单状态不允许该操作"})
	case errors.Is(err, ErrPlanInactive):
		c.JSON(http.StatusBadRequest, gin.H{"error": "plan_inactive", "message": "该套餐已下架"})
	case errors.Is(err, ErrDuplicateSlug):
		c.JSON(http.StatusConflict, gin.H{"error": "duplicate_slug", "message": "套餐标识已存在"})
	default:
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal_error", "message": "服务暂时不可用"})
	}
}

// QuotaStore exposes quota methods for session handler integration.
type QuotaStore interface {
	AssertCanStart(ctx context.Context, userID, mode string) error
	ConsumeCredits(ctx context.Context, userID, sessionID, mode string) error
}
