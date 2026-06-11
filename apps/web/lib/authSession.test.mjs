import assert from "node:assert/strict";
import test from "node:test";

import axios from "axios";

import {
  configureAuthSession,
  handleSessionExpired,
  refreshAccessToken,
} from "./authSession.ts";

function createMemoryAuthStore(initial = {}) {
  const state = {
    accessToken: initial.accessToken ?? "access_old",
    refreshToken: initial.refreshToken ?? "refresh_old",
    tokenExpiresAt: initial.tokenExpiresAt ?? null,
    loggedOut: false,
  };

  return {
    state,
    accessor: {
      getAccessToken: () => state.accessToken,
      getRefreshToken: () => state.refreshToken,
      getTokenExpiresAt: () => state.tokenExpiresAt,
      setTokens: (accessToken, refreshToken, expiresAt = null) => {
        state.accessToken = accessToken;
        state.refreshToken = refreshToken;
        state.tokenExpiresAt = expiresAt;
      },
      logout: () => {
        state.loggedOut = true;
        state.accessToken = null;
        state.refreshToken = null;
        state.tokenExpiresAt = null;
      },
    },
  };
}

test("refreshAccessToken stores nested token payload from refresh response", async (t) => {
  const store = createMemoryAuthStore();
  configureAuthSession(store.accessor);

  const originalPost = axios.post;
  axios.post = async (url, body) => {
    assert.equal(url, "/api/auth/refresh");
    assert.deepEqual(body, { refresh_token: "refresh_old" });
    return {
      data: {
        user: { id: "user_1" },
        token: {
          access_token: "access_new",
          refresh_token: "refresh_new",
          expires_at: "2030-01-01T00:00:00.000Z",
        },
      },
    };
  };

  t.after(() => {
    axios.post = originalPost;
  });

  const accessToken = await refreshAccessToken();
  assert.equal(accessToken, "access_new");
  assert.equal(store.state.accessToken, "access_new");
  assert.equal(store.state.refreshToken, "refresh_new");
  assert.equal(store.state.tokenExpiresAt, "2030-01-01T00:00:00.000Z");
});

test("refreshAccessToken deduplicates concurrent refresh calls", async (t) => {
  const store = createMemoryAuthStore();
  configureAuthSession(store.accessor);

  let refreshCalls = 0;
  const originalPost = axios.post;
  axios.post = async () => {
    refreshCalls += 1;
    await new Promise((resolve) => setTimeout(resolve, 20));
    return {
      data: {
        token: {
          access_token: "access_deduped",
          refresh_token: "refresh_deduped",
        },
      },
    };
  };

  t.after(() => {
    axios.post = originalPost;
  });

  const [first, second] = await Promise.all([refreshAccessToken(), refreshAccessToken()]);
  assert.equal(first, "access_deduped");
  assert.equal(second, "access_deduped");
  assert.equal(refreshCalls, 1);
});

test("handleSessionExpired clears auth state", () => {
  const store = createMemoryAuthStore();
  configureAuthSession(store.accessor);

  handleSessionExpired();
  assert.equal(store.state.loggedOut, true);
  assert.equal(store.state.accessToken, null);
});
