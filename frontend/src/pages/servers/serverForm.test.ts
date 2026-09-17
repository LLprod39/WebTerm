import { describe, expect, it } from "vitest";

import { asPayload, initialForm } from "./serverForm";

describe("server form AI access defaults", () => {
  it("creates servers in the normal interactive mode by default", () => {
    const form = initialForm();

    expect(form.ai_read_only).toBe(false);
    expect(asPayload(form).ai_read_only).toBe(false);
  });

  it("normalizes legacy read-only values without dropping sudo settings", () => {
    const form = { ...initialForm(), ai_read_only: true };

    const payload = asPayload({
      ...form,
      sudo_auth_mode: "stored_password" as const,
      sudo_password: "stored-securely",
    });

    expect(payload).toEqual(expect.objectContaining({
      ai_read_only: false,
      sudo_auth_mode: "stored_password",
      sudo_password: "stored-securely",
    }));
  });
});
