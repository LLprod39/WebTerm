import { describe, expect, it } from "vitest";

import { safeFirstRunNextPath } from "@/lib/first-run-readiness";

describe("safeFirstRunNextPath", () => {
  it("keeps an internal workspace path", () => {
    expect(safeFirstRunNextPath("/servers?group=core")).toBe("/servers?group=core");
  });

  it.each([
    "https://evil.example",
    "//evil.example",
    "%2F%2Fevil.example",
    "/\\evil.example",
    "/%5Cevil.example",
    "/login",
    "/settings/readiness?firstRun=1",
    "%E0%A4%A",
  ])("rejects unsafe or recursive destination %s", (value) => {
    expect(safeFirstRunNextPath(value)).toBe("/dashboard");
  });
});
