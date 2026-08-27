import { describe, expect, it } from "vitest";

import type { AgentConfig } from "@/lib/api";

import { buildAgentProfileSavePayload } from "./agentProfilePayload";

describe("buildAgentProfileSavePayload", () => {
  const form = {
    name: "Pilot operator",
    description: "Uses workspace AI routing",
    model: "gemini-2.5-pro",
    provider_binding: { target_id: "grok_subscription", connection_id: 7 },
  } satisfies Partial<AgentConfig>;

  it("does not POST hidden model or provider binding fields for ordinary users", () => {
    const payload = buildAgentProfileSavePayload(form, false);

    expect(payload).toMatchObject({
      name: "Pilot operator",
      description: "Uses workspace AI routing",
    });
    expect(payload).not.toHaveProperty("model");
    expect(payload).not.toHaveProperty("provider_binding");
  });

  it("preserves explicit routing fields for routing administrators", () => {
    expect(buildAgentProfileSavePayload(form, true)).toBe(form);
  });
});
