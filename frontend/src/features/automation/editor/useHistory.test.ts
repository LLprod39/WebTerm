import { describe, expect, it } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useHistory } from "./useHistory";
import type { CanvasNode } from "../graph";

const node = (id: string): CanvasNode => ({
  id,
  type: "workflow",
  position: { x: 0, y: 0 },
  data: {
    backend: { id, type: "trigger/manual", position: { x: 0, y: 0 }, data: {} },
    handles: ["out"],
  },
});

describe("useHistory", () => {
  it("undoes and redoes discrete graph snapshots", () => {
    const { result } = renderHook(() =>
      useHistory({ nodes: [node("a")], edges: [] }),
    );
    act(() => {
      result.current.push({ nodes: [node("a"), node("b")], edges: [] });
    });
    expect(result.current.present.nodes).toHaveLength(2);
    act(() => {
      result.current.undo();
    });
    expect(result.current.present.nodes).toHaveLength(1);
    act(() => {
      result.current.redo();
    });
    expect(result.current.present.nodes.map((n) => n.id)).toEqual(["a", "b"]);
  });
});
