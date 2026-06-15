import { describe, expect, it } from "vitest";

import { buildPipelineRiskSummary } from "@/components/pipeline/pipelineRiskSummary";
import type { PipelineEdge, PipelineNode } from "@/lib/api";

function node(id: string, type: string, data: Record<string, unknown> = {}): PipelineNode {
  return { id, type, position: { x: 0, y: 0 }, data };
}

function edge(source: string, target: string, sourceHandle = "out"): PipelineEdge {
  return { id: `${source}-${target}-${sourceHandle}`, source, target, sourceHandle };
}

describe("buildPipelineRiskSummary", () => {
  it("flags mutating MCP calls without approval", () => {
    const summary = buildPipelineRiskSummary(
      [
        node("manual", "trigger/manual"),
        node("grant", "agent/mcp_call", {
          tool_name: "keycloak_assign_realm_role",
          permission_mode: "ASSISTED",
        }),
        node("report", "output/report"),
      ],
      [edge("manual", "grant"), edge("grant", "report", "success")],
    );

    expect(summary.level).toBe("dangerous");
    expect(summary.mutatingCount).toBe(1);
    expect(summary.missingApprovalCount).toBe(1);
    expect(summary.items[0]).toMatchObject({ nodeId: "grant", hasApproval: false });
  });

  it("treats mutating actions behind approved approval gates as review risk", () => {
    const summary = buildPipelineRiskSummary(
      [
        node("manual", "trigger/manual"),
        node("approval", "logic/human_approval"),
        node("restart", "ops/service_action", { action: "restart", service: "nginx" }),
        node("health", "ops/http_check", { url: "https://example.test/health" }),
      ],
      [
        edge("manual", "approval"),
        edge("approval", "restart", "approved"),
        edge("restart", "health", "success"),
      ],
    );

    expect(summary.level).toBe("review");
    expect(summary.approvalCount).toBe(1);
    expect(summary.missingApprovalCount).toBe(0);
    expect(summary.verificationCount).toBe(1);
    expect(summary.items[0]).toMatchObject({ nodeId: "restart", hasApproval: true });
  });

  it("keeps read-only graphs safe", () => {
    const summary = buildPipelineRiskSummary(
      [
        node("manual", "trigger/manual"),
        node("lookup", "agent/mcp_call", {
          tool_name: "keycloak_lookup_subject_access",
          permission_mode: "READ_ONLY",
        }),
        node("report", "output/report"),
      ],
      [edge("manual", "lookup"), edge("lookup", "report", "success")],
    );

    expect(summary.level).toBe("safe");
    expect(summary.items).toHaveLength(0);
    expect(summary.missingApprovalCount).toBe(0);
  });

  it("flags file writes but not file reads", () => {
    const readSummary = buildPipelineRiskSummary(
      [node("manual", "trigger/manual"), node("read_file", "ops/file_action", { action: "read", path: "/etc/os-release" })],
      [edge("manual", "read_file")],
    );
    const writeSummary = buildPipelineRiskSummary(
      [node("manual", "trigger/manual"), node("write_file", "ops/file_action", { action: "write", path: "/etc/app.conf" })],
      [edge("manual", "write_file")],
    );

    expect(readSummary.level).toBe("safe");
    expect(writeSummary.level).toBe("dangerous");
    expect(writeSummary.items[0]).toMatchObject({ nodeId: "write_file", risk: "mutating", hasApproval: false });
  });

  it("flags package mutations but not package update listing", () => {
    const listSummary = buildPipelineRiskSummary(
      [node("manual", "trigger/manual"), node("packages", "ops/package_action", { action: "list_updates" })],
      [edge("manual", "packages")],
    );
    const installSummary = buildPipelineRiskSummary(
      [node("manual", "trigger/manual"), node("install", "ops/package_action", { action: "install", packages: ["curl"] })],
      [edge("manual", "install")],
    );

    expect(listSummary.level).toBe("safe");
    expect(installSummary.level).toBe("dangerous");
    expect(installSummary.items[0]).toMatchObject({ nodeId: "install", risk: "mutating", hasApproval: false });
  });

  it("flags disk cleanup mutations but not disk inspection", () => {
    const inspectSummary = buildPipelineRiskSummary(
      [node("manual", "trigger/manual"), node("disk", "ops/disk_cleanup", { action: "inspect" })],
      [edge("manual", "disk")],
    );
    const cleanupSummary = buildPipelineRiskSummary(
      [node("manual", "trigger/manual"), node("cleanup", "ops/disk_cleanup", { action: "tmp_cleanup", dry_run: false })],
      [edge("manual", "cleanup")],
    );

    expect(inspectSummary.level).toBe("safe");
    expect(cleanupSummary.level).toBe("dangerous");
    expect(cleanupSummary.items[0]).toMatchObject({ nodeId: "cleanup", risk: "mutating", hasApproval: false });
  });

  it("uses MCP metadata when a mutating tool has a nonstandard name", () => {
    const summary = buildPipelineRiskSummary(
      [
        node("manual", "trigger/manual"),
        node("approval", "logic/human_approval"),
        node("sync", "agent/mcp_call", {
          tool_name: "keycloak_sync_subject",
          mutates_state: true,
          operation_kind: "identity_access_change",
          risk_level: "high",
        }),
        node("report", "output/report"),
      ],
      [edge("manual", "approval"), edge("approval", "sync", "approved"), edge("sync", "report", "success")],
    );

    expect(summary.level).toBe("review");
    expect(summary.mutatingCount).toBe(1);
    expect(summary.items[0]).toMatchObject({
      nodeId: "sync",
      hasApproval: true,
      reason: 'MCP operation "identity_access_change" is marked as state-changing.',
    });
  });
});
