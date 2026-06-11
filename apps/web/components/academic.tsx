import Link from "next/link";
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  BookOpenCheck,
  BrainCircuit,
  Database,
  FileText,
  History,
  Home,
  CreditCard,
  LayoutDashboard,
  Mic2,
  ScrollText,
  Settings2,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  UserRound,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { LearnerSidebarCard } from "@/components/learner/LearnerSidebarCard";

type NavItem = {
  href: string;
  label: string;
  labelZh: string;
  icon: LucideIcon;
  admin?: boolean;
  disabled?: boolean;
};

const navItems: NavItem[] = [
  { href: "/practice", label: "Practice", labelZh: "练习", icon: Home },
  { href: "/background", label: "Profile", labelZh: "画像", icon: UserRound },
  { href: "/knowledge", label: "Knowledge", labelZh: "资料", icon: Database },
  { href: "/history", label: "Reports", labelZh: "复盘", icon: History },
  { href: "/pronunciation", label: "Pronunciation", labelZh: "发音", icon: Mic2 },
  { href: "/settings/subscription", label: "Subscription", labelZh: "订阅", icon: CreditCard },
  { href: "/admin", label: "Console", labelZh: "总览", icon: LayoutDashboard, admin: true },
  { href: "/admin/questions", label: "Questions", labelZh: "题库", icon: BookOpenCheck, admin: true },
  { href: "/admin/knowledge", label: "Knowledge", labelZh: "知识库", icon: Database, admin: true },
  { href: "/admin/knowledge/imports", label: "Imports", labelZh: "导入", icon: FileText, admin: true },
  { href: "/admin/prompts", label: "Prompts", labelZh: "提示词", icon: Sparkles, admin: true },
  { href: "/admin/review", label: "Review", labelZh: "审核", icon: ShieldCheck, admin: true },
  { href: "/admin/audit", label: "Audit", labelZh: "审计", icon: ScrollText, admin: true },
  { href: "/admin/observability", label: "Observability", labelZh: "观测", icon: Activity, admin: true },
  { href: "/admin/agent-console", label: "Agent Console", labelZh: "实时", icon: TerminalSquare, admin: true },
  { href: "/admin/calibration", label: "Calibration", labelZh: "校准", icon: BarChart3, admin: true },
  { href: "/admin/subscriptions", label: "Subscriptions", labelZh: "订阅", icon: CreditCard, admin: true },
];

export function AcademicShell({
  children,
  activePath,
  userName,
  userRole,
  headerSlot,
  className,
  wide = false,
}: {
  children: ReactNode;
  activePath: string;
  userName?: string;
  userRole?: string;
  headerSlot?: ReactNode;
  className?: string;
  wide?: boolean;
}) {
  const canAdmin = userRole === "operator" || userRole === "admin";
  const visibleItems = navItems.filter((item) => !item.admin || canAdmin);

  return (
    <div className="min-h-screen overflow-x-hidden bg-background text-foreground">
      <div className="pointer-events-none fixed inset-0 z-0 bg-[linear-gradient(160deg,hsl(var(--academic-accent-soft)/0.45)_0%,transparent_42%,hsl(var(--academic-paper)/0.8)_100%)]" />
      <div className="relative z-10 grid min-h-screen lg:grid-cols-[216px_minmax(0,1fr)]">
        <aside className="hidden min-h-screen flex-col border-r border-slate-200/80 bg-white/90 px-3 py-5 shadow-[8px_0_24px_rgba(15,23,42,0.03)] backdrop-blur-xl lg:flex">
          <Link href="/practice" className="flex items-center gap-3 rounded-lg px-2 py-2 text-academic-navy">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-academic-navy text-white">
              <Mic2 className="h-5 w-5" />
            </span>
            <span>
              <span className="block text-sm font-semibold leading-4">IELTS Speaking</span>
              <span className="text-xs text-slate-500">Agent Studio</span>
            </span>
          </Link>

          <nav className="mt-8 grid gap-1">
            {visibleItems.map((item) => (
              <AcademicNavLink key={item.href} item={item} active={isActiveNavItem(activePath, item.href)} />
            ))}
          </nav>

          <div className="mt-6 space-y-3">
            <LearnerSidebarCard userName={userName} userRole={userRole} />
            <div className="rounded-lg border border-slate-200 bg-academic-paper p-3">
              <p className="text-xs font-semibold uppercase text-slate-600">Study Guardrail</p>
              <p className="mt-2 text-xs leading-5 text-slate-600">
                AI scoring is for practice reference only. 模拟评分仅供练习参考。
              </p>
            </div>
          </div>
        </aside>

        <main className={cn("min-w-0 max-w-full overflow-x-hidden px-3 py-4 sm:px-4 lg:px-5 xl:px-6", className)}>
          <div className="mb-4 flex items-center justify-between rounded-lg border border-slate-200 bg-white/90 px-3 py-3 shadow-sm backdrop-blur lg:hidden">
            <Link href="/practice" className="flex items-center gap-2 font-semibold text-academic-navy">
              <Mic2 className="h-5 w-5 text-academic-accent" />
              IELTS Speaking
            </Link>
            {headerSlot}
          </div>
          <div className={cn("mx-auto flex w-full min-w-0 flex-col gap-5", wide ? "max-w-[1720px]" : "max-w-[1580px]")}>{children}</div>
        </main>
      </div>
    </div>
  );
}

function isActiveNavItem(activePath: string, href: string) {
  if (href === "/admin") return activePath === "/admin";
  if (href === "/admin/knowledge") return activePath === "/admin/knowledge";
  return activePath === href || activePath.startsWith(`${href}/`);
}

function AcademicNavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  const content = (
    <span
      className={cn(
        "flex min-h-10 items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-academic-navy text-white shadow-sm"
          : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
        item.disabled && "cursor-not-allowed opacity-50 hover:bg-transparent",
      )}
    >
      <Icon className={cn("h-4 w-4 shrink-0", active ? "text-white" : "text-slate-400")} />
      <span className="min-w-0">
        <span className="block truncate leading-4">{item.label}</span>
        <span className={cn("text-[11px]", active ? "text-slate-300" : "text-slate-400")}>{item.labelZh}</span>
      </span>
    </span>
  );

  if (item.disabled) return content;
  return <Link href={item.href}>{content}</Link>;
}

export function PageHeader({
  eyebrow,
  title,
  titleZh,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  titleZh?: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 rounded-lg border border-slate-200 bg-white/95 p-5 shadow-sm backdrop-blur sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="text-xs font-semibold uppercase tracking-wide text-academic-accent">{eyebrow}</p>}
        <h1 className="mt-1 font-serif text-3xl leading-tight text-academic-navy sm:text-4xl">
          {title}
          {titleZh && <span className="ml-2 align-middle text-base font-sans font-semibold text-slate-500">{titleZh}</span>}
        </h1>
        {description && <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Panel({
  children,
  className,
  tone = "light",
}: {
  children: ReactNode;
  className?: string;
  tone?: "light" | "dark" | "paper";
}) {
  return (
    <section
      className={cn(
        "min-w-0 max-w-full rounded-lg border p-5 shadow-sm",
        tone === "light" && "border-slate-200 bg-white",
        tone === "paper" && "border-academic-paper-border bg-academic-paper",
        tone === "dark" && "border-white/10 bg-academic-navy text-white shadow-[0_18px_50px_rgba(11,19,43,0.18)]",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function DetailDialog({
  open,
  title,
  titleZh,
  description,
  actions,
  children,
  className,
  onClose,
}: {
  open: boolean;
  title: string;
  titleZh?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  onClose: () => void;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" aria-label="关闭详情窗口" className="absolute inset-0 cursor-default bg-slate-950/45 backdrop-blur-sm" onClick={onClose} />
      <section
        className={cn(
          "relative z-10 flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.28)]",
          className,
        )}
      >
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 sm:px-5">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-academic-navy">
              {title}
              {titleZh && <span className="ml-2 text-xs font-medium text-slate-500">{titleZh}</span>}
            </h2>
            {description && <p className="mt-1 break-words text-xs leading-5 text-slate-500">{description}</p>}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {actions}
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-academic-navy focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-academic-accent"
              aria-label="关闭"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">{children}</div>
      </section>
    </div>
  );
}

export function SectionHeading({
  icon: Icon,
  label,
  labelZh,
  action,
}: {
  icon?: LucideIcon;
  label: string;
  labelZh?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex min-w-0 items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        {Icon && <Icon className="h-4 w-4 text-academic-accent" />}
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">
          {label}
          {labelZh && <span className="ml-2 text-xs font-medium text-slate-400">{labelZh}</span>}
        </h2>
      </div>
      {action}
    </div>
  );
}

export function StatusBadge({
  children,
  tone = "slate",
  className,
}: {
  children: ReactNode;
  tone?: "gold" | "teal" | "sage" | "coral" | "red" | "slate" | "blue";
  className?: string;
}) {
  const tones = {
    gold: "border-amber-200 bg-academic-score-soft text-amber-800",
    teal: "border-blue-200 bg-academic-accent-soft text-blue-800",
    sage: "border-emerald-200 bg-academic-success-soft text-emerald-800",
    coral: "border-orange-200 bg-academic-warn-soft text-orange-800",
    red: "border-red-200 bg-red-50 text-red-700",
    slate: "border-slate-200 bg-slate-100 text-slate-600",
    blue: "border-blue-200 bg-blue-50 text-blue-700",
  };

  return (
    <span className={cn("inline-flex max-w-full items-center rounded-md border px-2 py-1 text-xs font-semibold leading-none", tones[tone], className)}>
      {children}
    </span>
  );
}

export function MetricCard({
  icon: Icon,
  label,
  value,
  helper,
  tone = "light",
}: {
  icon?: LucideIcon;
  label: string;
  value: string;
  helper?: string;
  tone?: "light" | "gold" | "teal" | "sage";
}) {
  const toneClass = {
    light: "border-slate-200 bg-white",
    gold: "border-amber-200 bg-academic-score-soft",
    teal: "border-blue-200 bg-academic-accent-soft",
    sage: "border-emerald-200 bg-academic-success-soft",
  }[tone];

  return (
    <div className={cn("rounded-lg border p-4 shadow-sm", toneClass)}>
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {Icon && <Icon className="h-4 w-4 text-academic-accent" />}
        {label}
      </div>
      <p className="mt-3 font-serif text-3xl text-academic-navy">{value}</p>
      {helper && <p className="mt-1 text-xs leading-5 text-slate-500">{helper}</p>}
    </div>
  );
}

export function EmptyState({
  icon: Icon = ScrollText,
  title,
  body,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
      <Icon className="mx-auto h-8 w-8 text-slate-400" />
      <h3 className="mt-3 text-sm font-semibold text-slate-900">{title}</h3>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">{body}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function MiniSparkline({ values, className }: { values: number[]; className?: string }) {
  const width = 180;
  const height = 54;
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 9);
  const range = Math.max(max - min, 1);
  const points = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
    const y = height - ((value - min) / range) * (height - 8) - 4;
    return `${x},${y}`;
  });

  return (
    <svg className={cn("h-14 w-full overflow-visible", className)} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Score trend">
      <polyline points={points.join(" ")} fill="none" stroke="hsl(var(--academic-accent))" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      {values.map((value, index) => {
        const [x, y] = points[index].split(",").map(Number);
        return <circle key={`${value}-${index}`} cx={x} cy={y} r="3.5" fill="hsl(var(--academic-accent))" />;
      })}
    </svg>
  );
}

export function Waveform({ active = false, bars = 36, className }: { active?: boolean; bars?: number; className?: string }) {
  return (
    <div className={cn("flex h-12 max-w-full items-center gap-1 overflow-hidden", className)} aria-hidden="true">
      {Array.from({ length: bars }).map((_, index) => {
        const height = 18 + ((index * 17) % 28);
        return (
          <span
            key={index}
            className={cn(
              "w-1.5 rounded-full transition-colors",
              active ? "bg-red-500 animate-pulse" : "bg-academic-accent/35",
            )}
            style={{
              height,
              animationDelay: `${index * 45}ms`,
            }}
          />
        );
      })}
    </div>
  );
}

export function InlineKpi({
  icon: Icon = BrainCircuit,
  label,
  value,
}: {
  icon?: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <span className="flex min-w-0 items-center gap-2 text-xs font-medium text-slate-500">
        <Icon className="h-4 w-4 shrink-0 text-academic-accent" />
        <span className="truncate">{label}</span>
      </span>
      <span className="min-w-0 max-w-[58%] break-words text-right text-sm font-semibold text-slate-900">{value}</span>
    </div>
  );
}

export function MonoBlock({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <pre className={cn("max-h-72 overflow-auto rounded-lg border border-slate-200 bg-slate-950 p-3 text-xs leading-5 text-slate-100", className)}>
      {children}
    </pre>
  );
}

export function SidebarIconButton({
  href,
  title,
  icon: Icon = Settings2,
}: {
  href: string;
  title: string;
  icon?: LucideIcon;
}) {
  return (
    <Link
      href={href}
      title={title}
      className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 transition-colors hover:border-slate-300 hover:text-academic-navy"
    >
      <Icon className="h-4 w-4" />
    </Link>
  );
}

export function DividerLabel({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
      <span className="h-px flex-1 bg-slate-200" />
      {children}
      <span className="h-px flex-1 bg-slate-200" />
    </div>
  );
}

export function DocumentIcon() {
  return <FileText className="h-4 w-4" />;
}
