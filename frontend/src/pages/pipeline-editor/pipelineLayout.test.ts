import { describe, expect, it } from "vitest";

import type { PipelineEdge, PipelineNode } from "@/lib/api";

import { layoutPipelineGraph, looksVertical } from "./pipelineLayout";

function node(id: string, x: number, y: number, type = "agent/react"): PipelineNode {
  return { id, type, position: { x, y }, data: {} };
}

function edge(source: string, target: string, id?: string): PipelineEdge {
  return { id: id ?? `${source}-${target}`, source, target };
}

describe("looksVertical", () => {
  it("returns false for fewer than two nodes", () => {
    expect(looksVertical([])).toBe(false);
    expect(looksVertical([node("a", 0, 0)])).toBe(false);
  });

  it("returns true for a tall stacked (TB) graph", () => {
    const nodes = [node("a", 100, 0), node("b", 110, 160), node("c", 90, 320)];
    expect(looksVertical(nodes)).toBe(true);
  });

  it("returns false for a wide horizontal (LR) graph", () => {
    const nodes = [node("a", 0, 40), node("b", 280, 40), node("c", 560, 50)];
    expect(looksVertical(nodes)).toBe(false);
  });

  it("returns false when ySpan is large but not enough vs xSpan", () => {
    // ySpan=150, xSpan=200 → 150 > 200*1.25 is false
    const nodes = [node("a", 0, 0), node("b", 200, 150)];
    expect(looksVertical(nodes)).toBe(false);
  });
});

describe("layoutPipelineGraph", () => {
  it("assigns increasing x for a linear chain with rankdir LR", () => {
    const nodes = [node("a", 0, 400), node("b", 0, 200), node("c", 0, 0)];
    const edges = [edge("a", "b"), edge("b", "c")];
    const laid = layoutPipelineGraph(nodes, edges, "LR");

    expect(laid.map((n) => n.id)).toEqual(["a", "b", "c"]);
    expect(laid[0].position.x).toBeLessThan(laid[1].position.x);
    expect(laid[1].position.x).toBeLessThan(laid[2].position.x);
    // ids/data preserved
    expect(laid[0].data).toBe(nodes[0].data);
    expect(laid[1].type).toBe("agent/react");
  });

  it("places condition children at different y when branching", () => {
    const nodes = [
      node("trigger", 0, 0, "trigger/manual"),
      node("cond", 0, 200, "logic/condition"),
      node("yes", 0, 400, "agent/react"),
      node("no", 0, 600, "agent/react"),
    ];
    const edges = [
      edge("trigger", "cond"),
      edge("cond", "yes", "cond-yes"),
      edge("cond", "no", "cond-no"),
    ];
    const laid = layoutPipelineGraph(nodes, edges, "LR");
    const byId = Object.fromEntries(laid.map((n) => [n.id, n]));

    expect(byId.trigger.position.x).toBeLessThan(byId.cond.position.x);
    expect(byId.cond.position.x).toBeLessThan(byId.yes.position.x);
    expect(byId.cond.position.x).toBeLessThan(byId.no.position.x);
    expect(byId.yes.position.y).not.toBe(byId.no.position.y);
  });

  it("does not mutate input nodes", () => {
    const nodes = [node("a", 10, 20), node("b", 10, 200)];
    const edges = [edge("a", "b")];
    const before = structuredClone(nodes);
    layoutPipelineGraph(nodes, edges, "LR");
    expect(nodes).toEqual(before);
  });
});
