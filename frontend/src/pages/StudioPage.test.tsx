import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import StudioPage from "@/pages/StudioPage";
import * as api from "@/lib/api";
import * as draftApi from "@/lib/studioPipelineDraftsApi";
import {
  authSession,
  multiTriggerPipelineDetail,
  multiTriggerPipelineListItem,
  pendingManualPipelineRun,
  ticketReportPipelineDetail,
  ticketReportPipelineListItem,
} from "./studioPageTestFixtures";

const toastMock = vi.fn();
const navigateMock = vi.hoisted(() => vi.fn());

vi.mock("@/components/StudioNav", () => ({
  StudioNav: () => <div>StudioNav</div>,
}));

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: toastMock }),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock("@/lib/featureAccess", () => ({
  hasFeatureAccess: () => true,
}));

vi.mock("@/lib/i18n", () => ({
  useI18n: () => ({ lang: "en", setLang: () => undefined, t: (key: string) => key }),
  localize: (lang: string, ru: string, en: string) => (lang === "ru" ? ru : en),
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

vi.mock("@/lib/studioPipelineDraftsApi", () => ({
  studioPipelineDrafts: {
    list: vi.fn(),
    create: vi.fn(),
    get: vi.fn(),
    discard: vi.fn(),
    revise: vi.fn(),
    apply: vi.fn(),
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
    navigateMock.mockClear();

    vi.mocked(api.fetchAuthSession).mockResolvedValue(authSession());
    vi.mocked(api.studioPipelines.list).mockResolvedValue([multiTriggerPipelineListItem()]);
    vi.mocked(api.studioPipelines.get).mockResolvedValue(multiTriggerPipelineDetail());
    vi.mocked(api.studioPipelines.run).mockResolvedValue(pendingManualPipelineRun() as never);

    vi.mocked(api.studioTemplates.list).mockResolvedValue([]);
    vi.mocked(api.studioTemplates.use).mockResolvedValue({} as never);
    vi.mocked(api.studioMCP.list).mockResolvedValue([]);
    vi.mocked(api.studioRuns.list).mockResolvedValue([]);
    vi.mocked(api.studioSkills.list).mockResolvedValue([]);
    vi.mocked(api.studioAgents.list).mockResolvedValue([]);
    vi.mocked(draftApi.studioPipelineDrafts.list).mockResolvedValue([]);
  });

  it("prompts for the manual trigger when a pipeline has multiple manual entries", async () => {
    renderPage();

    const runButton = await screen.findByRole("button", { name: /^Run$/ });
    fireEvent.click(runButton);

    expect(await screen.findByText(/Choose manual trigger/i)).toBeInTheDocument();

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

    expect(await screen.findByRole("heading", { name: /^Webhook trigger$/i })).toBeInTheDocument();
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

    expect(await screen.findByRole("heading", { name: /^Monitoring trigger$/i })).toBeInTheDocument();
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

  it("shows the pipeline list without launchpad or template starter panels", async () => {
    vi.mocked(draftApi.studioPipelineDrafts.list).mockResolvedValue([
      {
        id: 5,
        status: "ready",
        intent: "create",
        title: "Existing draft",
        user_goal: "Create a daily health report",
        source_pipeline_id: null,
        applied_pipeline_id: null,
        selected_node_id: "",
        created_at: "2026-04-10T10:00:00Z",
        updated_at: "2026-04-10T10:05:00Z",
        applied_at: null,
        latest_revision: {
          id: 9,
          session_id: 5,
          user_message: "Create a daily health report",
          created_at: "2026-04-10T10:05:00Z",
          preview_nodes: [],
          preview_edges: [],
          response: {
            reply: "Draft ready.",
            target_node_id: null,
            node_patch: {},
            graph_patch: {
              anchor_node_id: null,
              nodes: [
                { ref: "manual_start", type: "trigger/manual", label: "Manual start", data: {} },
                { ref: "report", type: "output/report", label: "Report", data: {} },
              ],
              edges: [{ source: "manual_start", target: "report" }],
            },
            warnings: [],
            validation: { ok: true, errors: [], warnings: [] },
            risk: { level: "safe", items: [] },
            patch_summary: "Creates a manual report pipeline.",
          },
        },
      },
    ] as never);

    renderPage();

    expect(await screen.findByRole("heading", { name: "All pipelines" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Search pipelines" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Automation launchpad" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Graph-first cockpit for AI automations/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Open AI Drafts/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Automation request")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Template quick start" })).not.toBeInTheDocument();
    expect(api.studioTemplates.list).not.toHaveBeenCalled();
  });

  it("opens the editor run dialog instead of blind-running templates that need context", async () => {
    vi.mocked(api.studioPipelines.list).mockResolvedValue([ticketReportPipelineListItem()] as never);
    vi.mocked(api.studioPipelines.get).mockResolvedValue(ticketReportPipelineDetail() as never);

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /^Run$/ }));

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/studio/pipeline/66", { state: { openRunDialog: true } });
    });
    expect(api.studioPipelines.run).not.toHaveBeenCalled();
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({
        description: expect.stringMatching(/Fill context fields before running: ticket_id/i),
      }),
    );
  });
});
