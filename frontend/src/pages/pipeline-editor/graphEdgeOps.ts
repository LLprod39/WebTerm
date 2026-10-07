import type { Edge } from "@xyflow/react";

/** Default outgoing handle when manifests are unavailable. */
export function defaultSourceHandleForType(nodeType: string): string {
  if (nodeType === "logic/condition") return "true";
  if (nodeType === "logic/human_approval") return "approved";
  if (nodeType === "logic/telegram_input") return "received";
  if (nodeType === "logic/wait") return "done";
  return "out";
}

/** First available source handle: manifest list[0], else type default, else `out`. */
export function firstSourceHandleForType(
  nodeType: string,
  sourceHandles?: string[] | null,
): string {
  if (sourceHandles?.length) return sourceHandles[0];
  return defaultSourceHandleForType(nodeType) || "out";
}

export function makeEdgeId(source: string, target: string, sourceHandle?: string | null) {
  return `edge_${source}_${target}_${sourceHandle || "out"}`;
}

/**
 * Split A→B into A→N→B, preserving the original edge's `sourceHandle`.
 * The N→B edge uses `newNodeSourceHandle` (default `out`).
 */
export function insertBetween<E extends Edge>(
  edges: E[],
  edgeId: string,
  newNodeId: string,
  options?: {
    newNodeSourceHandle?: string | null;
    edgeType?: string;
  },
): E[] {
  const edge = edges.find((item) => item.id === edgeId);
  if (!edge) return edges;

  const newNodeSourceHandle = options?.newNodeSourceHandle || "out";
  const edgeType = options?.edgeType ?? edge.type;
  const without = edges.filter((item) => item.id !== edgeId);

  const left = {
    ...edge,
    id: makeEdgeId(edge.source, newNodeId, edge.sourceHandle),
    source: edge.source,
    target: newNodeId,
    sourceHandle: edge.sourceHandle,
    targetHandle: undefined,
    type: edgeType,
  } as E;

  const right = {
    ...edge,
    id: makeEdgeId(newNodeId, edge.target, newNodeSourceHandle),
    source: newNodeId,
    target: edge.target,
    sourceHandle: newNodeSourceHandle,
    targetHandle: edge.targetHandle,
    type: edgeType,
  } as E;

  return [...without, left, right];
}
