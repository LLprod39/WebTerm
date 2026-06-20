import { useCallback, type Dispatch, type DragEvent, type SetStateAction } from "react";
import {
  addEdge,
  type Connection,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import type { NodeType } from "@/components/pipeline/nodes";
import type { PipelineNode } from "@/lib/api";
import { isNodeType, localize } from "./presentation";
import {
  buildConnectionAutofillPatch,
  buildDefaultNodeData,
  getNodeDisplayLabel,
} from "./pipelineGraphUtils";

type FlowPosition = { x: number; y: number };

export function usePipelineEditorGraphActions({
  clearGraphOverlay,
  lang,
  nodeIdCounter,
  nodes,
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
  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      setHasLocalChanges(true);
      setEdges((eds) => addEdge(connection, eds));

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
      toast({
        description: localize(
          lang,
          `${getNodeDisplayLabel(nextTarget, lang)} получил стартовые настройки из соединения.`,
          `${getNodeDisplayLabel(nextTarget, lang)} picked up starter settings from the connection.`,
        ),
      });
    },
    [clearGraphOverlay, lang, nodes, pipelineName, setActiveRunId, setEdges, setHasLocalChanges, setNodes, setSelectedNode, toast],
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

  const handleAddNode = useCallback(
    (type: NodeType) => {
      const id = `node_${nodeIdCounter.current++}`;
      const selected = selectedNode ? nodes.find((item) => item.id === selectedNode.id) : null;
      const newNode = {
        id,
        type,
        position: selected
          ? { x: selected.position.x + 260, y: selected.position.y + 24 }
          : screenToFlowPosition({ x: 300, y: 200 + nodeIdCounter.current * 80 }),
        data: buildDefaultNodeData(type),
      };
      setHasLocalChanges(true);
      setNodes((nds) => [...nds, newNode as unknown as Node]);
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(newNode as PipelineNode);
    },
    [clearGraphOverlay, nodeIdCounter, nodes, screenToFlowPosition, selectedNode, setActiveRunId, setHasLocalChanges, setNodes, setSelectedNode],
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
        description: localize(lang, `${getNodeDisplayLabel(sourceNode, lang)} продублирован.`, `${getNodeDisplayLabel(sourceNode, lang)} duplicated.`),
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
      if (!type || !isNodeType(type)) return;
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const id = `node_${nodeIdCounter.current++}`;
      const newNode = { id, type, position, data: buildDefaultNodeData(type as NodeType) };
      setHasLocalChanges(true);
      setNodes((nds) => [...nds, newNode as unknown as Node]);
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(newNode as PipelineNode);
    },
    [clearGraphOverlay, nodeIdCounter, screenToFlowPosition, setActiveRunId, setHasLocalChanges, setNodes, setSelectedNode],
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

  const onPaneClick = useCallback(() => setSelectedNode(null), [setSelectedNode]);

  return {
    handleAddNode,
    handleDeleteNode,
    handleDragOver,
    handleDrop,
    handleDuplicateNode,
    handleUpdateNodeData,
    onConnect,
    onNodeClick,
    onPaneClick,
  };
}
