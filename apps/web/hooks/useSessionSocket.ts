import { useEffect, useRef, useState, useCallback } from 'react';
import { useAuthStore } from '@/store/authStore';

export interface SessionEvent {
  type: string;
  session_id: string;
  run_id?: string;
  payload: Record<string, unknown>;
  created_at?: string;
}

type SocketStatus = 'connecting' | 'connected' | 'reconnecting' | 'disconnected';

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_BASE_DELAY_MS = 500;

export function useSessionSocket(sessionId: string) {
  const [status, setStatus] = useState<SocketStatus>('connecting');
  const [lastEvent, setLastEvent] = useState<SessionEvent | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const { accessToken, hasHydrated, isAuthenticated } = useAuthStore();
  const canConnect = hasHydrated && isAuthenticated && Boolean(accessToken && sessionId);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const closeSocket = useCallback(() => {
    const socket = socketRef.current;
    socketRef.current = null;
    if (socket && socket.readyState !== WebSocket.CLOSED) {
      socket.close();
    }
  }, []);

  const connect = useCallback(() => {
    if (!canConnect || !accessToken) {
      closeSocket();
      setStatus('disconnected');
      return;
    }
    if (
      socketRef.current?.readyState === WebSocket.OPEN ||
      socketRef.current?.readyState === WebSocket.CONNECTING
    ) return;

    shouldReconnectRef.current = true;
    clearReconnectTimer();
    setStatus(reconnectAttemptsRef.current > 0 ? 'reconnecting' : 'connecting');
    const wsUrl = buildSessionWebSocketUrl(sessionId, accessToken);
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      if (socketRef.current !== ws) return;
      reconnectAttemptsRef.current = 0;
      setStatus('connected');
    };

    ws.onmessage = (event) => {
      if (socketRef.current !== ws) return;
      try {
        const data: SessionEvent = JSON.parse(event.data);
        setLastEvent(data);
      } catch (err) {
        console.warn('Failed to parse WebSocket message', err);
      }
    };

    ws.onclose = () => {
      if (socketRef.current !== ws) return;
      socketRef.current = null;
      if (!shouldReconnectRef.current || reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setStatus('disconnected');
        return;
      }
      reconnectAttemptsRef.current += 1;
      setStatus('reconnecting');
      const delay = Math.min(
        RECONNECT_BASE_DELAY_MS * 2 ** (reconnectAttemptsRef.current - 1),
        5000
      );
      reconnectTimerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      if (socketRef.current !== ws || !shouldReconnectRef.current) return;
      setStatus('reconnecting');
    };
  }, [accessToken, canConnect, clearReconnectTimer, closeSocket, sessionId]);

  useEffect(() => {
    if (!canConnect) {
      shouldReconnectRef.current = false;
      clearReconnectTimer();
      closeSocket();
      setStatus('disconnected');
      return;
    }

    shouldReconnectRef.current = true;
    connect();
    return () => {
      shouldReconnectRef.current = false;
      clearReconnectTimer();
      closeSocket();
    };
  }, [canConnect, closeSocket, connect, clearReconnectTimer]);

  const sendMessage = useCallback((type: string, payload: Record<string, unknown>) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({
        type,
        session_id: sessionId,
        run_id: newClientRunId(),
        payload,
        created_at: new Date().toISOString(),
      }));
    } else {
      console.warn("WebSocket is not connected. Message not sent.");
    }
  }, [sessionId]);

  const reconnect = useCallback(() => {
    if (!canConnect) return;
    reconnectAttemptsRef.current = 0;
    clearReconnectTimer();
    closeSocket();
    shouldReconnectRef.current = true;
    connect();
  }, [canConnect, clearReconnectTimer, closeSocket, connect]);

  return { status, lastEvent, sendMessage, reconnect };
}

function buildSessionWebSocketUrl(sessionId: string, accessToken: string) {
  const configuredBase = process.env.NEXT_PUBLIC_WS_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL;
  let base: string;

  if (configuredBase) {
    base = normalizeBrowserWebSocketBase(configuredBase);
  } else if (typeof window !== "undefined" && !["localhost", "127.0.0.1"].includes(window.location.hostname)) {
    base = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:18080`;
  } else {
    base = "ws://localhost:18080";
  }

  const url = new URL(`/api/ws/sessions/${sessionId}`, base);
  url.searchParams.set("access_token", accessToken);
  return url.toString();
}

function normalizeBrowserWebSocketBase(configuredBase: string) {
  const fallbackOrigin = typeof window === "undefined" ? "http://localhost" : window.location.origin;
  const url = new URL(configuredBase, fallbackOrigin);
  url.protocol = url.protocol.replace(/^http/i, "ws");

  if (typeof window !== "undefined" && isLoopbackHost(url.hostname) && !isLoopbackHost(window.location.hostname)) {
    url.hostname = window.location.hostname;
  }

  return url.toString();
}

function isLoopbackHost(hostname: string) {
  const normalized = hostname.toLowerCase().replace(/^\[/, "").replace(/\]$/, "");
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1";
}

function newClientRunId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `web_${crypto.randomUUID().replace(/-/g, "")}`;
  }
  return `web_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}
