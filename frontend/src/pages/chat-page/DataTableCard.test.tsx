import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTableCard } from "./DataTableCard";

describe("DataTableCard", () => {
  it("renders BoardUI table with headers and cells", () => {
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

    const table = container.querySelector("table.bui-table");
    expect(table).toBeTruthy();
    expect(table).toHaveClass("bui-table-sm");
    expect(screen.getByText("Область")).toBeInTheDocument();
    expect(screen.getByText(/Проверить конкретный хост/)).toBeInTheDocument();
    expect(container.firstElementChild).toHaveClass("rounded-2xl");
  });

  it("keeps dense inventory columns in BoardUI table", () => {
    const { container } = render(
      <DataTableCard
        table={{
          title: "Servers",
          headers: ["ID", "Name", "Host", "Port"],
          rows: [[1, "api-prod", "10.0.0.1", 22]],
        }}
      />,
    );

    expect(screen.getByText("Servers")).toBeInTheDocument();
    expect(screen.getByText("api-prod")).toBeInTheDocument();
    expect(container.querySelector("table")).toHaveClass("bui-table", "bui-table-sm");
    expect(container.querySelector("table")?.parentElement).toHaveClass("overflow-x-auto");
  });
});
