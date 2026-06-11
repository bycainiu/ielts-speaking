"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { ensureValidAccessToken, handleSessionExpired } from "@/lib/authSession";
import { isPublicPath } from "@/lib/publicPaths";
import { useAuthStore } from "@/store/authStore";

export function AuthSessionGuard() {
  const pathname = usePathname();
  const router = useRouter();
  const { hasHydrated, isAuthenticated } = useAuthStore();

  useEffect(() => {
    if (!hasHydrated || !isAuthenticated || isPublicPath(pathname)) return;

    let cancelled = false;

    const maintainSession = async () => {
      const token = await ensureValidAccessToken();
      if (!cancelled && !token) {
        handleSessionExpired();
      }
    };

    void maintainSession();
    const intervalId = window.setInterval(() => {
      void maintainSession();
    }, 60_000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [hasHydrated, isAuthenticated, pathname]);

  useEffect(() => {
    if (!hasHydrated || isAuthenticated || isPublicPath(pathname)) return;
    router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [hasHydrated, isAuthenticated, pathname, router]);

  return null;
}
