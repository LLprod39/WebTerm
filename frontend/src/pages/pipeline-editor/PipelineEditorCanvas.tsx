import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  type Connection,
  type EdgeChange,
  type NodeChange,
  type NodeMouseHandler,
  type NodeTypes,
  type OnConnectEnd,
} from "@xyflow/react";
import { useCallback, useMemo, type DragEvent, type ReactNode } from "react";
import { Zap } from "lucide-react";

import type { PipelineEdge, PipelineNode } from "@/lib/api";
import { type NodeType } from "@/components/pipeline/nodes";

import { localize, nodeTypes } from "./presentation";
import {
  STUDIO_DEFAULT_EDGE_OPTIONS,
  studioEdgeTypes,
  type StudioEdgeData,
} from "./edges/StudioEdge";

export type CanvasConnectEndEmpty = (
  event: MouseEvent | TouchEvent,
  connection: {
    nodeId: string | null;
    handleId: string | null;
    handleType: "source" | "target" | null;
  },
) => void;

export function PipelineEditorCanvas({
  displayEdges,
  displayNodes,
  emptySlot,
  lang,
  onConnect,
  onConnectEndEmpty,
  onDeleteEdge,
  onDragOver,
  onDrop,
  onEdgesChange,
  onInsertEdge,
  onNodeClick,
  onNodesChange,
  onPaneClick,
  pluginNodeTypes,
  showMiniMap,
}: {
  displayEdges: PipelineEdge[];
  displayNodes: PipelineNode[];
  /** Stream D empty CTA; when set, replaces the default Zap placeholder. */
  emptySlot?: ReactNode;
  lang: "en" | "ru";
  onConnect: (connection: Connection) => void;
  /** Fired when a drag from a source handle ends on empty pane (opens QuickNodePicker). */
  onConnectEndEmpty?: CanvasConnectEndEmpty;
  onDeleteEdge?: (edgeId: string) => void;
  onDragOver: (event: DragEvent) => void;
  onDrop: (event: DragEvent) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onInsertEdge?: (edgeId: string) => void;
  onNodeClick: NodeMouseHandler;
  onNodesChange: (changes: NodeChange[]) => void;
  onPaneClick: () => void;
  pluginNodeTypes?: NodeTypes;
  showMiniMap: boolean;
}) {
  const resolvedNodeTypes = useMemo<NodeTypes>(
    () => ({ ...nodeTypes, ...(pluginNodeTypes || {}) }),
    [pluginNodeTypes],
  );

  const onConnectEnd: OnConnectEnd = useCallback(
    (event, connectionState) => {
      if (!onConnectEndEmpty) return;
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

  const decoratedEdges = useMemo(
    () =>
      displayEdges.map((edge) => {
        const existingData = (edge as PipelineEdge & { data?: StudioEdgeData }).data;
        const data: StudioEdgeData = {
          ...(existingData || {}),
          onInsert: onInsertEdge,
          onDelete: onDeleteEdge,
        };
        return {
          ...edge,
          type: "studio" as const,
          data,
          label:
            edge.sourceHandle && edge.sourceHandle !== "out"
              ? edge.sourceHandle
              : edge.label,
        };
      }),
    [displayEdges, onDeleteEdge, onInsertEdge],
  );

  return (
    <ReactFlow
      nodes={displayNodes}
      edges={decoratedEdges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      onConnectEnd={onConnectEnd}
      onNodeClick={onNodeClick}
      onPaneClick={onPaneClick}
      onDragOver={onDragOver}
      onDrop={onDrop}
      nodeTypes={resolvedNodeTypes}
      edgeTypes={studioEdgeTypes}
      fitView
      proOptions={{ hideAttribution: true }}
      defaultEdgeOptions={{
        ...STUDIO_DEFAULT_EDGE_OPTIONS,
        labelStyle: { fontSize: 10, fill: "hsl(var(--muted-foreground))" },
        labelBgStyle: { fill: "hsl(var(--background))", fillOpacity: 0.8 },
      }}
    >
      <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
      <Controls className="!border-border/70 !bg-background/78 [&>button]:!border-border/70 [&>button]:!bg-background/80 [&>button]:!text-foreground [&>button:hover]:!bg-background" />
      {showMiniMap && (
        <MiniMap
          style={{ background: "hsl(var(--background) / 0.85)", border: "1px solid hsl(var(--border))" }}
          maskColor="hsl(var(--background) / 0.82)"
          nodeColor={(node) => {
            const type = (node.type || "") as NodeType;
            if (type.startsWith("trigger/")) return "rgb(251 191 36 / 0.8)";
            if (type.startsWith("agent/")) return "rgb(167 139 250 / 0.8)";
            if (type.startsWith("logic/")) return "rgb(192 132 252 / 0.8)";
            if (type.startsWith("output/")) return "rgb(52 211 153 / 0.8)";
            return "hsl(var(--muted-foreground))";
          }}
        />
      )}
      {displayNodes.length === 0 && (
        <Panel position="top-center" style={{ pointerEvents: emptySlot ? "auto" : "none", marginTop: "25%" }}>
          {emptySlot ?? (
            <div className="text-center select-none space-y-3">
              <Zap className="h-12 w-12 text-primary/20 mx-auto" />
              <p className="text-sm text-muted-foreground/70 font-medium">
                {localize(lang, "Добавьте первый шаг", "Add the first step")}
              </p>
              <p className="text-xs text-muted-foreground/50 max-w-xs mx-auto">
                {localize(
                  lang,
                  "Добавьте шаги из палитры и соедините их в порядок выполнения.",
                  "Add steps from the palette and connect them into an execution flow.",
                )}
              </p>
            </div>
          )}
        </Panel>
      )}
    </ReactFlow>
  );
}
