import { graphlib, layout as dagreLayout } from "@dagrejs/dagre";

import type { PipelineEdge, PipelineNode } from "@/lib/api";

/** Default card size — matches NodeBase (`w-[248px]`, ~min-h 76–80). */
export const PIPELINE_LAYOUT_NODE_WIDTH = 248;
export const PIPELINE_LAYOUT_NODE_HEIGHT = 80;

export type PipelineLayoutDirection = "LR" | "TB";

/** Nodes may carry React Flow measured dimensions after render. */
export type LayoutablePipelineNode = PipelineNode & {
  width?: number;
  height?: number;
  measured?: { width?: number; height?: number };
};

function nodeSize(node: LayoutablePipelineNode): { width: number; height: number } {
  const width = node.measured?.width ?? node.width ?? PIPELINE_LAYOUT_NODE_WIDTH;
  const height = node.measured?.height ?? node.height ?? PIPELINE_LAYOUT_NODE_HEIGHT;
  return {
    width: Number.isFinite(width) && width > 0 ? width : PIPELINE_LAYOUT_NODE_WIDTH,
    height: Number.isFinite(height) && height > 0 ? height : PIPELINE_LAYOUT_NODE_HEIGHT,
  };
}

/**
 * Detect graphs that look vertically stacked (legacy top→bottom).
 * Port of automation `looksVertical` for `PipelineNode[]`.
 */
export function looksVertical(nodes: PipelineNode[]): boolean {
  if (nodes.length < 2) return false;
  const xs = nodes.map((n) => n.position.x);
  const ys = nodes.map((n) => n.position.y);
  const xSpan = Math.max(...xs) - Math.min(...xs);
  const ySpan = Math.max(...ys) - Math.min(...ys);
  return ySpan > xSpan * 1.25 && ySpan > 120;
}

/**
 * Lay out pipeline nodes with @dagrejs/dagre.
 * Returns new nodes with updated `position` only — ids, data, and handles are unchanged.
 * Dagre uses center coordinates; output uses React Flow top-left positions.
 */
export function layoutPipelineGraph(
  nodes: LayoutablePipelineNode[],
  edges: PipelineEdge[],
  direction: PipelineLayoutDirection = "LR",
): PipelineNode[] {
  if (!nodes.length) return nodes;

  const graph = new graphlib.Graph({ multigraph: true });
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: direction,
    nodesep: 48,
    ranksep: 72,
    marginx: 24,
    marginy: 24,
  });

  const sizes = new Map<string, { width: number; height: number }>();
  for (const node of nodes) {
    const size = nodeSize(node);
    sizes.set(node.id, size);
    graph.setNode(node.id, { width: size.width, height: size.height });
  }

  const known = new Set(nodes.map((n) => n.id));
  for (const edge of edges) {
    if (!known.has(edge.source) || !known.has(edge.target)) continue;
    graph.setEdge(edge.source, edge.target, {}, edge.id);
  }

  dagreLayout(graph);

  return nodes.map((node) => {
    const laid = graph.node(node.id) as { x?: number; y?: number } | undefined;
    if (!laid || typeof laid.x !== "number" || typeof laid.y !== "number") {
      return node;
    }
    const size = sizes.get(node.id) ?? {
      width: PIPELINE_LAYOUT_NODE_WIDTH,
      height: PIPELINE_LAYOUT_NODE_HEIGHT,
    };
    return {
      ...node,
      position: {
        x: laid.x - size.width / 2,
        y: laid.y - size.height / 2,
      },
    };
  });
}
