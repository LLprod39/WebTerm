import { describe, expect, it } from "vitest";

import { NODE_PALETTE, NODE_TYPES } from "@/components/pipeline/nodes";

describe("pipeline node catalog", () => {
  it("exposes the merge node in the editor palette and node map", () => {
    const logicPalette = NODE_PALETTE.find((section) => section.category === "Logic");
    expect(logicPalette?.nodes.some((node) => node.type === "logic/merge")).toBe(true);
    expect(NODE_TYPES["logic/merge"]).toBe("MergeNode");
  });

  it("exposes monitoring trigger and telegram input nodes", () => {
    const triggerPalette = NODE_PALETTE.find((section) => section.category === "Triggers");
    const logicPalette = NODE_PALETTE.find((section) => section.category === "Logic");
    expect(triggerPalette?.nodes.some((node) => node.type === "trigger/monitoring")).toBe(true);
    expect(logicPalette?.nodes.some((node) => node.type === "logic/telegram_input")).toBe(true);
    expect(NODE_TYPES["trigger/monitoring"]).toBe("TriggerNode");
    expect(NODE_TYPES["logic/telegram_input"]).toBe("TelegramInputNode");
  });
});
