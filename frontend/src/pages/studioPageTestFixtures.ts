import type { AuthSessionResponse, PipelineDetail, PipelineListItem } from "@/lib/api";
import { featureMap } from "@/test/featureFlags";

export function authSession(): AuthSessionResponse {
  return {
    authenticated: true,
    user: {
      id: 1,
      username: "admin",
      email: "admin@example.com",
      is_staff: true,
      features: featureMap(),
    },
  };
}

export function multiTriggerPipelineListItem(): PipelineListItem {
  return {
    id: 42,
    name: "Multi Trigger Pipeline",
    description: "demo",
    icon: "W",
    tags: [],
    is_shared: false,
    is_template: false,
    node_count: 4,
    created_at: "2026-04-10T10:00:00Z",
    updated_at: "2026-04-10T10:00:00Z",
    last_run: null,
    graph_version: 2,
    trigger_summary: {
      active_total: 2,
      active_manual: 2,
      active_webhook: 0,
      active_schedule: 0,
      last_triggered_at: null,
    },
  };
}

export function multiTriggerPipelineDetail(): PipelineDetail {
  return {
    ...multiTriggerPipelineListItem(),
    nodes: [
      { id: "manual_a", type: "trigger/manual", position: { x: 0, y: 0 }, data: { label: "Manual A" } },
      { id: "manual_b", type: "trigger/manual", position: { x: 0, y: 100 }, data: { label: "Manual B" } },
      { id: "merge", type: "logic/merge", position: { x: 100, y: 50 }, data: { mode: "any" } },
      { id: "report", type: "output/report", position: { x: 200, y: 50 }, data: {} },
    ],
    edges: [
      { id: "e1", source: "manual_a", target: "merge", sourceHandle: "out" },
      { id: "e2", source: "manual_b", target: "merge", sourceHandle: "out" },
      { id: "e3", source: "merge", target: "report", sourceHandle: "out" },
    ],
    triggers: [],
  };
}

export function pendingManualPipelineRun() {
  return {
    id: 700,
    pipeline_id: 42,
    pipeline_name: "Multi Trigger Pipeline",
    status: "pending",
    current_node_id: null,
    current_node_label: null,
    report_markdown: "",
    error: "",
    trigger_data: {},
    node_states: {},
    created_at: "2026-04-10T10:00:00Z",
    updated_at: "2026-04-10T10:00:00Z",
    started_at: null,
    finished_at: null,
    shared_via_pipeline: false,
    is_owner: true,
    owner: null,
    owner_username: "admin",
    trigger_id: null,
    entry_node_id: "manual_b",
    trigger_type: "manual",
    trigger_name: "Manual B",
    trigger_node_id: "manual_b",
  };
}

export function ticketReportPipelineListItem(): PipelineListItem {
  return {
    id: 66,
    name: "Ticket Report",
    description: "needs context",
    icon: "T",
    tags: [],
    is_shared: false,
    is_template: false,
    node_count: 2,
    created_at: "2026-04-10T10:00:00Z",
    updated_at: "2026-04-10T10:00:00Z",
    last_run: null,
    graph_version: 2,
    trigger_summary: {
      active_total: 1,
      active_manual: 1,
      active_webhook: 0,
      active_schedule: 0,
      last_triggered_at: null,
    },
  };
}

export function ticketReportPipelineDetail(): PipelineDetail {
  return {
    ...ticketReportPipelineListItem(),
    nodes: [
      {
        id: "manual_start",
        type: "trigger/manual",
        position: { x: 0, y: 0 },
        data: { label: "Manual Start" },
      },
      {
        id: "report",
        type: "output/report",
        position: { x: 180, y: 0 },
        data: { template: "Ticket: {ticket_id}" },
      },
    ],
    edges: [{ id: "e1", source: "manual_start", target: "report", sourceHandle: "out" }],
    triggers: [],
  };
}
