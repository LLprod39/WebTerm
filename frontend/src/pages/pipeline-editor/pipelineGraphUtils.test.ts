import { describe, expect, it } from "vitest";

import type { PipelineNode } from "@/lib/api";

import {
  applyWorkspaceAiRoutingPolicy,
  buildDefaultNodeData,
  getMissingRunContextFields,
  getPipelineRuntimePlaceholders,
} from "./pipelineGraphUtils";

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

  it("defaults LLM requests to workspace AI routing", () => {
    expect(buildDefaultNodeData("agent/llm_query")).toMatchObject({
      provider: "auto",
      on_failure: "abort",
    });
  });

  it("removes hidden AI routing overrides from every ordinary-user AI node", () => {
    const nodes = ["agent/llm_query", "agent/react", "agent/multi"].map((type, index) => ({
      id: `ai_${index}`,
      type,
      position: { x: index * 100, y: 0 },
      data: {
        label: type,
        provider: "gemini",
        model: "gemini-2.5-pro",
        provider_binding: { target_id: "grok_subscription", connection_id: 7 },
      },
    })) as unknown as PipelineNode[];

    const result = applyWorkspaceAiRoutingPolicy(nodes, false);

    for (const node of result) {
      expect(node.data).toMatchObject({
        provider: "auto",
        model: "",
        provider_binding: {},
      });
    }
  });

  it("preserves explicit AI routing overrides for routing administrators", () => {
    const nodes = [{
      id: "llm",
      type: "agent/llm_query",
      position: { x: 0, y: 0 },
      data: {
        provider: "openai",
        model: "gpt-5.4",
        provider_binding: { target_id: "codex_subscription", connection_id: 3 },
      },
    }] as unknown as PipelineNode[];

    expect(applyWorkspaceAiRoutingPolicy(nodes, true)).toBe(nodes);
  });
});
