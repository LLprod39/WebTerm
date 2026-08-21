import { describe, expect, it } from "vitest";

import { asPayload, enforcePilotServerAccess, initialForm } from "./serverForm";

describe("server form AI access defaults", () => {
  it("creates servers writable for authorized automation by default", () => {
    const form = initialForm();

    expect(form.ai_read_only).toBe(false);
    expect(asPayload(form, true).ai_read_only).toBe(false);
  });

  it("keeps unprivileged payloads read-only", () => {
    const form = initialForm();

    expect(asPayload(form).ai_read_only).toBe(true);
  });

  it("preserves an explicit AI read-only selection", () => {
    const form = { ...initialForm(), ai_read_only: true };

    expect(asPayload(form).ai_read_only).toBe(true);
  });

  it("removes unsafe AI and sudo access without the automation capability", () => {
    const unsafeForm = {
      ...initialForm(),
      ai_read_only: false,
      sudo_auth_mode: "stored_password" as const,
      sudo_password: "must-not-leave-the-browser",
    };

    expect(enforcePilotServerAccess(unsafeForm)).toEqual(expect.objectContaining({
      ai_read_only: true,
      sudo_auth_mode: "none",
      sudo_password: "",
    }));
    expect(asPayload(unsafeForm)).toEqual(expect.objectContaining({
      ai_read_only: true,
      sudo_auth_mode: "none",
      sudo_password: "",
    }));
  });

  it("preserves elevated settings only for an explicitly authorized operator", () => {
    const operatorForm = {
      ...initialForm(),
      ai_read_only: false,
      sudo_auth_mode: "nopasswd" as const,
    };

    expect(asPayload(operatorForm, true)).toEqual(expect.objectContaining({
      ai_read_only: false,
      sudo_auth_mode: "nopasswd",
    }));
  });
});
