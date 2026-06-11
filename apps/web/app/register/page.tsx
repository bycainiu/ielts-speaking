"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Loader2, Mic2, ShieldCheck, UserPlus } from "lucide-react";

import { StatusBadge } from "@/components/academic";
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
  "h-11 border-slate-200 bg-white text-slate-900 placeholder:text-slate-400 focus-visible:ring-[#D4AF37] focus-visible:ring-offset-0";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const setTokens = useAuthStore((state) => state.setTokens);
  const fetchUser = useAuthStore((state) => state.fetchUser);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const res = await authApi.post("/auth/register", {
        email,
        password,
        display_name: displayName,
      });
      setTokens(res.data.token.access_token, res.data.token.refresh_token);
      await fetchUser();
      router.push("/background");
    } catch (err: unknown) {
      const apiError = err as ApiError;
      setError(apiError.response?.data?.message || "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f5f7fb] text-[#102033]">
      <div className="pointer-events-none fixed inset-0 bg-[linear-gradient(135deg,rgba(58,124,165,0.10),rgba(247,244,234,0.74)_45%,rgba(212,175,55,0.10))]" />
      <main className="relative z-10 flex min-h-screen items-center justify-center px-4 py-8">
        <div className="grid w-full max-w-5xl gap-6 lg:grid-cols-[420px_minmax(0,1fr)] lg:items-center">
          <section className="mx-auto w-full max-w-[420px] rounded-lg border border-[#E9DFC6] bg-[#F7F4EA]/95 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.12)] backdrop-blur">
            <div className="mb-6 text-center">
              <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-[#0B132B] text-[#D4AF37]">
                <Mic2 className="h-5 w-5" />
              </div>
              <h2 className="mt-4 font-serif text-3xl text-[#0B132B]">Create account</h2>
              <p className="mt-1 text-sm text-slate-600">创建账号并进入个性化练习</p>
            </div>

            <form onSubmit={handleRegister} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="displayName" className="text-slate-700">
                  Display name / 昵称
                </Label>
                <Input
                  id="displayName"
                  type="text"
                  placeholder="Alex Chen"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  required
                  className={inputClass}
                />
              </div>

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
                  minLength={8}
                  className={inputClass}
                />
                <p className="text-xs text-slate-500">至少 8 位字符，建议包含字母与数字。</p>
              </div>

              {error && (
                <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm leading-5 text-red-700">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <Button type="submit" variant="gold" className="h-11 w-full" disabled={loading}>
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <UserPlus className="mr-2 h-4 w-4" />}
                {loading ? "Creating..." : "Sign up / 注册"}
              </Button>
            </form>

            <div className="mt-5 text-center text-sm text-slate-600">
              Already have an account?{" "}
              <Button asChild variant="link" className="h-auto p-0 text-[#3A7CA5] hover:text-[#0B132B]">
                <Link href="/login">Sign in / 登录</Link>
              </Button>
            </div>
          </section>

          <section className="hidden min-w-0 lg:block">
            <Link href="/practice" className="inline-flex items-center gap-3 rounded-lg px-1 py-2 text-[#0B132B]">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#0B132B] text-[#D4AF37]">
                <Mic2 className="h-5 w-5" />
              </span>
              <span>
                <span className="block text-sm font-semibold leading-4">IELTS Speaking</span>
                <span className="text-xs text-slate-500">Agent Studio</span>
              </span>
            </Link>

            <div className="mt-12 max-w-xl">
              <StatusBadge tone="gold">Guided onboarding</StatusBadge>
              <h1 className="mt-4 font-serif text-5xl leading-tight text-[#0B132B]">
                Build your speaking profile
                <span className="block text-2xl font-sans font-semibold text-[#D4AF37]">建立你的口语画像</span>
              </h1>
              <p className="mt-4 max-w-lg text-sm leading-6 text-slate-600">
                New accounts continue to a profile questionnaire so the examiner can adapt topics, follow-ups, and review focus.
              </p>
            </div>

            <div className="mt-10 grid max-w-lg gap-3">
              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-2 text-sm font-semibold text-[#0B132B]">
                  <ShieldCheck className="h-4 w-4 text-[#4F8A6B]" />
                  Privacy aware / 隐私可控
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-600">
                  Background facts can be excluded from personalization or deleted later from profile controls.
                </p>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
