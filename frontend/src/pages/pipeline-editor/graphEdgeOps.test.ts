import { describe, expect, it } from "vitest";
import type { Edge } from "@xyflow/react";

import {
  defaultSourceHandleForType,
  firstSourceHandleForType,
  insertBetween,
  makeEdgeId,
} from "./graphEdgeOps";

describe("graphEdgeOps", () => {
  it("defaults source handles for branching node types", () => {
    expect(defaultSourceHandleForType("logic/condition")).toBe("true");
    expect(defaultSourceHandleForType("logic/wait")).toBe("done");
    expect(defaultSourceHandleForType("agent/ssh_cmd")).toBe("out");
  });

  it("prefers the first manifest source handle when present", () => {
    expect(firstSourceHandleForType("logic/condition", ["true", "false"])).toBe("true");
    expect(firstSourceHandleForType("agent/react", ["success", "error", "out"])).toBe("success");
    expect(firstSourceHandleForType("logic/wait", null)).toBe("done");
  });

  it("insertBetween splits A→B into A→N→B and preserves sourceHandle", () => {
    const edges: Edge[] = [
      {
        id: "ab",
        source: "a",
        target: "b",
        sourceHandle: "approved",
        targetHandle: undefined,
        type: "studio",
      },
    ];

    const next = insertBetween(edges, "ab", "n", {
      newNodeSourceHandle: "out",
      edgeType: "studio",
    });

    expect(next).toHaveLength(2);
    expect(next.find((edge) => edge.id === "ab")).toBeUndefined();
    expect(next).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: makeEdgeId("a", "n", "approved"),
          source: "a",
          target: "n",
          sourceHandle: "approved",
          type: "studio",
        }),
        expect.objectContaining({
          id: makeEdgeId("n", "b", "out"),
          source: "n",
          target: "b",
          sourceHandle: "out",
          type: "studio",
        }),
      ]),
    );
  });

  it("returns edges unchanged when the edge id is missing", () => {
    const edges: Edge[] = [{ id: "ab", source: "a", target: "b", sourceHandle: "out" }];
    expect(insertBetween(edges, "missing", "n")).toBe(edges);
  });
});
