import { describe, expect, it } from "vitest";

import { resolveLlmQueryModelLabel } from "./LLMQueryNode";

describe("resolveLlmQueryModelLabel", () => {
  it("does not invent a fake model when model is empty", () => {
    expect(resolveLlmQueryModelLabel("", "en")).toBe("Settings → AI");
    expect(resolveLlmQueryModelLabel("   ", "ru")).toBe("Настройки → ИИ");
    expect(resolveLlmQueryModelLabel(undefined, "en")).toBe("Settings → AI");
    expect(resolveLlmQueryModelLabel("", "en")).not.toContain("gemini");
  });

  it("shows an explicit model override when present", () => {
    expect(resolveLlmQueryModelLabel("gemini-2.0-flash", "en")).toBe("gemini-2.0-flash");
  });
});
