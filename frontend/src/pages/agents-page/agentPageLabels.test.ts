import { describe, expect, it } from "vitest";

import {
  FULL_AGENT_TOOL_OPTIONS,
  READ_ONLY_AGENT_TOOL_KEYS,
  buildDefaultToolsConfig,
  buildExternalToolsConfig,
  enforceReadOnlyToolsConfig,
} from "./agentPageLabels";

describe("pilot-safe agent tool defaults", () => {
  it("keeps external-system agents free of SSH tools", () => {
    const config = buildExternalToolsConfig();

    expect(config.open_connection).toBe(false);
    expect(config.ssh_execute).toBe(false);
    expect(config.read_console).toBe(false);
    expect(config.report).toBe(true);
    expect(config.read_skill).toBe(true);
    expect(config.read_material).toBe(true);
  });

  it("enables only the explicit read-only allowlist", () => {
    const config = buildDefaultToolsConfig();

    expect(config.ssh_execute).toBe(true);
    expect(config.read_console).toBe(true);
    expect(config.run_script_material).toBe(true);
    expect(config.update_material_task).toBe(true);
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

    expect(sanitized.run_script_material).toBe(true);
    expect(sanitized.update_material_task).toBe(true);
    expect(sanitized.ssh_execute).toBe(true);
  });
});
