-- +goose Up

CREATE TYPE subscription_status AS ENUM ('active', 'expired', 'cancelled');
CREATE TYPE subscription_source AS ENUM ('signup', 'checkout', 'admin');
CREATE TYPE subscription_order_status AS ENUM ('pending', 'paid', 'failed', 'cancelled');

CREATE TABLE subscription_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE,
    name text NOT NULL,
    name_zh text NOT NULL DEFAULT '',
    price_cents integer NOT NULL DEFAULT 0 CHECK (price_cents >= 0),
    currency text NOT NULL DEFAULT 'CNY',
    billing_period_days integer NOT NULL DEFAULT 30 CHECK (billing_period_days > 0),
    credit_limit integer CHECK (credit_limit IS NULL OR credit_limit >= 0),
    features jsonb NOT NULL DEFAULT '[]'::jsonb,
    sort_order integer NOT NULL DEFAULT 0,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(features) = 'array')
);

CREATE TABLE user_subscriptions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    plan_id uuid NOT NULL REFERENCES subscription_plans(id),
    status subscription_status NOT NULL DEFAULT 'active',
    credits_used integer NOT NULL DEFAULT 0 CHECK (credits_used >= 0),
    period_start timestamptz NOT NULL DEFAULT now(),
    period_end timestamptz NOT NULL,
    source subscription_source NOT NULL DEFAULT 'signup',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX user_subscriptions_plan_idx ON user_subscriptions (plan_id);
CREATE INDEX user_subscriptions_period_end_idx ON user_subscriptions (period_end);

CREATE TABLE subscription_orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id uuid NOT NULL REFERENCES subscription_plans(id),
    amount_cents integer NOT NULL CHECK (amount_cents >= 0),
    currency text NOT NULL DEFAULT 'CNY',
    status subscription_order_status NOT NULL DEFAULT 'pending',
    payment_method text,
    mock_transaction_id text,
    paid_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX subscription_orders_user_idx ON subscription_orders (user_id, created_at DESC);
CREATE INDEX subscription_orders_status_idx ON subscription_orders (status, created_at DESC);

CREATE TABLE subscription_usage_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id uuid NOT NULL UNIQUE REFERENCES practice_sessions(id) ON DELETE CASCADE,
    credits integer NOT NULL CHECK (credits > 0),
    mode text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX subscription_usage_events_user_idx ON subscription_usage_events (user_id, created_at DESC);

INSERT INTO subscription_plans (slug, name, name_zh, price_cents, credit_limit, sort_order, features) VALUES
(
    'free',
    'Free',
    '免费版',
    0,
    3,
    0,
    '["每月 3 次练习额度","完整模考消耗 3 次","Part/话题练习各 1 次","AI 评分报告","基础发音反馈"]'::jsonb
),
(
    'basic',
    'Basic',
    '基础版',
    4900,
    10,
    1,
    '["每月 10 次练习额度","完整模考消耗 3 次","Part/话题练习各 1 次","AI 多维评分","发音分析","历史复盘"]'::jsonb
),
(
    'pro',
    'Pro',
    '专业版',
    12900,
    30,
    2,
    '["每月 30 次练习额度","完整模考消耗 3 次","Part/话题练习各 1 次","Agent 实时模考","深度评分报告","优先 Agent 响应"]'::jsonb
),
(
    'unlimited',
    'Unlimited',
    '无限版',
    29900,
    NULL,
    3,
    '["不限练习次数","完整模考无上限","全部 AI Agent 能力","高级可观测性","专属学习路径","优先新功能体验"]'::jsonb
);

-- +goose Down

DROP TABLE IF EXISTS subscription_usage_events;
DROP TABLE IF EXISTS subscription_orders;
DROP TABLE IF EXISTS user_subscriptions;
DROP TABLE IF EXISTS subscription_plans;
DROP TYPE IF EXISTS subscription_order_status;
DROP TYPE IF EXISTS subscription_source;
DROP TYPE IF EXISTS subscription_status;
