import assert from "node:assert/strict";
import test from "node:test";

import { planTierMeta } from "./billing.ts";

test("planTierMeta maps known subscription slugs", () => {
  assert.equal(planTierMeta("free").labelZh, "免费版");
  assert.equal(planTierMeta("pro").tone, "gold");
  assert.equal(planTierMeta("unlimited").upgradeHref, "/settings/subscription");
});

test("planTierMeta falls back to free for unknown slugs", () => {
  assert.equal(planTierMeta("unknown").slug, "unknown");
  assert.equal(planTierMeta("unknown").labelZh, "免费版");
});
