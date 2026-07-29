import { describe, expect, it } from "vitest";

import { asPayload, initialForm } from "./serverForm";

describe("server form safety defaults", () => {
  it("creates servers in AI read-only mode unless the owner opts out", () => {
    const form = initialForm();

    expect(form.ai_read_only).toBe(true);
    expect(asPayload(form).ai_read_only).toBe(true);
  });
});
