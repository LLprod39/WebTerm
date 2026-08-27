import { describe, expect, it } from "vitest";

import { NODE_PALETTE, NODE_TYPES } from "@/components/pipeline/nodes";
import {
  getLlmQueryModelLabel,
  getNodeBranchLabel,
  getNodePaletteText,
  getNodeTypeGuidance,
  getNodeTypeInfo,
} from "@/components/pipeline/nodes/nodeMeta";

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

  it("has localized metadata, palette text, and guidance for every node type", () => {
    const paletteTypes = new Set(NODE_PALETTE.flatMap((section) => section.nodes.map((node) => node.type)));

    for (const type of Object.keys(NODE_TYPES)) {
      expect(paletteTypes.has(type as keyof typeof NODE_TYPES)).toBe(true);

      const info = getNodeTypeInfo(type, "ru");
      const paletteText = getNodePaletteText(type, "ru");
      const guidance = getNodeTypeGuidance(type, "ru");

      expect(info.label).toBeTruthy();
      expect(paletteText.label).toBe(info.label);
      expect(paletteText.description).toBeTruthy();
      expect(guidance.summary).toBeTruthy();
      expect(guidance.checklist.length).toBeGreaterThan(0);
    }
  });

  it("uses operator-friendly branch labels", () => {
    expect(getNodeBranchLabel("true", "ru")).toBe("Да");
    expect(getNodeBranchLabel("false", "ru")).toBe("Нет");
    expect(getNodeBranchLabel("approved", "ru")).toBe("Да");
    expect(getNodeBranchLabel("rejected", "ru")).toBe("Нет");
    expect(getNodeBranchLabel("timeout", "ru")).toBe("Timeout");
    expect(getNodeBranchLabel("error", "ru")).toBe("Ошибка");
  });

  it("describes workspace routing without advertising a hardcoded Gemini model", () => {
    const guidance = getNodeTypeGuidance("agent/llm_query", "en");

    expect(guidance.checklist.join(" ")).toContain("workspace settings");
    expect(guidance.checklist.join(" ")).not.toMatch(/choose provider/i);
    expect(getLlmQueryModelLabel({}, "en")).toBe("Auto · workspace model");
    expect(getLlmQueryModelLabel({ model: "gpt-5.4" }, "en")).toBe("gpt-5.4");
  });
});
