"use client";

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { AdminUserContext } from "@/lib/adminSessionContext";

type UserContextsResponse = {
  contexts: AdminUserContext[];
};

export function useAdminUserContexts(userHashes: string[], enabled: boolean) {
  const [contextMap, setContextMap] = useState<Record<string, AdminUserContext>>({});
  const [loading, setLoading] = useState(false);

  const normalizedHashes = useMemo(
    () =>
      Array.from(
        new Set(
          userHashes
            .map((item) => item.trim())
            .filter(Boolean),
        ),
      ),
    [userHashes],
  );
  const hashesKey = normalizedHashes.join(",");

  useEffect(() => {
    if (!enabled || normalizedHashes.length === 0) {
      setContextMap({});
      setLoading(false);
      return;
    }

    let cancelled = false;
    async function loadContexts() {
      setLoading(true);
      try {
        const response = await api.get<UserContextsResponse>("/admin/sessions/user-contexts", {
          params: { hashes: hashesKey },
        });
        if (cancelled) return;
        const nextMap = Object.fromEntries((response.data.contexts ?? []).map((item) => [item.user_hash, item]));
        setContextMap(nextMap);
      } catch {
        if (!cancelled) {
          setContextMap({});
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadContexts();
    return () => {
      cancelled = true;
    };
  }, [enabled, hashesKey, normalizedHashes.length]);

  return { contextMap, loading };
}
