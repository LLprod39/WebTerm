import { describe, expect, it } from "vitest";
import {
  buildNode,
  duplicateNode,
  fromCanvas,
  insertBetween,
  layoutHorizontal,
  looksVertical,
  nextNodePosition,
  nodeIssues,
  schemaDefaults,
  toCanvas,
  validConnection,
} from "./graph";
import type { NodeManifest, PipelineNode } from "@/api/automation";
const manual = {
  type: "trigger/manual",
  category: "Triggers",
  purpose: "Start",
  source_handles: ["out"],
  risk_level: "read_only",
  idempotency: "idempotent",
  mutates_state: false,
  supports_dry_run: false,
  requires_approval_by_default: false,
  input_schema: {
    properties: { is_active: { type: "boolean", default: true } },
  },
  output_schema: {},
  tags: [],
} satisfies NodeManifest;
const condition = {
  type: "logic/condition",
  category: "Logic",
  purpose: "Branch",
  source_handles: ["true", "false"],
  risk_level: "read_only",
  idempotency: "idempotent",
  mutates_state: false,
  supports_dry_run: false,
  requires_approval_by_default: false,
  input_schema: {
    properties: {
      check_value: { type: "string", title: "Значение" },
    },
    required: ["check_value"],
  },
  output_schema: {},
  tags: [],
} satisfies NodeManifest;
describe("backend graph preservation", () => {
  it("keeps backend node types and fields while discarding transient canvas state", () => {
    const node: PipelineNode = {
      id: "start",
      type: "trigger/manual",
      position: { x: 10, y: 20 },
      data: { is_active: false, label: "Start", custom: { keep: true } },
    };
    const canvas = toCanvas([node], [manual]);
    canvas[0].selected = true;
    canvas[0].position = { x: 30, y: 40 };
    const result = fromCanvas(canvas, [
      {
        id: "e",
        source: "start",
        target: "next",
        sourceHandle: "out",
        selected: true,
      },
    ]);
    expect(result.nodes[0]).toEqual({ ...node, position: { x: 30, y: 40 } });
    expect(result.nodes[0].type).toBe("trigger/manual");
    expect(result.edges[0]).not.toHaveProperty("selected");
    expect(result.edges[0].sourceHandle).toBe("out");
  });
  it("new trigger creation never silently activates scheduled or external execution", () => {
    expect(schemaDefaults(manual).is_active).toBe(false);
  });
  it("rejects self edges and cycles while allowing a branch join", () => {
    const edges = [
      { id: "ab", source: "a", target: "b" },
      { id: "bc", source: "b", target: "c" },
    ];
    expect(validConnection("a", "a", edges)).toBe(false);
    expect(validConnection("c", "a", edges)).toBe(false);
    expect(validConnection("a", "c", edges)).toBe(true);
    expect(validConnection(null, "c", edges)).toBe(false);
  });
  it("places the next node to the right of the selection", () => {
    const nodes = toCanvas(
      [
        {
          id: "a",
          type: "trigger/manual",
          position: { x: 40, y: 80 },
          data: {},
        },
      ],
      [manual],
    );
    expect(nextNodePosition(nodes, "a")).toEqual({ x: 320, y: 80 });
  });
  it("lays out connected nodes left to right by depth", () => {
    const nodes = toCanvas(
      [
        {
          id: "a",
          type: "trigger/manual",
          position: { x: 0, y: 0 },
          data: {},
        },
        {
          id: "b",
          type: "logic/condition",
          position: { x: 0, y: 200 },
          data: {},
        },
        {
          id: "c",
          type: "action/command",
          position: { x: 0, y: 400 },
          data: {},
        },
      ],
      [manual],
    );
    const laid = layoutHorizontal(nodes, [
      { id: "ab", source: "a", target: "b" },
      { id: "bc", source: "b", target: "c" },
    ]);
    expect(laid[0].position.x).toBeLessThan(laid[1].position.x);
    expect(laid[1].position.x).toBeLessThan(laid[2].position.x);
    expect(looksVertical(nodes)).toBe(true);
    expect(looksVertical(laid)).toBe(false);
  });
  it("reports missing required fields", () => {
    const built = buildNode(condition, { x: 10, y: 10 });
    expect(nodeIssues(built, condition)).toEqual([
      "Заполните поле «Значение»",
    ]);
    built.data.backend.data.check_value = "ok";
    expect(nodeIssues(built, condition)).toEqual([]);
  });
  it("duplicates a node with a new id and inactive trigger", () => {
    const original = buildNode(
      manual,
      { x: 10, y: 10 },
      { label: "Start", is_active: true },
    );
    const copy = duplicateNode(original, [manual]);
    expect(copy.id).not.toBe(original.id);
    expect(copy.data.backend.data.is_active).toBe(false);
    expect(copy.position.x).toBe(original.position.x + 40);
  });
  it("inserts a node between an existing edge", () => {
    const mid = buildNode(condition, { x: 100, y: 0 });
    const edges = insertBetween(
      [{ id: "ab", source: "a", target: "b", sourceHandle: "out" }],
      "ab",
      mid,
    );
    expect(edges).toHaveLength(2);
    expect(edges[0]).toMatchObject({
      source: "a",
      target: mid.id,
      sourceHandle: "out",
    });
    expect(edges[1]).toMatchObject({
      source: mid.id,
      target: "b",
    });
  });
});
