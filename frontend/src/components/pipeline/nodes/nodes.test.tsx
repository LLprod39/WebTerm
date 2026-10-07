import { render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "@/lib/i18n";
import { NODE_PALETTE, NODE_TYPES } from "@/components/pipeline/nodes";
import {
  getNodeBranchLabel,
  getNodePaletteText,
  getNodeTypeGuidance,
  getNodeTypeInfo,
} from "@/components/pipeline/nodes/nodeMeta";
import { ConditionNode } from "@/components/pipeline/nodes/ConditionNode";
import { HumanApprovalNode } from "@/components/pipeline/nodes/HumanApprovalNode";
import { OpsNode } from "@/components/pipeline/nodes/OpsNode";
import { OutputNode } from "@/components/pipeline/nodes/OutputNode";

const OPS_TYPES = Object.keys(NODE_TYPES).filter((type) => type.startsWith("ops/"));

const WEBHOOK_COPY = [
  "Отправка результата в URL",
  "POST results to URL",
  "Отправка результата во внешний HTTP endpoint",
  "POST the result to an external endpoint",
];

function nodeProps(type: string, data: Record<string, unknown> = {}): NodeProps {
  return {
    id: "n1",
    type,
    data,
    selected: false,
    dragging: false,
    zIndex: 0,
    selectable: true,
    deletable: true,
    draggable: true,
    isConnectable: true,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
  } as NodeProps;
}

function renderNode(ui: ReactElement) {
  return render(
    <I18nProvider>
      <ReactFlowProvider>{ui}</ReactFlowProvider>
    </I18nProvider>,
  );
}

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

  it("maps every ops/* type to OpsNode", () => {
    expect(OPS_TYPES.length).toBeGreaterThan(0);
    for (const type of OPS_TYPES) {
      expect(NODE_TYPES[type as keyof typeof NODE_TYPES]).toBe("OpsNode");
    }
    expect(NODE_TYPES["output/report"]).toBe("OutputNode");
    expect(NODE_TYPES["output/webhook"]).toBe("OutputNode");
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

  it("guides LLM query users to Settings → AI instead of per-node model pick", () => {
    const guidance = getNodeTypeGuidance("agent/llm_query", "en");
    expect(guidance.checklist.join(" ")).toContain("Settings → AI");
    expect(guidance.checklist.join(" ").toLowerCase()).not.toContain("choose provider");
  });
});

describe("studio L/R node rendering", () => {
  it("ops nodes show palette copy, not webhook URL copy", () => {
    for (const type of OPS_TYPES) {
      const palette = getNodePaletteText(type, "ru");
      const { container, unmount } = renderNode(<OpsNode {...nodeProps(type)} />);
      expect(screen.getByText(palette.label)).toBeTruthy();
      expect(screen.getByText(palette.description)).toBeTruthy();
      const text = container.textContent || "";
      for (const bad of WEBHOOK_COPY) {
        expect(text).not.toContain(bad);
      }
      unmount();
    }
  });

  it("output webhook still shows webhook copy; report does not", () => {
    const { unmount: unmountWebhook } = renderNode(<OutputNode {...nodeProps("output/webhook")} />);
    expect(screen.getByText("Отправка результата в URL")).toBeTruthy();
    unmountWebhook();

    const { container } = renderNode(<OutputNode {...nodeProps("output/report")} />);
    expect(screen.getByText("Финальный markdown-отчёт")).toBeTruthy();
    expect(container.textContent || "").not.toContain("Отправка результата в URL");
  });

  it("uses Left target and Right source handles", () => {
    const { container } = renderNode(<ConditionNode {...nodeProps("logic/condition")} />);
    const target = container.querySelector('.react-flow__handle[data-handlepos="left"]');
    const sources = container.querySelectorAll('.react-flow__handle[data-handlepos="right"]');
    expect(target).toBeTruthy();
    expect(target?.className).toContain("target");
    expect(sources.length).toBe(2);
    for (const source of sources) {
      expect(source.className).toContain("source");
    }
    expect(container.querySelector('[data-handleid="true"]')).toBeTruthy();
    expect(container.querySelector('[data-handleid="false"]')).toBeTruthy();
  });

  it("keeps multi-port handle ids and places labels inside (no -bottom-5)", () => {
    const { container } = renderNode(<HumanApprovalNode {...nodeProps("logic/human_approval")} />);
    for (const id of ["approved", "rejected", "timeout"]) {
      expect(container.querySelector(`[data-handleid="${id}"]`)).toBeTruthy();
    }
    expect(container.innerHTML).not.toContain("-bottom-5");
    const labels = [...container.querySelectorAll("span")].filter((el) =>
      ["Да", "Нет", "Timeout"].includes(el.textContent || ""),
    );
    expect(labels.length).toBe(3);
    for (const label of labels) {
      expect(label.className).toContain("right-3");
      expect(label.className).not.toContain("-bottom-5");
    }
  });
});
