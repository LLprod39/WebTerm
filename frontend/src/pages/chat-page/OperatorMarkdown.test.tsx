import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OperatorMarkdown } from "./OperatorMarkdown";

function cursors(container: HTMLElement) {
  return container.querySelectorAll("[data-operator-stream-cursor]");
}

describe("OperatorMarkdown", () => {
  it("renders exactly one zero-width CSS cursor inside the final text block", () => {
    const { container, rerender } = render(
      <OperatorMarkdown content="Проверяю доступные playbook" streaming />,
    );

    expect(cursors(container)).toHaveLength(1);
    expect(cursors(container)[0]).toHaveClass("w-0", "motion-safe:animate-pulse");
    expect(cursors(container)[0]).not.toHaveClass("ml-0.5");
    expect(cursors(container)[0].closest("p")).not.toBeNull();
    expect(container.textContent).not.toContain("\uE000");

    rerender(<OperatorMarkdown content="Проверяю доступные playbook и runbook" streaming />);
    expect(cursors(container)).toHaveLength(1);
    expect(screen.getByText(/playbook и runbook/)).toBeInTheDocument();
  });

  it("keeps one cursor for an empty stream and removes it after streaming finishes", () => {
    const { container, rerender } = render(<OperatorMarkdown content="" streaming />);
    expect(cursors(container)).toHaveLength(1);

    rerender(<OperatorMarkdown content="" streaming={false} />);
    expect(cursors(container)).toHaveLength(0);
  });

  it.each([
    ["GFM list", "- health check\n- nginx reload", "ul"],
    ["GFM table", "| host | ok |\n| --- | --- |\n| web-01 | true |", "table"],
    ["fenced code", "```bash\nsystemctl status nginx\n```", "pre"],
    ["external link", "[Документация](https://example.com/runbook)", "a"],
  ])("preserves %s while attaching a single cursor", (_name, content, semanticSelector) => {
    const { container } = render(<OperatorMarkdown content={content} streaming />);

    expect(container.querySelector(semanticSelector)).not.toBeNull();
    expect(cursors(container)).toHaveLength(1);
    expect(container.textContent).not.toContain("\uE000");
  });

  it("renders wide description tables as fixed, wrapping content without horizontal scrolling", () => {
    const markdown = [
      "| Playbook | Описание |",
      "| --- | --- |",
      "| health-check-production | Очень длинное описание проверки инфраструктуры с дополнительными параметрами и рекомендациями по восстановлению сервиса |",
    ].join("\n");
    const { container } = render(<OperatorMarkdown content={markdown} />);

    const wrapper = container.querySelector("[data-operator-table]");
    const table = wrapper?.querySelector("table");
    const firstHeader = screen.getByText("Playbook").closest("th");
    const description = screen.getByText(/Очень длинное описание/).closest("td");

    expect(wrapper).toHaveClass("w-full", "min-w-0", "overflow-hidden");
    expect(wrapper?.querySelector(".overflow-x-auto")).toBeNull();
    expect(table).toHaveClass("w-full", "min-w-0", "table-fixed");
    expect(table).not.toHaveClass("min-w-[360px]");
    expect(firstHeader).toHaveClass("first:w-[40%]", "sm:first:w-[26%]", "whitespace-normal");
    expect(description).toHaveClass("break-words", "[overflow-wrap:anywhere]", "whitespace-normal");
  });

  it("uses comfortable 14px prose and list rhythm", () => {
    render(
      <OperatorMarkdown content={"Основной абзац с объяснением.\n\n- Первый пункт\n- Второй пункт"} />,
    );

    expect(screen.getByText("Основной абзац с объяснением.").closest("p")).toHaveClass(
      "text-[14px]",
      "leading-6",
    );
    expect(screen.getByText("Первый пункт").closest("li")).toHaveClass(
      "text-[14px]",
      "leading-6",
    );
    expect(screen.getByRole("list")).toHaveClass("space-y-1.5", "pl-5");
  });

  it("does not render a cursor for a completed markdown response", () => {
    const { container } = render(
      <OperatorMarkdown content="Ответ **готов** и больше не печатается." streaming={false} />,
    );

    expect(screen.getByText("готов")).toBeInTheDocument();
    expect(cursors(container)).toHaveLength(0);
  });

  it("does not leave a standalone cursor when a live table is represented by a skeleton", () => {
    const { container } = render(
      <OperatorMarkdown
        content={"| host | ok |\n| --- | --- |\n| web-01 | true |"}
        streaming
        stripTables
      />,
    );

    expect(cursors(container)).toHaveLength(0);
    expect(container.querySelector(".operator-md")).toBeNull();
  });
});
