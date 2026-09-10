import { afterEach, describe, it, expect, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataTable, ConfirmDialog } from "@/components/ui";
afterEach(cleanup);
describe("data views and confirmation", () => {
  it("filters, sorts and paginates actual rows without losing results", async () => {
    const user = userEvent.setup();
    render(
      <DataTable
        rows={Array.from({ length: 18 }, (_, id) => ({
          id,
          name: `server-${String(id).padStart(2, "0")}`,
        }))}
        rowKey={(r) => r.id}
        searchValue={(r) => r.name}
        pageSize={5}
        columns={[
          {
            key: "name",
            label: "Сервер",
            sortValue: (r) => r.name,
            render: (r) => r.name,
          },
        ]}
      />,
    );
    expect(screen.getByText("1–5 из 18")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Следующая страница" }),
    );
    expect(screen.getByText("6–10 из 18")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox"), "server-17");
    expect(screen.getByText("server-17")).toBeInTheDocument();
    expect(screen.getByText("1–1 из 1")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Следующая страница" }),
    ).toBeDisabled();
  });
  it("requires the exact target before a destructive operation", async () => {
    const user = userEvent.setup();
    const confirm = vi.fn();
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Удалить сервер?"
        description="Запись будет удалена"
        typedText="production-01"
        onConfirm={confirm}
      />,
    );
    const button = screen.getByRole("button", { name: "Подтвердить" });
    expect(button).toBeDisabled();
    await user.type(screen.getByRole("textbox"), "production-02");
    expect(button).toBeDisabled();
    await user.clear(screen.getByRole("textbox"));
    await user.type(screen.getByRole("textbox"), "production-01");
    await user.click(button);
    expect(confirm).toHaveBeenCalledTimes(1);
  });
});
