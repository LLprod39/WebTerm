import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import * as api from "@/lib/api";
import PipelineEditorPage from "@/pages/PipelineEditorPage";

export function buildQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
}

export function renderPage(queryClient: QueryClient) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/studio/pipeline/45"]}>
        <Routes>
          <Route path="/studio/pipeline/:id" element={<PipelineEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export const stalePipeline = {
  id: 45,
  name: "All Nodes Smoke Test",
  description: "",
  icon: "S",
  tags: [],
  is_shared: false,
  node_count: 3,
  updated_at: "2026-04-11T08:00:00Z",
  last_run: null,
  graph_version: 2,
  nodes: [
    {
      id: "webhook_start",
      type: "trigger/webhook",
      position: { x: 0, y: 0 },
      data: { label: "Webhook Start", is_active: true },
    },
    {
      id: "trigger_merge",
      type: "logic/merge",
      position: { x: 240, y: 0 },
      data: { label: "Any Trigger Entry", mode: "any" },
    },
    {
      id: "entry_report",
      type: "output/report",
      position: { x: 480, y: 0 },
      data: { label: "Entry Snapshot" },
    },
  ],
  edges: [
    {
      id: "stale_webhook_to_merge",
      source: "webhook_start",
      target: "trigger_merge",
      sourceHandle: "out",
    },
    {
      id: "stale_merge_to_report",
      source: "trigger_merge",
      target: "entry_report",
      sourceHandle: "out",
    },
  ],
  triggers: [
    {
      id: 401,
      pipeline_id: 45,
      node_id: "manual_start",
      name: "Manual Start",
      trigger_type: "manual",
      is_active: true,
    },
    {
      id: 402,
      pipeline_id: 45,
      node_id: "webhook_start",
      name: "Webhook Start",
      trigger_type: "webhook",
      is_active: true,
      webhook_url: "/api/studio/triggers/test/receive/",
    },
    {
      id: 403,
      pipeline_id: 45,
      node_id: "schedule_start",
      name: "Schedule Start",
      trigger_type: "schedule",
      is_active: true,
      cron_expr: "0 * * * *",
    },
  ],
};

export const freshPipeline = {
  ...stalePipeline,
  node_count: 5,
  nodes: [
    {
      id: "manual_start",
      type: "trigger/manual",
      position: { x: -200, y: -120 },
      data: { label: "Manual Start", is_active: true },
    },
    {
      id: "webhook_start",
      type: "trigger/webhook",
      position: { x: 0, y: 0 },
      data: { label: "Webhook Start", is_active: true },
    },
    {
      id: "schedule_start",
      type: "trigger/schedule",
      position: { x: -200, y: 120 },
      data: { label: "Schedule Start", is_active: true },
    },
    {
      id: "trigger_merge",
      type: "logic/merge",
      position: { x: 240, y: 0 },
      data: { label: "Any Trigger Entry", mode: "any" },
    },
    {
      id: "entry_report",
      type: "output/report",
      position: { x: 480, y: 0 },
      data: { label: "Entry Snapshot" },
    },
  ],
  edges: [
    {
      id: "manual_to_merge",
      source: "manual_start",
      target: "trigger_merge",
      sourceHandle: "out",
    },
    {
      id: "webhook_to_merge",
      source: "webhook_start",
      target: "trigger_merge",
      sourceHandle: "out",
    },
    {
      id: "schedule_to_merge",
      source: "schedule_start",
      target: "trigger_merge",
      sourceHandle: "out",
    },
    {
      id: "merge_to_report",
      source: "trigger_merge",
      target: "entry_report",
      sourceHandle: "out",
    },
  ],
};

export function setupPipelineEditorApiMocks() {
  vi.mocked(api.studioPipelines.get).mockResolvedValue(freshPipeline as never);
  vi.mocked(api.studioPipelines.run).mockResolvedValue({
    id: 99,
    pipeline_id: 45,
    pipeline_name: "All Nodes Smoke Test",
    status: "queued",
    node_states: {},
    nodes_snapshot: freshPipeline.nodes,
    context: {},
    summary: "",
    error: "",
    duration_seconds: null,
    started_at: null,
    finished_at: null,
    created_at: "2026-04-11T08:10:00Z",
    triggered_by: "tester",
    trigger_id: 401,
    entry_node_id: "manual_start",
    trigger_type: "manual",
    trigger_name: "Manual Start",
    trigger_node_id: "manual_start",
  } as never);
  vi.mocked(api.studioPipelines.validateRun).mockResolvedValue({
    ok: true,
    validation: { ok: true, errors: [] },
    risk: { level: "safe", items: [] },
    dry_run: {
      ok: true,
      executed: false,
      mode: "validate_only",
      checks: ["graph_contract", "manual_trigger", "references", "risk_review"],
      message: "No runtime actions were executed.",
    },
    entry_node_id: "manual_start",
    trigger_type: "manual",
    would_create_run: false,
  } as never);
  vi.mocked(api.studioPipelines.update).mockImplementation(async (_id, data) => ({
    ...freshPipeline,
    ...data,
  }) as never);
  vi.mocked(api.studioAgents.list).mockResolvedValue([]);
  vi.mocked(api.studioServers.list).mockResolvedValue([]);
  vi.mocked(api.studioRuns.list).mockResolvedValue([]);
  vi.mocked(api.studioRuns.get).mockResolvedValue(null as never);
  vi.mocked(api.studioRuns.stop).mockResolvedValue({ ok: true } as never);
  vi.mocked(api.studioMCP.list).mockResolvedValue([]);
  vi.mocked(api.studioMCP.tools).mockResolvedValue({ tools: [] } as never);
  vi.mocked(api.studioSkills.list).mockResolvedValue([]);
  vi.mocked(api.studioNodeManifests.get).mockResolvedValue({ version: 1, count: 0, nodes: [] } as never);
  vi.mocked(api.fetchModels).mockResolvedValue({ providers: [], defaults: {} } as never);
  vi.mocked(api.refreshModels).mockResolvedValue({ providers: [], defaults: {} } as never);
}
