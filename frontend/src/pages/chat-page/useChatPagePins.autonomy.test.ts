import { describe, expect, it } from "vitest";

import { DEFAULT_AUTONOMY_MODE, parseAutonomyMode } from "./useChatPagePins";

describe("parseAutonomyMode", () => {
  it("defaults to confirm_each", () => {
    expect(DEFAULT_AUTONOMY_MODE).toBe("confirm_each");
    expect(parseAutonomyMode(undefined)).toBe("confirm_each");
    expect(parseAutonomyMode(null)).toBe("confirm_each");
    expect(parseAutonomyMode("nope")).toBe("confirm_each");
    expect(parseAutonomyMode({})).toBe("confirm_each");
  });

  it("accepts known modes including plan_once without making it default", () => {
    expect(parseAutonomyMode("confirm_each")).toBe("confirm_each");
    expect(parseAutonomyMode("plan_once")).toBe("plan_once");
    expect(parseAutonomyMode("autonomous")).toBe("autonomous");
  });
});
