import type { Node, Edge } from "@xyflow/react";
import type {
  PipelineNode,
  PipelineEdge,
  NodeManifest,
  NodeState,
  Values,
} from "@/api/automation";

export type CanvasData = Record<string, unknown> & {
  backend: PipelineNode;
  handles: string[];
  status?: string;
  runView?: boolean;
  issueCount?: number;
  connectedHandles?: string[];
  actions?: {
    onAddOutput?: (nodeId: string, handle: string) => void;
    onConfigure?: (nodeId: string) => void;
    onDuplicate?: (nodeId: string) => void;
    onDelete?: (nodeId: string) => void;
  };
};
export type CanvasNode = Node<CanvasData, "workflow">;

export const HORIZONTAL_GAP = 280;
export const VERTICAL_GAP = 130;
export const LAYOUT_ORIGIN = { x: 72, y: 96 };

export function toCanvas(
  nodes: PipelineNode[],
  manifests: NodeManifest[],
): CanvasNode[] {
  return nodes.map((node, index) => ({
    id: node.id,
    type: "workflow",
    position: node.position ?? {
      x: LAYOUT_ORIGIN.x + index * HORIZONTAL_GAP,
      y: LAYOUT_ORIGIN.y,
    },
    data: {
      backend: node,
      handles: manifests.find((m) => m.type === node.type)?.source_handles ?? [
        "out",
      ],
    },
  }));
}

export function runToCanvas(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  states: Record<string, NodeState>,
  selected: string | undefined,
): CanvasNode[] {
  return toCanvas(nodes, []).map((node) => ({
    ...node,
    selected: node.id === selected,
    ariaLabel: String(node.data.backend.data.label || node.data.backend.type),
    data: {
      ...node.data,
      runView: true,
      status: states[node.id]?.status,
      handles: [
        ...new Set(
          edges
            .filter((edge) => edge.source === node.id)
            .map((edge) => edge.sourceHandle || "out"),
        ),
      ],
    },
  }));
}

export function fromCanvas(
  nodes: CanvasNode[],
  edges: Edge[],
): { nodes: PipelineNode[]; edges: PipelineEdge[] } {
  return {
    nodes: nodes.map((n) => ({
      ...n.data.backend,
      id: n.id,
      position: n.position,
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle ?? undefined,
      targetHandle: e.targetHandle ?? undefined,
    })),
  };
}

export function graphSignature(
  nodes: CanvasNode[],
  edges: Edge[],
  name: string,
  description: string,
) {
  return JSON.stringify({ ...fromCanvas(nodes, edges), name, description });
}

export function schemaDefaults(manifest: NodeManifest): Values {
  const defaults: Values = {
    label:
      manifest.type.split("/").at(-1)?.replaceAll("_", " ") ?? manifest.type,
  };
  for (const [key, schema] of Object.entries(
    manifest.input_schema.properties ?? {},
  )) {
    if (schema.default !== undefined)
      defaults[key] = structuredClone(schema.default);
  }
  if (manifest.type.startsWith("trigger/")) defaults.is_active = false;
  return defaults;
}

export function validConnection(
  source: string | null,
  target: string | null,
  edges: Edge[],
) {
  if (!source || !target || source === target) return false;
  const adjacency = new Map<string, string[]>();
  for (const e of edges)
    adjacency.set(e.source, [...(adjacency.get(e.source) ?? []), e.target]);
  const stack = [target];
  const visited = new Set<string>();
  while (stack.length) {
    const node = stack.pop()!;
    if (node === source) return false;
    if (visited.has(node)) continue;
    visited.add(node);
    stack.push(...(adjacency.get(node) ?? []));
  }
  return true;
}

/** Place a new node to the right of the selected node, or continue the flow. */
export function nextNodePosition(
  nodes: CanvasNode[],
  selectedId: string | null,
): { x: number; y: number } {
  if (selectedId) {
    const selected = nodes.find((n) => n.id === selectedId);
    if (selected) {
      return {
        x: selected.position.x + HORIZONTAL_GAP,
        y: selected.position.y,
      };
    }
  }
  if (!nodes.length) return { ...LAYOUT_ORIGIN };
  const rightmost = nodes.reduce((best, node) =>
    node.position.x > best.position.x ? node : best,
  );
  return {
    x: rightmost.position.x + HORIZONTAL_GAP,
    y: rightmost.position.y,
  };
}

/**
 * Left-to-right layered layout (n8n-style): triggers/roots on the left,
 * downstream steps advance by column.
 */
export function layoutHorizontal(
  nodes: CanvasNode[],
  edges: Edge[],
): CanvasNode[] {
  if (!nodes.length) return nodes;

  const ids = new Set(nodes.map((n) => n.id));
  const outgoing = new Map<string, string[]>();
  const incoming = new Map<string, number>();
  for (const id of ids) {
    outgoing.set(id, []);
    incoming.set(id, 0);
  }
  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
    outgoing.get(edge.source)!.push(edge.target);
    incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1);
  }

  const roots = nodes
    .filter(
      (n) =>
        n.data.backend.type.startsWith("trigger/") ||
        (incoming.get(n.id) ?? 0) === 0,
    )
    .map((n) => n.id);
  const start = roots.length ? roots : [nodes[0].id];

  const level = new Map<string, number>();
  const queue = [...start];
  for (const id of start) level.set(id, 0);
  while (queue.length) {
    const id = queue.shift()!;
    const next = (level.get(id) ?? 0) + 1;
    for (const child of outgoing.get(id) ?? []) {
      const prev = level.get(child);
      if (prev === undefined || next > prev) {
        level.set(child, next);
        queue.push(child);
      }
    }
  }

  let orphanColumn = Math.max(0, ...level.values()) + 1;
  for (const node of nodes) {
    if (!level.has(node.id)) {
      level.set(node.id, orphanColumn);
      orphanColumn += 1;
    }
  }

  const columns = new Map<number, string[]>();
  for (const node of nodes) {
    const col = level.get(node.id) ?? 0;
    const list = columns.get(col) ?? [];
    list.push(node.id);
    columns.set(col, list);
  }

  const positions = new Map<string, { x: number; y: number }>();
  for (const [col, columnIds] of [...columns.entries()].sort(
    (a, b) => a[0] - b[0],
  )) {
    columnIds.forEach((id, row) => {
      positions.set(id, {
        x: LAYOUT_ORIGIN.x + col * HORIZONTAL_GAP,
        y: LAYOUT_ORIGIN.y + row * VERTICAL_GAP,
      });
    });
  }

  return nodes.map((node) => ({
    ...node,
    position: positions.get(node.id) ?? node.position,
  }));
}

/** Detect graphs that look vertically stacked (legacy top→bottom). */
export function looksVertical(nodes: CanvasNode[]): boolean {
  if (nodes.length < 2) return false;
  const xs = nodes.map((n) => n.position.x);
  const ys = nodes.map((n) => n.position.y);
  const xSpan = Math.max(...xs) - Math.min(...xs);
  const ySpan = Math.max(...ys) - Math.min(...ys);
  return ySpan > xSpan * 1.25 && ySpan > 120;
}

export function isEmptyValue(value: unknown): boolean {
  if (value === undefined || value === null) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

/** Client-side missing required fields for a node. */
export function nodeIssues(
  node: PipelineNode | CanvasNode,
  manifest: NodeManifest | undefined,
): string[] {
  if (!manifest) return [];
  const data =
    "data" in node && node.data && "backend" in node.data
      ? (node as CanvasNode).data.backend.data
      : (node as PipelineNode).data;
  const required = manifest.input_schema.required ?? [];
  const issues: string[] = [];
  for (const key of required) {
    if (key === "label") continue;
    if (isEmptyValue(data[key])) {
      const title =
        manifest.input_schema.properties?.[key]?.title || key;
      issues.push(`Заполните поле «${title}»`);
    }
  }
  return issues;
}

export function buildNode(
  manifest: NodeManifest,
  position: { x: number; y: number },
  data?: Values,
): CanvasNode {
  const id = `${manifest.type.replaceAll("/", "-")}-${crypto.randomUUID().slice(0, 8)}`;
  const backend: PipelineNode = {
    id,
    type: manifest.type,
    position,
    data: data ?? schemaDefaults(manifest),
  };
  return toCanvas([backend], [manifest])[0];
}

export function duplicateNode(
  node: CanvasNode,
  manifests: NodeManifest[],
): CanvasNode {
  const manifest = manifests.find((m) => m.type === node.data.backend.type);
  const id = `${node.data.backend.type.replaceAll("/", "-")}-${crypto.randomUUID().slice(0, 8)}`;
  const backend: PipelineNode = {
    ...structuredClone(node.data.backend),
    id,
    position: {
      x: node.position.x + 40,
      y: node.position.y + 40,
    },
  };
  if (backend.type.startsWith("trigger/")) {
    backend.data = { ...backend.data, is_active: false };
  }
  return {
    ...toCanvas([backend], manifest ? [manifest] : [])[0],
    data: {
      ...toCanvas([backend], manifest ? [manifest] : [])[0].data,
      handles: node.data.handles,
    },
  };
}

/** Split A→B into A→N→B; returns updated edges and the inserted node id. */
export function insertBetween(
  edges: Edge[],
  edgeId: string,
  node: CanvasNode,
): Edge[] {
  const edge = edges.find((item) => item.id === edgeId);
  if (!edge) return edges;
  const without = edges.filter((item) => item.id !== edgeId);
  return [
    ...without,
    {
      id: crypto.randomUUID(),
      source: edge.source,
      target: node.id,
      sourceHandle: edge.sourceHandle,
      targetHandle: undefined,
    },
    {
      id: crypto.randomUUID(),
      source: node.id,
      target: edge.target,
      sourceHandle: node.data.handles[0] ?? "out",
      targetHandle: edge.targetHandle,
    },
  ];
}
