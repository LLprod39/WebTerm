import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, Link, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, request } from "@/api/client";
import { serverWorkspaceApi } from "@/api/server-workspace";
import type { ServerDetail } from "@/api/infrastructure";
import { TerminalFileEditor } from "@/features/infrastructure/TerminalFileEditor";
import { ServerFiles } from "@/features/infrastructure/ServerFiles";

vi.mock("@/api/client", () => ({ api: { post: vi.fn() }, request: vi.fn() }));
vi.mock("@/api/server-workspace", () => ({
  serverWorkspaceApi: { files: vi.fn(), read: vi.fn(), write: vi.fn() },
}));
const server = {
  id: 91,
  capabilities: { read_files: true, write_files: true },
} as unknown as ServerDetail;
const file = {
  name: "app.conf",
  path: "/tmp/app.conf",
  is_dir: false,
  size: 3,
  modified_at: 1,
  permissions: "rw-r--r--",
};
function client() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}
function deferred() {
  let resolve!: (value: unknown) => void;
  const promise = new Promise<unknown>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("remote editor save consistency", () => {
  afterEach(cleanup);
  beforeEach(() => {
    vi.mocked(request).mockResolvedValue({
      file: { path: file.path, content: "original" },
    });
  });
  it("marks only the submitted terminal file version as saved", async () => {
    const pending = deferred();
    vi.mocked(api.post).mockReturnValue(pending.promise);
    const close = vi.fn();
    render(
      <QueryClientProvider client={client()}>
        <TerminalFileEditor
          server={server}
          path={file.path}
          elevate={false}
          onClose={close}
        />
      </QueryClientProvider>,
    );
    const editor = await screen.findByLabelText("Содержимое удалённого файла");
    fireEvent.change(editor, { target: { value: "submitted" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить файл" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/servers/api/91/files/write/",
        expect.objectContaining({ content: "submitted" }),
      ),
    );
    fireEvent.change(editor, { target: { value: "newer draft" } });
    await act(async () => pending.resolve({ success: true }));
    await screen.findByText("Есть несохранённые изменения");
    expect(editor).toHaveValue("newer draft");
    expect(
      screen.getByRole("button", { name: "Сохранить файл" }),
    ).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(
      await screen.findByRole("dialog", { name: "Закрыть без сохранения?" }),
    ).toBeVisible();
    expect(close).not.toHaveBeenCalled();
  });
  it("keeps file browser changes dirty after a save and guards SPA navigation", async () => {
    const pending = deferred();
    vi.mocked(serverWorkspaceApi.files).mockResolvedValue({
      path: "/tmp",
      parent_path: "/",
      entries: [file],
    } as never);
    vi.mocked(serverWorkspaceApi.read).mockResolvedValue({
      file: {
        path: file.path,
        content: "original",
        size: 8,
        encoding: "utf-8",
      },
    });
    vi.mocked(serverWorkspaceApi.write).mockReturnValue(
      pending.promise as ReturnType<typeof serverWorkspaceApi.write>,
    );
    const router = createMemoryRouter([
      {
        path: "/",
        element: (
          <>
            <Link to="/away">Away</Link>
            <ServerFiles server={server} />
          </>
        ),
      },
      { path: "/away", element: <h1>Away page</h1> },
    ]);
    render(
      <QueryClientProvider client={client()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "app.conf" }));
    const editor = await screen.findByLabelText("Содержимое файла");
    fireEvent.change(editor, { target: { value: "submitted" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(serverWorkspaceApi.write).toHaveBeenCalledWith(
        91,
        file.path,
        "submitted",
      ),
    );
    fireEvent.change(editor, { target: { value: "newer draft" } });
    await act(async () => pending.resolve({ file: { content: "submitted" } }));
    await screen.findByText("Есть несохранённые изменения");
    expect(editor).toHaveValue("newer draft");
    await act(async () => {
      await router.navigate("/away");
    });
    expect(
      await screen.findByRole("dialog", {
        name: "Выйти без сохранения файла?",
      }),
    ).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "Away page" }),
    ).not.toBeInTheDocument();
  });
});
