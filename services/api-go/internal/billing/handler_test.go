package billing

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
)

type fakeStore struct {
	plans []Plan
}

func (f fakeStore) ListActivePlans(_ context.Context) ([]Plan, error) { return f.plans, nil }
func (f fakeStore) ListAllPlans(_ context.Context) ([]Plan, error)     { return f.plans, nil }
func (f fakeStore) GetPlanBySlug(_ context.Context, slug string) (Plan, error) {
	for _, plan := range f.plans {
		if plan.Slug == slug {
			return plan, nil
		}
	}
	return Plan{}, ErrNotFound
}
func (f fakeStore) GetPlanByID(_ context.Context, planID string) (Plan, error) {
	for _, plan := range f.plans {
		if plan.ID == planID {
			return plan, nil
		}
	}
	return Plan{}, ErrNotFound
}
func (f fakeStore) CreatePlan(_ context.Context, input PlanInput) (Plan, error) {
	return Plan{ID: "new", Slug: input.Slug, Name: input.Name, Features: input.Features}, nil
}
func (f fakeStore) UpdatePlan(_ context.Context, planID string, _ PlanPatch) (Plan, error) {
	return Plan{ID: planID}, nil
}
func (f fakeStore) EnsureSignupSubscription(_ context.Context, _ string) error { return nil }
func (f fakeStore) GetUserSubscriptionSummary(_ context.Context, _ string) (SubscriptionSummary, error) {
	limit := 3
	left := 2
	return SubscriptionSummary{
		Plan:        Plan{Slug: "free", NameZh: "免费版", CreditLimit: &limit},
		CreditsUsed: 1,
		CreditsLeft: &left,
	}, nil
}
func (f fakeStore) ActivateSubscription(_ context.Context, _, _, _ string) error { return nil }
func (f fakeStore) AdminUpdateUserSubscription(_ context.Context, _ string, _ AdminUserPatch) (UserSubscription, error) {
	return UserSubscription{}, nil
}
func (f fakeStore) CreateOrder(_ context.Context, _, _ string) (Order, error) { return Order{ID: "order_1"}, nil }
func (f fakeStore) GetOrder(_ context.Context, _, _ string) (Order, error)    { return Order{}, nil }
func (f fakeStore) ListOrders(_ context.Context, _ string, _ int) ([]Order, error) {
	return nil, nil
}
func (f fakeStore) ConfirmOrder(_ context.Context, _, _, _ string) (Order, error) { return Order{}, nil }
func (f fakeStore) CancelOrder(_ context.Context, _, _ string) (Order, error)     { return Order{}, nil }
func (f fakeStore) AssertCanStart(_ context.Context, _, _ string) error            { return nil }
func (f fakeStore) ConsumeCredits(_ context.Context, _, _, _ string) error         { return nil }
func (f fakeStore) ListAdminUsers(_ context.Context, _ AdminUserFilter) ([]AdminUserRow, error) {
	return nil, nil
}
func (f fakeStore) GetAdminUserDetail(_ context.Context, _ string) (AdminUserDetail, error) {
	return AdminUserDetail{}, nil
}
func (f fakeStore) UpdateAdminUser(_ context.Context, _ string, _ AdminUserPatch) (AdminUserRow, error) {
	return AdminUserRow{}, nil
}
func (f fakeStore) GetSubscriptionStats(_ context.Context) (SubscriptionStats, error) {
	return SubscriptionStats{PlanCounts: map[string]int{"free": 1}}, nil
}

func TestHandlerListPublicPlans(t *testing.T) {
	gin.SetMode(gin.TestMode)
	limit := 10
	handler := NewHandler(fakeStore{plans: []Plan{{
		ID: "plan_1", Slug: "pro", Name: "Pro", NameZh: "专业版", PriceCents: 12900,
		CreditLimit: &limit, Features: json.RawMessage(`["a"]`), Active: true,
		CreatedAt: time.Now(), UpdatedAt: time.Now(),
	}}})

	recorder := httptest.NewRecorder()
	ctx, _ := gin.CreateTestContext(recorder)
	ctx.Request = httptest.NewRequest(http.MethodGet, "/api/billing/plans", nil)
	handler.ListPublicPlans(ctx)

	if recorder.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", recorder.Code, recorder.Body.String())
	}
}
