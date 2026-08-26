import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "@/lib/i18n";

import { OperatorThinkingPanel, type ThinkingPhase } from "./OperatorThinkingPanel";
import type { StreamToolStep } from "./useOperatorChatWs";

type PanelProps = {
  phase: ThinkingPhase;
  statusMessage?: string;
  reasoningText?: string;
  hasReasoningStream?: boolean;
  toolSteps?: StreamToolStep[];
  preferExpanded?: boolean;
};

function panel(props: PanelProps) {
  return (
    <I18nProvider>
      <OperatorThinkingPanel startedAt={null} {...props} />
    </I18nProvider>
  );
}

describe("OperatorThinkingPanel", () => {
  it("never exposes raw reasoning and preserves a manual collapse for the active turn", () => {
    const steps: StreamToolStep[] = [
      { id: "inventory", name: "inventory.list", status: "done", preview: "15 playbooks" },
    ];
    const { rerender } = render(
      panel({
        phase: "thinking",
        reasoningText: "PRIVATE_CHAIN first secret",
        hasReasoningStream: true,
        toolSteps: steps,
        preferExpanded: true,
      }),
    );

    const toggle = screen.getByRole("button", { name: /Проверяет данные/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("inventory.list")).toBeInTheDocument();
    expect(screen.queryByText(/PRIVATE_CHAIN|first secret/)).not.toBeInTheDocument();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("inventory.list")).not.toBeInTheDocument();

    rerender(
      panel({
        phase: "thinking",
        reasoningText: "PRIVATE_CHAIN next token",
        hasReasoningStream: true,
        toolSteps: steps,
        preferExpanded: true,
      }),
    );

    expect(screen.getByRole("button", { name: /Проверяет данные/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByText(/PRIVATE_CHAIN|next token/)).not.toBeInTheDocument();
  });

  it("auto-expands failures and redacts secrets from the brief tool preview", () => {
    render(
      panel({
        phase: "tools",
        toolSteps: [
          {
            id: "deploy",
            name: "deploy.check",
            status: "error",
            preview: "password=super-secret\nconnection failed",
          },
        ],
      }),
    );

    expect(screen.getByRole("button", { name: /Выполняет/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByText("Один из шагов завершился с ошибкой")).toBeInTheDocument();
    expect(screen.getByText(/password=••• connection failed/)).toBeInTheDocument();
    expect(screen.queryByText(/super-secret/)).not.toBeInTheDocument();
  });

  it("shows a stable elapsed time for completed tool steps", () => {
    render(
      panel({
        phase: "tools",
        preferExpanded: true,
        toolSteps: [
          {
            id: "inventory",
            name: "inventory.list",
            status: "done",
            startedAt: 1_000,
            completedAt: 3_500,
          },
        ],
      }),
    );

    expect(screen.getByText("2s")).toBeInTheDocument();
  });

  it("auto-expands confirmation requests without printing the backend status verbatim", () => {
    render(
      panel({
        phase: "thinking",
        statusMessage: "Awaiting confirmation for UNSAFE_INTERNAL_COMMAND",
      }),
    );

    expect(screen.getByRole("button", { name: /Анализирует/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByText("Требуется подтверждение для продолжения")).toBeInTheDocument();
    expect(screen.queryByText(/UNSAFE_INTERNAL_COMMAND/)).not.toBeInTheDocument();
  });

  it("quietly collapses completed details when answer streaming begins", () => {
    const steps: StreamToolStep[] = [
      { id: "health", name: "health.check", status: "done", preview: "healthy" },
    ];
    const { rerender } = render(
      panel({ phase: "thinking", toolSteps: steps, preferExpanded: true }),
    );
    expect(screen.getByRole("button", { name: /Проверяет данные/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    rerender(panel({ phase: "streaming", toolSteps: steps, preferExpanded: true }));
    expect(screen.getByRole("button", { name: /Формирует ответ/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByText("health.check")).not.toBeInTheDocument();
  });

  it("uses the safe composing stage and disables continuous spinner motion for reduced motion", () => {
    const { container } = render(
      panel({
        phase: "streaming",
        statusMessage: "private backend streaming detail",
      }),
    );

    expect(screen.getByRole("status")).toHaveTextContent("Формирует ответ");
    expect(screen.queryByText(/private backend streaming detail/)).not.toBeInTheDocument();
    expect(container.querySelector("svg")).not.toHaveClass("animate-spin");
  });
});
