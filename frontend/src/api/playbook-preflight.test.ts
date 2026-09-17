import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api";
import { runValidatedPlaybook, validatePlaybookRevision } from "./playbook-preflight";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn(async () => ({ success: true })) }));

describe("playbook preflight API", () => {
  beforeEach(() => vi.mocked(apiFetch).mockClear());

  it("validates an exact revision and execution context", async () => {
    const payload = {
      binding_profile_id: 9,
      server_ids: [1],
      group_ids: [3],
      inventory_bindings: { web: { server_ids: [1], group_ids: [3] } },
      variable_names: ["release", "token"],
    };

    await validatePlaybookRevision(7, 12, payload);

    expect(apiFetch).toHaveBeenCalledWith(
      "/servers/api/playbooks/7/revisions/12/validate/",
      { method: "POST", body: JSON.stringify(payload), timeoutMs: 60_000 },
    );
  });

  it("runs only with validation evidence and the exact reviewed payload", async () => {
    const payload = {
      revision_id: 12,
      validation_id: 77,
      binding_profile_id: 9,
      server_ids: [1],
      group_ids: [],
      inventory_bindings: { web: { server_ids: [1], group_ids: [] } },
      extra_vars: { release: 42, enabled: true },
      concurrency: 6,
      dry_run: true,
      become: false,
      tags: "deploy",
      skip_tags: "risky",
      limit: "web",
      engine: "ansible" as const,
    };

    await runValidatedPlaybook(7, payload);

    expect(apiFetch).toHaveBeenCalledWith("/servers/api/playbooks/7/run/", {
      method: "POST",
      body: JSON.stringify(payload),
      timeoutMs: 60_000,
    });
  });
});
