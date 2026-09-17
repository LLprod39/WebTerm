import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AssistantAction } from "@/api";

import { ActionCard, MessageBubble, MetricSeriesReportCard } from "./ChatMessageViews";


function dangerousAction(): AssistantAction {
  return {
    id: 42,
    chat_id: 1,
    message_id: 2,
    action_type: "operator.run_fanout",
    title: "Fan-out command",
    description: "Run uptime on the selected servers.",
    status: "requires_confirmation",
    risk: "mutating",
    required_feature: "servers",
    requires_confirmation: true,
    input: { command: "uptime", server_ids: [1, 2] },
    result: {},
    error: "",
    target_url: "",
    blast_radius: {
      server_ids: [1, 2],
      server_names: ["web-01", "web-02"],
      count: 2,
      typed_confirm_required: true,
      typed_confirm_token: "FANOUT",
      typed_confirm_hint: "Type FANOUT",
    },
    dry_run_preview: { command: "uptime" },
    undo_payload: {},
    async_run_ref: {},
    created_at: "2026-07-21T00:00:00Z",
    updated_at: "2026-07-21T00:00:00Z",
    confirmed_at: null,
    completed_at: null,
  };
}


describe("ActionCard", () => {
  it("requires the exact typed token and shows the frozen blast radius", () => {
    const onConfirm = vi.fn();
    render(
      <ActionCard
        action={dangerousAction()}
        isWorking={false}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getAllByText(/web-01, web-02/)).toHaveLength(2);
    expect(screen.getByText(/Что произойдёт|What will happen/i)).toBeInTheDocument();
    expect(screen.getByText(/Где|Where/i)).toBeInTheDocument();
    expect(screen.getByText(/runtime/i)).toBeInTheDocument();
    expect(screen.getByText("$ uptime")).toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: /подтвердить|confirm/i });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByRole("textbox", { name: /подтверждение|confirmation/i }), {
      target: { value: "FANOUT" },
    });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith(42, "FANOUT");
  });
});

describe("MetricSeriesReportCard", () => {
  it("renders a responsive, stable report card with chart semantics and summary", () => {
    render(
      <MetricSeriesReportCard
        chart={{
          title: "CPU web-01",
          series: [18, 21, 26, 31],
          unit: "%",
        }}
      />,
    );

    const report = screen.getByTestId("metric-series-report");
    expect(report).toHaveAttribute("role", "img");
    expect(report).toHaveAttribute("aria-label", expect.stringMatching(/CPU web-01/i));
    expect(report).toHaveClass("w-full", "max-w-[640px]", "min-h-[190px]", "sm:min-h-[220px]");
    expect(screen.getByText("31%")).toBeInTheDocument();
    expect(screen.getByText(/Рост на 13%|Up 13%/i)).toBeInTheDocument();
  });
});

describe("MessageBubble structured evidence", () => {
  it("renders one readable durable playbook table instead of a duplicate markdown table", () => {
    render(
      <MessageBubble
        message={{
          id: 91,
          role: "assistant",
          content: "Доступно 2 playbook/runbook; полный каталог приведён в таблице.",
          created_at: "2026-08-25T12:00:00Z",
          metadata: {
            tables: [
              {
                title: "Playbook / runbook · 2",
                kind: "playbooks",
                headers: ["Playbook / runbook", "Назначение и последний запуск"],
                rows: [
                  ["Base Linux hardening", "Базовая защита Linux · последний запуск: completed"],
                  ["Docker prune (safe)", "Безопасная очистка Docker · последний запуск: failed"],
                ],
              },
            ],
          },
        }}
        actionWorkingId={null}
        onConfirmAction={vi.fn()}
        onCancelAction={vi.fn()}
      />,
    );

    expect(screen.getAllByText("Playbook / runbook · 2")).toHaveLength(1);
    expect(screen.getByText("Base Linux hardening")).toBeInTheDocument();
    expect(screen.getByText(/Базовая защита Linux/)).toBeInTheDocument();
    expect(screen.getAllByRole("table")).toHaveLength(1);
  });
});
