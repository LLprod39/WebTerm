import { useMemo } from "react";
import {
  Background,
  MarkerType,
  MiniMap,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { PipelineRun } from "@/api/automation";
import { useTheme } from "@/app/theme";
import { EmptyState } from "@/components/ui";
import { runToCanvas } from "./graph";
import { pipelineNodeTypes } from "./editor/nodes/StepNode";
import { pipelineEdgeTypes } from "./editor/edges/StepEdge";
import "./editor/editor.css";

export default function RunCanvas({
  run,
  selected,
  onSelect,
}: {
  run: PipelineRun;
  selected: string | undefined;
  onSelect: (id: string) => void;
}) {
  const { theme } = useTheme();
  const nodes = useMemo(
    () =>
      runToCanvas(
        run.nodes_snapshot,
        run.edges_snapshot ?? [],
        run.node_states,
        selected,
      ),
    [run.nodes_snapshot, run.edges_snapshot, run.node_states, selected],
  );
  const edges = useMemo(
    () =>
      (run.edges_snapshot ?? []).map((edge) => ({
        ...edge,
        type: "step" as const,
        sourceHandle: edge.sourceHandle || "out",
        selectable: false,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 16,
          height: 16,
        },
        data: { readOnly: true },
        label:
          edge.sourceHandle && edge.sourceHandle !== "out"
            ? edge.sourceHandle
            : undefined,
      })),
    [run.edges_snapshot],
  );
  if (!nodes.length)
    return (
      <EmptyState
        title="Схема запуска недоступна"
        description="В этом запуске нет сохранённых узлов."
      />
    );
  return (
    <>
      {run.edges_snapshot === undefined && (
        <p className="auto-run-canvas-note">
          Для этого запуска связи недоступны. Показаны сохранённые шаги и их
          результаты.
        </p>
      )}
      <div
        className="auto-canvas auto-run-canvas auto-flow-canvas"
        role="region"
        aria-label="Схема выполнения процесса"
      >
        <ReactFlow
          colorMode={theme}
          nodes={nodes}
          edges={edges}
          nodeTypes={pipelineNodeTypes}
          edgeTypes={pipelineEdgeTypes}
          onNodeClick={(_, node) => onSelect(node.id)}
          onNodesChange={(changes) => {
            const change = changes.find(
              (item) => item.type === "select" && item.selected,
            );
            if (change?.type === "select") onSelect(change.id);
          }}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesReconnectable={false}
          edgesFocusable={false}
          connectOnClick={false}
          deleteKeyCode={null}
          fitView
          fitViewOptions={{ padding: 0.25, maxZoom: 1.1 }}
          minZoom={0.15}
          maxZoom={1.8}
        >
          <Background />
          <MiniMap
            pannable
            zoomable
            bgColor="var(--surface)"
            nodeColor="var(--border-strong)"
            maskColor="color-mix(in srgb, var(--background) 75%, transparent)"
          />
        </ReactFlow>
      </div>
    </>
  );
}
