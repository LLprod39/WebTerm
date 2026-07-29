import { describe, expect, it } from "vitest";

import { normalizeInternalRedirectPath } from "@/lib/safeRedirect";

describe("normalizeInternalRedirectPath", () => {
  it.each([
    "",
    "dashboard",
    "https://evil.example/phish",
    "//evil.example/phish",
    "/\\evil.example/phish",
    "/%2f%2fevil.example/phish",
    "/%5cevil.example/phish",
    "javascript:alert(1)",
    "data:text/html,phish",
    " /dashboard",
    "/dashboard\n",
  ])("rejects unsafe or ambiguous redirect %s", (value) => {
    expect(normalizeInternalRedirectPath(value)).toBeNull();
  });

  it.each([
    ["/dashboard", "/dashboard"],
    ["/servers?group=prod#active", "/servers?group=prod#active"],
    ["/settings/readiness?next=https://evil.example", "/settings/readiness?next=https://evil.example"],
  ])("keeps a same-origin route %s", (value, expected) => {
    expect(normalizeInternalRedirectPath(value)).toBe(expected);
  });
});
