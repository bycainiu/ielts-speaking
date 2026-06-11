import axios from "axios";

export type AuthTokenPayload = {
  access_token: string;
  refresh_token: string;
  expires_at?: string;
};

export function parseAuthTokens(data: unknown): AuthTokenPayload | null {
  if (!data || typeof data !== "object") return null;

  const root = data as Record<string, unknown>;
  const tokenSource =
    root.token && typeof root.token === "object" ? (root.token as Record<string, unknown>) : root;

  const accessToken = typeof tokenSource.access_token === "string" ? tokenSource.access_token : "";
  const refreshToken = typeof tokenSource.refresh_token === "string" ? tokenSource.refresh_token : "";
  if (!accessToken || !refreshToken) return null;

  const expiresAt = typeof tokenSource.expires_at === "string" ? tokenSource.expires_at : undefined;
  return {
    access_token: accessToken,
    refresh_token: refreshToken,
    expires_at: expiresAt,
  };
}

export function tokenExpiresSoon(expiresAt: string | null | undefined, bufferMs = 120_000) {
  if (!expiresAt) return false;
  const expiresMs = Date.parse(expiresAt);
  if (Number.isNaN(expiresMs)) return false;
  return Date.now() >= expiresMs - bufferMs;
}

export type AuthStoreAccessor = {
  getAccessToken: () => string | null;
  getRefreshToken: () => string | null;
  getTokenExpiresAt: () => string | null;
  setTokens: (accessToken: string, refreshToken: string, expiresAt?: string | null) => void;
  logout: () => void;
};

let authStoreAccessor: AuthStoreAccessor | null = null;
let refreshPromise: Promise<string> | null = null;

export function configureAuthSession(accessor: AuthStoreAccessor) {
  authStoreAccessor = accessor;
}

function requireAuthStore() {
  if (!authStoreAccessor) {
    throw new Error("Auth session is not configured");
  }
  return authStoreAccessor;
}

export function redirectToLogin() {
  if (typeof window === "undefined") return;
  if (window.location.pathname === "/login" || window.location.pathname === "/register") return;

  const next = `${window.location.pathname}${window.location.search}`;
  const destination = next && next !== "/" ? `/login?next=${encodeURIComponent(next)}` : "/login";
  window.location.href = destination;
}

export function handleSessionExpired() {
  try {
    requireAuthStore().logout();
  } catch {
    // Ignore if auth store is not ready during SSR.
  }
  redirectToLogin();
}

export async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    const store = requireAuthStore();
    const refreshToken = store.getRefreshToken();
    if (!refreshToken) {
      throw new Error("No refresh token available");
    }

    const response = await axios.post("/api/auth/refresh", { refresh_token: refreshToken });
    const tokens = parseAuthTokens(response.data);
    if (!tokens) {
      throw new Error("Invalid refresh response");
    }

    store.setTokens(tokens.access_token, tokens.refresh_token, tokens.expires_at ?? null);
    return tokens.access_token;
  })().finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
}

export async function ensureValidAccessToken(): Promise<string | null> {
  const store = requireAuthStore();
  const refreshToken = store.getRefreshToken();
  if (!refreshToken) return null;

  const currentToken = store.getAccessToken();
  if (!currentToken) return null;

  if (!tokenExpiresSoon(store.getTokenExpiresAt())) {
    return currentToken;
  }

  try {
    return await refreshAccessToken();
  } catch {
    return null;
  }
}

export async function authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  let accessToken = await ensureValidAccessToken();
  if (!accessToken) {
    handleSessionExpired();
    throw new Error("Authentication required");
  }

  const request = async (token: string) => {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${token}`);
    return fetch(input, { ...init, headers });
  };

  const response = await request(accessToken);
  if (response.status !== 401) {
    return response;
  }

  try {
    accessToken = await refreshAccessToken();
  } catch {
    handleSessionExpired();
    throw new Error("Session expired");
  }

  const retryResponse = await request(accessToken);
  if (retryResponse.status === 401) {
    handleSessionExpired();
    throw new Error("Session expired");
  }

  return retryResponse;
}

export async function handleUnauthorizedResponse(retry: () => Promise<unknown>) {
  try {
    await refreshAccessToken();
    return retry();
  } catch {
    handleSessionExpired();
    throw new Error("Session expired");
  }
}
