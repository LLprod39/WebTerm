import { useCallback, type DragEvent, type MouseEvent } from "react";
import {
  Background,
  BackgroundVariant,
  ConnectionLineType,
  ConnectionMode,
  MiniMap,
  ReactFlow,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type Edge,
  type NodeChange,
  type OnConnectEnd,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useTheme } from "@/app/theme";
import type { CanvasNode } from "../graph";
import { validConnection } from "../graph";
import { pipelineNodeTypes } from "./nodes/StepNode";
import {
  DEFAULT_EDGE_OPTIONS,
  pipelineEdgeTypes,
  type StepEdgeData,
} from "./edges/StepEdge";
import { CanvasControls } from "./CanvasControls";
import type { ContextTarget } from "./ContextMenu";

const PALETTE_MIME = "application/webterm-pipeline-node";

export function FlowCanvas({
  nodes,
  edges,
  showMinimap,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onConnectEndEmpty,
  onSelectNode,
  onPaneClick,
  onDropType,
  onLayout,
  onToggleMinimap,
  onContextMenu,
  onInsertEdge,
  onDeleteEdge,
}: {
  nodes: CanvasNode[];
  edges: Edge<StepEdgeData>[];
  showMinimap: boolean;
  onNodesChange: (nodes: CanvasNode[], pushHistory: boolean) => void;
  onEdgesChange: (edges: Edge<StepEdgeData>[], pushHistory: boolean) => void;
  onConnect: (connection: Connection) => void;
  onConnectEndEmpty: (
    event: MouseEvent | TouchEvent,
    connection: {
      nodeId: string | null;
      handleId: string | null;
      handleType: "source" | "target" | null;
    },
  ) => void;
  onSelectNode: (id: string | null) => void;
  onPaneClick: () => void;
  onDropType: (type: string, position: { x: number; y: number }) => void;
  onLayout: () => void;
  onToggleMinimap: () => void;
  onContextMenu: (target: ContextTarget, x: number, y: number) => void;
  onInsertEdge: (edgeId: string) => void;
  onDeleteEdge: (edgeId: string) => void;
}) {
  const { theme } = useTheme();
  const { screenToFlowPosition } = useReactFlow();

  const handleNodesChange = useCallback(
    (changes: NodeChange<CanvasNode>[]) => {
      const next = applyNodeChanges(changes, nodes);
      const structural = changes.some(
        (change) =>
          change.type === "position" ||
          change.type === "remove" ||
          change.type === "add" ||
          change.type === "replace",
      );
      const dragEnded = changes.some(
        (change) =>
          change.type === "position" &&
          "dragging" in change &&
          change.dragging === false,
      );
      onNodesChange(next, dragEnded || (structural && !changes.some((c) => c.type === "position" && "dragging" in c && c.dragging)));
    },
    [nodes, onNodesChange],
  );

  const handleEdgesChange = useCallback(
    (changes: Parameters<typeof applyEdgeChanges<Edge<StepEdgeData>>>[0]) => {
      const next = applyEdgeChanges(changes, edges);
      const structural = changes.some((change) => change.type !== "select");
      onEdgesChange(next, structural);
    },
    [edges, onEdgesChange],
  );

  const onConnectEnd: OnConnectEnd = useCallback(
    (event, connectionState) => {
      if (connectionState.isValid) return;
      const from = connectionState.fromNode;
      const handle = connectionState.fromHandle;
      if (!from || handle?.type !== "source") return;
      onConnectEndEmpty(event as MouseEvent | TouchEvent, {
        nodeId: from.id,
        handleId: handle.id ?? "out",
        handleType: "source",
      });
    },
    [onConnectEndEmpty],
  );

  const decoratedEdges = edges.map((edge) => ({
    ...edge,
    type: "step" as const,
    data: {
      ...edge.data,
      onInsert: onInsertEdge,
      onDelete: onDeleteEdge,
    },
    label:
      edge.sourceHandle && edge.sourceHandle !== "out"
        ? edge.sourceHandle
        : edge.label,
  }));

  return (
    <div
      className="auto-flow-canvas"
      onDragOver={(event: DragEvent) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      }}
      onDrop={(event: DragEvent) => {
        event.preventDefault();
        const type = event.dataTransfer.getData(PALETTE_MIME);
        if (!type) return;
        const position = screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        });
        onDropType(type, position);
      }}
      onContextMenu={(event) => {
        const target = event.target as HTMLElement;
        const node = target.closest(".react-flow__node");
        const edge = target.closest(".react-flow__edge");
        event.preventDefault();
        if (node?.getAttribute("data-id")) {
          onContextMenu(
            { kind: "node", id: node.getAttribute("data-id")! },
            event.clientX,
            event.clientY,
          );
          return;
        }
        if (edge?.getAttribute("data-id")) {
          onContextMenu(
            { kind: "edge", id: edge.getAttribute("data-id")! },
            event.clientX,
            event.clientY,
          );
          return;
        }
        const position = screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        });
        onContextMenu(
          { kind: "pane", x: position.x, y: position.y },
          event.clientX,
          event.clientY,
        );
      }}
    >
      <ReactFlow<CanvasNode, Edge<StepEdgeData>>
        colorMode={theme}
        nodes={nodes}
        edges={decoratedEdges}
        nodeTypes={pipelineNodeTypes}
        edgeTypes={pipelineEdgeTypes}
        defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
        connectionMode={ConnectionMode.Strict}
        connectionLineType={ConnectionLineType.Bezier}
        snapToGrid
        snapGrid={[16, 16]}
        selectionOnDrag
        panOnDrag={[1, 2]}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        onConnectEnd={onConnectEnd}
        isValidConnection={(connection) =>
          validConnection(connection.source, connection.target, edges)
        }
        onNodeClick={(_event, node) => onSelectNode(node.id)}
        onPaneClick={onPaneClick}
        fitView
        fitViewOptions={{ padding: 0.22, maxZoom: 1 }}
        minZoom={0.2}
        maxZoom={2}
        deleteKeyCode={null}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={18} size={1} variant={BackgroundVariant.Dots} />
        {showMinimap && (
          <MiniMap
            bgColor="var(--surface)"
            nodeColor="var(--border-strong)"
            maskColor="color-mix(in srgb, var(--background) 75%, transparent)"
          />
        )}
      </ReactFlow>
      <CanvasControls
        showMinimap={showMinimap}
        onToggleMinimap={onToggleMinimap}
        onLayout={onLayout}
      />
    </div>
  );
}

export { addEdge, PALETTE_MIME };
