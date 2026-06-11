import Link from "next/link";
import { FileQuestion, Home } from "lucide-react";

export default function NotFoundPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-10 text-academic-navy">
      <section className="w-full max-w-[520px] rounded-lg border border-slate-200 bg-white p-6 text-center shadow-sm">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-lg bg-academic-navy text-academic-score">
          <FileQuestion className="h-6 w-6" />
        </span>
        <p className="mt-5 text-xs font-semibold uppercase tracking-wide text-academic-accent">Page not found</p>
        <h1 className="mt-2 font-serif text-3xl text-academic-navy">页面不存在</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          当前链接没有对应页面，可能是会话已删除、报告尚未生成，或地址输入有误。
        </p>
        <Link
          href="/practice"
          className="mt-5 inline-flex h-10 items-center justify-center rounded-md border border-academic-score/35 bg-academic-score-soft px-4 text-sm font-semibold text-amber-800 transition-colors hover:bg-academic-paper"
        >
          <Home className="mr-2 h-4 w-4" />
          返回练习台
        </Link>
      </section>
    </main>
  );
}
