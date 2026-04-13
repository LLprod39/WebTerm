import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PipelineEditorPage, { buildPipelineSavePayload } from "@/pages/PipelineEditorPage";
import * as api from "@/lib/api";

const toastMock = vi.fn();

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: toastMock }),
}));

vi.mock("@xyflow/react", async () => {
  const React = await import("react");

  const useNodesState = (initial: unknown[] = []) => {
    const [nodes, setNodes] = React.useState(initial);
    return [nodes, setNodes, () => {}] as const;
  };

  const useEdgesState = (initial: unknown[] = []) => {
    const [edges, setEdges] = React.useState(initial);
    return [edges, setEdges, () => {}] as const;
  };

  return {
    ReactFlowProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
    ReactFlow: ({ children }: { children?: ReactNode }) => <div data-testid="react-flow">{children}</div>,
    Background: () => null,
    Controls: () => null,
    MiniMap: () => null,
    Panel: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
    addEdge: (connection: Record<string, unknown>, edges: unknown[]) => [
      ...edges,
      {
        id: `edge_${String(connection.source)}_${String(connection.target)}_${String(connection.sourceHandle || "out")}`,
        ...connection,
      },
    ],
    useNodesState,
    useEdgesState,
    useReactFlow: () => ({
      screenToFlowPosition: ({ x, y }: { x: number; y: number }) => ({ x, y }),
      fitView: () => undefined,
    }),
    BackgroundVariant: { Dots: "dots" },
  };
});

vi.mock("@/lib/api", () => ({
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
  studioAgents: {
    list: vi.fn(),
  },
  studioServers: {
    list: vi.fn(),
  },
  studioRuns: {
    get: vi.fn(),
    list: vi.fn(),
    stop: vi.fn(),
  },
  studioMCP: {
    list: vi.fn(),
    tools: vi.fn(),
  },
  studioSkills: {
    list: vi.fn(),
  },
  fetchModels: vi.fn(),
  refreshModels: vi.fn(),
  getStudioPipelineRunWsUrl: vi.fn(() => "ws://localhost/ws/studio/pipeline-runs/test/live/"),
}));

function buildQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
}

class MockWebSocket {
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(_url: string) {
    queueMicrotask(() => this.onopen?.(new Event("open")));
  }

  close() {
    this.onclose?.({} as CloseEvent);
  }
}

vi.stubGlobal("WebSocket", MockWebSocket);

const stalePipeline = {
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

const freshPipeline = {
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

function renderPage(queryClient: QueryClient) {
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

describe("PipelineEditorPage save hydration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toastMock.mockReset();
    document.documentElement.lang = "ru";

    vi.mocked(api.studioPipelines.get).mockResolvedValue(freshPipeline as never);
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
    vi.mocked(api.fetchModels).mockResolvedValue({ providers: [], defaults: {} } as never);
    vi.mocked(api.refreshModels).mockResolvedValue({ providers: [], defaults: {} } as never);
  });

  it("saves the fresh server graph instead of stale cached trigger edges", async () => {
    const queryClient = buildQueryClient();
    queryClient.setQueryData(["studio", "pipeline", 45], stalePipeline);

    renderPage(queryClient);

    await waitFor(() => {
      expect(api.studioPipelines.get).toHaveBeenCalledWith(45);
    });

    const saveButton = await screen.findByRole("button", { name: /^Save$/ });
    await waitFor(() => expect(saveButton).not.toBeDisabled());

    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(api.studioPipelines.update).toHaveBeenCalledTimes(1);
    });

    const [, payload] = vi.mocked(api.studioPipelines.update).mock.calls[0];
    expect(payload.nodes).toHaveLength(freshPipeline.nodes.length);
    expect(payload.edges).toHaveLength(freshPipeline.edges.length);
    expect(payload.edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: "manual_start", target: "trigger_merge" }),
        expect.objectContaining({ source: "webhook_start", target: "trigger_merge" }),
        expect.objectContaining({ source: "schedule_start", target: "trigger_merge" }),
      ]),
    );
  });

  it("prefers the authoritative server graph when the editor has no local changes", () => {
    const payload = buildPipelineSavePayload({
      pipelineId: 45,
      pipeline: freshPipeline,
      pipelineName: "All Nodes Smoke Test",
      nodes: stalePipeline.nodes as unknown as api.PipelineNode[],
      edges: stalePipeline.edges as unknown as api.PipelineEdge[],
      hasLocalChanges: false,
    });

    expect(payload.nodes).toEqual(freshPipeline.nodes);
    expect(payload.edges).toEqual(freshPipeline.edges);
  });

  it("shows the current step badge when the latest run is active", async () => {
    vi.mocked(api.studioPipelines.get).mockResolvedValue({
      ...freshPipeline,
      last_run: {
        id: 88,
        status: "running",
        started_at: "2026-04-11T08:10:00Z",
        finished_at: null,
      },
    } as never);
    vi.mocked(api.studioRuns.get).mockResolvedValue({
      id: 88,
      pipeline_id: 45,
      pipeline_name: "All Nodes Smoke Test",
      status: "running",
      node_states: {
        entry_report: {
          status: "running",
          started_at: "2026-04-11T08:10:15Z",
        },
        trigger_merge: {
          status: "completed",
          started_at: "2026-04-11T08:10:05Z",
          finished_at: "2026-04-11T08:10:10Z",
          routing_ports: ["out"],
        },
      },
      nodes_snapshot: freshPipeline.nodes as api.PipelineNode[],
      context: {},
      summary: "",
      error: "",
      duration_seconds: null,
      started_at: "2026-04-11T08:10:00Z",
      finished_at: null,
      created_at: "2026-04-11T08:10:00Z",
      triggered_by: "tester",
      trigger_id: 402,
      entry_node_id: "webhook_start",
      trigger_type: "webhook",
      trigger_name: "Webhook Start",
      trigger_node_id: "webhook_start",
    } as never);

    const queryClient = buildQueryClient();
    renderPage(queryClient);

    expect(await screen.findByText(/Текущий шаг:/)).toHaveTextContent("Entry Snapshot");
  });

  it("keeps assistant chat history when sending follow-up edits", async () => {
    vi.mocked(api.studioPipelines.assistant)
      .mockResolvedValueOnce({
        reply: "Добавлю Telegram-уведомление.",
        target_node_id: null,
        node_patch: {},
        graph_patch: { anchor_node_id: "entry_report", nodes: [], edges: [], update_nodes: [], remove_node_ids: [], remove_edge_ids: [] },
        warnings: [],
      } as never)
      .mockResolvedValueOnce({
        reply: "Сделаю текст уведомления короче.",
        target_node_id: "entry_report",
        node_patch: { title: "Краткий отчет" },
        graph_patch: { anchor_node_id: null, nodes: [], edges: [], update_nodes: [], remove_node_ids: [], remove_edge_ids: [] },
        warnings: [],
      } as never);

    const queryClient = buildQueryClient();
    renderPage(queryClient);

    await waitFor(() => expect(api.studioPipelines.get).toHaveBeenCalledWith(45));

    fireEvent.click(await screen.findByRole("button", { name: "AI Builder" }));

    const textarea = await screen.findByPlaceholderText("Опишите задачу или попросите изменить текущий пайплайн…");
    fireEvent.change(textarea, { target: { value: "Собери автоматизацию для Telegram-уведомления." } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    await waitFor(() => expect(api.studioPipelines.assistant).toHaveBeenCalledTimes(1));

    fireEvent.change(await screen.findByPlaceholderText("Опишите задачу или попросите изменить текущий пайплайн…"), {
      target: { value: "Теперь укороти текст отчета." },
    });
    fireEvent.keyDown(await screen.findByPlaceholderText("Опишите задачу или попросите изменить текущий пайплайн…"), { key: "Enter" });

    await waitFor(() => expect(api.studioPipelines.assistant).toHaveBeenCalledTimes(2));

    const secondCall = vi.mocked(api.studioPipelines.assistant).mock.calls[1][0];
    expect(secondCall.history).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ role: "user", content: "Собери автоматизацию для Telegram-уведомления." }),
        expect.objectContaining({ role: "assistant", content: "Добавлю Telegram-уведомление." }),
        expect.objectContaining({ role: "user", content: "Теперь укороти текст отчета." }),
      ]),
    );
  });
});
