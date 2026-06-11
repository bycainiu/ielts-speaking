import assert from "node:assert/strict";
import test from "node:test";

import { displaySessionMeta, displaySessionTitle, displayUserMeta, displayUserName } from "./adminSessionContext.ts";

test("admin session helpers return empty fallbacks when context is missing", () => {
  assert.equal(displayUserName(null), "");
  assert.equal(displayUserMeta(null), "");
  assert.equal(displaySessionMeta(null), "");
  assert.equal(displaySessionTitle(null, "12345678-1234-1234-1234-1234567890ab"), "12345678...90ab");
});

test("admin session helpers preserve readable fields when context exists", () => {
  const context = {
    session_id: "12345678-1234-1234-1234-1234567890ab",
    user_id: "user-001",
    user_email: "learner@example.com",
    user_display_name: "Learner",
    mode: "topic_practice",
    status: "completed",
    topic_label: "History",
    target_part: 1,
    created_at: "2026-06-09T10:00:00.000Z",
    updated_at: "2026-06-09T10:00:00.000Z",
  };

  assert.equal(displayUserName(context), "Learner");
  assert.equal(displayUserMeta(context), "learner@example.com · user-001");
  assert.match(displaySessionTitle(context, context.session_id), /^History · /);
  assert.match(displaySessionMeta(context), /^主题练习 · Part 1/);
});

test("user display helpers also support admin user context shape", () => {
  const userContext = {
    user_id: "user-002",
    user_hash: "sha256:test",
    user_email: "operator@example.com",
    user_display_name: "Ops Admin",
    created_at: "2026-06-09T10:00:00.000Z",
    updated_at: "2026-06-09T10:00:00.000Z",
  };

  assert.equal(displayUserName(userContext), "Ops Admin");
  assert.equal(displayUserMeta(userContext), "operator@example.com · user-002");
});

test("legacy observability sessions do not expose raw web_obs ids as titles", () => {
  assert.equal(displaySessionTitle(null, "web_obs_1781012375039"), "Legacy Observability Probe · web_obs_...5039");
});
