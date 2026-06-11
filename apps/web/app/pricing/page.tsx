"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Activity, BrainCircuit, Mic2, ShieldCheck, Sparkles, Zap } from "lucide-react";

import { MarketingSection, MarketingShell, PricingCard } from "@/components/marketing/MarketingShell";
import { Button } from "@/components/ui/button";
import { billingApi } from "@/lib/api";
import { parsePlanFeatures, type SubscriptionPlan } from "@/lib/billing";

const featureCards = [
  {
    icon: Mic2,
    title: "实时模考体验",
    body: "Multi-Agent 考官编排完整 Part 1–3 流程，贴近真实考场节奏。",
  },
  {
    icon: BrainCircuit,
    title: "多维 AI 评分",
    body: "流利度、词汇、语法、发音四维反馈，附证据片段与改进建议。",
  },
  {
    icon: Activity,
    title: "Agent 可观测",
    body: "练习过程透明可追溯，帮助理解 AI 如何评估你的回答。",
  },
];

const faqs = [
  {
    q: "什么是「练习额度」？",
    a: "每个订阅周期内可用于完成练习的次数。完整模考消耗 3 次，Part 或话题练习各消耗 1 次。",
  },
  {
    q: "未完成练习会扣额度吗？",
    a: "不会。只有提交并完成评分（finish）的练习才会扣减额度，取消不计费。",
  },
  {
    q: "可以随时升级吗？",
    a: "可以。升级后立即生效，新周期从支付确认时开始，额度重置。",
  },
  {
    q: "目前支持真实支付吗？",
    a: "当前为模拟支付流程，用于演示订阅体验；正式支付通道将在后续版本接入。",
  },
];

export default function PricingPage() {
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    billingApi
      .listPlans()
      .then((res) => {
        setPlans(
          res.data.plans.map((plan) => ({
            ...plan,
            features: parsePlanFeatures(plan.features),
          })),
        );
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <MarketingShell>
      <section className="relative overflow-hidden px-4 pb-24 pt-20 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="max-w-3xl"
          >
            <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-1.5 text-xs text-white/70">
              <Sparkles className="h-3.5 w-3.5 text-[#D4AF37]" />
              Agentic IELTS Speaking Practice
            </p>
            <h1 className="mt-6 font-serif text-4xl leading-tight text-white sm:text-6xl">
              用 AI Agent 练出
              <span className="bg-gradient-to-r from-[#D4AF37] to-[#7ec8e3] bg-clip-text text-transparent"> 考场级口语</span>
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-white/70">
              像 Warp 编排 coding agents 一样，我们编排 Examiner、Planner 与 Scorer，为你提供可观测、可复盘、可量化的雅思口语练习体验。
            </p>
            <div className="mt-10 flex flex-wrap gap-3">
              <Button asChild variant="gold" size="lg">
                <Link href="/register">免费开始</Link>
              </Button>
              <Button asChild variant="soft" size="lg" className="border-white/15 bg-white/5 text-white hover:bg-white/10">
                <a href="#pricing">查看套餐</a>
              </Button>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.7 }}
            className="mt-16 grid gap-4 rounded-2xl border border-white/10 bg-gradient-to-br from-white/10 to-white/5 p-6 sm:grid-cols-3"
          >
            {[
              { label: "练习会话", value: "10k+" },
              { label: "Agent 调用", value: "50k+" },
              { label: "平均提分", value: "+0.8 band" },
            ].map((item) => (
              <div key={item.label} className="rounded-xl bg-[#0B132B]/50 p-5 text-center">
                <p className="font-serif text-3xl text-[#D4AF37]">{item.value}</p>
                <p className="mt-1 text-sm text-white/60">{item.label}</p>
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      <MarketingSection
        id="features"
        eyebrow="Why Agent Studio"
        title="更智能的练习，更可控的体验"
        description="从实时对话到评分报告，全流程由 Agent 协作完成，让你始终知道 AI 在做什么。"
        dark
      >
        <div className="grid gap-6 md:grid-cols-3">
          {featureCards.map((card, index) => (
            <motion.div
              key={card.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.1 }}
              className="rounded-2xl border border-white/10 bg-white/5 p-6"
            >
              <card.icon className="h-8 w-8 text-[#D4AF37]" />
              <h3 className="mt-4 text-lg font-semibold text-white">{card.title}</h3>
              <p className="mt-2 text-sm leading-6 text-white/65">{card.body}</p>
            </motion.div>
          ))}
        </div>
      </MarketingSection>

      <MarketingSection
        id="pricing"
        eyebrow="Pricing"
        title="按练习强度选择合适套餐"
        description="参考主流 AI 产品的订阅分层：从免费体验到无限练习，按需升级。"
      >
        {loading ? (
          <p className="text-white/60">加载套餐中…</p>
        ) : (
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {plans.map((plan) => (
              <PricingCard
                key={plan.slug}
                plan={{
                  slug: plan.slug,
                  name_zh: plan.name_zh,
                  price_cents: plan.price_cents,
                  credit_limit: plan.credit_limit,
                  features: plan.features,
                }}
                highlighted={plan.slug === "pro"}
                ctaHref={plan.slug === "free" ? "/register" : `/pricing/subscribe?plan=${plan.slug}`}
                ctaLabel={plan.slug === "free" ? "免费注册" : "选择套餐"}
              />
            ))}
          </div>
        )}
        <p className="mt-8 text-center text-sm text-white/50">
          完整模考 = 3 次额度 · Part/话题练习 = 1 次额度 · Unlimited 套餐不限次数
        </p>
      </MarketingSection>

      <MarketingSection id="faq" eyebrow="FAQ" title="常见问题" dark>
        <div className="grid gap-4 md:grid-cols-2">
          {faqs.map((item) => (
            <div key={item.q} className="rounded-xl border border-white/10 bg-white/5 p-5">
              <h3 className="font-semibold text-white">{item.q}</h3>
              <p className="mt-2 text-sm leading-6 text-white/65">{item.a}</p>
            </div>
          ))}
        </div>
      </MarketingSection>

      <section className="px-4 py-20 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-col items-center rounded-3xl border border-[#D4AF37]/30 bg-gradient-to-r from-[#0B132B] to-[#1a3a52] px-6 py-14 text-center">
          <Zap className="h-10 w-10 text-[#D4AF37]" />
          <h2 className="mt-4 font-serif text-3xl text-white">准备好开始练习了吗？</h2>
          <p className="mt-3 max-w-xl text-white/65">注册即享 Free 套餐，3 次额度体验完整 Agent 模考流程。</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild variant="gold" size="lg">
              <Link href="/register">立即注册</Link>
            </Button>
            <Button asChild variant="soft" size="lg" className="border-white/15 bg-white/5 text-white">
              <Link href="/pricing/subscribe">已有账号，升级套餐</Link>
            </Button>
          </div>
          <p className="mt-6 flex items-center justify-center gap-2 text-xs text-white/45">
            <ShieldCheck className="h-4 w-4" />
            模拟评分仅供练习参考
          </p>
        </div>
      </section>
    </MarketingShell>
  );
}
