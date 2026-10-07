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
 *
 * Stack mutations happen outside `setPresent` updaters so React 18 StrictMode
 * double-invokes cannot slice past/future twice.
 */
export function usePipelineGraphHistory(initial: PipelineGraphSnapshot) {
  const [present, setPresent] = useState(() => cloneSnapshot(initial));
  const presentRef = useRef(present);
  const past = useRef<PipelineGraphSnapshot[]>([]);
  const future = useRef<PipelineGraphSnapshot[]>([]);

  const replace = useCallback((next: PipelineGraphSnapshot) => {
    const cloned = cloneSnapshot(next);
    presentRef.current = cloned;
    setPresent(cloned);
  }, []);

  const push = useCallback((next: PipelineGraphSnapshot) => {
    past.current = [...past.current, cloneSnapshot(presentRef.current)].slice(-LIMIT);
    future.current = [];
    const cloned = cloneSnapshot(next);
    presentRef.current = cloned;
    setPresent(cloned);
  }, []);

  const undo = useCallback((): PipelineGraphSnapshot | null => {
    const previous = past.current.at(-1);
    if (!previous) return null;
    past.current = past.current.slice(0, -1);
    future.current = [cloneSnapshot(presentRef.current), ...future.current].slice(0, LIMIT);
    const restored = cloneSnapshot(previous);
    presentRef.current = restored;
    setPresent(restored);
    return restored;
  }, []);

  const redo = useCallback((): PipelineGraphSnapshot | null => {
    const next = future.current[0];
    if (!next) return null;
    future.current = future.current.slice(1);
    past.current = [...past.current, cloneSnapshot(presentRef.current)].slice(-LIMIT);
    const restored = cloneSnapshot(next);
    presentRef.current = restored;
    setPresent(restored);
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
