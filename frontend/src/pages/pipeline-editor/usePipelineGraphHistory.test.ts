import { describe, expect, it } from "vitest";
import { renderHook, act } from "@testing-library/react";
import {
  usePipelineGraphHistory,
  type PipelineNode,
} from "./usePipelineGraphHistory";

const node = (id: string): PipelineNode => ({
  id,
  type: "agent/llm",
  position: { x: 0, y: 0 },
  data: { label: id },
});

describe("usePipelineGraphHistory", () => {
  it("pushes, undoes, and redoes discrete graph snapshots", () => {
    const { result } = renderHook(() =>
      usePipelineGraphHistory({ nodes: [node("a")], edges: [] }),
    );

    expect(result.current.present.nodes).toHaveLength(1);
    expect(result.current.canUndo()).toBe(false);
    expect(result.current.canRedo()).toBe(false);

    act(() => {
      result.current.push({ nodes: [node("a"), node("b")], edges: [] });
    });
    expect(result.current.present.nodes).toHaveLength(2);
    expect(result.current.canUndo()).toBe(true);

    act(() => {
      result.current.undo();
    });
    expect(result.current.present.nodes).toHaveLength(1);
    expect(result.current.canRedo()).toBe(true);

    act(() => {
      result.current.redo();
    });
    expect(result.current.present.nodes.map((n) => n.id)).toEqual(["a", "b"]);
  });

  it("clones snapshots so later mutations do not rewrite history", () => {
    const { result } = renderHook(() =>
      usePipelineGraphHistory({ nodes: [node("a")], edges: [] }),
    );
    const next = { nodes: [node("a"), node("b")], edges: [] };

    act(() => {
      result.current.push(next);
    });
    next.nodes.push(node("mutated"));

    act(() => {
      result.current.undo();
    });
    act(() => {
      result.current.redo();
    });
    expect(result.current.present.nodes.map((n) => n.id)).toEqual(["a", "b"]);
  });

  it("caps past history at 50 entries", () => {
    const { result } = renderHook(() =>
      usePipelineGraphHistory({ nodes: [node("0")], edges: [] }),
    );

    for (let i = 1; i <= 55; i += 1) {
      act(() => {
        result.current.push({ nodes: [node(String(i))], edges: [] });
      });
    }

    let undoCount = 0;
    while (result.current.canUndo()) {
      act(() => {
        result.current.undo();
      });
      undoCount += 1;
      if (undoCount > 60) break;
    }
    expect(undoCount).toBe(50);
    expect(result.current.present.nodes[0]?.id).toBe("5");
  });

  it("setPresent replaces without stacking undo", () => {
    const { result } = renderHook(() =>
      usePipelineGraphHistory({ nodes: [node("a")], edges: [] }),
    );

    act(() => {
      result.current.setPresent({ nodes: [node("z")], edges: [] });
    });
    expect(result.current.present.nodes.map((n) => n.id)).toEqual(["z"]);
    expect(result.current.canUndo()).toBe(false);
  });

  it("undo/redo remain consistent when push/undo run back-to-back (StrictMode-safe refs)", () => {
    const { result } = renderHook(() =>
      usePipelineGraphHistory({ nodes: [node("a")], edges: [] }),
    );

    act(() => {
      result.current.push({ nodes: [node("a"), node("b")], edges: [] });
      result.current.push({ nodes: [node("a"), node("b"), node("c")], edges: [] });
    });
    expect(result.current.present.nodes.map((n) => n.id)).toEqual(["a", "b", "c"]);

    act(() => {
      result.current.undo();
    });
    expect(result.current.present.nodes.map((n) => n.id)).toEqual(["a", "b"]);
    expect(result.current.canRedo()).toBe(true);

    act(() => {
      result.current.redo();
    });
    expect(result.current.present.nodes.map((n) => n.id)).toEqual(["a", "b", "c"]);
  });
});
