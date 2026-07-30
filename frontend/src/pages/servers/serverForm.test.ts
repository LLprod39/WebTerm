import { describe, expect, it } from "vitest";

import { asPayload, initialForm } from "./serverForm";

describe("server form AI access defaults", () => {
  it("creates servers with AI write access enabled", () => {
    const form = initialForm();

    expect(form.ai_read_only).toBe(false);
    expect(asPayload(form).ai_read_only).toBe(false);
  });

  it("preserves an explicit AI read-only selection", () => {
    const form = { ...initialForm(), ai_read_only: true };

    expect(asPayload(form).ai_read_only).toBe(true);
  });
});
