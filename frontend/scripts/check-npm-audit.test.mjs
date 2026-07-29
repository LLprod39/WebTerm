import assert from "node:assert/strict";
import test from "node:test";

import { auditPolicyErrors } from "./check-npm-audit.mjs";

const allowedAudit = {
  vulnerabilities: {
    "react-router": {
      severity: "high",
      via: [{ url: "https://github.com/advisories/GHSA-qwww-vcr4-c8h2" }],
    },
    "react-router-dom": { severity: "high", via: ["react-router"] },
  },
};
const allowedLock = {
  packages: {
    "node_modules/react-router": { version: "7.18.2" },
    "node_modules/react-router-dom": { version: "7.18.2" },
  },
};

test("passes when npm reports no high or critical vulnerabilities", () => {
  assert.deepEqual(auditPolicyErrors({ vulnerabilities: {} }, { packages: {} }, []), []);
});

test("allows only the reviewed RSC advisory for the exact non-RSC SPA dependency graph", () => {
  assert.deepEqual(auditPolicyErrors(allowedAudit, allowedLock, [["main.tsx", "createRoot(app)"]]), []);
});

test("rejects an additional high severity package", () => {
  const audit = structuredClone(allowedAudit);
  audit.vulnerabilities.postcss = { severity: "high", via: [] };
  assert.match(auditPolicyErrors(audit, allowedLock, [])[0], /unapproved high or critical/);
});

test("rejects a dependency version that was not reviewed", () => {
  const lock = structuredClone(allowedLock);
  lock.packages["node_modules/react-router"].version = "7.18.3";
  assert.match(auditPolicyErrors(allowedAudit, lock, [])[0], /requires a new security review/);
});

test("rejects the exception when production source uses an RSC API", () => {
  const errors = auditPolicyErrors(allowedAudit, allowedLock, [
    ["main.tsx", "routeRSCServerRequest(request)"],
  ]);
  assert.match(errors[0], /RSC-only advisory is applicable/);
});
