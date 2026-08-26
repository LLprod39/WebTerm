import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTableCard } from "./DataTableCard";

describe("DataTableCard", () => {
  it("wraps a two-column prose table without a mobile horizontal scroller", () => {
    const { container } = render(
      <DataTableCard
        table={{
          headers: ["Область", "Что могу сделать"],
          rows: [
            [
              "Диагностика",
              "Проверить конкретный хост, собрать Linux-обзор и выполнить безопасные команды с подтверждением пользователя",
            ],
          ],
        }}
      />,
    );

    const wrapper = container.querySelector("table")?.parentElement;
    const table = container.querySelector("table");
    const firstHeader = screen.getByText("Область").closest("th");
    const description = screen.getByText(/Проверить конкретный хост/).closest("span");

    expect(wrapper).toHaveClass("min-w-0", "overflow-hidden");
    expect(wrapper).not.toHaveClass("overflow-x-auto");
    expect(table).toHaveClass("table-fixed", "min-w-0");
    expect(table).not.toHaveClass("min-w-[420px]");
    expect(firstHeader).toHaveClass("first:w-[40%]", "sm:first:w-[32%]", "whitespace-normal");
    expect(description).toHaveClass("break-words", "[overflow-wrap:anywhere]");
    expect(description).not.toHaveClass("truncate");
  });

  it("keeps dense horizontal mode for multi-column inventory", () => {
    const { container } = render(
      <DataTableCard
        table={{
          headers: ["ID", "Name", "Host", "Port"],
          rows: [[1, "api-prod", "10.0.0.1", 22]],
        }}
      />,
    );

    expect(container.querySelector("table")?.parentElement).toHaveClass("overflow-x-auto");
    expect(container.querySelector("table")).toHaveClass("min-w-[420px]");
  });
});
