package billing

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/ielts-speaking/platform/services/api-go/internal/quota"
)

func (s PostgresStore) ListActivePlans(ctx context.Context) ([]Plan, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, slug, name, name_zh, price_cents, currency, billing_period_days,
			credit_limit, features, sort_order, active, created_at, updated_at
		from subscription_plans
		where active = true
		order by sort_order asc, price_cents asc
	`)
	if err != nil {
		return nil, fmt.Errorf("list active plans: %w", err)
	}
	defer rows.Close()
	return scanPlans(rows)
}

func (s PostgresStore) ListAllPlans(ctx context.Context) ([]Plan, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, slug, name, name_zh, price_cents, currency, billing_period_days,
			credit_limit, features, sort_order, active, created_at, updated_at
		from subscription_plans
		order by sort_order asc, price_cents asc
	`)
	if err != nil {
		return nil, fmt.Errorf("list all plans: %w", err)
	}
	defer rows.Close()
	return scanPlans(rows)
}

func (s PostgresStore) GetPlanBySlug(ctx context.Context, slug string) (Plan, error) {
	return scanPlan(s.db.QueryRowContext(ctx, planSelectSQL+` where slug = $1`, strings.TrimSpace(slug)))
}

func (s PostgresStore) GetPlanByID(ctx context.Context, planID string) (Plan, error) {
	return scanPlan(s.db.QueryRowContext(ctx, planSelectSQL+` where id = $1::uuid`, planID))
}

func (s PostgresStore) CreatePlan(ctx context.Context, input PlanInput) (Plan, error) {
	input = normalizePlanInput(input)
	features := input.Features
	if len(features) == 0 {
		features = json.RawMessage(`[]`)
	}
	return scanPlan(s.db.QueryRowContext(ctx, `
		insert into subscription_plans (
			slug, name, name_zh, price_cents, currency, billing_period_days,
			credit_limit, features, sort_order, active, updated_at
		) values ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, now())
		returning id::text, slug, name, name_zh, price_cents, currency, billing_period_days,
			credit_limit, features, sort_order, active, created_at, updated_at
	`, input.Slug, input.Name, input.NameZh, input.PriceCents, input.Currency,
		input.BillingPeriodDays, input.CreditLimit, features, input.SortOrder, input.Active))
}

func (s PostgresStore) UpdatePlan(ctx context.Context, planID string, patch PlanPatch) (Plan, error) {
	current, err := s.GetPlanByID(ctx, planID)
	if err != nil {
		return Plan{}, err
	}

	name := current.Name
	if patch.Name != nil {
		name = strings.TrimSpace(*patch.Name)
	}
	nameZh := current.NameZh
	if patch.NameZh != nil {
		nameZh = strings.TrimSpace(*patch.NameZh)
	}
	priceCents := current.PriceCents
	if patch.PriceCents != nil {
		priceCents = *patch.PriceCents
	}
	currency := current.Currency
	if patch.Currency != nil {
		currency = strings.TrimSpace(*patch.Currency)
	}
	billingPeriodDays := current.BillingPeriodDays
	if patch.BillingPeriodDays != nil {
		billingPeriodDays = *patch.BillingPeriodDays
	}
	creditLimit := current.CreditLimit
	if patch.CreditLimit != nil {
		creditLimit = *patch.CreditLimit
	}
	features := current.Features
	if patch.Features != nil {
		features = *patch.Features
	}
	sortOrder := current.SortOrder
	if patch.SortOrder != nil {
		sortOrder = *patch.SortOrder
	}
	active := current.Active
	if patch.Active != nil {
		active = *patch.Active
	}

	return scanPlan(s.db.QueryRowContext(ctx, `
		update subscription_plans
		set name = $2, name_zh = $3, price_cents = $4, currency = $5,
			billing_period_days = $6, credit_limit = $7, features = $8::jsonb,
			sort_order = $9, active = $10, updated_at = now()
		where id = $1::uuid
		returning id::text, slug, name, name_zh, price_cents, currency, billing_period_days,
			credit_limit, features, sort_order, active, created_at, updated_at
	`, planID, name, nameZh, priceCents, currency, billingPeriodDays, creditLimit, features, sortOrder, active))
}

func (s PostgresStore) EnsureSignupSubscription(ctx context.Context, userID string) error {
	plan, err := s.GetPlanBySlug(ctx, "free")
	if err != nil {
		return err
	}
	now := time.Now().UTC()
	periodEnd := now.AddDate(0, 0, plan.BillingPeriodDays)
	_, err = s.db.ExecContext(ctx, `
		insert into user_subscriptions (
			user_id, plan_id, status, credits_used, period_start, period_end, source, updated_at
		) values ($1::uuid, $2::uuid, 'active', 0, $3, $4, 'signup', now())
		on conflict (user_id) do nothing
	`, userID, plan.ID, now, periodEnd)
	if err != nil {
		return fmt.Errorf("ensure signup subscription: %w", err)
	}
	return nil
}

func (s PostgresStore) GetUserSubscriptionSummary(ctx context.Context, userID string) (SubscriptionSummary, error) {
	sub, plan, err := s.loadActiveSubscription(ctx, userID)
	if err != nil {
		return SubscriptionSummary{}, err
	}
	sub.Plan = &plan
	summary := SubscriptionSummary{
		Subscription: sub,
		Plan:         plan,
		CreditsUsed:  sub.CreditsUsed,
		CreditLimit:  plan.CreditLimit,
	}
	if plan.CreditLimit != nil {
		left := *plan.CreditLimit - sub.CreditsUsed
		if left < 0 {
			left = 0
		}
		summary.CreditsLeft = &left
	}
	return summary, nil
}

func (s PostgresStore) ActivateSubscription(ctx context.Context, userID, planID, source string) error {
	plan, err := s.GetPlanByID(ctx, planID)
	if err != nil {
		return err
	}
	if !plan.Active {
		return ErrPlanInactive
	}
	now := time.Now().UTC()
	periodEnd := now.AddDate(0, 0, plan.BillingPeriodDays)
	_, err = s.db.ExecContext(ctx, `
		insert into user_subscriptions (
			user_id, plan_id, status, credits_used, period_start, period_end, source, updated_at
		) values ($1::uuid, $2::uuid, 'active', 0, $3, $4, $5::subscription_source, now())
		on conflict (user_id) do update set
			plan_id = excluded.plan_id,
			status = 'active',
			credits_used = 0,
			period_start = excluded.period_start,
			period_end = excluded.period_end,
			source = excluded.source,
			updated_at = now()
	`, userID, planID, now, periodEnd, source)
	if err != nil {
		return fmt.Errorf("activate subscription: %w", err)
	}
	return nil
}

func (s PostgresStore) AdminUpdateUserSubscription(ctx context.Context, userID string, patch AdminUserPatch) (UserSubscription, error) {
	if patch.PlanSlug != nil {
		plan, err := s.GetPlanBySlug(ctx, *patch.PlanSlug)
		if err != nil {
			return UserSubscription{}, err
		}
		if err := s.ActivateSubscription(ctx, userID, plan.ID, SourceAdmin); err != nil {
			return UserSubscription{}, err
		}
	}
	if patch.ResetCredits != nil && *patch.ResetCredits {
		if _, err := s.db.ExecContext(ctx, `
			update user_subscriptions set credits_used = 0, updated_at = now() where user_id = $1::uuid
		`, userID); err != nil {
			return UserSubscription{}, fmt.Errorf("reset credits: %w", err)
		}
	}
	if patch.ExtendPeriodDays != nil && *patch.ExtendPeriodDays > 0 {
		if _, err := s.db.ExecContext(ctx, `
			update user_subscriptions
			set period_end = period_end + ($2 || ' days')::interval, updated_at = now()
			where user_id = $1::uuid
		`, userID, fmt.Sprintf("%d", *patch.ExtendPeriodDays)); err != nil {
			return UserSubscription{}, fmt.Errorf("extend period: %w", err)
		}
	}
	sub, _, err := s.loadActiveSubscription(ctx, userID)
	return sub, err
}

func (s PostgresStore) CreateOrder(ctx context.Context, userID, planID string) (Order, error) {
	plan, err := s.GetPlanByID(ctx, planID)
	if err != nil {
		return Order{}, err
	}
	if !plan.Active {
		return Order{}, ErrPlanInactive
	}
	return scanOrder(s.db.QueryRowContext(ctx, `
		insert into subscription_orders (user_id, plan_id, amount_cents, currency, status)
		values ($1::uuid, $2::uuid, $3, $4, 'pending')
		returning id::text, user_id::text, plan_id::text, amount_cents, currency, status,
			payment_method, mock_transaction_id, paid_at, created_at
	`, userID, planID, plan.PriceCents, plan.Currency))
}

func (s PostgresStore) GetOrder(ctx context.Context, userID, orderID string) (Order, error) {
	order, err := scanOrder(s.db.QueryRowContext(ctx, orderSelectSQL+`
		where id = $1::uuid and user_id = $2::uuid
	`, orderID, userID))
	if err != nil {
		return Order{}, err
	}
	plan, err := s.GetPlanByID(ctx, order.PlanID)
	if err == nil {
		order.Plan = &plan
	}
	return order, nil
}

func (s PostgresStore) ListOrders(ctx context.Context, userID string, limit int) ([]Order, error) {
	if limit <= 0 {
		limit = 20
	}
	rows, err := s.db.QueryContext(ctx, orderSelectSQL+`
		where user_id = $1::uuid
		order by created_at desc
		limit $2
	`, userID, limit)
	if err != nil {
		return nil, fmt.Errorf("list orders: %w", err)
	}
	defer rows.Close()

	orders := make([]Order, 0)
	for rows.Next() {
		order, err := scanOrderRow(rows)
		if err != nil {
			return nil, err
		}
		plan, err := s.GetPlanByID(ctx, order.PlanID)
		if err == nil {
			order.Plan = &plan
		}
		orders = append(orders, order)
	}
	return orders, rows.Err()
}

func (s PostgresStore) ConfirmOrder(ctx context.Context, userID, orderID, paymentMethod string) (Order, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return Order{}, err
	}
	defer tx.Rollback()

	var planID, status string
	var amountCents int
	if err := tx.QueryRowContext(ctx, `
		select plan_id::text, status::text, amount_cents
		from subscription_orders
		where id = $1::uuid and user_id = $2::uuid
		for update
	`, orderID, userID).Scan(&planID, &status, &amountCents); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return Order{}, ErrNotFound
		}
		return Order{}, err
	}
	if status != OrderPending {
		return Order{}, ErrOrderNotPending
	}

	mockTxnID := fmt.Sprintf("mock_%d", time.Now().UnixNano())
	paidAt := time.Now().UTC()
	order, err := scanOrder(tx.QueryRowContext(ctx, `
		update subscription_orders
		set status = 'paid', payment_method = $3, mock_transaction_id = $4, paid_at = $5
		where id = $1::uuid and user_id = $2::uuid
		returning id::text, user_id::text, plan_id::text, amount_cents, currency, status,
			payment_method, mock_transaction_id, paid_at, created_at
	`, orderID, userID, strings.TrimSpace(paymentMethod), mockTxnID, paidAt))
	if err != nil {
		return Order{}, err
	}

	plan, err := s.GetPlanByID(ctx, planID)
	if err != nil {
		return Order{}, err
	}
	now := paidAt
	periodEnd := now.AddDate(0, 0, plan.BillingPeriodDays)
	if _, err := tx.ExecContext(ctx, `
		insert into user_subscriptions (
			user_id, plan_id, status, credits_used, period_start, period_end, source, updated_at
		) values ($1::uuid, $2::uuid, 'active', 0, $3, $4, 'checkout', now())
		on conflict (user_id) do update set
			plan_id = excluded.plan_id,
			status = 'active',
			credits_used = 0,
			period_start = excluded.period_start,
			period_end = excluded.period_end,
			source = 'checkout',
			updated_at = now()
	`, userID, planID, now, periodEnd); err != nil {
		return Order{}, err
	}

	if err := tx.Commit(); err != nil {
		return Order{}, err
	}
	planCopy := plan
	order.Plan = &planCopy
	return order, nil
}

func (s PostgresStore) CancelOrder(ctx context.Context, userID, orderID string) (Order, error) {
	order, err := scanOrder(s.db.QueryRowContext(ctx, `
		update subscription_orders
		set status = 'cancelled'
		where id = $1::uuid and user_id = $2::uuid and status = 'pending'
		returning id::text, user_id::text, plan_id::text, amount_cents, currency, status,
			payment_method, mock_transaction_id, paid_at, created_at
	`, orderID, userID))
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return Order{}, ErrOrderNotPending
		}
		return Order{}, err
	}
	return order, nil
}

func (s PostgresStore) AssertCanStart(ctx context.Context, userID, mode string) error {
	sub, plan, err := s.loadActiveSubscription(ctx, userID)
	if err != nil {
		return err
	}
	if err := ensureSubscriptionActive(sub); err != nil {
		return err
	}
	if plan.CreditLimit == nil {
		return nil
	}
	required := quota.CreditWeight(mode)
	remaining := *plan.CreditLimit - sub.CreditsUsed
	if remaining < required {
		return quota.Exceeded(required, remaining, plan.Slug)
	}
	return nil
}

func (s PostgresStore) ConsumeCredits(ctx context.Context, userID, sessionID, mode string) error {
	sub, plan, err := s.loadActiveSubscription(ctx, userID)
	if err != nil {
		return err
	}
	if plan.CreditLimit == nil {
		return nil
	}
	credits := quota.CreditWeight(mode)

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()

	var exists bool
	if err := tx.QueryRowContext(ctx, `
		select exists(select 1 from subscription_usage_events where session_id = $1::uuid)
	`, sessionID).Scan(&exists); err != nil {
		return err
	}
	if exists {
		return tx.Commit()
	}

	if _, err := tx.ExecContext(ctx, `
		insert into subscription_usage_events (user_id, session_id, credits, mode)
		values ($1::uuid, $2::uuid, $3, $4)
	`, userID, sessionID, credits, mode); err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx, `
		update user_subscriptions
		set credits_used = credits_used + $3, updated_at = now()
		where user_id = $1::uuid and id = $2::uuid
	`, userID, sub.ID, credits); err != nil {
		return err
	}
	return tx.Commit()
}

func (s PostgresStore) ListAdminUsers(ctx context.Context, filter AdminUserFilter) ([]AdminUserRow, error) {
	limit := filter.Limit
	if limit <= 0 {
		limit = 50
	}
	query := `
		select u.id::text, u.email, u.role::text, u.status::text, up.display_name,
			sp.slug, sp.name_zh, us.credits_used, sp.credit_limit, us.period_end, u.created_at, u.last_login_at
		from users u
		left join user_profiles up on up.user_id = u.id
		left join user_subscriptions us on us.user_id = u.id
		left join subscription_plans sp on sp.id = us.plan_id
		where u.deleted_at is null
	`
	args := make([]any, 0, 6)
	argN := 1
	if q := strings.TrimSpace(filter.Query); q != "" {
		query += fmt.Sprintf(" and lower(u.email) like $%d", argN)
		args = append(args, "%"+strings.ToLower(q)+"%")
		argN++
	}
	if role := strings.TrimSpace(filter.Role); role != "" {
		query += fmt.Sprintf(" and u.role::text = $%d", argN)
		args = append(args, role)
		argN++
	}
	if status := strings.TrimSpace(filter.Status); status != "" {
		query += fmt.Sprintf(" and u.status::text = $%d", argN)
		args = append(args, status)
		argN++
	}
	if planSlug := strings.TrimSpace(filter.PlanSlug); planSlug != "" {
		query += fmt.Sprintf(" and sp.slug = $%d", argN)
		args = append(args, planSlug)
		argN++
	}
	query += fmt.Sprintf(" order by u.created_at desc limit $%d offset $%d", argN, argN+1)
	args = append(args, limit, filter.Offset)

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("list admin users: %w", err)
	}
	defer rows.Close()

	items := make([]AdminUserRow, 0)
	for rows.Next() {
		var row AdminUserRow
		var displayName sql.NullString
		var planSlug, planNameZh sql.NullString
		var creditsUsed sql.NullInt64
		var creditLimit sql.NullInt64
		var periodEnd sql.NullTime
		var lastLogin sql.NullTime
		if err := rows.Scan(
			&row.ID, &row.Email, &row.Role, &row.Status, &displayName,
			&planSlug, &planNameZh, &creditsUsed, &creditLimit, &periodEnd, &row.CreatedAt, &lastLogin,
		); err != nil {
			return nil, err
		}
		if displayName.Valid {
			row.DisplayName = &displayName.String
		}
		if planSlug.Valid {
			row.PlanSlug = &planSlug.String
		}
		if planNameZh.Valid {
			row.PlanNameZh = &planNameZh.String
		}
		if creditsUsed.Valid {
			v := int(creditsUsed.Int64)
			row.CreditsUsed = &v
		}
		if creditLimit.Valid {
			v := int(creditLimit.Int64)
			row.CreditLimit = &v
		}
		if periodEnd.Valid {
			t := periodEnd.Time
			row.PeriodEnd = &t
		}
		if lastLogin.Valid {
			t := lastLogin.Time
			row.LastLoginAt = &t
		}
		items = append(items, row)
	}
	return items, rows.Err()
}

func (s PostgresStore) GetAdminUserDetail(ctx context.Context, userID string) (AdminUserDetail, error) {
	var row AdminUserRow
	var displayName sql.NullString
	var lastLogin sql.NullTime
	err := s.db.QueryRowContext(ctx, `
		select id::text, email, role::text, status::text, created_at, last_login_at
		from users where id = $1::uuid and deleted_at is null
	`, userID).Scan(&row.ID, &row.Email, &row.Role, &row.Status, &row.CreatedAt, &lastLogin)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return AdminUserDetail{}, ErrNotFound
		}
		return AdminUserDetail{}, err
	}
	if lastLogin.Valid {
		t := lastLogin.Time
		row.LastLoginAt = &t
	}

	var planSlug, planNameZh sql.NullString
	var creditsUsed sql.NullInt64
	var creditLimit sql.NullInt64
	var periodEnd sql.NullTime
	if err := s.db.QueryRowContext(ctx, `
		select up.display_name, sp.slug, sp.name_zh, us.credits_used, sp.credit_limit, us.period_end
		from users u
		left join user_profiles up on up.user_id = u.id
		left join user_subscriptions us on us.user_id = u.id
		left join subscription_plans sp on sp.id = us.plan_id
		where u.id = $1::uuid
	`, userID).Scan(&displayName, &planSlug, &planNameZh, &creditsUsed, &creditLimit, &periodEnd); err != nil && !errors.Is(err, sql.ErrNoRows) {
		return AdminUserDetail{}, err
	}
	if displayName.Valid {
		row.DisplayName = &displayName.String
	}
	if planSlug.Valid {
		row.PlanSlug = &planSlug.String
	}
	if planNameZh.Valid {
		row.PlanNameZh = &planNameZh.String
	}
	if creditsUsed.Valid {
		v := int(creditsUsed.Int64)
		row.CreditsUsed = &v
	}
	if creditLimit.Valid {
		v := int(creditLimit.Int64)
		row.CreditLimit = &v
	}
	if periodEnd.Valid {
		t := periodEnd.Time
		row.PeriodEnd = &t
	}

	detail := AdminUserDetail{User: row}
	subSummary, err := s.GetUserSubscriptionSummary(ctx, userID)
	if err == nil {
		detail.Subscription = &subSummary.Subscription
	}
	orders, err := s.ListOrders(ctx, userID, 10)
	if err == nil {
		detail.RecentOrders = orders
	}
	return detail, nil
}

func (s PostgresStore) UpdateAdminUser(ctx context.Context, userID string, patch AdminUserPatch) (AdminUserRow, error) {
	if patch.Role != nil {
		if _, err := s.db.ExecContext(ctx, `
			update users set role = $2::user_role where id = $1::uuid and deleted_at is null
		`, userID, *patch.Role); err != nil {
			return AdminUserRow{}, fmt.Errorf("update role: %w", err)
		}
	}
	if patch.Status != nil {
		if _, err := s.db.ExecContext(ctx, `
			update users set status = $2::user_status where id = $1::uuid and deleted_at is null
		`, userID, *patch.Status); err != nil {
			return AdminUserRow{}, fmt.Errorf("update status: %w", err)
		}
	}
	if patch.PlanSlug != nil || patch.ResetCredits != nil || patch.ExtendPeriodDays != nil {
		if _, err := s.AdminUpdateUserSubscription(ctx, userID, patch); err != nil {
			return AdminUserRow{}, err
		}
	}

	var row AdminUserRow
	var displayName sql.NullString
	var planSlug, planNameZh sql.NullString
	var creditsUsed sql.NullInt64
	var creditLimit sql.NullInt64
	var periodEnd sql.NullTime
	var lastLogin sql.NullTime
	err := s.db.QueryRowContext(ctx, `
		select u.id::text, u.email, u.role::text, u.status::text, up.display_name,
			sp.slug, sp.name_zh, us.credits_used, sp.credit_limit, us.period_end, u.created_at, u.last_login_at
		from users u
		left join user_profiles up on up.user_id = u.id
		left join user_subscriptions us on us.user_id = u.id
		left join subscription_plans sp on sp.id = us.plan_id
		where u.id = $1::uuid and u.deleted_at is null
	`, userID).Scan(
		&row.ID, &row.Email, &row.Role, &row.Status, &displayName,
		&planSlug, &planNameZh, &creditsUsed, &creditLimit, &periodEnd, &row.CreatedAt, &lastLogin,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return AdminUserRow{}, ErrNotFound
		}
		return AdminUserRow{}, err
	}
	if displayName.Valid {
		row.DisplayName = &displayName.String
	}
	if planSlug.Valid {
		row.PlanSlug = &planSlug.String
	}
	if planNameZh.Valid {
		row.PlanNameZh = &planNameZh.String
	}
	if creditsUsed.Valid {
		v := int(creditsUsed.Int64)
		row.CreditsUsed = &v
	}
	if creditLimit.Valid {
		v := int(creditLimit.Int64)
		row.CreditLimit = &v
	}
	if periodEnd.Valid {
		t := periodEnd.Time
		row.PeriodEnd = &t
	}
	if lastLogin.Valid {
		t := lastLogin.Time
		row.LastLoginAt = &t
	}
	return row, nil
}

func (s PostgresStore) GetSubscriptionStats(ctx context.Context) (SubscriptionStats, error) {
	stats := SubscriptionStats{PlanCounts: map[string]int{}}
	rows, err := s.db.QueryContext(ctx, `
		select coalesce(sp.slug, 'none'), count(*)
		from users u
		left join user_subscriptions us on us.user_id = u.id
		left join subscription_plans sp on sp.id = us.plan_id
		where u.deleted_at is null
		group by sp.slug
	`)
	if err != nil {
		return stats, err
	}
	defer rows.Close()
	for rows.Next() {
		var slug string
		var count int
		if err := rows.Scan(&slug, &count); err != nil {
			return stats, err
		}
		stats.PlanCounts[slug] = count
	}

	startOfMonth := time.Now().UTC()
	startOfMonth = time.Date(startOfMonth.Year(), startOfMonth.Month(), 1, 0, 0, 0, 0, time.UTC)
	if err := s.db.QueryRowContext(ctx, `
		select coalesce(sum(amount_cents), 0), count(*)
		from subscription_orders
		where status = 'paid' and paid_at >= $1
	`, startOfMonth).Scan(&stats.MonthlyRevenue, &stats.PaidOrders); err != nil {
		return stats, err
	}
	return stats, rows.Err()
}

const planSelectSQL = `
	select id::text, slug, name, name_zh, price_cents, currency, billing_period_days,
		credit_limit, features, sort_order, active, created_at, updated_at
	from subscription_plans
`

const orderSelectSQL = `
	select id::text, user_id::text, plan_id::text, amount_cents, currency, status::text,
		payment_method, mock_transaction_id, paid_at, created_at
	from subscription_orders
`

func (s PostgresStore) loadActiveSubscription(ctx context.Context, userID string) (UserSubscription, Plan, error) {
	sub, err := scanUserSubscription(s.db.QueryRowContext(ctx, `
		select us.id::text, us.user_id::text, us.plan_id::text, us.status::text, us.credits_used,
			us.period_start, us.period_end, us.source::text, us.created_at, us.updated_at
		from user_subscriptions us
		where us.user_id = $1::uuid
	`, userID))
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			if ensureErr := s.EnsureSignupSubscription(ctx, userID); ensureErr != nil {
				return UserSubscription{}, Plan{}, ensureErr
			}
			return s.loadActiveSubscription(ctx, userID)
		}
		return UserSubscription{}, Plan{}, err
	}
	plan, err := s.GetPlanByID(ctx, sub.PlanID)
	if err != nil {
		return UserSubscription{}, Plan{}, err
	}
	if err := ensureSubscriptionActive(sub); err != nil {
		return sub, plan, err
	}
	return sub, plan, nil
}

func ensureSubscriptionActive(sub UserSubscription) error {
	now := time.Now().UTC()
	if sub.Status == StatusCancelled {
		return quota.ErrSubscriptionExpired
	}
	if now.After(sub.PeriodEnd) {
		return quota.ErrSubscriptionExpired
	}
	return nil
}

func normalizePlanInput(input PlanInput) PlanInput {
	input.Slug = strings.TrimSpace(strings.ToLower(input.Slug))
	input.Name = strings.TrimSpace(input.Name)
	input.NameZh = strings.TrimSpace(input.NameZh)
	if input.Currency == "" {
		input.Currency = "CNY"
	}
	if input.BillingPeriodDays <= 0 {
		input.BillingPeriodDays = 30
	}
	return input
}

func scanPlans(rows *sql.Rows) ([]Plan, error) {
	items := make([]Plan, 0)
	for rows.Next() {
		plan, err := scanPlanRow(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, plan)
	}
	return items, rows.Err()
}

func scanPlan(row *sql.Row) (Plan, error) {
	var plan Plan
	var creditLimit sql.NullInt64
	var features []byte
	if err := row.Scan(
		&plan.ID, &plan.Slug, &plan.Name, &plan.NameZh, &plan.PriceCents, &plan.Currency,
		&plan.BillingPeriodDays, &creditLimit, &features, &plan.SortOrder, &plan.Active,
		&plan.CreatedAt, &plan.UpdatedAt,
	); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return Plan{}, ErrNotFound
		}
		return Plan{}, err
	}
	if creditLimit.Valid {
		v := int(creditLimit.Int64)
		plan.CreditLimit = &v
	}
	plan.Features = json.RawMessage(features)
	return plan, nil
}

func scanPlanRow(rows *sql.Rows) (Plan, error) {
	var plan Plan
	var creditLimit sql.NullInt64
	var features []byte
	if err := rows.Scan(
		&plan.ID, &plan.Slug, &plan.Name, &plan.NameZh, &plan.PriceCents, &plan.Currency,
		&plan.BillingPeriodDays, &creditLimit, &features, &plan.SortOrder, &plan.Active,
		&plan.CreatedAt, &plan.UpdatedAt,
	); err != nil {
		return Plan{}, err
	}
	if creditLimit.Valid {
		v := int(creditLimit.Int64)
		plan.CreditLimit = &v
	}
	plan.Features = json.RawMessage(features)
	return plan, nil
}

func scanUserSubscription(row *sql.Row) (UserSubscription, error) {
	var sub UserSubscription
	if err := row.Scan(
		&sub.ID, &sub.UserID, &sub.PlanID, &sub.Status, &sub.CreditsUsed,
		&sub.PeriodStart, &sub.PeriodEnd, &sub.Source, &sub.CreatedAt, &sub.UpdatedAt,
	); err != nil {
		return UserSubscription{}, err
	}
	return sub, nil
}

func scanOrder(row *sql.Row) (Order, error) {
	var order Order
	var paymentMethod, mockTxn sql.NullString
	var paidAt sql.NullTime
	if err := row.Scan(
		&order.ID, &order.UserID, &order.PlanID, &order.AmountCents, &order.Currency, &order.Status,
		&paymentMethod, &mockTxn, &paidAt, &order.CreatedAt,
	); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return Order{}, ErrNotFound
		}
		return Order{}, err
	}
	if paymentMethod.Valid {
		order.PaymentMethod = &paymentMethod.String
	}
	if mockTxn.Valid {
		order.MockTransactionID = &mockTxn.String
	}
	if paidAt.Valid {
		t := paidAt.Time
		order.PaidAt = &t
	}
	return order, nil
}

func scanOrderRow(rows *sql.Rows) (Order, error) {
	var order Order
	var paymentMethod, mockTxn sql.NullString
	var paidAt sql.NullTime
	if err := rows.Scan(
		&order.ID, &order.UserID, &order.PlanID, &order.AmountCents, &order.Currency, &order.Status,
		&paymentMethod, &mockTxn, &paidAt, &order.CreatedAt,
	); err != nil {
		return Order{}, err
	}
	if paymentMethod.Valid {
		order.PaymentMethod = &paymentMethod.String
	}
	if mockTxn.Valid {
		order.MockTransactionID = &mockTxn.String
	}
	if paidAt.Valid {
		t := paidAt.Time
		order.PaidAt = &t
	}
	return order, nil
}
