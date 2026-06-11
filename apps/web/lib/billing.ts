export type SubscriptionPlan = {
  id: string;
  slug: string;
  name: string;
  name_zh: string;
  price_cents: number;
  currency: string;
  billing_period_days: number;
  credit_limit: number | null;
  features: string[];
  sort_order: number;
  active: boolean;
};

export type SubscriptionSummary = {
  subscription: {
    id: string;
    user_id: string;
    plan_id: string;
    status: string;
    credits_used: number;
    period_start: string;
    period_end: string;
    source: string;
  };
  plan: SubscriptionPlan;
  credits_used: number;
  credit_limit: number | null;
  credits_left: number | null;
};

export type SubscriptionOrder = {
  id: string;
  user_id: string;
  plan_id: string;
  amount_cents: number;
  currency: string;
  status: string;
  payment_method?: string | null;
  mock_transaction_id?: string | null;
  paid_at?: string | null;
  created_at: string;
  plan?: SubscriptionPlan;
};

export type AdminUserRow = {
  id: string;
  email: string;
  role: string;
  status: string;
  display_name?: string | null;
  plan_slug?: string | null;
  plan_name_zh?: string | null;
  credits_used?: number | null;
  credit_limit?: number | null;
  period_end?: string | null;
  created_at: string;
  last_login_at?: string | null;
};

export type SubscriptionStats = {
  plan_counts: Record<string, number>;
  monthly_revenue_cents: number;
  paid_orders_this_month: number;
};

export function parsePlanFeatures(raw: unknown): string[] {
  if (Array.isArray(raw)) {
    return raw.filter((item): item is string => typeof item === "string");
  }
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw) as unknown;
      return parsePlanFeatures(parsed);
    } catch {
      return [];
    }
  }
  return [];
}

export function formatPrice(cents: number, currency = "CNY"): string {
  if (cents === 0) return "免费";
  const amount = cents / 100;
  if (currency === "CNY") return `¥${amount.toFixed(0)}`;
  return `${amount.toFixed(2)} ${currency}`;
}

export function formatCreditLimit(limit: number | null): string {
  if (limit === null) return "不限";
  return `${limit} 次/月`;
}

export function creditUsagePercent(used: number, limit: number | null): number {
  if (limit === null || limit <= 0) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

export type PlanTierMeta = {
  slug: string;
  label: string;
  labelZh: string;
  tone: "slate" | "teal" | "gold" | "sage";
  permissions: string[];
  upgradeHref: string;
};

const planTierCatalog: Record<string, Omit<PlanTierMeta, "slug">> = {
  free: {
    label: "Free",
    labelZh: "免费版",
    tone: "slate",
    permissions: ["每月 3 次加权额度", "Part/主题 1 次 · 模考 3 次", "基础评分报告"],
    upgradeHref: "/pricing/subscribe?plan=basic",
  },
  basic: {
    label: "Basic",
    labelZh: "基础版",
    tone: "teal",
    permissions: ["每月 10 次加权额度", "完整模考 + 分项练习", "历史报告复盘"],
    upgradeHref: "/pricing/subscribe?plan=pro",
  },
  pro: {
    label: "Pro",
    labelZh: "专业版",
    tone: "gold",
    permissions: ["每月 30 次加权额度", "Agent 可观测轨迹", "优先评分队列"],
    upgradeHref: "/pricing/subscribe?plan=unlimited",
  },
  unlimited: {
    label: "Unlimited",
    labelZh: "无限版",
    tone: "sage",
    permissions: ["不限练习次数", "完整模考无限制", "全部高级功能"],
    upgradeHref: "/settings/subscription",
  },
};

export function planTierMeta(slug: string): PlanTierMeta {
  const meta = planTierCatalog[slug] ?? planTierCatalog.free;
  return { slug, ...meta };
}
