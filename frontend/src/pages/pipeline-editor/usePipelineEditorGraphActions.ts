import {
  useCallback,
  useMemo,
  useState,
  type Dispatch,
  type DragEvent,
  type SetStateAction,
} from "react";
import {
  addEdge,
  type Connection,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import type { PipelineNode, StudioCapabilityNode } from "@/lib/api";
import { isPluginStudioNode } from "@/plugins/studioNodes";
import { isNodeType, localize } from "./presentation";
import {
  buildConnectionAutofillPatch,
  buildDefaultNodeData,
  getNodeDisplayLabel,
} from "./pipelineGraphUtils";
import {
  firstSourceHandleForType,
  insertBetween,
  makeEdgeId,
} from "./graphEdgeOps";
import type { QuickPickerPosition } from "./QuickNodePicker";
import type { PipelineGraphSnapshot } from "./usePipelineGraphHistory";

type FlowPosition = { x: number; y: number };

export type StudioPendingConnect =
  | {
      kind: "connect";
      sourceNodeId: string;
      sourceHandle: string;
      position: QuickPickerPosition;
    }
  | {
      kind: "insert";
      edgeId: string;
      position: QuickPickerPosition;
    }
  | null;

export type StudioPickerRequest = NonNullable<StudioPendingConnect>;

function clientPointFromEvent(event: MouseEvent | TouchEvent): { x: number; y: number } {
  if ("clientX" in event) {
    return { x: event.clientX, y: event.clientY };
  }
  const touch = event.changedTouches?.[0] || event.touches?.[0];
  return { x: touch?.clientX ?? 0, y: touch?.clientY ?? 0 };
}

/** Resolve React Flow edge id under a client point (drop-on-edge). */
export function edgeIdAtClientPoint(clientX: number, clientY: number): string | null {
  if (typeof document === "undefined" || typeof document.elementsFromPoint !== "function") {
    return null;
  }
  for (const el of document.elementsFromPoint(clientX, clientY)) {
    const edge = (el as Element).closest?.(".react-flow__edge");
    if (!edge) continue;
    const id = edge.getAttribute("data-id");
    if (id) return id;
  }
  return null;
}

export function usePipelineEditorGraphActions({
  clearGraphOverlay,
  edges,
  lang,
  nodeIdCounter,
  nodes,
  nodeManifests,
  onRequestPicker,
  pipelineName,
  pushHistory,
  screenToFlowPosition,
  selectedNode,
  setActiveRunId,
  setEdges,
  setHasLocalChanges,
  setNodes,
  setSelectedNode,
  toast,
}: {
  clearGraphOverlay: () => void;
  edges: Edge[];
  lang: "en" | "ru";
  nodeIdCounter: { current: number };
  nodes: PipelineNode[];
  nodeManifests: StudioCapabilityNode[];
  /** Optional external picker opener (integrator can own UI). */
  onRequestPicker?: (request: StudioPickerRequest) => void;
  pipelineName: string;
  /** Commit after-state snapshot for undo/redo. */
  pushHistory?: (snapshot: PipelineGraphSnapshot) => void;
  screenToFlowPosition: (position: FlowPosition) => FlowPosition;
  selectedNode: PipelineNode | null;
  setActiveRunId: Dispatch<SetStateAction<number | null>>;
  setEdges: Dispatch<SetStateAction<Edge[]>>;
  setHasLocalChanges: Dispatch<SetStateAction<boolean>>;
  setNodes: Dispatch<SetStateAction<Node[]>>;
  setSelectedNode: Dispatch<SetStateAction<PipelineNode | null>>;
  toast: (options: { description: string }) => void;
}) {
  const [pendingConnect, setPendingConnect] = useState<StudioPendingConnect>(null);

  const manifestByType = useMemo(
    () => new Map(nodeManifests.map((manifest) => [manifest.type, manifest])),
    [nodeManifests],
  );

  const resolveSourceHandle = useCallback(
    (nodeType: string) =>
      firstSourceHandleForType(nodeType, manifestByType.get(nodeType)?.source_handles),
    [manifestByType],
  );

  const applyGraph = useCallback(
    (nextNodes: Node[], nextEdges: Edge[]) => {
      setHasLocalChanges(true);
      setNodes(nextNodes);
      setEdges(nextEdges);
      pushHistory?.({ nodes: nextNodes, edges: nextEdges });
    },
    [pushHistory, setEdges, setHasLocalChanges, setNodes],
  );

  const openPicker = useCallback(
    (request: StudioPickerRequest) => {
      setPendingConnect(request);
      onRequestPicker?.(request);
    },
    [onRequestPicker],
  );

  const clearPendingConnect = useCallback(() => {
    setPendingConnect(null);
  }, []);

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;

      const nextEdges = addEdge(
        {
          ...connection,
          id: makeEdgeId(connection.source, connection.target, connection.sourceHandle),
          type: "studio",
        },
        edges,
      );

      const sourceNode = nodes.find((item) => item.id === connection.source);
      const targetNode = nodes.find((item) => item.id === connection.target);

      clearGraphOverlay();
      setActiveRunId(null);

      if (!targetNode) {
        applyGraph(nodes as unknown as Node[], nextEdges);
        return;
      }

      if (!sourceNode) {
        applyGraph(nodes as unknown as Node[], nextEdges);
        setSelectedNode(targetNode);
        return;
      }

      const patch = buildConnectionAutofillPatch(targetNode, sourceNode, pipelineName);
      if (!Object.keys(patch).length) {
        applyGraph(nodes as unknown as Node[], nextEdges);
        setSelectedNode(targetNode);
        return;
      }

      const nextTarget = { ...targetNode, data: { ...(targetNode.data || {}), ...patch } } as PipelineNode;
      const nextNodes = (nodes as unknown as Node[]).map((item) =>
        item.id === targetNode.id ? (nextTarget as unknown as Node) : item,
      );
      applyGraph(nextNodes, nextEdges);
      setSelectedNode(nextTarget);
      // Silent autofill — no toast about starter settings.
    },
    [
      applyGraph,
      clearGraphOverlay,
      edges,
      nodes,
      pipelineName,
      setActiveRunId,
      setSelectedNode,
    ],
  );

  const onNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      setActiveRunId(null);
      const rawNode =
        nodes.find((item) => item.id === node.id) ||
        (node as unknown as PipelineNode);
      setSelectedNode(rawNode);
    },
    [nodes, setActiveRunId, setSelectedNode],
  );

  const buildNodeAt = useCallback(
    (type: string, position: FlowPosition) => {
      const id = `node_${nodeIdCounter.current++}`;
      const manifest = manifestByType.get(type);
      return {
        id,
        type,
        position,
        data: buildDefaultNodeData(type, manifest),
      } as PipelineNode;
    },
    [manifestByType, nodeIdCounter],
  );

  const createNodeAt = useCallback(
    (type: string, position: FlowPosition) => {
      const newNode = buildNodeAt(type, position);
      const nextNodes = [...(nodes as unknown as Node[]), newNode as unknown as Node];
      applyGraph(nextNodes, edges);
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(newNode);
      return newNode;
    },
    [applyGraph, buildNodeAt, clearGraphOverlay, edges, nodes, setActiveRunId, setSelectedNode],
  );

  const handleAddNode = useCallback(
    (type: string) => {
      const selected = selectedNode ? nodes.find((item) => item.id === selectedNode.id) : null;
      const position = selected
        ? { x: selected.position.x + 280, y: selected.position.y }
        : screenToFlowPosition({ x: 300, y: 200 + nodeIdCounter.current * 80 });

      const newNode = buildNodeAt(type, position);
      let nextEdges = edges;

      if (selected && !type.startsWith("trigger/")) {
        const sourceHandle = resolveSourceHandle(selected.type);
        nextEdges = addEdge(
          {
            id: makeEdgeId(selected.id, newNode.id, sourceHandle),
            source: selected.id,
            target: newNode.id,
            sourceHandle,
            type: "studio",
          },
          edges,
        );
      }

      applyGraph([...(nodes as unknown as Node[]), newNode as unknown as Node], nextEdges);
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(newNode);
    },
    [
      applyGraph,
      buildNodeAt,
      clearGraphOverlay,
      edges,
      nodeIdCounter,
      nodes,
      resolveSourceHandle,
      screenToFlowPosition,
      selectedNode,
      setActiveRunId,
      setSelectedNode,
    ],
  );

  const insertNodeOnEdge = useCallback(
    (edgeId: string, type: string) => {
      const found = edges.find((item) => item.id === edgeId);
      if (!found) return;

      const sourceNode = nodes.find((item) => item.id === found.source);
      const targetNode = nodes.find((item) => item.id === found.target);
      const position =
        sourceNode && targetNode
          ? {
              x: (sourceNode.position.x + targetNode.position.x) / 2,
              y: (sourceNode.position.y + targetNode.position.y) / 2,
            }
          : sourceNode
            ? { x: sourceNode.position.x + 280, y: sourceNode.position.y }
            : screenToFlowPosition({ x: 320, y: 200 });

      const newNode = buildNodeAt(type, position);
      const nextEdges = insertBetween(edges, edgeId, newNode.id, {
        newNodeSourceHandle: resolveSourceHandle(type),
        edgeType: "studio",
      });

      applyGraph([...(nodes as unknown as Node[]), newNode as unknown as Node], nextEdges);
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(newNode);
    },
    [
      applyGraph,
      buildNodeAt,
      clearGraphOverlay,
      edges,
      nodes,
      resolveSourceHandle,
      screenToFlowPosition,
      setActiveRunId,
      setSelectedNode,
    ],
  );

  const handlePickPending = useCallback(
    (type: string) => {
      const pending = pendingConnect;
      if (!pending) {
        handleAddNode(type);
        return;
      }

      if (pending.kind === "insert") {
        insertNodeOnEdge(pending.edgeId, type);
        clearPendingConnect();
        return;
      }

      const flowPosition =
        pending.position.flowX != null && pending.position.flowY != null
          ? { x: pending.position.flowX, y: pending.position.flowY }
          : screenToFlowPosition({ x: pending.position.x, y: pending.position.y });

      const newNode = buildNodeAt(type, flowPosition);
      let nextEdges = edges;
      if (!type.startsWith("trigger/")) {
        nextEdges = addEdge(
          {
            id: makeEdgeId(pending.sourceNodeId, newNode.id, pending.sourceHandle),
            source: pending.sourceNodeId,
            target: newNode.id,
            sourceHandle: pending.sourceHandle,
            type: "studio",
          },
          edges,
        );
      }

      applyGraph([...(nodes as unknown as Node[]), newNode as unknown as Node], nextEdges);
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(newNode);
      clearPendingConnect();
    },
    [
      applyGraph,
      buildNodeAt,
      clearGraphOverlay,
      clearPendingConnect,
      edges,
      handleAddNode,
      insertNodeOnEdge,
      nodes,
      pendingConnect,
      screenToFlowPosition,
      setActiveRunId,
      setSelectedNode,
    ],
  );

  const onConnectEndEmpty = useCallback(
    (
      event: MouseEvent | TouchEvent,
      connection: {
        nodeId: string | null;
        handleId: string | null;
        handleType: "source" | "target" | null;
      },
    ) => {
      if (!connection.nodeId || connection.handleType !== "source") return;
      const client = clientPointFromEvent(event);
      const flow = screenToFlowPosition(client);
      openPicker({
        kind: "connect",
        sourceNodeId: connection.nodeId,
        sourceHandle: connection.handleId || "out",
        position: { x: client.x, y: client.y, flowX: flow.x, flowY: flow.y },
      });
    },
    [openPicker, screenToFlowPosition],
  );

  const requestInsertOnEdge = useCallback(
    (edgeId: string, clientPosition?: { x: number; y: number }) => {
      const client = clientPosition || { x: 240, y: 180 };
      const flow = screenToFlowPosition(client);
      openPicker({
        kind: "insert",
        edgeId,
        position: { x: client.x, y: client.y, flowX: flow.x, flowY: flow.y },
      });
    },
    [openPicker, screenToFlowPosition],
  );

  const handleDeleteEdge = useCallback(
    (edgeId: string) => {
      const nextEdges = edges.filter((edge) => edge.id !== edgeId);
      applyGraph(nodes as unknown as Node[], nextEdges);
      clearGraphOverlay();
      setActiveRunId(null);
    },
    [applyGraph, clearGraphOverlay, edges, nodes, setActiveRunId],
  );

  const handleDuplicateNode = useCallback(
    (nodeId: string) => {
      const sourceNode = nodes.find((item) => item.id === nodeId);
      if (!sourceNode) return;

      const duplicatedNode = {
        ...sourceNode,
        id: `node_${nodeIdCounter.current++}`,
        position: {
          x: sourceNode.position.x + 40,
          y: sourceNode.position.y + 40,
        },
        data: { ...(sourceNode.data || {}) },
      } satisfies PipelineNode;

      applyGraph(
        [...(nodes as unknown as Node[]), duplicatedNode as unknown as Node],
        edges,
      );
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(duplicatedNode);
      toast({
        description: localize(
          lang,
          `${getNodeDisplayLabel(sourceNode, lang)} продублирован.`,
          `${getNodeDisplayLabel(sourceNode, lang)} duplicated.`,
        ),
      });
    },
    [
      applyGraph,
      clearGraphOverlay,
      edges,
      lang,
      nodeIdCounter,
      nodes,
      setActiveRunId,
      setSelectedNode,
      toast,
    ],
  );

  const handleDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }, []);

  const handleDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();
      const type = event.dataTransfer.getData("application/pipeline-node-type");
      const manifest = manifestByType.get(type);
      if (!type || (!isNodeType(type) && !isPluginStudioNode(manifest))) return;

      const hitEdgeId = edgeIdAtClientPoint(event.clientX, event.clientY);
      if (hitEdgeId && edges.some((edge) => edge.id === hitEdgeId) && !type.startsWith("trigger/")) {
        insertNodeOnEdge(hitEdgeId, type);
        return;
      }

      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      createNodeAt(type, position);
    },
    [createNodeAt, edges, insertNodeOnEdge, manifestByType, screenToFlowPosition],
  );

  const handleUpdateNodeData = useCallback(
    (nodeId: string, data: Record<string, unknown>) => {
      setHasLocalChanges(true);
      setNodes((nds) =>
        nds.map((node) => (node.id === nodeId ? { ...node, data } : node)),
      );
      setSelectedNode((prev) => (prev?.id === nodeId ? { ...prev, data } : prev));
    },
    [setHasLocalChanges, setNodes, setSelectedNode],
  );

  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      const nextNodes = (nodes as unknown as Node[]).filter((node) => node.id !== nodeId);
      const nextEdges = edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId);
      applyGraph(nextNodes, nextEdges);
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(null);
    },
    [applyGraph, clearGraphOverlay, edges, nodes, setActiveRunId, setSelectedNode],
  );

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    clearPendingConnect();
  }, [clearPendingConnect, setSelectedNode]);

  return {
    clearPendingConnect,
    handleAddNode,
    handleDeleteEdge,
    handleDeleteNode,
    handleDragOver,
    handleDrop,
    handleDuplicateNode,
    handlePickPending,
    handleUpdateNodeData,
    insertNodeOnEdge,
    onConnect,
    onConnectEndEmpty,
    onNodeClick,
    onPaneClick,
    pendingConnect,
    requestInsertOnEdge,
    setPendingConnect,
  };
}
