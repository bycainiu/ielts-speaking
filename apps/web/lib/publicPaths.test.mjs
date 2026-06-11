import assert from "node:assert/strict";
import test from "node:test";

import { isPublicPath, resolveHomeDestination } from "./publicPaths.ts";

test("isPublicPath allows marketing and auth entry routes", () => {
  assert.equal(isPublicPath("/"), true);
  assert.equal(isPublicPath("/login"), true);
  assert.equal(isPublicPath("/register"), true);
  assert.equal(isPublicPath("/pricing"), true);
  assert.equal(isPublicPath("/pricing/subscribe"), true);
  assert.equal(isPublicPath("/pricing/checkout"), true);
});

test("isPublicPath blocks authenticated app routes", () => {
  assert.equal(isPublicPath("/practice"), false);
  assert.equal(isPublicPath("/admin/subscriptions"), false);
  assert.equal(isPublicPath("/settings/subscription"), false);
});

test("resolveHomeDestination sends guests to pricing and users to practice", () => {
  assert.equal(resolveHomeDestination(false), "/pricing");
  assert.equal(resolveHomeDestination(true), "/practice");
});
