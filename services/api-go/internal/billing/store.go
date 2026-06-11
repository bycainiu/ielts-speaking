package billing

import (
	"context"
	"database/sql"
)

type Store interface {
	ListActivePlans(ctx context.Context) ([]Plan, error)
	ListAllPlans(ctx context.Context) ([]Plan, error)
	GetPlanBySlug(ctx context.Context, slug string) (Plan, error)
	GetPlanByID(ctx context.Context, planID string) (Plan, error)
	CreatePlan(ctx context.Context, input PlanInput) (Plan, error)
	UpdatePlan(ctx context.Context, planID string, patch PlanPatch) (Plan, error)

	EnsureSignupSubscription(ctx context.Context, userID string) error
	GetUserSubscriptionSummary(ctx context.Context, userID string) (SubscriptionSummary, error)
	ActivateSubscription(ctx context.Context, userID, planID, source string) error
	AdminUpdateUserSubscription(ctx context.Context, userID string, patch AdminUserPatch) (UserSubscription, error)

	CreateOrder(ctx context.Context, userID, planID string) (Order, error)
	GetOrder(ctx context.Context, userID, orderID string) (Order, error)
	ListOrders(ctx context.Context, userID string, limit int) ([]Order, error)
	ConfirmOrder(ctx context.Context, userID, orderID, paymentMethod string) (Order, error)
	CancelOrder(ctx context.Context, userID, orderID string) (Order, error)

	AssertCanStart(ctx context.Context, userID, mode string) error
	ConsumeCredits(ctx context.Context, userID, sessionID, mode string) error

	ListAdminUsers(ctx context.Context, filter AdminUserFilter) ([]AdminUserRow, error)
	GetAdminUserDetail(ctx context.Context, userID string) (AdminUserDetail, error)
	UpdateAdminUser(ctx context.Context, userID string, patch AdminUserPatch) (AdminUserRow, error)
	GetSubscriptionStats(ctx context.Context) (SubscriptionStats, error)
}

type PostgresStore struct {
	db *sql.DB
}

func NewPostgresStore(db *sql.DB) PostgresStore {
	return PostgresStore{db: db}
}
