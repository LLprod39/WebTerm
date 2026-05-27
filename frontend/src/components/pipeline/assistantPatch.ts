import type {
  PipelineEdge,
  PipelineNode,
  StudioPipelineAssistantResponse,
  StudioPipelineGraphPatch,
} from "@/lib/api";

export type AssistantPatchStats = {
  addedNodes: number;
  addedEdges: number;
  updatedNodes: number;
  removedNodes: number;
  removedEdges: number;
  hasChanges: boolean;
};

export type AssistantPatchResult = {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  refToNodeId: Record<string, string>;
  stats: AssistantPatchStats;
};

type ApplyAssistantPatchOptions = {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  response: StudioPipelineAssistantResponse;
  normalizeNodeData?: (data: Record<string, unknown>, nodeType: string) => Record<string, unknown>;
};

function safeGraphId(rawValue: string, prefix: string, usedIds: Set<string>) {
  const fallback = prefix || "node";
  const base =
    rawValue
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 48) || fallback;
  const seeded = /^[a-z_]/.test(base) ? base : `${fallback}_${base}`;
  let candidate = seeded;
  let index = 2;
  while (usedIds.has(candidate)) {
    candidate = `${seeded}_${index}`;
    index += 1;
  }
  usedIds.add(candidate);
  return candidate;
}

function cloneData<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function defaultSourceHandleForType(nodeType: string): string {
  if (nodeType === "logic/condition") return "true";
  if (nodeType === "logic/human_approval") return "approved";
  if (nodeType === "logic/telegram_input") return "received";
  if (nodeType === "logic/wait") return "done";
  return "out";
}

function allowedSourceHandlesForType(nodeType: string): Set<string> {
  if (nodeType === "logic/condition") return new Set(["true", "false"]);
  if (nodeType === "logic/human_approval") return new Set(["approved", "rejected", "timeout"]);
  if (nodeType === "logic/telegram_input") return new Set(["received", "timeout"]);
  if (nodeType === "logic/wait") return new Set(["done", "out"]);
  if (nodeType === "logic/parallel" || nodeType === "logic/merge" || nodeType.startsWith("trigger/")) return new Set(["out"]);
  if (nodeType.startsWith("agent/") || nodeType.startsWith("output/")) return new Set(["success", "error", "out"]);
  return new Set(["out"]);
}

function normalizeSourceHandleForType(rawHandle: string | undefined, nodeType: string): string {
  const value = String(rawHandle || "").trim();
  return allowedSourceHandlesForType(nodeType).has(value) ? value : defaultSourceHandleForType(nodeType);
}

function getPatch(response: StudioPipelineAssistantResponse): StudioPipelineGraphPatch {
  return response.graph_patch || {
    anchor_node_id: null,
    nodes: [],
    edges: [],
    update_nodes: [],
    remove_node_ids: [],
    remove_edge_ids: [],
  };
}

function getNodeAnchor(nodes: PipelineNode[], anchorNodeId?: string | null) {
  if (anchorNodeId) {
    const match = nodes.find((node) => node.id === anchorNodeId);
    if (match) return match;
  }
  if (!nodes.length) return null;
  return nodes.reduce((rightmost, node) => (node.position.x > rightmost.position.x ? node : rightmost), nodes[0]);
}

export function getAssistantPatchStats(response: StudioPipelineAssistantResponse): AssistantPatchStats {
  const patch = getPatch(response);
  const updatedNodes = (patch.update_nodes?.length || 0) + (response.target_node_id && Object.keys(response.node_patch || {}).length ? 1 : 0);
  const stats = {
    addedNodes: patch.nodes?.length || 0,
    addedEdges: patch.edges?.length || 0,
    updatedNodes,
    removedNodes: patch.remove_node_ids?.length || 0,
    removedEdges: patch.remove_edge_ids?.length || 0,
    hasChanges: false,
  };
  stats.hasChanges = stats.addedNodes + stats.addedEdges + stats.updatedNodes + stats.removedNodes + stats.removedEdges > 0;
  return stats;
}

export function applyAssistantGraphPatch({
  nodes,
  edges,
  response,
  normalizeNodeData,
}: ApplyAssistantPatchOptions): AssistantPatchResult {
  const patch = getPatch(response);
  let nextNodes = cloneData(nodes);
  let nextEdges = cloneData(edges);

  const nodeMap = new Map(nextNodes.map((node) => [node.id, node]));
  if (response.target_node_id && response.node_patch && Object.keys(response.node_patch).length) {
    const target = nodeMap.get(response.target_node_id);
    if (target) {
      const data = { ...(target.data || {}), ...cloneData(response.node_patch) };
      target.data = normalizeNodeData ? normalizeNodeData(data, target.type) : data;
    }
  }

  const removeNodeIds = new Set((patch.remove_node_ids || []).map((item) => String(item).trim()).filter(Boolean));
  const removeEdgeIds = new Set((patch.remove_edge_ids || []).map((item) => String(item).trim()).filter(Boolean));
  if (removeNodeIds.size) {
    nextNodes = nextNodes.filter((node) => !removeNodeIds.has(node.id));
  }
  if (removeNodeIds.size || removeEdgeIds.size) {
    nextEdges = nextEdges.filter(
      (edge) => !removeEdgeIds.has(edge.id) && !removeNodeIds.has(edge.source) && !removeNodeIds.has(edge.target),
    );
  }

  const refreshedNodeMap = new Map(nextNodes.map((node) => [node.id, node]));
  for (const update of patch.update_nodes || []) {
    const target = refreshedNodeMap.get(update.node_id);
    if (!target) continue;
    const data = { ...(target.data || {}), ...cloneData(update.data || {}) };
    target.data = normalizeNodeData ? normalizeNodeData(data, target.type) : data;
  }

  const anchor = getNodeAnchor(nextNodes, patch.anchor_node_id || response.target_node_id);
  const anchorX = anchor?.position.x || 0;
  const anchorY = anchor?.position.y || 0;
  const usedNodeIds = new Set(nextNodes.map((node) => node.id));
  const usedEdgeIds = new Set(nextEdges.map((edge) => edge.id));
  const refToNodeId: Record<string, string> = {};

  (patch.nodes || []).forEach((item, index) => {
    const ref = String(item.ref || "").trim();
    const type = String(item.type || "").trim();
    if (!ref || !type) return;
    const id = safeGraphId(ref, "node", usedNodeIds);
    refToNodeId[ref] = id;
    const data = cloneData(item.data || {});
    if (item.label && !String(data.label || "").trim()) {
      data.label = item.label;
    }
    const normalizedData = normalizeNodeData ? normalizeNodeData(data, type) : data;
    const xOffset = typeof item.x_offset === "number" ? item.x_offset : anchor ? 260 * (index + 1) : 260 * index;
    const yOffset = typeof item.y_offset === "number" ? item.y_offset : 90 * index;
    nextNodes.push({
      id,
      type,
      position: { x: anchorX + xOffset, y: anchorY + yOffset },
      data: normalizedData,
    });
  });

  const finalNodeMap = new Map(nextNodes.map((node) => [node.id, node]));
  for (const edge of patch.edges || []) {
    const rawSource = String(edge.source || "").trim();
    const rawTarget = String(edge.target || "").trim();
    const source = refToNodeId[rawSource] || rawSource;
    const target = refToNodeId[rawTarget] || rawTarget;
    if (!source || !target) continue;
    const sourceNodeType = finalNodeMap.get(source)?.type || "";
    const sourceHandle = normalizeSourceHandleForType(edge.source_handle, sourceNodeType);
    const id = safeGraphId(`edge_${source}_${target}_${sourceHandle}`, "edge", usedEdgeIds);
    nextEdges.push({
      id,
      source,
      target,
      sourceHandle,
      ...(edge.target_handle ? { targetHandle: edge.target_handle } : {}),
      ...(edge.label ? { label: edge.label } : {}),
    });
  }

  return {
    nodes: nextNodes,
    edges: nextEdges,
    refToNodeId,
    stats: getAssistantPatchStats(response),
  };
}
