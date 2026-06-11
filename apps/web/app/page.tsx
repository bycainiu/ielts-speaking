"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Mic2 } from "lucide-react";

import { resolveHomeDestination } from "@/lib/publicPaths";
import { useAuthStore } from "@/store/authStore";

export default function HomePage() {
  const router = useRouter();
  const { hasHydrated, isAuthenticated } = useAuthStore();

  useEffect(() => {
    if (!hasHydrated) return;
    router.replace(resolveHomeDestination(isAuthenticated));
  }, [hasHydrated, isAuthenticated, router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 text-academic-navy">
      <div className="rounded-lg border border-academic-paper-border bg-academic-paper p-6 text-center shadow-sm">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-academic-navy text-academic-score">
          <Mic2 className="h-5 w-5" />
        </div>
        <h1 className="mt-4 font-serif text-2xl text-academic-navy">IELTS Speaking</h1>
        <p className="mt-2 flex items-center justify-center text-sm text-slate-600">
          <Loader2 className="mr-2 h-4 w-4 animate-spin text-academic-score" />
          正在进入…
        </p>
      </div>
    </main>
  );
}
