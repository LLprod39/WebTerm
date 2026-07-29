import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { formatCommandListText, parseCommandListText } from "@/components/pipeline/commandList";
import { getPipelineClientValidationErrors } from "@/components/pipeline/pipelineClientValidation";
import { buildPipelineSavePayload } from "@/pages/pipeline-editor/pipelineGraphUtils";
import * as api from "@/lib/api";
import {
  buildQueryClient,
  freshPipeline,
  renderPage,
  setupPipelineEditorApiMocks,
  stalePipeline,
} from "@/pages/pipeline-editor/pipelineEditorPageTestHarness";

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
    ReactFlow: ({
      children,
      nodes = [],
      onNodeClick,
    }: {
      children?: ReactNode;
      nodes?: Array<{ id: string; data?: { label?: string } }>;
      onNodeClick?: (event: unknown, node: { id: string; data?: { label?: string } }) => void;
    }) => (
      <div data-testid="react-flow">
        {nodes.map((node) => (
          <button key={node.id} type="button" data-testid={`node-${node.id}`} onClick={() => onNodeClick?.({}, node)}>
            {node.data?.label || node.id}
          </button>
        ))}
        {children}
      </div>
    ),
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
    validateRun: vi.fn(),
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
  studioNodeManifests: {
    get: vi.fn(),
  },
  fetchModels: vi.fn(),
  refreshModels: vi.fn(),
  getStudioPipelineRunWsUrl: vi.fn(() => "ws://localhost/ws/studio/pipeline-runs/test/live/"),
}));

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

describe("PipelineEditorPage save hydration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toastMock.mockReset();
    document.documentElement.lang = "ru";

    setupPipelineEditorApiMocks();
  });

  it("saves the fresh server graph instead of stale cached trigger edges", async () => {
    const queryClient = buildQueryClient();
    queryClient.setQueryData(["studio", "pipeline", 45], stalePipeline);

    renderPage(queryClient);

    await waitFor(() => {
      expect(api.studioPipelines.get).toHaveBeenCalledWith(45);
    });

    const saveButton = await screen.findByRole("button", { name: /^(Save|Сохранить)$/ });
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

  it("keeps the assigned approval user in save payload", () => {
    const approvalPipeline = {
      ...freshPipeline,
      nodes: [
        ...freshPipeline.nodes,
        {
          id: "approval_gate",
          type: "logic/human_approval",
          position: { x: 720, y: 0 },
          data: {
            label: "Approve Recovery",
            to_email: "",
            tg_chat_id: "",
            timeout_minutes: 45,
            approver_username: "oncall-approver",
          },
        },
      ],
    };

    const payload = buildPipelineSavePayload({
      pipelineId: 45,
      pipeline: approvalPipeline,
      pipelineName: "All Nodes Smoke Test",
      nodes: approvalPipeline.nodes as unknown as api.PipelineNode[],
      edges: approvalPipeline.edges as unknown as api.PipelineEdge[],
      hasLocalChanges: true,
    });
    const approvalNode = payload.nodes.find((item) => item.id === "approval_gate");
    expect(approvalNode?.data).toMatchObject({ approver_username: "oncall-approver" });
  });

  it("round-trips SSH preflight and verification command lists", () => {
    expect(parseCommandListText(" systemctl is-active nginx \n\n nginx -t \r\n")).toEqual([
      "systemctl is-active nginx",
      "nginx -t",
    ]);
    expect(formatCommandListText(["systemctl is-active nginx", "", "curl -fsS http://localhost/health"])).toBe(
      "systemctl is-active nginx\ncurl -fsS http://localhost/health",
    );
  });

  it("reports a local validation error for contains conditions without a check value", () => {
    const errors = getPipelineClientValidationErrors([
      {
        id: "condition",
        type: "logic/condition",
        position: { x: 0, y: 0 },
        data: { check_type: "contains", check_value: "" },
      },
    ] as unknown as api.PipelineNode[]);

    expect(errors).toHaveLength(1);
    expect(errors[0]).toMatchObject({ nodeId: "condition", field: "check_value" });
  });

  it("checks configured values against node manifest schema enum and range", () => {
    const manifests = [
      {
        type: "ops/log_query",
        input_schema: {
          type: "object",
          properties: {
            source: { type: "string", enum: ["journal", "docker"] },
            lines: { type: "integer", minimum: 20, maximum: 240 },
          },
        },
      },
    ] as unknown as api.StudioCapabilityNode[];

    const errors = getPipelineClientValidationErrors([
      {
        id: "logs",
        type: "ops/log_query",
        position: { x: 0, y: 0 },
        data: { source: "unknown", lines: 500 },
      },
    ] as unknown as api.PipelineNode[], manifests);

    expect(errors).toEqual([
      expect.objectContaining({ nodeId: "logs", field: "source" }),
      expect.objectContaining({ nodeId: "logs", field: "lines" }),
    ]);
  });

  it("checks MCP arguments against embedded tool schema", () => {
    const errors = getPipelineClientValidationErrors([
      {
        id: "inspect",
        type: "agent/mcp_call",
        position: { x: 0, y: 0 },
        data: {
          tool_name: "kubernetes_describe_workload",
          arguments: { namespace: "auth", kind: "cronjob" },
          input_schema: {
            type: "object",
            properties: {
              namespace: { type: "string" },
              kind: { type: "string", enum: ["deployment", "statefulset"] },
              name: { type: "string" },
            },
            required: ["namespace", "kind", "name"],
          },
        },
      },
    ] as unknown as api.PipelineNode[]);

    expect(errors).toEqual([
      expect.objectContaining({ nodeId: "inspect", field: "name" }),
      expect.objectContaining({ nodeId: "inspect", field: "kind" }),
    ]);
  });

});
