"use client";

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { AdminSessionContext } from "@/lib/adminSessionContext";

type SessionContextsResponse = {
  contexts: AdminSessionContext[];
};

export function useAdminSessionContexts(sessionIds: string[], enabled: boolean) {
  const [contextMap, setContextMap] = useState<Record<string, AdminSessionContext>>({});
  const [loading, setLoading] = useState(false);

  const normalizedIds = useMemo(
    () =>
      Array.from(
        new Set(
          sessionIds
            .map((item) => item.trim())
            .filter(Boolean),
        ),
      ),
    [sessionIds],
  );
  const idsKey = normalizedIds.join(",");

  useEffect(() => {
    if (!enabled || normalizedIds.length === 0) {
      setContextMap({});
      setLoading(false);
      return;
    }

    let cancelled = false;
    async function loadContexts() {
      setLoading(true);
      try {
        const response = await api.get<SessionContextsResponse>("/admin/sessions/contexts", {
          params: { ids: idsKey },
        });
        if (cancelled) return;
        const nextMap = Object.fromEntries((response.data.contexts ?? []).map((item) => [item.session_id, item]));
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
  }, [enabled, idsKey, normalizedIds.length]);

  return { contextMap, loading };
}
