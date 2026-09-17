import type { PipelineEdge, PipelineNode, PipelineRun, NodeState } from "@/lib/api";

export interface PipelineRunGraphState {
  currentNodeId: string | null;
  traversedNodeIds: Set<string>;
  queuedNodeIds: Set<string>;
  activeEdgeIds: Set<string>;
  currentEdgeIds: Set<string>;
}

const ACTIVE_NODE_STATUSES = new Set(["running", "awaiting_approval", "awaiting_operator_reply"]);
const TERMINAL_NODE_STATUSES = new Set(["completed", "failed", "skipped"]);

function getEdgeHandle(edge: PipelineEdge): string {
  return String(edge.sourceHandle || "out");
}

function inferRoutingPorts(node: PipelineNode, state?: NodeState): Set<string> {
  const rawPorts = Array.isArray(state?.routing_ports) ? state.routing_ports.filter(Boolean) : [];
  if (rawPorts.length) {
    return new Set(rawPorts.map((port) => String(port)));
  }

  if (node.type.startsWith("trigger/")) {
    return new Set(["out"]);
  }

  if (!state?.status) {
    return new Set();
  }

  if (node.type === "logic/human_approval") {
    const decision = String(state.decision || "");
    return decision ? new Set([decision]) : new Set();
  }

  if (node.type === "logic/telegram_input") {
    const decision = String(state.decision || "");
    return decision ? new Set([decision]) : new Set();
  }

  if (node.type === "logic/wait") {
    return state.status === "completed" ? new Set(["done", "out"]) : new Set();
  }

  if (node.type === "logic/condition") {
    if (state.status !== "completed") {
      return new Set();
    }
    const passed = typeof state.passed === "boolean" ? state.passed : String(state.output || "").trim().toLowerCase() === "true";
    return new Set([passed ? "true" : "false"]);
  }

  if (node.type === "logic/parallel" || node.type === "logic/merge") {
    return TERMINAL_NODE_STATUSES.has(state.status) ? new Set(["out"]) : new Set();
  }

  if (node.type.startsWith("agent/") || node.type.startsWith("output/")) {
    if (state.status === "completed") {
      return new Set(["success", "out"]);
    }
    if (state.status === "failed") {
      return new Set(["error"]);
    }
    return new Set();
  }

  return TERMINAL_NODE_STATUSES.has(state.status) ? new Set(["out"]) : new Set();
}

export function getCurrentPipelineRunNodeId(run: PipelineRun | null | undefined, nodes: PipelineNode[]): string | null {
  if (!run) {
    return null;
  }

  for (const node of nodes) {
    const status = String(run.node_states?.[node.id]?.status || "");
    if (ACTIVE_NODE_STATUSES.has(status)) {
      return node.id;
    }
  }

  if (run.status === "pending") {
    return run.entry_node_id || null;
  }

  return null;
}

export function buildPipelineRunGraphState(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  run: PipelineRun | null | undefined,
): PipelineRunGraphState {
  if (!run) {
    return {
      currentNodeId: null,
      traversedNodeIds: new Set(),
      queuedNodeIds: new Set(),
      activeEdgeIds: new Set(),
      currentEdgeIds: new Set(),
    };
  }

  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const currentNodeId = getCurrentPipelineRunNodeId(run, nodes);
  const traversedNodeIds = new Set<string>();
  const queuedNodeIds = new Set<string>();
  const activeEdgeIds = new Set<string>();
  const currentEdgeIds = new Set<string>();

  if (run.entry_node_id) {
    traversedNodeIds.add(run.entry_node_id);
  }

  for (const [nodeId, state] of Object.entries(run.node_states || {})) {
    if (state?.status) {
      traversedNodeIds.add(nodeId);
    }
  }

  if (currentNodeId) {
    traversedNodeIds.add(currentNodeId);
  }

  for (const edge of edges) {
    const source = nodesById.get(edge.source);
    if (!source) {
      continue;
    }

    const sourceState = run.node_states?.[source.id];
    const routingPorts = inferRoutingPorts(source, sourceState);
    const edgeHandle = getEdgeHandle(edge);
    const isEntryEdge = source.id === run.entry_node_id && edgeHandle === "out";
    const isRouted = routingPorts.has(edgeHandle) || isEntryEdge;

    if (!isRouted) {
      continue;
    }

    const targetState = run.node_states?.[edge.target];
    const targetKnown = Boolean(targetState?.status) || edge.target === currentNodeId;
    if (!targetKnown && run.status !== "pending") {
      queuedNodeIds.add(edge.target);
    }

    activeEdgeIds.add(edge.id);
    traversedNodeIds.add(edge.source);
    if (targetKnown) {
      traversedNodeIds.add(edge.target);
    }
    if (edge.target === currentNodeId) {
      currentEdgeIds.add(edge.id);
    }
  }

  return {
    currentNodeId,
    traversedNodeIds,
    queuedNodeIds,
    activeEdgeIds,
    currentEdgeIds,
  };
}
