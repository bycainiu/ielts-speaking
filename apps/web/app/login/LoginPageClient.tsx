"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, Loader2, LogIn, Mic2, ShieldCheck } from "lucide-react";

import { MiniSparkline, StatusBadge } from "@/components/academic";
import { ImageCaptcha, type ImageCaptchaValue } from "@/components/auth/ImageCaptcha";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

type ApiError = {
  response?: {
    data?: {
      message?: string;
    };
  };
};

const inputClass =
  "h-11 border-slate-200 bg-white text-slate-900 placeholder:text-slate-400 focus-visible:ring-academic-score focus-visible:ring-offset-0";

export default function LoginPageClient() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [captcha, setCaptcha] = useState<ImageCaptchaValue>({ captchaId: "", captchaAnswer: "" });
  const [captchaReloadToken, setCaptchaReloadToken] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();
  const setTokens = useAuthStore((state) => state.setTokens);
  const fetchUser = useAuthStore((state) => state.fetchUser);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const res = await authApi.post("/auth/login", {
        email,
        password,
        captcha_id: captcha.captchaId,
        captcha_answer: captcha.captchaAnswer,
      });
      setTokens(res.data.token.access_token, res.data.token.refresh_token, res.data.token.expires_at);
      await fetchUser();
      const nextPath = searchParams.get("next");
      router.push(nextPath && nextPath.startsWith("/") && !nextPath.startsWith("//") ? nextPath : "/practice");
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Request failed.");
      setCaptchaReloadToken((value) => value + 1);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-academic-navy">
      <div className="pointer-events-none fixed inset-0 bg-[linear-gradient(135deg,rgba(58,124,165,0.12),rgba(247,244,234,0.72)_42%,rgba(212,175,55,0.10))]" />
      <main className="relative z-10 flex min-h-screen items-center justify-center px-4 py-8">
        <div className="grid w-full max-w-5xl gap-6 lg:grid-cols-[minmax(0,1fr)_420px] lg:items-center">
          <section className="hidden min-w-0 lg:block">
            <Link href="/practice" className="inline-flex items-center gap-3 rounded-lg px-1 py-2 text-academic-navy">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-academic-navy text-academic-score">
                <Mic2 className="h-5 w-5" />
              </span>
              <span>
                <span className="block text-sm font-semibold leading-4">IELTS Speaking</span>
                <span className="text-xs text-slate-500">Agent Studio</span>
              </span>
            </Link>

            <div className="mt-12 max-w-xl">
              <StatusBadge tone="teal">Academic Live Studio</StatusBadge>
              <h1 className="mt-4 font-serif text-5xl leading-tight text-academic-navy">
                Welcome back
                <span className="block text-2xl font-sans font-semibold text-academic-score">欢迎回来</span>
              </h1>
              <p className="mt-4 max-w-lg text-sm leading-6 text-slate-600">
                Continue IELTS speaking mock exams, replay reports, and pronunciation drills from one focused workspace.
              </p>
            </div>

            <div className="mt-10 grid max-w-lg grid-cols-2 gap-3">
              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-xs font-semibold uppercase text-slate-500">Score trend</p>
                <MiniSparkline values={[5.5, 6, 6, 6.5, 7]} className="mt-3" />
              </div>
              <div className="rounded-lg border border-academic-paper-border bg-academic-paper p-4 shadow-sm">
                <ShieldCheck className="h-5 w-5 text-emerald-600" />
                <p className="mt-3 text-sm font-semibold text-academic-navy">Practice reference</p>
                <p className="mt-1 text-xs leading-5 text-slate-600">AI scoring is not an official IELTS result.</p>
              </div>
            </div>
          </section>

          <section className="mx-auto w-full max-w-[420px] rounded-lg border border-academic-paper-border bg-academic-paper/95 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.12)] backdrop-blur">
            <div className="mb-6 text-center">
              <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-academic-navy text-academic-score">
                <Mic2 className="h-5 w-5" />
              </div>
              <h2 className="mt-4 font-serif text-3xl text-academic-navy">Welcome back</h2>
              <p className="mt-1 text-sm text-slate-600">登录后继续练习、复盘与订阅管理</p>
            </div>

            <form onSubmit={handleLogin} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email" className="text-slate-700">
                  Email / 邮箱
                </Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className={inputClass}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password" className="text-slate-700">
                  Password / 密码
                </Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className={inputClass}
                />
              </div>

              <ImageCaptcha
                value={captcha}
                onChange={setCaptcha}
                disabled={loading}
                reloadToken={captchaReloadToken}
                inputClassName={inputClass}
              />

              {error && (
                <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm leading-5 text-red-700">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <Button
                type="submit"
                variant="gold"
                className="h-11 w-full"
                disabled={loading || !captcha.captchaId || !captcha.captchaAnswer.trim()}
              >
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <LogIn className="mr-2 h-4 w-4" />}
                {loading ? "Signing in..." : "Sign in / 登录"}
              </Button>
            </form>

            <div className="mt-5 text-center text-sm text-slate-600">
              Don&apos;t have an account?{" "}
              <Button asChild variant="link" className="h-auto p-0 text-academic-accent hover:text-academic-navy">
                <Link href="/register">Sign up / 注册</Link>
              </Button>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
