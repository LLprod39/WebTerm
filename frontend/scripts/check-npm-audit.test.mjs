import { test } from "node:test";
import assert from "node:assert/strict";
import { assessAudit } from "./check-npm-audit.mjs";
test("audit fails closed on missing or high-severity results", () => {
  assert.throws(() => assessAudit({ error: "network failure" }));
  assert.equal(
    assessAudit({ metadata: { vulnerabilities: { high: 1, critical: 0 } } })
      .passed,
    false,
  );
  assert.equal(
    assessAudit({ metadata: { vulnerabilities: { high: 0, critical: 0 } } })
      .passed,
    true,
  );
});
