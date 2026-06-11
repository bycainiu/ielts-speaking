"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  Crown,
  History,
  LayoutDashboard,
  Loader2,
  ScrollText,
  ShieldCheck,
  Sparkles,
  UserRound,
  Users,
  Zap,
} from "lucide-react";

import { StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { billingApi } from "@/lib/api";
import {
  creditUsagePercent,
  formatCreditLimit,
  planTierMeta,
  type SubscriptionSummary,
} from "@/lib/billing";
import { cn } from "@/lib/utils";

const tierSurface: Record<string, string> = {
  slate: "border-slate-200 bg-gradient-to-br from-white via-slate-50 to-slate-100",
  teal: "border-blue-200/60 bg-gradient-to-br from-white via-academic-accent-soft to-academic-paper",
  gold: "border-amber-200/70 bg-gradient-to-br from-academic-score-soft via-white to-academic-paper shadow-sm",
  sage: "border-emerald-200/70 bg-gradient-to-br from-academic-success-soft via-white to-academic-paper shadow-sm",
  admin:
    "border-slate-700/40 bg-gradient-to-br from-academic-navy via-academic-slate to-slate-800 text-white shadow-md",
  operator:
    "border-blue-500/30 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white shadow-md",
};

const tierAccent: Record<string, string> = {
  slate: "text-slate-600",
  teal: "text-blue-700",
  gold: "text-amber-800",
  sage: "text-emerald-800",
  admin: "text-blue-200",
  operator: "text-blue-200",
};

type AdminRoleMeta = {
  role: string;
  label: string;
  labelZh: string;
  tone: "admin" | "operator";
  permissions: string[];
};

function adminRoleMeta(role?: string): AdminRoleMeta {
  if (role === "operator") {
    return {
      role: "operator",
      label: "Operator",
      labelZh: "运营员",
      tone: "operator",
      permissions: ["不限练习额度", "题库与知识库管理", "审核与观测权限", "用户订阅查看"],
    };
  }
  return {
    role: "admin",
    label: "Administrator",
    labelZh: "管理员",
    tone: "admin",
    permissions: ["不限练习额度", "全站管理端权限", "用户/角色/订阅管理", "审计与 Agent 观测"],
  };
}

function AdminSidebarCard({ userName, userRole }: { userName?: string; userRole?: string }) {
  const meta = adminRoleMeta(userRole);
  const isAdmin = meta.role === "admin";

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border p-3.5",
        tierSurface[meta.tone],
        "before:pointer-events-none before:absolute before:-right-10 before:-top-10 before:h-28 before:w-28 before:rounded-full",
        isAdmin ? "before:bg-blue-500/15" : "before:bg-blue-400/20",
      )}
    >
      {isAdmin ? (
        <ShieldCheck className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-blue-300/90" aria-hidden />
      ) : (
        <Sparkles className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-blue-300/90" aria-hidden />
      )}

      <div className="relative flex items-start gap-3">
        <span
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ring-2",
            isAdmin
              ? "bg-white text-academic-navy ring-white/30"
              : "bg-academic-accent text-white ring-blue-400/40",
          )}
        >
          {isAdmin ? <ShieldCheck className="h-4 w-4" /> : <Users className="h-4 w-4" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-white">{userName || "Staff"}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusBadge tone={isAdmin ? "blue" : "teal"} className={isAdmin ? "border-white/20 bg-white/10 text-white" : "border-blue-300/30 bg-blue-500/20 text-blue-100"}>
              {meta.labelZh}
            </StatusBadge>
            <span className={cn("text-[10px] font-semibold uppercase tracking-wide", tierAccent[meta.tone])}>
              {meta.label}
            </span>
          </div>
        </div>
      </div>

      <div className="relative mt-3 rounded-lg border border-white/10 bg-white/5 px-2.5 py-2">
        <p className="text-[11px] font-semibold text-white/90">权限豁免</p>
        <p className="mt-0.5 text-[11px] text-white/65">练习额度 · 无限制 · Privileged</p>
      </div>

      <ul className="relative mt-3 space-y-1 text-[11px] leading-4 text-white/75">
        {meta.permissions.map((item) => (
          <li key={item} className="flex items-start gap-1.5">
            <Zap className={cn("mt-0.5 h-3 w-3 shrink-0", tierAccent[meta.tone])} />
            <span>{item}</span>
          </li>
        ))}
      </ul>

      <div className="relative mt-3 grid grid-cols-2 gap-1.5">
        <Button asChild variant="gold" size="sm" className="h-8 text-[11px]">
          <Link href="/admin">
            <LayoutDashboard className="mr-1 h-3 w-3" />
            管理台
          </Link>
        </Button>
        <Button asChild variant="outline" size="sm" className="h-8 border-white/20 bg-white/10 text-[11px] text-white hover:bg-white/15">
          <Link href="/admin/subscriptions">
            <Users className="mr-1 h-3 w-3" />
            订阅
          </Link>
        </Button>
        <Button asChild variant="outline" size="sm" className="h-8 border-white/20 bg-white/10 text-[11px] text-white hover:bg-white/15">
          <Link href="/admin/audit">
            <ScrollText className="mr-1 h-3 w-3" />
            审计
          </Link>
        </Button>
        <Button asChild variant="outline" size="sm" className="h-8 border-white/20 bg-white/10 text-[11px] text-white hover:bg-white/15">
          <Link href="/background">资料</Link>
        </Button>
      </div>
    </div>
  );
}

export function LearnerSidebarCard({
  userName,
  userRole,
}: {
  userName?: string;
  userRole?: string;
}) {
  const [subscription, setSubscription] = useState<SubscriptionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const canAdmin = userRole === "operator" || userRole === "admin";

  useEffect(() => {
    if (canAdmin) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    void billingApi
      .getSubscription()
      .then((res) => {
        if (!cancelled) setSubscription(res.data.subscription);
      })
      .catch(() => {
        if (!cancelled) setSubscription(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [canAdmin]);

  if (canAdmin) {
    return <AdminSidebarCard userName={userName} userRole={userRole} />;
  }

  const tier = planTierMeta(subscription?.plan.slug ?? "free");
  const used = subscription?.credits_used ?? 0;
  const limit = subscription?.credit_limit ?? subscription?.plan.credit_limit ?? null;
  const usagePct = creditUsagePercent(used, limit);
  const showUpgrade = tier.slug !== "unlimited";

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border p-3.5",
        tierSurface[tier.tone],
        tier.slug === "pro" && "before:pointer-events-none before:absolute before:-right-8 before:-top-8 before:h-24 before:w-24 before:rounded-full before:bg-amber-200/30",
        tier.slug === "unlimited" && "before:pointer-events-none before:absolute before:-left-6 before:bottom-0 before:h-20 before:w-20 before:rounded-full before:bg-emerald-200/40",
      )}
    >
      {tier.slug === "pro" && (
        <Sparkles className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-amber-600/70" aria-hidden />
      )}
      {tier.slug === "unlimited" && (
        <Crown className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-emerald-600/80" aria-hidden />
      )}

      <div className="relative flex items-start gap-3">
        <span
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-academic-navy text-white",
            tier.slug === "unlimited" && "bg-emerald-600 text-white",
          )}
        >
          {tier.slug === "unlimited" ? <Crown className="h-4 w-4" /> : <UserRound className="h-4 w-4" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-slate-900">{userName || "Learner"}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusBadge tone={tier.tone}>{tier.labelZh}</StatusBadge>
            <span className={cn("text-[10px] font-semibold uppercase tracking-wide", tierAccent[tier.tone])}>
              {tier.label}
            </span>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="relative mt-3 flex items-center gap-2 text-xs text-slate-500">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          加载订阅…
        </div>
      ) : (
        <>
          <div className="relative mt-3">
            <div className="flex items-center justify-between text-[11px] font-medium text-slate-600">
              <span>本月额度</span>
              <span>
                {used} / {formatCreditLimit(limit)}
              </span>
            </div>
            {limit !== null ? (
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/80">
                <div
                  className={cn(
                    "h-full rounded-full transition-all",
                    tier.tone === "gold" && "bg-amber-500",
                    tier.tone === "teal" && "bg-academic-accent",
                    tier.tone === "sage" && "bg-emerald-500",
                    tier.tone === "slate" && "bg-slate-400",
                  )}
                  style={{ width: `${Math.max(usagePct, used > 0 ? 8 : 0)}%` }}
                />
              </div>
            ) : (
              <p className="mt-1 text-[11px] font-semibold text-emerald-700">不限次数 · 畅享练习</p>
            )}
          </div>

          <ul className="relative mt-3 space-y-1 text-[11px] leading-4 text-slate-600">
            {tier.permissions.map((item) => (
              <li key={item} className="flex items-start gap-1.5">
                <Zap className={cn("mt-0.5 h-3 w-3 shrink-0", tierAccent[tier.tone])} />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="relative mt-3 grid grid-cols-2 gap-1.5">
        {showUpgrade ? (
          <Button asChild variant="gold" size="sm" className="h-8 text-[11px]">
            <Link href={tier.upgradeHref}>
              <ArrowUpRight className="mr-1 h-3 w-3" />
              升级
            </Link>
          </Button>
        ) : (
          <Button asChild variant="soft" size="sm" className="h-8 text-[11px]">
            <Link href="/settings/subscription">订阅管理</Link>
          </Button>
        )}
        <Button asChild variant="soft" size="sm" className="h-8 text-[11px]">
          <Link href="/background">资料</Link>
        </Button>
        <Button asChild variant="outline" size="sm" className="h-8 border-slate-200 bg-white/80 text-[11px]">
          <Link href="/settings/subscription">订阅设置</Link>
        </Button>
        <Button asChild variant="outline" size="sm" className="h-8 border-slate-200 bg-white/80 text-[11px]">
          <Link href="/history">
            <History className="mr-1 h-3 w-3" />
            报告
          </Link>
        </Button>
      </div>
    </div>
  );
}
