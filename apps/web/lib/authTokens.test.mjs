import assert from "node:assert/strict";
import test from "node:test";

import { parseAuthTokens, tokenExpiresSoon } from "./authSession.ts";

test("parseAuthTokens reads nested token payload from auth response", () => {
  const parsed = parseAuthTokens({
    user: { id: "user_1" },
    token: {
      access_token: "access_1",
      refresh_token: "refresh_1",
      expires_at: "2030-01-01T00:00:00.000Z",
    },
  });

  assert.deepEqual(parsed, {
    access_token: "access_1",
    refresh_token: "refresh_1",
    expires_at: "2030-01-01T00:00:00.000Z",
  });
});

test("parseAuthTokens accepts flat token payload", () => {
  const parsed = parseAuthTokens({
    access_token: "access_2",
    refresh_token: "refresh_2",
  });

  assert.deepEqual(parsed, {
    access_token: "access_2",
    refresh_token: "refresh_2",
    expires_at: undefined,
  });
});

test("parseAuthTokens rejects incomplete payload", () => {
  assert.equal(parseAuthTokens({ token: { access_token: "only-access" } }), null);
  assert.equal(parseAuthTokens(null), null);
});

test("tokenExpiresSoon returns true inside refresh buffer", () => {
  const expiresAt = new Date(Date.now() + 30_000).toISOString();
  assert.equal(tokenExpiresSoon(expiresAt, 120_000), true);
});

test("tokenExpiresSoon returns false when expiry is far away", () => {
  const expiresAt = new Date(Date.now() + 30 * 60_000).toISOString();
  assert.equal(tokenExpiresSoon(expiresAt, 120_000), false);
});
