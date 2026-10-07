import { act, renderHook } from "@testing-library/react";
import type { DragEvent } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Edge, Node } from "@xyflow/react";

import {
  edgeIdAtClientPoint,
  usePipelineEditorGraphActions,
} from "./usePipelineEditorGraphActions";

function node(id: string, type = "agent/llm", position = { x: 0, y: 0 }): Node {
  return { id, type, position, data: { label: id } };
}

describe("edgeIdAtClientPoint", () => {
  it("reads data-id from .react-flow__edge under the point", () => {
    const edge = document.createElement("div");
    edge.className = "react-flow__edge";
    edge.setAttribute("data-id", "edge_a_b_out");
    const child = document.createElement("span");
    edge.appendChild(child);
    document.body.appendChild(edge);

    const stub = vi.fn().mockReturnValue([child]);
    Object.defineProperty(document, "elementsFromPoint", {
      configurable: true,
      writable: true,
      value: stub,
    });
    expect(edgeIdAtClientPoint(10, 20)).toBe("edge_a_b_out");
    edge.remove();
  });
});

describe("usePipelineEditorGraphActions", () => {
  const setNodes = vi.fn();
  const setEdges = vi.fn();
  const setSelectedNode = vi.fn();
  const setActiveRunId = vi.fn();
  const setHasLocalChanges = vi.fn();
  const pushHistory = vi.fn();
  const toast = vi.fn();
  const clearGraphOverlay = vi.fn();
  const onRequestPicker = vi.fn();
  const nodeIdCounter = { current: 1 };

  const baseNodes = [node("a", "trigger/manual", { x: 0, y: 0 }), node("b", "agent/llm", { x: 280, y: 0 })];
  const baseEdges: Edge[] = [
    { id: "edge_a_b_out", source: "a", target: "b", sourceHandle: "out", type: "studio" },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    nodeIdCounter.current = 1;
    setNodes.mockImplementation((updater) => {
      if (typeof updater === "function") return updater(baseNodes);
      return updater;
    });
    setEdges.mockImplementation((updater) => {
      if (typeof updater === "function") return updater(baseEdges);
      return updater;
    });
  });

  function renderActions(overrides: Partial<Parameters<typeof usePipelineEditorGraphActions>[0]> = {}) {
    return renderHook(() =>
      usePipelineEditorGraphActions({
        clearGraphOverlay,
        edges: baseEdges,
        lang: "en",
        nodeIdCounter,
        nodes: baseNodes as never[],
        nodeManifests: [],
        onRequestPicker,
        pipelineName: "Test",
        pushHistory,
        screenToFlowPosition: ({ x, y }) => ({ x, y }),
        selectedNode: baseNodes[0] as never,
        setActiveRunId,
        setEdges,
        setHasLocalChanges,
        setNodes,
        setSelectedNode,
        toast,
        ...overrides,
      }),
    );
  }

  it("opens picker on onConnectEndEmpty from a source handle", () => {
    const { result } = renderActions();
    act(() => {
      result.current.onConnectEndEmpty(
        new MouseEvent("mouseup", { clientX: 120, clientY: 80 }),
        { nodeId: "a", handleId: "out", handleType: "source" },
      );
    });
    expect(onRequestPicker).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "connect",
        sourceNodeId: "a",
        sourceHandle: "out",
        position: expect.objectContaining({ x: 120, y: 80 }),
      }),
    );
    expect(result.current.pendingConnect?.kind).toBe("connect");
  });

  it("add-from-palette creates an edge to the selected node", () => {
    const { result } = renderActions();
    act(() => {
      result.current.handleAddNode("agent/llm");
    });
    expect(setNodes).toHaveBeenCalled();
    expect(setEdges).toHaveBeenCalled();
    expect(pushHistory).toHaveBeenCalledTimes(1);
    const snapshot = pushHistory.mock.calls[0][0];
    expect(snapshot.nodes.some((n: Node) => n.id.startsWith("node_"))).toBe(true);
    expect(snapshot.edges.some((e: Edge) => e.source === "a" && e.target?.startsWith("node_"))).toBe(
      true,
    );
  });

  it("drop on an edge inserts between via insertBetween", () => {
    const edge = document.createElement("div");
    edge.className = "react-flow__edge";
    edge.setAttribute("data-id", "edge_a_b_out");
    document.body.appendChild(edge);
    Object.defineProperty(document, "elementsFromPoint", {
      configurable: true,
      writable: true,
      value: vi.fn().mockReturnValue([edge]),
    });

    const { result } = renderActions({ selectedNode: null });
    const dt = {
      getData: () => "logic/condition",
    } as unknown as DataTransfer;

    act(() => {
      result.current.handleDrop({
        preventDefault: () => undefined,
        clientX: 40,
        clientY: 40,
        dataTransfer: dt,
      } as unknown as DragEvent);
    });

    expect(pushHistory).toHaveBeenCalledTimes(1);
    const snapshot = pushHistory.mock.calls[0][0];
    expect(snapshot.nodes).toHaveLength(3);
    expect(snapshot.edges).toHaveLength(2);
    expect(snapshot.edges.find((e: Edge) => e.id === "edge_a_b_out")).toBeUndefined();

    edge.remove();
  });

  it("handlePickPending pushes the after-state so redo can restore", () => {
    const { result } = renderActions();
    act(() => {
      result.current.onConnectEndEmpty(
        new MouseEvent("mouseup", { clientX: 10, clientY: 10 }),
        { nodeId: "a", handleId: "out", handleType: "source" },
      );
    });
    act(() => {
      result.current.handlePickPending("agent/llm");
    });
    expect(pushHistory).toHaveBeenCalledTimes(1);
    const snapshot = pushHistory.mock.calls[0][0];
    expect(snapshot.nodes).toHaveLength(3);
    expect(snapshot.edges.some((e: Edge) => e.source === "a")).toBe(true);
  });

  it("delete node / edge / duplicate / connect push history", () => {
    const { result } = renderActions();
    act(() => result.current.handleDeleteEdge("edge_a_b_out"));
    act(() => result.current.handleDuplicateNode("b"));
    act(() =>
      result.current.onConnect({
        source: "a",
        target: "b",
        sourceHandle: "out",
        targetHandle: null,
      }),
    );
    act(() => result.current.handleDeleteNode("b"));
    expect(pushHistory.mock.calls.length).toBeGreaterThanOrEqual(4);
  });
});
