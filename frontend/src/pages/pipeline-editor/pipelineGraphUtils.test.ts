import { describe, expect, it } from "vitest";

import type { PipelineNode } from "@/lib/api";

import { buildDefaultNodeData, getMissingRunContextFields, getPipelineRuntimePlaceholders } from "./pipelineGraphUtils";

describe("pipelineGraphUtils runtime context fields", () => {
  it("extracts runtime context placeholders without built-in run tokens", () => {
    const fields = getPipelineRuntimePlaceholders([
      {
        id: "check",
        type: "agent/ssh_cmd",
        position: { x: 0, y: 0 },
        data: {
          command: "systemctl is-active {service_name} && curl -fsS https://{domain}/health",
          report: "{pipeline_name} {run_id} {check_output} {service_name}",
        },
      },
    ] as unknown as PipelineNode[]);

    expect(fields).toEqual(["domain", "service_name"]);
  });

  it("reports only empty required runtime context fields", () => {
    expect(getMissingRunContextFields(
      {
        domain: "",
        image_name: "repo/app:latest",
        retries: 0,
        dry_run: false,
        targets: [],
      },
      ["domain", "image_name", "retries", "dry_run", "targets", "ticket_id"],
    )).toEqual(["domain", "targets", "ticket_id"]);
  });

  it("defaults every changing SSH and ops node to preview-only mode", () => {
    for (const type of [
      "agent/ssh_cmd",
      "ops/file_action",
      "ops/package_action",
      "ops/disk_cleanup",
      "ops/service_action",
      "ops/docker_action",
      "ops/process_action",
      "ops/alert_update",
    ]) {
      expect(buildDefaultNodeData(type).dry_run, type).toBe(true);
    }
  });
});
