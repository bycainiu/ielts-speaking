"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

import { AcademicShell, PageHeader, Panel, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { billingApi } from "@/lib/api";
import { formatCreditLimit, formatPrice, parsePlanFeatures, type SubscriptionPlan, type SubscriptionSummary } from "@/lib/billing";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";

export default function SubscribePageClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [summary, setSummary] = useState<SubscriptionSummary | null>(null);
  const [selected, setSelected] = useState(searchParams.get("plan") || "pro");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!hasHydrated) return;
    if (!isAuthenticated) {
      router.push(`/login?next=${encodeURIComponent("/pricing/subscribe")}`);
      return;
    }
    if (!user) fetchUser();
  }, [hasHydrated, isAuthenticated, user, fetchUser, router]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [plansRes, subRes] = await Promise.all([billingApi.listPlans(), billingApi.getSubscription()]);
      setPlans(
        plansRes.data.plans.map((plan) => ({
          ...plan,
          features: parsePlanFeatures(plan.features),
        })),
      );
      setSummary(subRes.data.subscription);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated && user) load();
  }, [isAuthenticated, user, load]);

  const selectedPlan = useMemo(() => plans.find((p) => p.slug === selected), [plans, selected]);
  const currentSlug = summary?.plan.slug;

  const handleContinue = async () => {
    if (!selectedPlan || selectedPlan.slug === "free") return;
    setSubmitting(true);
    try {
      router.push(`/pricing/checkout?plan=${selectedPlan.slug}`);
    } finally {
      setSubmitting(false);
    }
  };

  if (!hasHydrated || !isAuthenticated || !user) return null;

  return (
    <AcademicShell activePath="/settings/subscription" userName={user.email} userRole={user.role}>
      <PageHeader
        title="选择订阅套餐"
        description="按练习强度选择合适层级，完整模考消耗 3 次额度。"
        actions={
          <Button asChild variant="soft">
            <Link href="/pricing">查看介绍</Link>
          </Button>
        }
      />

      {loading ? (
        <Panel className="flex items-center gap-2 text-slate-600">
          <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
        </Panel>
      ) : (
        <>
          {summary ? (
            <Panel>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-500">当前套餐</p>
                  <p className="text-xl font-semibold text-slate-900">{summary.plan.name_zh}</p>
                  <p className="mt-1 text-sm text-slate-600">
                    已用 {summary.credits_used}
                    {summary.credit_limit !== null ? ` / ${summary.credit_limit}` : " / 不限"} · 到期{" "}
                    {new Date(summary.subscription.period_end).toLocaleDateString("zh-CN")}
                  </p>
                </div>
                <StatusBadge tone="teal">{formatCreditLimit(summary.credit_limit)}</StatusBadge>
              </div>
            </Panel>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {plans.map((plan) => {
              const isCurrent = plan.slug === currentSlug;
              const isSelected = plan.slug === selected;
              return (
                <button
                  key={plan.slug}
                  type="button"
                  onClick={() => setSelected(plan.slug)}
                  className={cn(
                    "rounded-xl border p-5 text-left transition",
                    isSelected ? "border-[#D4AF37] bg-[#F7F4EA]" : "border-slate-200 bg-white hover:border-slate-300",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold text-slate-900">{plan.name_zh}</p>
                      <p className="mt-1 text-2xl font-serif text-[#0B132B]">{formatPrice(plan.price_cents)}</p>
                    </div>
                    {isCurrent ? <StatusBadge tone="sage">当前</StatusBadge> : null}
                  </div>
                  <p className="mt-2 text-sm text-slate-600">{formatCreditLimit(plan.credit_limit)}</p>
                  <ul className="mt-4 space-y-1 text-xs text-slate-600">
                    {plan.features.slice(0, 3).map((f) => (
                      <li key={f}>· {f}</li>
                    ))}
                  </ul>
                </button>
              );
            })}
          </div>

          <Panel>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-sm text-slate-500">已选套餐</p>
                <p className="text-lg font-semibold">{selectedPlan?.name_zh || "—"}</p>
              </div>
              <Button
                variant="gold"
                disabled={!selectedPlan || selectedPlan.slug === "free" || selectedPlan.slug === currentSlug || submitting}
                onClick={handleContinue}
              >
                {selectedPlan?.slug === currentSlug ? "当前套餐" : "继续支付"}
              </Button>
            </div>
          </Panel>
        </>
      )}
    </AcademicShell>
  );
}
