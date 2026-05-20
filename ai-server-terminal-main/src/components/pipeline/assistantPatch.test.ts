import { describe, expect, it } from "vitest";

import { applyAssistantGraphPatch, getAssistantPatchStats } from "@/components/pipeline/assistantPatch";
import type { PipelineEdge, PipelineNode, StudioPipelineAssistantResponse } from "@/lib/api";

function response(overrides: Partial<StudioPipelineAssistantResponse>): StudioPipelineAssistantResponse {
  return {
    reply: "ok",
    target_node_id: null,
    node_patch: {},
    graph_patch: {
      anchor_node_id: null,
      nodes: [],
      edges: [],
      update_nodes: [],
      remove_node_ids: [],
      remove_edge_ids: [],
    },
    warnings: [],
    ...overrides,
  };
}

describe("assistant graph patch helper", () => {
  it("adds nodes from refs, links edges, updates data, and removes deleted graph items", () => {
    const nodes: PipelineNode[] = [
      { id: "manual", type: "trigger/manual", position: { x: 0, y: 0 }, data: { label: "Manual" } },
      { id: "old_wait", type: "logic/wait", position: { x: 120, y: 80 }, data: {} },
    ];
    const edges: PipelineEdge[] = [
      { id: "edge_old", source: "manual", target: "old_wait", sourceHandle: "out" },
    ];
    const draft = response({
      target_node_id: "manual",
      node_patch: { label: "Manual Start" },
      graph_patch: {
        anchor_node_id: "manual",
        nodes: [
          { ref: "inspect-step", type: "agent/llm_query", label: "Inspect", data: { prompt: "Check it" } },
          { ref: "report-step", type: "output/report", label: "Report", data: {} },
        ],
        edges: [
          { source: "manual", target: "inspect-step" },
          { source: "inspect-step", target: "report-step", source_handle: "success" },
        ],
        update_nodes: [],
        remove_node_ids: ["old_wait"],
        remove_edge_ids: ["edge_old"],
      },
    });

    const result = applyAssistantGraphPatch({ nodes, edges, response: draft });

    expect(result.nodes.map((node) => node.id)).toEqual(["manual", "inspect_step", "report_step"]);
    expect(result.nodes[0].data.label).toBe("Manual Start");
    expect(result.edges).toEqual([
      expect.objectContaining({ source: "manual", target: "inspect_step", sourceHandle: "out" }),
      expect.objectContaining({ source: "inspect_step", target: "report_step", sourceHandle: "success" }),
    ]);
    expect(getAssistantPatchStats(draft)).toMatchObject({
      addedNodes: 2,
      addedEdges: 2,
      updatedNodes: 1,
      removedNodes: 1,
      removedEdges: 1,
      hasChanges: true,
    });
  });

  it("normalizes invalid source handles for typed logic nodes", () => {
    const nodes: PipelineNode[] = [
      { id: "manual", type: "trigger/manual", position: { x: 0, y: 0 }, data: {} },
    ];
    const draft = response({
      graph_patch: {
        anchor_node_id: "manual",
        nodes: [
          { ref: "ask_ops", type: "logic/telegram_input", label: "Ask Ops", data: {} },
          { ref: "report", type: "output/report", label: "Report", data: {} },
        ],
        edges: [
          { source: "manual", target: "ask_ops" },
          { source: "ask_ops", target: "report", source_handle: "out" },
        ],
        update_nodes: [],
        remove_node_ids: [],
        remove_edge_ids: [],
      },
    });

    const result = applyAssistantGraphPatch({ nodes, edges: [], response: draft });

    expect(result.edges).toEqual([
      expect.objectContaining({ source: "manual", target: "ask_ops", sourceHandle: "out" }),
      expect.objectContaining({ source: "ask_ops", target: "report", sourceHandle: "received" }),
    ]);
  });
});
