"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, RefreshCcw, Save, Users } from "lucide-react";
import { useRouter } from "next/navigation";

import {
  AcademicShell,
  EmptyState,
  MetricCard,
  PageHeader,
  Panel,
  SectionHeading,
  StatusBadge,
} from "@/components/academic";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { adminBillingApi } from "@/lib/api";
import {
  formatPrice,
  parsePlanFeatures,
  type AdminUserRow,
  type SubscriptionPlan,
  type SubscriptionStats,
} from "@/lib/billing";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";

type Tab = "plans" | "users";

const textareaClass =
  "mt-1 min-h-28 w-full resize-y rounded-md border border-slate-200 bg-white px-3 py-2 font-mono text-xs leading-5 text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-academic-score focus:ring-2 focus:ring-academic-score/25";

const slugTone: Record<string, "sage" | "teal" | "gold" | "slate"> = {
  free: "slate",
  basic: "teal",
  pro: "gold",
  unlimited: "sage",
};

export default function AdminSubscriptionsPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [tab, setTab] = useState<Tab>("plans");
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [featureTexts, setFeatureTexts] = useState<Record<string, string>>({});
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [stats, setStats] = useState<SubscriptionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingPlanId, setSavingPlanId] = useState<string | null>(null);
  const [userQuery, setUserQuery] = useState("");
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const canAdmin = user?.role === "operator" || user?.role === "admin";

  useEffect(() => {
    if (!hasHydrated) return;
    if (!isAuthenticated) {
      router.push("/login");
      return;
    }
    if (!user) fetchUser();
  }, [hasHydrated, isAuthenticated, user, fetchUser, router]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [plansRes, usersRes, statsRes] = await Promise.all([
        adminBillingApi.listPlans(),
        adminBillingApi.listUsers({ limit: 100 }),
        adminBillingApi.getStats(),
      ]);
      const nextPlans = plansRes.data.plans.map((plan) => ({
        ...plan,
        features: parsePlanFeatures(plan.features),
      }));
      setPlans(nextPlans);
      setFeatureTexts(
        Object.fromEntries(nextPlans.map((plan) => [plan.id, JSON.stringify(plan.features, null, 2)])),
      );
      setUsers(usersRes.data.users);
      setStats(statsRes.data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (canAdmin) load();
  }, [canAdmin, load]);

  const filteredUsers = useMemo(() => {
    const q = userQuery.trim().toLowerCase();
    if (!q) return users;
    return users.filter((item) => item.email.toLowerCase().includes(q));
  }, [users, userQuery]);

  const selectedUser = useMemo(
    () => users.find((item) => item.id === selectedUserId) ?? null,
    [users, selectedUserId],
  );

  const updatePlanField = <K extends keyof SubscriptionPlan>(planId: string, field: K, value: SubscriptionPlan[K]) => {
    setPlans((current) =>
      current.map((plan) => (plan.id === planId ? { ...plan, [field]: value } : plan)),
    );
  };

  const savePlan = async (plan: SubscriptionPlan) => {
    setSavingPlanId(plan.id);
    setMessage("");
    try {
      let features = plan.features;
      const rawFeatures = featureTexts[plan.id];
      if (rawFeatures) {
        features = JSON.parse(rawFeatures) as string[];
      }
      await adminBillingApi.updatePlan(plan.id, {
        name: plan.name,
        name_zh: plan.name_zh,
        price_cents: plan.price_cents,
        billing_period_days: plan.billing_period_days,
        credit_limit: plan.credit_limit,
        features,
        sort_order: plan.sort_order,
        active: plan.active,
      });
      setMessage("Saved successfully.");
      await load();
    } catch {
      setMessage("Save failed. Check that the features JSON is valid.");
    } finally {
      setSavingPlanId(null);
    }
  };

  const patchUser = async (userId: string, body: Record<string, unknown>) => {
    setMessage("");
    try {
      await adminBillingApi.patchUser(userId, body);
      setMessage("User subscription updated.");
      await load();
    } catch {
      setMessage("Update failed.");
    }
  };

  if (!hasHydrated || !isAuthenticated || !user) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/admin/subscriptions" userName={user.email} userRole={user.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">You do not have permission to access subscription management.</Panel>
      </AcademicShell>
    );
  }

  return (
    <AcademicShell activePath="/admin/subscriptions" userName={user.email} userRole={user.role} wide>
      <PageHeader
        title="Subscription management"
        description="Configure plans, review user subscriptions, and adjust tiers."
        actions={
          <Button variant="soft" onClick={load} disabled={loading}>
            <RefreshCcw className="mr-2 h-4 w-4" /> Refresh
          </Button>
        }
      />

      {stats ? (
        <section className="grid gap-4 md:grid-cols-3">
          <MetricCard label="Free users" value={String(stats.plan_counts.free ?? 0)} helper="Current Free plan" />
          <MetricCard label="Pro users" value={String(stats.plan_counts.pro ?? 0)} helper="Pro + Unlimited" />
          <MetricCard
            label="Monthly revenue"
            value={formatPrice(stats.monthly_revenue_cents)}
            helper={`${stats.paid_orders_this_month} paid orders`}
          />
        </section>
      ) : null}

      {message ? (
        <Panel className="border-academic-score/30 bg-academic-paper text-sm text-slate-800">{message}</Panel>
      ) : null}

      <div className="flex gap-2">
        <Button variant={tab === "plans" ? "gold" : "soft"} onClick={() => setTab("plans")}>
          Plan settings
        </Button>
        <Button variant={tab === "users" ? "gold" : "soft"} onClick={() => setTab("users")}>
          <Users className="mr-2 h-4 w-4" /> User management
        </Button>
      </div>

      {loading ? (
        <Panel className="flex items-center gap-2 text-slate-600">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading...
        </Panel>
      ) : tab === "plans" ? (
        <div className="grid gap-4">
          {plans.map((plan) => (
            <Panel key={plan.id} tone="paper" className="border-slate-200">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-academic-paper-border pb-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-lg font-semibold text-slate-900">{plan.name_zh}</h3>
                    <StatusBadge tone={slugTone[plan.slug] ?? "slate"}>{plan.slug}</StatusBadge>
                    {!plan.active ? <StatusBadge tone="coral">Inactive</StatusBadge> : null}
                  </div>
                  <p className="mt-1 text-sm text-slate-600">
                    Display price {formatPrice(plan.price_cents)} · Period {plan.billing_period_days} days ·{" "}
                    {plan.credit_limit === null ? "Unlimited credits" : `${plan.credit_limit} credits/month`}
                  </p>
                </div>
                <Button variant="gold" size="sm" disabled={savingPlanId === plan.id} onClick={() => void savePlan(plan)}>
                  {savingPlanId === plan.id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                  Save
                </Button>
              </div>

              <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <Label htmlFor={`${plan.id}-name`}>Name</Label>
                  <Input
                    id={`${plan.id}-name`}
                    value={plan.name_zh}
                    onChange={(e) => updatePlanField(plan.id, "name_zh", e.target.value)}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor={`${plan.id}-price`}>Price (cents)</Label>
                  <Input
                    id={`${plan.id}-price`}
                    type="number"
                    value={plan.price_cents}
                    onChange={(e) => updatePlanField(plan.id, "price_cents", Number(e.target.value))}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor={`${plan.id}-period`}>Period (days)</Label>
                  <Input
                    id={`${plan.id}-period`}
                    type="number"
                    value={plan.billing_period_days}
                    onChange={(e) => updatePlanField(plan.id, "billing_period_days", Number(e.target.value))}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor={`${plan.id}-quota`}>Credit limit (empty = unlimited)</Label>
                  <Input
                    id={`${plan.id}-quota`}
                    value={plan.credit_limit ?? ""}
                    placeholder="Leave empty for unlimited"
                    onChange={(e) =>
                      updatePlanField(plan.id, "credit_limit", e.target.value === "" ? null : Number(e.target.value))
                    }
                    className="mt-1"
                  />
                </div>
              </div>

              <div className="mt-4">
                <Label htmlFor={`${plan.id}-features`}>Features (JSON array)</Label>
                <textarea
                  id={`${plan.id}-features`}
                  className={textareaClass}
                  value={featureTexts[plan.id] ?? "[]"}
                  onChange={(e) => setFeatureTexts((current) => ({ ...current, [plan.id]: e.target.value }))}
                />
                <p className="mt-2 text-xs text-slate-500">Example: [&quot;30 sessions/month&quot;, &quot;AI scoring&quot;]</p>
              </div>

              <label className="mt-4 flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={plan.active}
                  onChange={(e) => updatePlanField(plan.id, "active", e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-academic-score focus:ring-academic-score"
                />
                Show this plan on the pricing page
              </label>
            </Panel>
          ))}
        </div>
      ) : (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
          <Panel>
            <SectionHeading label="User list" labelZh="搜索与订阅管理" />
            <Input
              placeholder="Search email"
              value={userQuery}
              onChange={(e) => setUserQuery(e.target.value)}
              className="mt-4 max-w-md"
            />
            {filteredUsers.length === 0 ? (
              <EmptyState title="No users" body="No users match the current search." />
            ) : (
              <div className="mt-4 overflow-x-auto rounded-lg border border-slate-200">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-3 py-2 font-medium">Email</th>
                      <th className="px-3 py-2 font-medium">Role</th>
                      <th className="px-3 py-2 font-medium">Plan</th>
                      <th className="px-3 py-2 font-medium">Usage</th>
                      <th className="px-3 py-2 font-medium">Expires</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white">
                    {filteredUsers.map((row) => (
                      <tr
                        key={row.id}
                        className={cn(
                          "cursor-pointer border-t border-slate-100 text-slate-800 hover:bg-slate-50",
                          selectedUserId === row.id && "bg-academic-paper",
                        )}
                        onClick={() => setSelectedUserId(row.id)}
                      >
                        <td className="px-3 py-3">{row.email}</td>
                        <td className="px-3 py-3">{row.role}</td>
                        <td className="px-3 py-3">{row.plan_name_zh || "Unavailable"}</td>
                        <td className="px-3 py-3">
                          {row.credits_used ?? 0}
                          {row.credit_limit !== null && row.credit_limit !== undefined ? ` / ${row.credit_limit}` : " / unlimited"}
                        </td>
                        <td className="px-3 py-3">
                          {row.period_end ? new Date(row.period_end).toLocaleDateString("zh-CN") : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel tone="paper">
            <SectionHeading label="User actions" />
            {!selectedUser ? (
              <EmptyState title="Select a user" body="Choose a user from the list to manage their subscription." />
            ) : (
              <div className="mt-4 space-y-4">
                <div className="rounded-lg border border-academic-paper-border bg-white p-3">
                  <p className="text-sm font-semibold text-slate-900">{selectedUser.email}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {selectedUser.role} · {selectedUser.status}
                  </p>
                </div>
                <div className="grid gap-2">
                  <Label>Change plan</Label>
                  <div className="grid grid-cols-2 gap-2">
                    {plans.map((plan) => (
                      <Button
                        key={plan.id}
                        variant={selectedUser.plan_slug === plan.slug ? "gold" : "soft"}
                        size="sm"
                        onClick={() => void patchUser(selectedUser.id, { plan_slug: plan.slug })}
                      >
                        {plan.name_zh}
                      </Button>
                    ))}
                  </div>
                </div>
                <Button variant="soft" className="w-full" onClick={() => void patchUser(selectedUser.id, { reset_credits: true })}>
                  Reset usage
                </Button>
                <Button variant="soft" className="w-full" onClick={() => void patchUser(selectedUser.id, { extend_period_days: 30 })}>
                  Extend 30 days
                </Button>
                <div className="grid grid-cols-2 gap-2">
                  <Button variant="teal" size="sm" onClick={() => void patchUser(selectedUser.id, { role: "operator" })}>
                    Set Operator
                  </Button>
                  <Button variant="soft" size="sm" onClick={() => void patchUser(selectedUser.id, { role: "user" })}>
                    Set User
                  </Button>
                </div>
                <Button
                  variant="dangerOutline"
                  className="w-full"
                  onClick={() =>
                    void patchUser(selectedUser.id, {
                      status: selectedUser.status === "active" ? "disabled" : "active",
                    })
                  }
                >
                  {selectedUser.status === "active" ? "Disable user" : "Enable user"}
                </Button>
              </div>
            )}
          </Panel>
        </div>
      )}
    </AcademicShell>
  );
}
