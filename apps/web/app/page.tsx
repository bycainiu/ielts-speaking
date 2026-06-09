"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Mic2 } from "lucide-react";

import { useAuthStore } from "@/store/authStore";

export default function HomePage() {
  const router = useRouter();
  const { hasHydrated, isAuthenticated } = useAuthStore();

  useEffect(() => {
    if (!hasHydrated) return;
    router.replace(isAuthenticated ? "/practice" : "/login");
  }, [hasHydrated, isAuthenticated, router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f5f7fb] px-4 text-[#102033]">
      <div className="rounded-lg border border-[#E9DFC6] bg-[#F7F4EA] p-6 text-center shadow-sm">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-[#0B132B] text-[#D4AF37]">
          <Mic2 className="h-5 w-5" />
        </div>
        <h1 className="mt-4 font-serif text-2xl text-[#0B132B]">IELTS Speaking</h1>
        <p className="mt-2 flex items-center justify-center text-sm text-slate-600">
          <Loader2 className="mr-2 h-4 w-4 animate-spin text-[#D4AF37]" />
          Opening workspace / 正在进入练习台
        </p>
      </div>
    </main>
  );
}
