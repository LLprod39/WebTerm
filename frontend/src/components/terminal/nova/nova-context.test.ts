import { describe, expect, it } from "vitest";

import {
  hasNovaContextContent,
  novaContextFingerprint,
} from "../nova-context";
import type { NovaContextPayload } from "../ai-types";

describe("novaContextFingerprint", () => {
  it("returns empty for missing context", () => {
    expect(novaContextFingerprint(undefined)).toBe("");
    expect(novaContextFingerprint(null)).toBe("");
    expect(novaContextFingerprint({})).toBe("");
  });

  it("keys on cwd / user / hostname / shell", () => {
    const a: NovaContextPayload = {
      session: { cwd: "/home/a", user: "nikita", hostname: "nikitavm", shell: "/bin/bash" },
    };
    const same: NovaContextPayload = {
      session: {
        cwd: "/home/a",
        user: "nikita",
        hostname: "nikitavm",
        shell: "/bin/bash",
        python: "/usr/bin/python3",
        source: "prompt",
      },
      recent_activity: [{ command: "hostname" }],
    };
    const changedCwd: NovaContextPayload = {
      session: { cwd: "/tmp", user: "nikita", hostname: "nikitavm", shell: "/bin/bash" },
    };

    expect(novaContextFingerprint(a)).toBe(novaContextFingerprint(same));
    expect(novaContextFingerprint(a)).not.toBe(novaContextFingerprint(changedCwd));
  });

  it("uses activity-only sentinel when session fields are empty", () => {
    const onlyActivity: NovaContextPayload = {
      recent_activity: [{ command: "ls" }],
    };
    expect(novaContextFingerprint(onlyActivity)).toBe("activity-only");
  });
});

describe("hasNovaContextContent", () => {
  it("detects session or activity", () => {
    expect(hasNovaContextContent(undefined)).toBe(false);
    expect(hasNovaContextContent({})).toBe(false);
    expect(hasNovaContextContent({ session: { cwd: "/" } })).toBe(true);
    expect(hasNovaContextContent({ recent_activity: [{ command: "pwd" }] })).toBe(true);
  });
});

describe("agent_start context dedupe policy", () => {
  it("shows context only when fingerprint changes", () => {
    const fpA = novaContextFingerprint({
      session: { cwd: "/home", user: "u", hostname: "h", shell: "/bin/bash" },
    });
    const fpB = novaContextFingerprint({
      session: { cwd: "/home", user: "u", hostname: "h", shell: "/bin/bash" },
    });
    const fpC = novaContextFingerprint({
      session: { cwd: "/var", user: "u", hostname: "h", shell: "/bin/bash" },
    });

    let last = "";
    const decisions = [fpA, fpB, fpC].map((fp) => {
      const show = Boolean(fp) && fp !== last;
      if (fp) last = fp;
      return show;
    });

    expect(decisions).toEqual([true, false, true]);
  });
});
