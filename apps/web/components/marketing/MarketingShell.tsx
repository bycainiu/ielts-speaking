"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { Mic2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function MarketingShell({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-h-screen bg-[#050816] text-white", className)}>
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_top,rgba(58,124,165,0.35),transparent_55%),radial-gradient(ellipse_at_bottom_right,rgba(212,175,55,0.12),transparent_45%)]" />
      <header className="relative z-20 border-b border-white/10 bg-[#0B132B]/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
          <Link href="/pricing" className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#D4AF37] text-[#0B132B]">
              <Mic2 className="h-5 w-5" />
            </span>
            <span>
              <span className="block font-serif text-lg leading-5">IELTS Speaking</span>
              <span className="text-xs text-white/60">Agent Studio</span>
            </span>
          </Link>
          <nav className="hidden items-center gap-8 text-sm text-white/75 md:flex">
            <a href="#features" className="transition hover:text-white">
              产品能力
            </a>
            <a href="#pricing" className="transition hover:text-white">
              定价
            </a>
            <a href="#faq" className="transition hover:text-white">
              常见问题
            </a>
          </nav>
          <div className="flex items-center gap-2">
            <Button asChild variant="soft" className="border-white/15 bg-white/5 text-white hover:bg-white/10">
              <Link href="/login">登录</Link>
            </Button>
            <Button asChild variant="gold">
              <Link href="/register">免费开始</Link>
            </Button>
          </div>
        </div>
      </header>
      <main className="relative z-10">{children}</main>
      <footer className="relative z-10 border-t border-white/10 bg-[#0B132B]/60">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-10 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="text-sm text-white/50">AI 评分仅供练习参考 · 订阅可随时升级</p>
          <div className="flex gap-4 text-sm text-white/60">
            <Link href="/pricing/subscribe" className="hover:text-white">
              选择套餐
            </Link>
            <Link href="/settings/subscription" className="hover:text-white">
              订阅管理
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

export function MarketingSection({
  id,
  eyebrow,
  title,
  description,
  children,
  dark = false,
}: {
  id?: string;
  eyebrow?: string;
  title: string;
  description?: string;
  children: ReactNode;
  dark?: boolean;
}) {
  return (
    <section
      id={id}
      className={cn("px-4 py-20 sm:px-6", dark ? "bg-[#0B132B]/40" : "")}
    >
      <div className="mx-auto max-w-6xl">
        {eyebrow ? (
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#D4AF37]">{eyebrow}</p>
        ) : null}
        <h2 className="mt-3 font-serif text-3xl text-white sm:text-4xl">{title}</h2>
        {description ? <p className="mt-4 max-w-2xl text-base leading-7 text-white/65">{description}</p> : null}
        <div className="mt-10">{children}</div>
      </div>
    </section>
  );
}

export function PricingCard({
  plan,
  highlighted = false,
  ctaHref,
  ctaLabel,
}: {
  plan: {
    slug: string;
    name_zh: string;
    price_cents: number;
    credit_limit: number | null;
    features: string[];
  };
  highlighted?: boolean;
  ctaHref: string;
  ctaLabel: string;
}) {
  return (
    <div
      className={cn(
        "relative flex h-full flex-col rounded-2xl border p-6 transition duration-300 hover:-translate-y-1",
        highlighted
          ? "border-[#D4AF37]/60 bg-gradient-to-b from-[#D4AF37]/15 to-white/5 shadow-[0_20px_60px_rgba(212,175,55,0.15)]"
          : "border-white/10 bg-white/5 hover:border-white/20",
      )}
    >
      {highlighted ? (
        <span className="absolute -top-3 left-6 rounded-full bg-[#D4AF37] px-3 py-1 text-xs font-semibold text-[#0B132B]">
          最受欢迎
        </span>
      ) : null}
      <h3 className="text-xl font-semibold text-white">{plan.name_zh}</h3>
      <p className="mt-4 font-serif text-4xl text-white">
        {plan.price_cents === 0 ? "免费" : `¥${(plan.price_cents / 100).toFixed(0)}`}
        <span className="ml-1 text-sm font-sans text-white/50">/月</span>
      </p>
      <p className="mt-2 text-sm text-white/60">
        {plan.credit_limit === null ? "不限练习次数" : `每月 ${plan.credit_limit} 次练习额度`}
      </p>
      <ul className="mt-6 flex-1 space-y-3 text-sm text-white/75">
        {plan.features.map((feature) => (
          <li key={feature} className="flex gap-2">
            <span className="text-[#D4AF37]">✓</span>
            <span>{feature}</span>
          </li>
        ))}
      </ul>
      <Button asChild variant={highlighted ? "gold" : "soft"} className="mt-8 w-full">
        <Link href={ctaHref}>{ctaLabel}</Link>
      </Button>
    </div>
  );
}
