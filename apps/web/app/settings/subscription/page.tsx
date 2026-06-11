"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Loader2, RefreshCcw } from "lucide-react";

import { AcademicShell, EmptyState, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { billingApi } from "@/lib/api";
import {
  creditUsagePercent,
  formatCreditLimit,
  formatPrice,
  parsePlanFeatures,
  type SubscriptionOrder,
  type SubscriptionSummary,
} from "@/lib/billing";
import { useAuthStore } from "@/store/authStore";

export default function SubscriptionSettingsPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [summary, setSummary] = useState<SubscriptionSummary | null>(null);
  const [orders, setOrders] = useState<SubscriptionOrder[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!hasHydrated) return;
    if (!isAuthenticated) {
      router.push("/login?next=/settings/subscription");
      return;
    }
    if (!user) fetchUser();
  }, [hasHydrated, isAuthenticated, user, fetchUser, router]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [subRes, ordersRes] = await Promise.all([billingApi.getSubscription(), billingApi.listOrders()]);
      setSummary(subRes.data.subscription);
      setOrders(ordersRes.data.orders);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated && user) load();
  }, [isAuthenticated, user, load]);

  if (!hasHydrated || !isAuthenticated || !user) return null;

  const usagePercent = summary ? creditUsagePercent(summary.credits_used, summary.credit_limit) : 0;

  return (
    <AcademicShell activePath="/settings/subscription" userName={user.email} userRole={user.role}>
      <PageHeader
        title="Subscription"
        description="View your current plan, usage, and order history."
        actions={
          <div className="flex gap-2">
            <Button variant="soft" onClick={load} disabled={loading}>
              <RefreshCcw className="mr-2 h-4 w-4" /> Refresh
            </Button>
            <Button asChild variant="gold">
              <Link href="/pricing/subscribe">Upgrade plan</Link>
            </Button>
          </div>
        }
      />

      {loading ? (
        <Panel className="flex items-center gap-2 text-slate-600">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading...
        </Panel>
      ) : summary ? (
        <>
          <div className="grid gap-5 lg:grid-cols-2">
            <Panel>
              <SectionHeading label="Current plan" labelZh="当前套餐" />
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <h3 className="text-2xl font-semibold text-slate-900">{summary.plan.name_zh}</h3>
                <StatusBadge tone="teal">{summary.subscription.status}</StatusBadge>
              </div>
              <p className="mt-2 text-sm text-slate-600">
                Period: {new Date(summary.subscription.period_start).toLocaleDateString("zh-CN")} —{" "}
                {new Date(summary.subscription.period_end).toLocaleDateString("zh-CN")}
              </p>
              <div className="mt-6">
                <div className="flex justify-between text-sm text-slate-600">
                  <span>Usage</span>
                  <span>
                    {summary.credits_used}
                    {summary.credit_limit !== null ? ` / ${summary.credit_limit}` : " / unlimited"}
                  </span>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-academic-accent transition-all"
                    style={{ width: `${summary.credit_limit === null ? 8 : usagePercent}%` }}
                  />
                </div>
                {summary.credits_left !== null ? (
                  <p className="mt-2 text-sm text-slate-500">{summary.credits_left} credits remaining</p>
                ) : (
                  <p className="mt-2 text-sm text-slate-500">Unlimited plan — no practice limit</p>
                )}
              </div>
            </Panel>

            <Panel>
              <SectionHeading label="Plan benefits" />
              <ul className="mt-4 space-y-2 text-sm text-slate-700">
                {parsePlanFeatures(summary.plan.features).map((feature) => (
                  <li key={feature} className="flex gap-2">
                    <span className="text-academic-score">✓</span>
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-6 text-sm text-slate-500">
                Price: {formatPrice(summary.plan.price_cents)} / {summary.plan.billing_period_days} days ·{" "}
                {formatCreditLimit(summary.plan.credit_limit)}
              </p>
              <Button asChild variant="teal" className="mt-4">
                <Link href={`/pricing/checkout?plan=${summary.plan.slug}`}>
                  Renew current plan <ArrowUpRight className="ml-1 h-4 w-4" />
                </Link>
              </Button>
            </Panel>
          </div>

          <Panel>
            <SectionHeading label="Order history" labelZh="Payment records" />
            {orders.length === 0 ? (
              <EmptyState title="No orders yet" body="Your payment history will appear here." />
            ) : (
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-slate-200 text-slate-500">
                    <tr>
                      <th className="px-3 py-2 font-medium">Date</th>
                      <th className="px-3 py-2 font-medium">Plan</th>
                      <th className="px-3 py-2 font-medium">Amount</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                      <th className="px-3 py-2 font-medium">Method</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map((order) => (
                      <tr key={order.id} className="border-b border-slate-100">
                        <td className="px-3 py-3">{new Date(order.created_at).toLocaleString("zh-CN")}</td>
                        <td className="px-3 py-3">{order.plan?.name_zh || order.plan_id.slice(0, 8)}</td>
                        <td className="px-3 py-3">{formatPrice(order.amount_cents, order.currency)}</td>
                        <td className="px-3 py-3">
                          <StatusBadge tone={order.status === "paid" ? "sage" : "coral"}>{order.status}</StatusBadge>
                        </td>
                        <td className="px-3 py-3">{order.payment_method || "Unavailable"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      ) : (
        <EmptyState title="Unable to load subscription" body="Please refresh or try again later." />
      )}
    </AcademicShell>
  );
}
