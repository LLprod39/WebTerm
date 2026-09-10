import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ActionCard } from "@/features/intelligence/Chat";
import { intelligenceApi, type ChatAction } from "@/api/intelligence";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const action: ChatAction = {
  id: 41,
  title: "Удалить временный каталог",
  description: "Команда выполнится на prod-01",
  status: "requires_confirmation",
  risk: "dangerous",
  action_type: "server.execute",
  input: { command: "rm -rf /tmp/build-cache", server_id: 7 },
  result: {},
  error: "",
  requires_confirmation: true,
  blast_radius: {
    typed_confirm_required: true,
    typed_confirm_token: "prod-01",
    server_names: ["prod-01"],
  },
  dry_run_preview: {},
  target_url: "",
};
const renderAction = (value = action, disabled = false) =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ActionCard action={value} disabled={disabled} onUpdate={() => {}} />
    </QueryClientProvider>,
  );
describe("Operator action approval boundaries", () => {
  it("does not execute on display and requires exact typed confirmation before a destructive action", async () => {
    const confirm = vi
      .spyOn(intelligenceApi, "chatAction")
      .mockResolvedValue({ ...action, status: "completed" });
    renderAction();
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Рассмотреть действие" }),
    );
    const submit = screen.getByRole("button", { name: "Подтвердить действие" });
    expect(submit).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText("Введите «prod-01» для подтверждения"),
      { target: { value: "prod-02" } },
    );
    expect(submit).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText("Введите «prod-01» для подтверждения"),
      { target: { value: "prod-01" } },
    );
    fireEvent.click(submit);
    await waitFor(() =>
      expect(confirm).toHaveBeenCalledExactlyOnceWith(41, "confirm", "prod-01"),
    );
  });
  it("keeps the review open and reports an authorization failure without assuming completion", async () => {
    vi.spyOn(intelligenceApi, "chatAction").mockRejectedValue(
      new Error("Недостаточно прав для действия"),
    );
    renderAction({ ...action, blast_radius: {} });
    fireEvent.click(
      screen.getByRole("button", { name: "Рассмотреть действие" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Подтвердить действие" }),
    );
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    await waitFor(() =>
      expect(
        screen.getAllByText("Недостаточно прав для действия").length,
      ).toBeGreaterThan(0),
    );
    expect(
      screen.getByRole("button", { name: "Подтвердить действие" }),
    ).toBeEnabled();
  });
  it("prevents confirmation while the current turn still owns execution", () => {
    const confirm = vi.spyOn(intelligenceApi, "chatAction");
    renderAction(action, true);
    expect(
      screen.getByRole("button", { name: "Рассмотреть действие" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Отклонить" })).toBeDisabled();
    expect(confirm).not.toHaveBeenCalled();
  });
  it("does not offer controls for a terminal action", () => {
    renderAction({ ...action, status: "completed" });
    expect(
      screen.queryByRole("button", { name: "Рассмотреть действие" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Отклонить" }),
    ).not.toBeInTheDocument();
  });
});
