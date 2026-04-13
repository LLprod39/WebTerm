import { describe, expect, it } from "vitest";

import type { PipelineEdge, PipelineNode, PipelineRun } from "@/lib/api";
import { buildPipelineRunGraphState } from "@/components/pipeline/pipelineRunGraph";

const nodes: PipelineNode[] = [
  { id: "webhook_start", type: "trigger/webhook", position: { x: 0, y: 0 }, data: {} },
  { id: "condition_gate", type: "logic/condition", position: { x: 160, y: 0 }, data: {} },
  { id: "approve_gate", type: "logic/human_approval", position: { x: 320, y: 0 }, data: {} },
  { id: "success_report", type: "output/report", position: { x: 480, y: -80 }, data: {} },
  { id: "reject_report", type: "output/report", position: { x: 480, y: 80 }, data: {} },
];

const edges: PipelineEdge[] = [
  { id: "e1", source: "webhook_start", target: "condition_gate", sourceHandle: "out" },
  { id: "e2", source: "condition_gate", target: "approve_gate", sourceHandle: "true" },
  { id: "e3", source: "condition_gate", target: "reject_report", sourceHandle: "false" },
  { id: "e4", source: "approve_gate", target: "success_report", sourceHandle: "approved" },
  { id: "e5", source: "approve_gate", target: "reject_report", sourceHandle: "rejected" },
];

describe("buildPipelineRunGraphState", () => {
  it("tracks the current running node and traversed entry path", () => {
    const run: PipelineRun = {
      id: 1,
      pipeline_id: 45,
      pipeline_name: "test",
      status: "running",
      node_states: {
        condition_gate: {
          status: "completed",
          routing_ports: ["true"],
        },
        approve_gate: {
          status: "running",
        },
      },
      nodes_snapshot: nodes,
      context: {},
      summary: "",
      error: "",
      duration_seconds: null,
      started_at: "2026-04-11T08:00:00Z",
      finished_at: null,
      created_at: "2026-04-11T08:00:00Z",
      triggered_by: "tester",
      trigger_id: 1,
      entry_node_id: "webhook_start",
      trigger_type: "webhook",
      trigger_name: "Webhook Start",
      trigger_node_id: "webhook_start",
    };

    const state = buildPipelineRunGraphState(nodes, edges, run);

    expect(state.currentNodeId).toBe("approve_gate");
    expect(state.activeEdgeIds).toEqual(new Set(["e1", "e2"]));
    expect(state.currentEdgeIds).toEqual(new Set(["e2"]));
    expect(state.traversedNodeIds).toEqual(new Set(["webhook_start", "condition_gate", "approve_gate"]));
  });

  it("routes only the selected condition branch", () => {
    const run: PipelineRun = {
      id: 2,
      pipeline_id: 45,
      pipeline_name: "test",
      status: "completed",
      node_states: {
        condition_gate: {
          status: "completed",
          routing_ports: ["false"],
        },
        reject_report: {
          status: "completed",
        },
      },
      nodes_snapshot: nodes,
      context: {},
      summary: "",
      error: "",
      duration_seconds: 2,
      started_at: "2026-04-11T08:00:00Z",
      finished_at: "2026-04-11T08:00:02Z",
      created_at: "2026-04-11T08:00:00Z",
      triggered_by: "tester",
      trigger_id: 1,
      entry_node_id: "webhook_start",
      trigger_type: "webhook",
      trigger_name: "Webhook Start",
      trigger_node_id: "webhook_start",
    };

    const state = buildPipelineRunGraphState(nodes, edges, run);

    expect(state.activeEdgeIds.has("e3")).toBe(true);
    expect(state.activeEdgeIds.has("e2")).toBe(false);
  });

  it("routes approval nodes using the decision field", () => {
    const run: PipelineRun = {
      id: 3,
      pipeline_id: 45,
      pipeline_name: "test",
      status: "completed",
      node_states: {
        approve_gate: {
          status: "completed",
          decision: "approved",
        },
        success_report: {
          status: "completed",
        },
      },
      nodes_snapshot: nodes,
      context: {},
      summary: "",
      error: "",
      duration_seconds: 2,
      started_at: "2026-04-11T08:00:00Z",
      finished_at: "2026-04-11T08:00:02Z",
      created_at: "2026-04-11T08:00:00Z",
      triggered_by: "tester",
      trigger_id: 1,
      entry_node_id: "webhook_start",
      trigger_type: "webhook",
      trigger_name: "Webhook Start",
      trigger_node_id: "webhook_start",
    };

    const state = buildPipelineRunGraphState(nodes, edges, run);

    expect(state.activeEdgeIds.has("e4")).toBe(true);
    expect(state.activeEdgeIds.has("e5")).toBe(false);
  });
});
