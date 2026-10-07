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

function completedAction(): AssistantAction {
  return {
    ...dangerousAction(),
    id: 43,
    title: "Run command",
    status: "completed",
    risk: "read",
    requires_confirmation: false,
    blast_radius: { server_ids: [1], server_names: ["nikitavm"], count: 1 },
    dry_run_preview: { command: "journalctl -p err -n 50 --no-pager" },
    result: { output: "-- No entries --" },
  };
}


describe("ActionCard", () => {
  it("keeps confirm controls inline and hides full where/command sections", () => {
    const onConfirm = vi.fn();
    const onOpenDetails = vi.fn();
    render(
      <ActionCard
        action={dangerousAction()}
        isWorking={false}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
        onOpenDetails={onOpenDetails}
      />,
    );

    expect(screen.getByText(/Затронет|Targets/i)).toBeInTheDocument();
    expect(screen.getByText(/web-01, web-02/)).toBeInTheDocument();
    expect(screen.getByText(/Run uptime on the selected servers/i)).toBeInTheDocument();
    expect(screen.queryByText(/Что произойдёт|What will happen/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Где|Where/i)).not.toBeInTheDocument();
    expect(screen.getByText(/runtime/i)).toBeInTheDocument();
    expect(screen.getByText(/\$ uptime/)).toBeInTheDocument();
    expect(screen.queryByRole("presentation")).not.toBeInTheDocument();

    const confirm = screen.getByRole("button", { name: /подтвердить|confirm/i });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByRole("textbox", { name: /подтверждение|confirmation/i }), {
      target: { value: "FANOUT" },
    });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith(42, "FANOUT");

    fireEvent.click(screen.getByRole("button", { name: /детали|details/i }));
    expect(onOpenDetails).toHaveBeenCalledWith(expect.objectContaining({ id: 42 }));
  });

  it("renders a compact completed chip without result body", () => {
    const onOpenDetails = vi.fn();
    render(
      <ActionCard
        action={completedAction()}
        isWorking={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        onOpenDetails={onOpenDetails}
      />,
    );

    expect(screen.getByText("Run command")).toBeInTheDocument();
    expect(screen.getByText(/Готово|Done/i)).toBeInTheDocument();
    expect(screen.queryByText(/Результат|Result/i)).not.toBeInTheDocument();
    expect(screen.queryByText("-- No entries --")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /детали|details/i }));
    expect(onOpenDetails).toHaveBeenCalled();
  });
});

describe("MetricSeriesReportCard", () => {
  it("renders a compact report with chart semantics and summary", () => {
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
    expect(report).toHaveClass("w-full", "max-w-[420px]");
    expect(report).not.toHaveClass("min-h-[190px]");
    expect(screen.getByText("31%")).toBeInTheDocument();
    expect(screen.getByText(/Рост на 13%|Up 13%/i)).toBeInTheDocument();
  });

  it("hides the sparkline when the series is flat", () => {
    const { container } = render(
      <MetricSeriesReportCard
        chart={{
          title: "disk_percent",
          series: [5, 5, 5, 5],
          unit: "%",
        }}
      />,
    );
    expect(screen.getByText("5.0%")).toBeInTheDocument();
    expect(container.querySelector("svg")).toBeNull();
  });
});

describe("MessageBubble evidence fold", () => {
  it("collapses stacked metrics/chart/alerts behind a disclosure", () => {
    render(
      <MessageBubble
        message={{
          id: 92,
          role: "assistant",
          content: "Сводка по серверу.",
          created_at: "2026-08-25T12:00:00Z",
          metadata: {
            metrics: {
              name: "nikitavm",
              status: "healthy",
              cpu_percent: 7,
              mem_percent: 19,
            },
            chart: { title: "disk", series: [5, 5, 5], unit: "%" },
            tables: [
              {
                title: "Алерты",
                kind: "alerts",
                items: Array.from({ length: 5 }, (_, i) => ({
                  id: i + 1,
                  title: "Server unreachable",
                  server_name: "nikitavm",
                  severity: "critical",
                })),
              },
            ],
          },
        }}
        actionWorkingId={null}
        onConfirmAction={vi.fn()}
        onCancelAction={vi.fn()}
      />,
    );

    expect(screen.getByText(/Данные ответа|Reply data/i)).toBeInTheDocument();
    expect(screen.queryByText("nikitavm")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Данные ответа|Reply data/i }));
    expect(screen.getByText("nikitavm")).toBeInTheDocument();
    expect(screen.getByText(/×5/)).toBeInTheDocument();
  });

  it("folds a single metrics block when the message also has actions", () => {
    render(
      <MessageBubble
        message={{
          id: 93,
          role: "assistant",
          content: "Проверил логи.",
          created_at: "2026-08-25T12:00:00Z",
          metadata: {
            metrics: {
              name: "nikitavm",
              status: "healthy",
              cpu_percent: 2.7,
              mem_percent: 19,
            },
            actions: [completedAction()],
          },
        }}
        actionWorkingId={null}
        onConfirmAction={vi.fn()}
        onCancelAction={vi.fn()}
        onOpenActionDetails={vi.fn()}
      />,
    );

    expect(screen.getByText(/Данные ответа|Reply data/i)).toBeInTheDocument();
    expect(screen.queryByText("2.7%")).not.toBeInTheDocument();
    expect(screen.getByText("Run command")).toBeInTheDocument();
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
    // BoardUI Table (react-aria) exposes role="grid".
    expect(screen.getAllByRole("grid")).toHaveLength(1);
  });
});
