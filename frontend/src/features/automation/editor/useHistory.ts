import { useCallback, useRef, useState } from "react";
import type { Edge } from "@xyflow/react";
import type { CanvasNode } from "../graph";

export type GraphSnapshot = {
  nodes: CanvasNode[];
  edges: Edge[];
};

const LIMIT = 50;

function cloneSnapshot(snapshot: GraphSnapshot): GraphSnapshot {
  return {
    nodes: structuredClone(snapshot.nodes),
    edges: structuredClone(snapshot.edges),
  };
}

export function useHistory(initial: GraphSnapshot) {
  const [present, setPresent] = useState(() => cloneSnapshot(initial));
  const past = useRef<GraphSnapshot[]>([]);
  const future = useRef<GraphSnapshot[]>([]);

  const replace = useCallback((next: GraphSnapshot) => {
    setPresent(cloneSnapshot(next));
  }, []);

  const push = useCallback((next: GraphSnapshot) => {
    setPresent((current) => {
      past.current = [...past.current, cloneSnapshot(current)].slice(-LIMIT);
      future.current = [];
      return cloneSnapshot(next);
    });
  }, []);

  const undo = useCallback(() => {
    setPresent((current) => {
      const previous = past.current.at(-1);
      if (!previous) return current;
      past.current = past.current.slice(0, -1);
      future.current = [cloneSnapshot(current), ...future.current].slice(
        0,
        LIMIT,
      );
      return cloneSnapshot(previous);
    });
  }, []);

  const redo = useCallback(() => {
    setPresent((current) => {
      const next = future.current[0];
      if (!next) return current;
      future.current = future.current.slice(1);
      past.current = [...past.current, cloneSnapshot(current)].slice(-LIMIT);
      return cloneSnapshot(next);
    });
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
