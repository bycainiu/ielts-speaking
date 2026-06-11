"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, CreditCard, Loader2, Smartphone, Wallet } from "lucide-react";

import { AcademicShell, PageHeader, Panel, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { billingApi } from "@/lib/api";
import { formatPrice, parsePlanFeatures, type SubscriptionPlan } from "@/lib/billing";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";

const paymentMethods = [
  { id: "card", label: "信用卡", icon: CreditCard },
  { id: "alipay", label: "支付宝", icon: Wallet },
  { id: "wechat", label: "微信支付", icon: Smartphone },
];

export default function CheckoutPageClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const planSlug = searchParams.get("plan") || "pro";
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [method, setMethod] = useState("card");
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!hasHydrated) return;
    if (!isAuthenticated) {
      router.push(`/login?next=${encodeURIComponent(`/pricing/checkout?plan=${planSlug}`)}`);
      return;
    }
    if (!user) fetchUser();
  }, [hasHydrated, isAuthenticated, user, fetchUser, router, planSlug]);

  useEffect(() => {
    billingApi
      .listPlans()
      .then((res) =>
        setPlans(
          res.data.plans.map((plan) => ({
            ...plan,
            features: parsePlanFeatures(plan.features),
          })),
        ),
      )
      .finally(() => setLoading(false));
  }, []);

  const plan = useMemo(() => plans.find((p) => p.slug === planSlug), [plans, planSlug]);

  const handlePay = async (event: FormEvent) => {
    event.preventDefault();
    if (!plan || plan.slug === "free") return;
    setPaying(true);
    setError("");
    try {
      const { data } = await billingApi.createCheckout(plan.slug);
      await billingApi.confirmCheckout(data.order.id, method);
      setSuccess(true);
      setTimeout(() => router.push("/settings/subscription"), 1800);
    } catch {
      setError("模拟支付失败，请重试");
    } finally {
      setPaying(false);
    }
  };

  if (!hasHydrated || !isAuthenticated || !user) return null;

  if (success) {
    return (
      <AcademicShell activePath="/settings/subscription" userName={user.email} userRole={user.role}>
        <Panel className="flex flex-col items-center py-16 text-center">
          <CheckCircle2 className="h-16 w-16 text-[#4F8A6B]" />
          <h2 className="mt-4 text-2xl font-semibold text-slate-900">支付成功</h2>
          <p className="mt-2 text-slate-600">订阅已激活，正在跳转到订阅管理…</p>
        </Panel>
      </AcademicShell>
    );
  }

  return (
    <AcademicShell activePath="/settings/subscription" userName={user.email} userRole={user.role}>
      <PageHeader
        title="确认支付"
        description="当前为模拟支付流程，不会产生真实扣款。"
        actions={
          <Button asChild variant="soft">
            <Link href="/pricing/subscribe">返回选套餐</Link>
          </Button>
        }
      />

      {loading || !plan ? (
        <Panel className="flex items-center gap-2 text-slate-600">
          <Loader2 className="h-4 w-4 animate-spin" /> 加载订单…
        </Panel>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
          <Panel>
            <form onSubmit={handlePay} className="space-y-6">
              <div>
                <Label className="text-slate-700">支付方式</Label>
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  {paymentMethods.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setMethod(item.id)}
                      className={cn(
                        "flex items-center gap-2 rounded-lg border px-4 py-3 text-sm",
                        method === item.id ? "border-[#D4AF37] bg-[#F7F4EA]" : "border-slate-200 bg-white",
                      )}
                    >
                      <item.icon className="h-4 w-4" />
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              {method === "card" ? (
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <Label htmlFor="card-number">卡号（模拟）</Label>
                    <Input id="card-number" placeholder="4242 4242 4242 4242" className="mt-1" />
                  </div>
                  <div>
                    <Label htmlFor="expiry">有效期</Label>
                    <Input id="expiry" placeholder="12/28" className="mt-1" />
                  </div>
                  <div>
                    <Label htmlFor="cvc">CVC</Label>
                    <Input id="cvc" placeholder="123" className="mt-1" />
                  </div>
                </div>
              ) : (
                <Panel className="bg-slate-50 text-sm text-slate-600">
                  点击确认后将模拟 {method === "alipay" ? "支付宝" : "微信"} 扫码支付成功。
                </Panel>
              )}

              {error ? <p className="text-sm text-red-600">{error}</p> : null}

              <Button type="submit" variant="gold" disabled={paying} className="w-full sm:w-auto">
                {paying ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 处理中…
                  </>
                ) : (
                  `确认支付 ${formatPrice(plan.price_cents)}`
                )}
              </Button>
            </form>
          </Panel>

          <Panel>
            <p className="text-sm text-slate-500">订单摘要</p>
            <h3 className="mt-1 text-xl font-semibold text-slate-900">{plan.name_zh}</h3>
            <p className="mt-4 text-3xl font-serif text-[#0B132B]">{formatPrice(plan.price_cents)}</p>
            <p className="mt-1 text-sm text-slate-600">计费周期 {plan.billing_period_days} 天</p>
            <StatusBadge tone="gold" className="mt-4">
              模拟支付
            </StatusBadge>
            <ul className="mt-6 space-y-2 text-sm text-slate-600">
              {plan.features.map((feature) => (
                <li key={feature}>✓ {feature}</li>
              ))}
            </ul>
          </Panel>
        </div>
      )}
    </AcademicShell>
  );
}
