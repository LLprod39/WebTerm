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

export function usePipelineEditorGraphActions({
  clearGraphOverlay,
  lang,
  nodeIdCounter,
  nodes,
  nodeManifests,
  onRequestPicker,
  pipelineName,
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
  lang: "en" | "ru";
  nodeIdCounter: { current: number };
  nodes: PipelineNode[];
  nodeManifests: StudioCapabilityNode[];
  /** Optional external picker opener (integrator can own UI). */
  onRequestPicker?: (request: StudioPickerRequest) => void;
  pipelineName: string;
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
      setHasLocalChanges(true);
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: makeEdgeId(connection.source, connection.target, connection.sourceHandle),
            type: "studio",
          },
          eds,
        ),
      );

      const sourceNode = nodes.find((item) => item.id === connection.source);
      const targetNode = nodes.find((item) => item.id === connection.target);
      if (!targetNode) return;

      clearGraphOverlay();
      setActiveRunId(null);
      if (!sourceNode) {
        setSelectedNode(targetNode);
        return;
      }

      const patch = buildConnectionAutofillPatch(targetNode, sourceNode, pipelineName);
      if (!Object.keys(patch).length) {
        setSelectedNode(targetNode);
        return;
      }

      const nextTarget = { ...targetNode, data: { ...(targetNode.data || {}), ...patch } } as PipelineNode;
      setNodes((nds) => nds.map((item) => (item.id === targetNode.id ? (nextTarget as unknown as Node) : item)));
      setSelectedNode(nextTarget);
      // Silent autofill — no toast about starter settings.
    },
    [clearGraphOverlay, nodes, pipelineName, setActiveRunId, setEdges, setHasLocalChanges, setNodes, setSelectedNode],
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

  const createNodeAt = useCallback(
    (type: string, position: FlowPosition) => {
      const id = `node_${nodeIdCounter.current++}`;
      const manifest = manifestByType.get(type);
      const newNode = {
        id,
        type,
        position,
        data: buildDefaultNodeData(type, manifest),
      };
      setHasLocalChanges(true);
      setNodes((nds) => [...nds, newNode as unknown as Node]);
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(newNode as PipelineNode);
      return newNode as PipelineNode;
    },
    [clearGraphOverlay, manifestByType, nodeIdCounter, setActiveRunId, setHasLocalChanges, setNodes, setSelectedNode],
  );

  const handleAddNode = useCallback(
    (type: string) => {
      const selected = selectedNode ? nodes.find((item) => item.id === selectedNode.id) : null;
      const position = selected
        ? { x: selected.position.x + 280, y: selected.position.y }
        : screenToFlowPosition({ x: 300, y: 200 + nodeIdCounter.current * 80 });

      const newNode = createNodeAt(type, position);

      if (selected && !type.startsWith("trigger/")) {
        const sourceHandle = resolveSourceHandle(selected.type);
        setEdges((eds) =>
          addEdge(
            {
              id: makeEdgeId(selected.id, newNode.id, sourceHandle),
              source: selected.id,
              target: newNode.id,
              sourceHandle,
              type: "studio",
            },
            eds,
          ),
        );
      }
    },
    [createNodeAt, nodeIdCounter, nodes, resolveSourceHandle, screenToFlowPosition, selectedNode, setEdges],
  );

  const insertNodeOnEdge = useCallback(
    (edgeId: string, type: string) => {
      setEdges((eds) => {
        const found = eds.find((item) => item.id === edgeId);
        if (!found) return eds;

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

        const newNode = {
          id: `node_${nodeIdCounter.current++}`,
          type,
          position,
          data: buildDefaultNodeData(type, manifestByType.get(type)),
        } as PipelineNode;

        setHasLocalChanges(true);
        setNodes((nds) => [...nds, newNode as unknown as Node]);
        clearGraphOverlay();
        setActiveRunId(null);
        setSelectedNode(newNode);

        return insertBetween(eds, edgeId, newNode.id, {
          newNodeSourceHandle: resolveSourceHandle(type),
          edgeType: "studio",
        });
      });
    },
    [
      clearGraphOverlay,
      manifestByType,
      nodeIdCounter,
      nodes,
      resolveSourceHandle,
      screenToFlowPosition,
      setActiveRunId,
      setEdges,
      setHasLocalChanges,
      setNodes,
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

      const newNode = createNodeAt(type, flowPosition);
      if (!type.startsWith("trigger/")) {
        setEdges((eds) =>
          addEdge(
            {
              id: makeEdgeId(pending.sourceNodeId, newNode.id, pending.sourceHandle),
              source: pending.sourceNodeId,
              target: newNode.id,
              sourceHandle: pending.sourceHandle,
              type: "studio",
            },
            eds,
          ),
        );
      }
      clearPendingConnect();
    },
    [
      clearPendingConnect,
      createNodeAt,
      handleAddNode,
      insertNodeOnEdge,
      pendingConnect,
      screenToFlowPosition,
      setEdges,
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
      setHasLocalChanges(true);
      setEdges((eds) => eds.filter((edge) => edge.id !== edgeId));
      clearGraphOverlay();
      setActiveRunId(null);
    },
    [clearGraphOverlay, setActiveRunId, setEdges, setHasLocalChanges],
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

      setHasLocalChanges(true);
      setNodes((nds) => [...nds, duplicatedNode as unknown as Node]);
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
    [clearGraphOverlay, lang, nodeIdCounter, nodes, setActiveRunId, setHasLocalChanges, setNodes, setSelectedNode, toast],
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
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      createNodeAt(type, position);
    },
    [createNodeAt, manifestByType, screenToFlowPosition],
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
      setHasLocalChanges(true);
      setNodes((nds) => nds.filter((node) => node.id !== nodeId));
      setEdges((eds) => eds.filter((edge) => edge.source !== nodeId && edge.target !== nodeId));
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(null);
    },
    [clearGraphOverlay, setActiveRunId, setEdges, setHasLocalChanges, setNodes, setSelectedNode],
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
