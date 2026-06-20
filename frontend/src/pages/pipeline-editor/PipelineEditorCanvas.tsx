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
} from "@xyflow/react";
import type { DragEvent } from "react";
import { Zap } from "lucide-react";

import type { PipelineEdge, PipelineNode } from "@/lib/api";
import { type NodeType } from "@/components/pipeline/nodes";

import { localize, nodeTypes } from "./presentation";

export function PipelineEditorCanvas({
  displayEdges,
  displayNodes,
  lang,
  onConnect,
  onDragOver,
  onDrop,
  onEdgesChange,
  onNodeClick,
  onNodesChange,
  onPaneClick,
  showMiniMap,
}: {
  displayEdges: PipelineEdge[];
  displayNodes: PipelineNode[];
  lang: "en" | "ru";
  onConnect: (connection: Connection) => void;
  onDragOver: (event: DragEvent) => void;
  onDrop: (event: DragEvent) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onNodeClick: NodeMouseHandler;
  onNodesChange: (changes: NodeChange[]) => void;
  onPaneClick: () => void;
  showMiniMap: boolean;
}) {
  return (
    <ReactFlow
      nodes={displayNodes}
      edges={displayEdges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      onNodeClick={onNodeClick}
      onPaneClick={onPaneClick}
      onDragOver={onDragOver}
      onDrop={onDrop}
      nodeTypes={nodeTypes}
      fitView
      proOptions={{ hideAttribution: true }}
      defaultEdgeOptions={{
        style: { strokeWidth: 2 },
        animated: true,
        labelStyle: { fontSize: 10, fill: "hsl(var(--muted-foreground))" },
        labelBgStyle: { fill: "hsl(var(--background))", fillOpacity: 0.8 },
      }}
    >
      <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
      <Controls className="!border-border/70 !bg-background/78 !backdrop-blur [&>button]:!border-border/70 [&>button]:!bg-background/80 [&>button]:!text-foreground [&>button:hover]:!bg-background" />
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
        <Panel position="top-center" style={{ pointerEvents: "none", marginTop: "25%" }}>
          <div className="text-center select-none space-y-3">
            <Zap className="h-12 w-12 text-primary/20 mx-auto" />
            <p className="text-sm text-muted-foreground/70 font-medium">
              {localize(lang, "Соберите OPS pipeline", "Build an OPS pipeline")}
            </p>
            <p className="text-xs text-muted-foreground/50 max-w-xs mx-auto">
              {localize(lang, "Добавьте шаги из палитры и соедините их в порядок выполнения.", "Add steps from the palette and connect them into an execution flow.")}
            </p>
          </div>
        </Panel>
      )}
    </ReactFlow>
  );
}
