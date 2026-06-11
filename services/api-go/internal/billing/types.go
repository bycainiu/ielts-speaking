package billing

import (
	"encoding/json"
	"time"
)

const (
	SourceSignup   = "signup"
	SourceCheckout = "checkout"
	SourceAdmin    = "admin"

	StatusActive    = "active"
	StatusExpired   = "expired"
	StatusCancelled = "cancelled"

	OrderPending   = "pending"
	OrderPaid      = "paid"
	OrderFailed    = "failed"
	OrderCancelled = "cancelled"
)

type Plan struct {
	ID                 string          `json:"id"`
	Slug               string          `json:"slug"`
	Name               string          `json:"name"`
	NameZh             string          `json:"name_zh"`
	PriceCents         int             `json:"price_cents"`
	Currency           string          `json:"currency"`
	BillingPeriodDays  int             `json:"billing_period_days"`
	CreditLimit        *int            `json:"credit_limit"`
	Features           json.RawMessage `json:"features"`
	SortOrder          int             `json:"sort_order"`
	Active             bool            `json:"active"`
	CreatedAt          time.Time       `json:"created_at"`
	UpdatedAt          time.Time       `json:"updated_at"`
}

type UserSubscription struct {
	ID          string    `json:"id"`
	UserID      string    `json:"user_id"`
	PlanID      string    `json:"plan_id"`
	Status      string    `json:"status"`
	CreditsUsed int       `json:"credits_used"`
	PeriodStart time.Time `json:"period_start"`
	PeriodEnd   time.Time `json:"period_end"`
	Source      string    `json:"source"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
	Plan        *Plan     `json:"plan,omitempty"`
}

type SubscriptionSummary struct {
	Subscription UserSubscription `json:"subscription"`
	Plan         Plan             `json:"plan"`
	CreditsUsed  int              `json:"credits_used"`
	CreditLimit  *int             `json:"credit_limit"`
	CreditsLeft  *int             `json:"credits_left"`
}

type Order struct {
	ID                string     `json:"id"`
	UserID            string     `json:"user_id"`
	PlanID            string     `json:"plan_id"`
	AmountCents       int        `json:"amount_cents"`
	Currency          string     `json:"currency"`
	Status            string     `json:"status"`
	PaymentMethod     *string    `json:"payment_method,omitempty"`
	MockTransactionID *string    `json:"mock_transaction_id,omitempty"`
	PaidAt            *time.Time `json:"paid_at,omitempty"`
	CreatedAt         time.Time  `json:"created_at"`
	Plan              *Plan      `json:"plan,omitempty"`
}

type UsageEvent struct {
	ID        string    `json:"id"`
	UserID    string    `json:"user_id"`
	SessionID string    `json:"session_id"`
	Credits   int       `json:"credits"`
	Mode      string    `json:"mode"`
	CreatedAt time.Time `json:"created_at"`
}

type PlanInput struct {
	Slug              string          `json:"slug"`
	Name              string          `json:"name"`
	NameZh            string          `json:"name_zh"`
	PriceCents        int             `json:"price_cents"`
	Currency          string          `json:"currency"`
	BillingPeriodDays int             `json:"billing_period_days"`
	CreditLimit       *int            `json:"credit_limit"`
	Features          json.RawMessage `json:"features"`
	SortOrder         int             `json:"sort_order"`
	Active            bool            `json:"active"`
}

type PlanPatch struct {
	Name              *string          `json:"name"`
	NameZh            *string          `json:"name_zh"`
	PriceCents        *int             `json:"price_cents"`
	Currency          *string          `json:"currency"`
	BillingPeriodDays *int             `json:"billing_period_days"`
	CreditLimit       **int            `json:"credit_limit"`
	Features          *json.RawMessage `json:"features"`
	SortOrder         *int             `json:"sort_order"`
	Active            *bool            `json:"active"`
}

type CheckoutInput struct {
	PlanSlug string `json:"plan_slug"`
}

type ConfirmCheckoutInput struct {
	PaymentMethod string `json:"payment_method"`
}

type AdminUserRow struct {
	ID           string     `json:"id"`
	Email        string     `json:"email"`
	Role         string     `json:"role"`
	Status       string     `json:"status"`
	DisplayName  *string    `json:"display_name,omitempty"`
	PlanSlug     *string    `json:"plan_slug,omitempty"`
	PlanNameZh   *string    `json:"plan_name_zh,omitempty"`
	CreditsUsed  *int       `json:"credits_used,omitempty"`
	CreditLimit  *int       `json:"credit_limit,omitempty"`
	PeriodEnd    *time.Time `json:"period_end,omitempty"`
	CreatedAt    time.Time  `json:"created_at"`
	LastLoginAt  *time.Time `json:"last_login_at,omitempty"`
}

type AdminUserDetail struct {
	User         AdminUserRow       `json:"user"`
	Subscription *UserSubscription  `json:"subscription,omitempty"`
	RecentOrders []Order            `json:"recent_orders"`
}

type AdminUserPatch struct {
	Role              *string `json:"role"`
	Status            *string `json:"status"`
	PlanSlug          *string `json:"plan_slug"`
	ResetCredits      *bool   `json:"reset_credits"`
	ExtendPeriodDays  *int    `json:"extend_period_days"`
}

type AdminUserFilter struct {
	Query    string
	Role     string
	Status   string
	PlanSlug string
	Limit    int
	Offset   int
}

type SubscriptionStats struct {
	PlanCounts    map[string]int `json:"plan_counts"`
	MonthlyRevenue int           `json:"monthly_revenue_cents"`
	PaidOrders    int            `json:"paid_orders_this_month"`
}
