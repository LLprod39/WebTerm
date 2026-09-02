import { describe, expect, it } from "vitest";
import { CATALOG_TYPES, resolveCatalog } from "./catalog";

/** Keep in sync with studio/executor/nodes + trigger types in node_manifest.py */
const BACKEND_TYPES = [
  "trigger/manual",
  "trigger/webhook",
  "trigger/schedule",
  "trigger/monitoring",
  "agent/react",
  "agent/multi",
  "agent/ssh_cmd",
  "agent/llm_query",
  "agent/mcp_call",
  "logic/condition",
  "logic/parallel",
  "logic/merge",
  "logic/wait",
  "logic/human_approval",
  "logic/telegram_input",
  "ops/server_snapshot",
  "ops/log_query",
  "ops/file_action",
  "ops/package_action",
  "ops/service_action",
  "ops/docker_action",
  "ops/process_action",
  "ops/disk_cleanup",
  "ops/backup_restore_check",
  "ops/http_check",
  "ops/alert_update",
  "output/telegram",
  "output/email",
  "output/webhook",
  "output/report",
  "output/slack",
];

describe("pipeline node catalog", () => {
  it("covers every known backend node type with a Russian title", () => {
    for (const type of BACKEND_TYPES) {
      expect(CATALOG_TYPES).toContain(type);
      const entry = resolveCatalog(type);
      expect(entry.title.trim().length).toBeGreaterThan(0);
      expect(entry.title).not.toBe(type);
    }
  });

  it("falls back gracefully for unknown types", () => {
    const entry = resolveCatalog("custom/widget");
    expect(entry.group).toBe("default");
    expect(entry.title).toContain("widget");
  });
});
