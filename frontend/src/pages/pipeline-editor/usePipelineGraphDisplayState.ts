import { useMemo, type CSSProperties } from "react";
import { buildPipelineRunGraphState } from "@/components/pipeline/pipelineRunGraph";
import type { PipelineEdge, PipelineNode, PipelineRun } from "@/lib/api";
import {
  getNodeDisplayLabel,
  getPipelineNodeStatusLabel,
  isLivePipelineRunStatus,
} from "./pipelineGraphUtils";

// Domain edges may arrive decorated with React Flow presentation props.
type DisplayPipelineEdge = PipelineEdge & {
  style?: CSSProperties;
  labelStyle?: CSSProperties;
  labelBgStyle?: CSSProperties;
};

export function usePipelineGraphDisplayState({
  edges,
  graphRunLive,
  lang,
  nodes,
}: {
  edges: DisplayPipelineEdge[];
  graphRunLive: PipelineRun | null;
  lang: "en" | "ru";
  nodes: PipelineNode[];
}) {
  const graphState = useMemo(
    () => buildPipelineRunGraphState(nodes, edges, graphRunLive),
    [edges, graphRunLive, nodes],
  );
  const highlightedNodeId = graphState.currentNodeId || graphRunLive?.entry_node_id || null;
  const highlightedNode = highlightedNodeId
    ? nodes.find((node) => node.id === highlightedNodeId) || null
    : null;
  const highlightedNodeLabel = highlightedNode ? getNodeDisplayLabel(highlightedNode, lang) : "";
  const displayNodes = useMemo(
    () =>
      nodes.map((node) => {
        const nodeState = graphRunLive?.node_states?.[node.id] as unknown as Record<string, unknown> | undefined;
        const status = typeof nodeState?.status === "string" ? nodeState.status : undefined;
        return {
          ...node,
          data: {
            ...(node.data || {}),
            status,
            status_label: getPipelineNodeStatusLabel(status, lang, nodeState),
            is_current_step: node.id === graphState.currentNodeId,
            is_in_active_path: graphState.traversedNodeIds.has(node.id),
            is_queued_step: graphState.queuedNodeIds.has(node.id),
            is_entry_point: graphRunLive?.entry_node_id === node.id,
          },
        };
      }),
    [
      graphRunLive?.entry_node_id,
      graphRunLive?.node_states,
      graphState.currentNodeId,
      graphState.queuedNodeIds,
      graphState.traversedNodeIds,
      lang,
      nodes,
    ],
  );
  const displayEdges = useMemo(
    () =>
      edges.map((edge) => {
        const isCurrent = graphState.currentEdgeIds.has(edge.id);
        const isActivePath = graphState.activeEdgeIds.has(edge.id);
        return {
          ...edge,
          animated: isCurrent || (isActivePath && isLivePipelineRunStatus(graphRunLive?.status)),
          style: {
            ...(edge.style || {}),
            strokeWidth: isCurrent ? 3.6 : isActivePath ? 2.8 : 2,
            stroke: isCurrent
              ? "rgb(59 130 246)"
              : isActivePath
                ? "rgb(45 212 191)"
                : "hsl(var(--muted-foreground) / 0.3)",
            opacity: isActivePath ? 1 : 0.42,
          },
          labelStyle: {
            ...(edge.labelStyle || {}),
            fontSize: 10,
            fill: isActivePath ? "rgb(125 211 252)" : "hsl(var(--muted-foreground))",
          },
          labelBgStyle: {
            ...(edge.labelBgStyle || {}),
            fill: "hsl(var(--background))",
            fillOpacity: isActivePath ? 0.92 : 0.78,
          },
          zIndex: isActivePath ? 20 : 1,
        };
      }),
    [edges, graphRunLive?.status, graphState.activeEdgeIds, graphState.currentEdgeIds],
  );

  return {
    displayEdges,
    displayNodes,
    graphState,
    highlightedNode,
    highlightedNodeLabel,
  };
}
