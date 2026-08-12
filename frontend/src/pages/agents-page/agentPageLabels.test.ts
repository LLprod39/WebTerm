import { describe, expect, it } from "vitest";

import {
  FULL_AGENT_TOOL_OPTIONS,
  READ_ONLY_AGENT_TOOL_KEYS,
  buildDefaultToolsConfig,
  enforceReadOnlyToolsConfig,
} from "./agentPageLabels";

describe("pilot-safe agent tool defaults", () => {
  it("enables only the explicit read-only allowlist", () => {
    const config = buildDefaultToolsConfig();

    expect(config.ssh_execute).toBe(true);
    expect(config.read_console).toBe(true);
    expect(config.run_script_material).toBe(false);
    expect(config.update_material_task).toBe(false);
    expect(Object.entries(config).filter(([, enabled]) => enabled).map(([key]) => key).sort())
      .toEqual([...READ_ONLY_AGENT_TOOL_KEYS].sort());
    expect(Object.keys(config)).toHaveLength(FULL_AGENT_TOOL_OPTIONS.length);
  });

  it("removes mutating tools from an untrusted profile payload", () => {
    const sanitized = enforceReadOnlyToolsConfig({
      ...buildDefaultToolsConfig(),
      run_script_material: true,
      update_material_task: true,
    });

    expect(sanitized.run_script_material).toBe(false);
    expect(sanitized.update_material_task).toBe(false);
    expect(sanitized.ssh_execute).toBe(true);
  });
});
