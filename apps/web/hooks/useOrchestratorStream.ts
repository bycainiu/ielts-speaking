import { useCallback, useEffect, useRef, useState } from "react";

import {
  type OrchestratorStreamEvent,
  type AgentStreamStatus,
  isTerminalAgentStreamKind,
  latestAgentStreamSeq,
  mergeAgentStreamEvents,
  parseSseBuffer,
} from "@/lib/orchestratorStream";
import { authenticatedFetch } from "@/lib/authSession";
import { useAuthStore } from "@/store/authStore";

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_BASE_DELAY_MS = 600;
const ORCHESTRATOR_API_PREFIX = "/api/agent-orchestrator";

export function useOrchestratorStream(runId: string, options?: { enabled?: boolean }) {
  const [events, setEvents] = useState<OrchestratorStreamEvent[]>([]);
  const [status, setStatus] = useState<AgentStreamStatus>("idle");
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const latestSeqRef = useRef(0);
  const terminalRef = useRef(false);
  const { accessToken, hasHydrated, isAuthenticated } = useAuthStore();
  const enabled = (options?.enabled ?? true) && Boolean(runId);
  const canConnect = enabled && hasHydrated && isAuthenticated && Boolean(accessToken);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const appendEvents = useCallback((incoming: OrchestratorStreamEvent[]) => {
    if (!incoming.length) return;
    setEvents((current) => {
      const next = mergeAgentStreamEvents(current, incoming);
      latestSeqRef.current = latestAgentStreamSeq(next);
      terminalRef.current = next.some((event) => isTerminalAgentStreamKind(event.kind));
      return next;
    });
  }, []);

  const connect = useCallback(
    async (afterSeq: number) => {
      if (!canConnect || !accessToken || terminalRef.current) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setStatus(afterSeq > 0 ? "reconnecting" : "loading");
      setError("");

      try {
        const replayResponse = await authenticatedFetch(
          `${ORCHESTRATOR_API_PREFIX}/agent/runs/${encodeURIComponent(runId)}/events?after_seq=${afterSeq}`,
          {
            cache: "no-store",
            signal: controller.signal,
          },
        );
        if (!replayResponse.ok) throw new Error(`events ${replayResponse.status}`);
        const replayEvents = (await replayResponse.json()) as OrchestratorStreamEvent[];
        appendEvents(replayEvents);
        if (terminalRef.current) {
          setStatus("completed");
          return;
        }

        const streamAfterSeq = latestSeqRef.current;
        const streamResponse = await authenticatedFetch(
          `${ORCHESTRATOR_API_PREFIX}/agent/runs/${encodeURIComponent(runId)}/stream?after_seq=${streamAfterSeq}`,
          {
            cache: "no-store",
            signal: controller.signal,
          },
        );
        if (!streamResponse.ok || !streamResponse.body) throw new Error(`stream ${streamResponse.status}`);
        setStatus("streaming");
        reconnectAttemptsRef.current = 0;

        const reader = streamResponse.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parsed = parseSseBuffer(buffer);
          buffer = parsed.remainder;
          appendEvents(parsed.events);
          if (terminalRef.current) {
            controller.abort();
            setStatus("completed");
            return;
          }
        }
        setStatus(terminalRef.current ? "completed" : "idle");
      } catch (err) {
        if (controller.signal.aborted || terminalRef.current) return;
        const message = err instanceof Error ? err.message : "Orchestrator stream disconnected.";
        setError(message);
        if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
          setStatus("failed");
          return;
        }
        reconnectAttemptsRef.current += 1;
        setStatus("reconnecting");
        const delay = Math.min(RECONNECT_BASE_DELAY_MS * 2 ** (reconnectAttemptsRef.current - 1), 6000);
        reconnectTimerRef.current = setTimeout(() => {
          void connect(latestSeqRef.current);
        }, delay);
      }
    },
    [accessToken, appendEvents, canConnect, runId],
  );

  useEffect(() => {
    stop();
    latestSeqRef.current = 0;
    terminalRef.current = false;
    reconnectAttemptsRef.current = 0;
    setEvents([]);
    setError("");
    setStatus(canConnect ? "loading" : "idle");
    if (canConnect) {
      void connect(0);
    }
    return stop;
  }, [canConnect, connect, runId, stop]);

  const reconnect = useCallback(() => {
    if (!canConnect) return;
    reconnectAttemptsRef.current = 0;
    terminalRef.current = false;
    void connect(latestSeqRef.current);
  }, [canConnect, connect]);

  return { events, status, error, reconnect, stop, latestSeq: latestSeqRef.current };
}
