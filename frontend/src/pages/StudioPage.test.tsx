import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import StudioPage from "@/pages/StudioPage";
import * as api from "@/lib/api";

const toastMock = vi.fn();

vi.mock("@/components/StudioNav", () => ({
  StudioNav: () => <div>StudioNav</div>,
}));

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: toastMock }),
}));

vi.mock("@/lib/featureAccess", () => ({
  hasFeatureAccess: () => true,
}));

vi.mock("@/lib/api", () => ({
  fetchAuthSession: vi.fn(),
  studioPipelines: {
    list: vi.fn(),
    get: vi.fn(),
    run: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    clone: vi.fn(),
    runs: vi.fn(),
    assistant: vi.fn(),
  },
  studioTemplates: {
    list: vi.fn(),
    use: vi.fn(),
  },
  studioMCP: {
    list: vi.fn(),
  },
  studioRuns: {
    list: vi.fn(),
  },
  studioSkills: {
    list: vi.fn(),
  },
  studioAgents: {
    list: vi.fn(),
  },
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <StudioPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("StudioPage quick run", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(api.fetchAuthSession).mockResolvedValue({
      authenticated: true,
      user: {
        id: 1,
        username: "admin",
        email: "admin@example.com",
        is_staff: true,
        features: {},
      },
    });

    vi.mocked(api.studioPipelines.list).mockResolvedValue([
      {
        id: 42,
        name: "Multi Trigger Pipeline",
        description: "demo",
        icon: "W",
        tags: [],
        is_shared: false,
        node_count: 4,
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
      },
    ]);
    vi.mocked(api.studioPipelines.get).mockResolvedValue({
      id: 42,
      name: "Multi Trigger Pipeline",
      description: "demo",
      icon: "W",
      tags: [],
      is_shared: false,
      node_count: 4,
      updated_at: "2026-04-10T10:00:00Z",
      last_run: null,
      graph_version: 2,
      nodes: [
        {
          id: "manual_a",
          type: "trigger/manual",
          position: { x: 0, y: 0 },
          data: { label: "Manual A" },
        },
        {
          id: "manual_b",
          type: "trigger/manual",
          position: { x: 0, y: 100 },
          data: { label: "Manual B" },
        },
        {
          id: "merge",
          type: "logic/merge",
          position: { x: 100, y: 50 },
          data: { mode: "any" },
        },
        {
          id: "report",
          type: "output/report",
          position: { x: 200, y: 50 },
          data: {},
        },
      ],
      edges: [
        { id: "e1", source: "manual_a", target: "merge", sourceHandle: "out" },
        { id: "e2", source: "manual_b", target: "merge", sourceHandle: "out" },
        { id: "e3", source: "merge", target: "report", sourceHandle: "out" },
      ],
      triggers: [],
    });
    vi.mocked(api.studioPipelines.run).mockResolvedValue({
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
    });

    vi.mocked(api.studioTemplates.list).mockResolvedValue([]);
    vi.mocked(api.studioTemplates.use).mockResolvedValue({} as never);
    vi.mocked(api.studioMCP.list).mockResolvedValue([]);
    vi.mocked(api.studioRuns.list).mockResolvedValue([]);
    vi.mocked(api.studioSkills.list).mockResolvedValue([]);
    vi.mocked(api.studioAgents.list).mockResolvedValue([]);
  });

  it("prompts for the manual trigger when a pipeline has multiple manual entries", async () => {
    renderPage();

    const runButton = await screen.findByRole("button", { name: /^Run$/ });
    fireEvent.click(runButton);

    expect(await screen.findByText("Choose Manual Trigger")).toBeInTheDocument();

    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "manual_b" } });
    fireEvent.click(screen.getByRole("button", { name: /^Run$/ }));

    await waitFor(() => {
      expect(api.studioPipelines.run).toHaveBeenCalledWith(42, undefined, "manual_b");
    });
  });

  it("shows webhook trigger instructions instead of manual run when the pipeline is webhook-only", async () => {
    vi.mocked(api.studioPipelines.list).mockResolvedValue([
      {
        id: 77,
        name: "Webhook Only Pipeline",
        description: "demo",
        icon: "W",
        tags: [],
        is_shared: false,
        node_count: 2,
        updated_at: "2026-04-10T10:00:00Z",
        last_run: null,
        graph_version: 2,
        trigger_summary: {
          active_total: 1,
          active_manual: 0,
          active_webhook: 1,
          active_schedule: 0,
          last_triggered_at: null,
        },
      },
    ]);
    vi.mocked(api.studioPipelines.get).mockResolvedValue({
      id: 77,
      name: "Webhook Only Pipeline",
      description: "demo",
      icon: "W",
      tags: [],
      is_shared: false,
      node_count: 2,
      updated_at: "2026-04-10T10:00:00Z",
      last_run: null,
      graph_version: 2,
      nodes: [
        {
          id: "webhook_start",
          type: "trigger/webhook",
          position: { x: 0, y: 0 },
          data: { label: "Incoming webhook" },
        },
        {
          id: "report",
          type: "output/report",
          position: { x: 180, y: 0 },
          data: {},
        },
      ],
      edges: [
        { id: "e1", source: "webhook_start", target: "report", sourceHandle: "out" },
      ],
      triggers: [
        {
          id: 12,
          pipeline_id: 77,
          node_id: "webhook_start",
          name: "Incoming webhook",
          trigger_type: "webhook",
          is_active: true,
          webhook_token: "token-123",
          webhook_url: "/api/studio/triggers/token-123/receive/",
          cron_expression: "",
          webhook_payload_map: {},
          last_triggered_at: null,
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("Waiting for webhook POST.")).toBeInTheDocument();

    const runButton = await screen.findByRole("button", { name: /^Run$/ });
    fireEvent.click(runButton);

    expect(await screen.findByText("Webhook Trigger")).toBeInTheDocument();
    expect(
      screen.getByText(/incoming webhook requests/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/token-123/)).toBeInTheDocument();
    expect(api.studioPipelines.run).not.toHaveBeenCalled();
  });

  it("shows monitoring trigger instructions instead of an error when the pipeline is monitoring-only", async () => {
    vi.mocked(api.studioPipelines.list).mockResolvedValue([
      {
        id: 88,
        name: "Monitoring Only Pipeline",
        description: "docker recovery",
        icon: "W",
        tags: [],
        is_shared: false,
        node_count: 2,
        updated_at: "2026-04-10T10:00:00Z",
        last_run: null,
        graph_version: 2,
        trigger_summary: {
          active_total: 1,
          active_manual: 0,
          active_webhook: 0,
          active_schedule: 0,
          active_monitoring: 1,
          last_triggered_at: null,
        },
      },
    ] as never);
    vi.mocked(api.studioPipelines.get).mockResolvedValue({
      id: 88,
      name: "Monitoring Only Pipeline",
      description: "docker recovery",
      icon: "W",
      tags: [],
      is_shared: false,
      node_count: 2,
      updated_at: "2026-04-10T10:00:00Z",
      last_run: null,
      graph_version: 2,
      nodes: [
        {
          id: "monitoring_start",
          type: "trigger/monitoring",
          position: { x: 0, y: 0 },
          data: { label: "Docker Alert" },
        },
        {
          id: "report",
          type: "output/report",
          position: { x: 180, y: 0 },
          data: {},
        },
      ],
      edges: [{ id: "e1", source: "monitoring_start", target: "report", sourceHandle: "out" }],
      triggers: [
        {
          id: 18,
          pipeline_id: 88,
          node_id: "monitoring_start",
          name: "Docker Alert",
          trigger_type: "monitoring",
          is_active: true,
          webhook_token: "unused-token",
          webhook_url: "/api/studio/triggers/unused-token/receive/",
          cron_expression: "",
          webhook_payload_map: {},
          monitoring_filters: {
            server_ids: [20],
            severities: ["critical"],
            alert_types: ["service"],
            container_names: ["mini-prod-mcp-demo"],
          },
          last_triggered_at: null,
        },
      ],
    } as never);

    renderPage();

    const runButton = await screen.findByRole("button", { name: /^Run$/ });
    fireEvent.click(runButton);

    expect(await screen.findByText("Monitoring Trigger")).toBeInTheDocument();
    expect(screen.getByText(/started by server monitoring alerts/i)).toBeInTheDocument();
    expect(screen.getByText(/mini-prod-mcp-demo/)).toBeInTheDocument();
    expect(toastMock).not.toHaveBeenCalledWith(
      expect.objectContaining({
        variant: "destructive",
        description: expect.stringMatching(/no active triggers/i),
      }),
    );
    expect(api.studioPipelines.run).not.toHaveBeenCalled();
  });
});
