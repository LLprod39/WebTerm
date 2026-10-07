import { useCallback, useRef, useState } from "react";
import type { Edge, Node } from "@xyflow/react";

/** React Flow–compatible node type for studio pipeline graphs. */
export type PipelineNode = Node;

/** React Flow–compatible edge type for studio pipeline graphs. */
export type PipelineEdge = Edge;

export type PipelineGraphSnapshot = {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
};

const LIMIT = 50;

function cloneSnapshot(snapshot: PipelineGraphSnapshot): PipelineGraphSnapshot {
  return {
    nodes: structuredClone(snapshot.nodes),
    edges: structuredClone(snapshot.edges),
  };
}

/**
 * Undo/redo stack for pipeline graph edits (mirrors automation `useHistory`).
 *
 * Integrator:
 * ```ts
 * const history = usePipelineGraphHistory({ nodes: [], edges: [] });
 * // history.present.nodes / .edges — current graph
 * // history.push(next) — commit a discrete edit (clears redo)
 * // history.setPresent(next) — replace without stacking (hydrate/reset)
 * // history.undo() / history.redo()
 * // history.canUndo() / history.canRedo()
 * ```
 */
export function usePipelineGraphHistory(initial: PipelineGraphSnapshot) {
  const [present, setPresent] = useState(() => cloneSnapshot(initial));
  const past = useRef<PipelineGraphSnapshot[]>([]);
  const future = useRef<PipelineGraphSnapshot[]>([]);

  const replace = useCallback((next: PipelineGraphSnapshot) => {
    setPresent(cloneSnapshot(next));
  }, []);

  const push = useCallback((next: PipelineGraphSnapshot) => {
    setPresent((current) => {
      past.current = [...past.current, cloneSnapshot(current)].slice(-LIMIT);
      future.current = [];
      return cloneSnapshot(next);
    });
  }, []);

  const undo = useCallback((): PipelineGraphSnapshot | null => {
    let restored: PipelineGraphSnapshot | null = null;
    setPresent((current) => {
      const previous = past.current.at(-1);
      if (!previous) return current;
      past.current = past.current.slice(0, -1);
      future.current = [cloneSnapshot(current), ...future.current].slice(0, LIMIT);
      restored = cloneSnapshot(previous);
      return restored;
    });
    return restored;
  }, []);

  const redo = useCallback((): PipelineGraphSnapshot | null => {
    let restored: PipelineGraphSnapshot | null = null;
    setPresent((current) => {
      const next = future.current[0];
      if (!next) return current;
      future.current = future.current.slice(1);
      past.current = [...past.current, cloneSnapshot(current)].slice(-LIMIT);
      restored = cloneSnapshot(next);
      return restored;
    });
    return restored;
  }, []);

  return {
    present,
    setPresent: replace,
    push,
    undo,
    redo,
    canUndo: () => past.current.length > 0,
    canRedo: () => future.current.length > 0,
  };
}
