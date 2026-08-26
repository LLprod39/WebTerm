import { createRef } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ChatComposerForm } from "./ChatComposerForm";
import type { ComposePaletteHandle } from "./ComposeCommandPalette";
import { ChatThreadSidebar } from "./ChatThreadSidebar";
import type { ChatPageController } from "./useChatPageController";

function composerController(overrides: Partial<ChatPageController> = {}): ChatPageController {
  return {
    lang: "ru",
    draft: "Проверь",
    setDraft: vi.fn(),
    caret: 7,
    setCaret: vi.fn(),
    paletteOpen: false,
    setPaletteOpen: vi.fn(),
    pinnedServers: [],
    pinnedUsers: [],
    unpinServer: vi.fn(),
    unpinUser: vi.fn(),
    pinServer: vi.fn(),
    paletteRef: createRef<ComposePaletteHandle>(),
    textareaRef: createRef<HTMLTextAreaElement>(),
    isBusy: false,
    handleStop: vi.fn(),
    submitMessage: vi.fn(),
    ...overrides,
  } as unknown as ChatPageController;
}

describe("chat page chrome", () => {
  it("keeps the composer minimal and points exact server selection to @", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ChatComposerForm c={composerController()} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByPlaceholderText("Что нужно сделать? Для точного сервера введите @")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Файл / проект" })).toHaveAttribute("href", "/automation");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByText("Без playbook")).not.toBeInTheDocument();
    expect(screen.queryByText("Модель")).not.toBeInTheDocument();
    expect(screen.getByText(/@ — точный сервер/)).toBeInTheDocument();
  });

  it("renders chat history as a usable mobile panel and closes it after navigation", () => {
    const setSearchParams = vi.fn();
    const onNavigate = vi.fn();
    const chat = {
      id: 17,
      title: "Проверка production",
      kind: "chat",
      created_at: "2026-08-20T10:00:00Z",
      updated_at: "2026-08-20T10:00:00Z",
    };
    const controller = {
      lang: "ru",
      toast: vi.fn(),
      queryClient: { invalidateQueries: vi.fn() },
      setSearchParams,
      chatFilter: "",
      setChatFilter: vi.fn(),
      chatsQuery: { isLoading: false },
      chats: [chat],
      filteredChats: [chat],
      chatGroups: [{ id: "today", labelRu: "Сегодня", labelEn: "Today", chats: [chat] }],
      activeChatId: 17,
      renamingChatId: null,
      setRenamingChatId: vi.fn(),
      renameDraft: "",
      setRenameDraft: vi.fn(),
      commitRename: vi.fn(),
      startRename: vi.fn(),
      deleteChatMutation: { mutate: vi.fn() },
      clearLastChatAndNew: vi.fn(),
    } as unknown as ChatPageController;

    render(
      <MemoryRouter>
        <ChatThreadSidebar c={controller} mobile onNavigate={onNavigate} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Проверка production/ }));
    expect(setSearchParams).toHaveBeenCalledWith({ chat: "17" });
    expect(onNavigate).toHaveBeenCalledOnce();
  });

  it("shows only an exact server selected through @", () => {
    const unpinServer = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ChatComposerForm
            c={composerController({
              pinnedServers: [{ id: 17, name: "prod-api-01", host: "10.0.0.17" }],
              unpinServer,
            })}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("prod-api-01")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Открепить" }));
    expect(unpinServer).toHaveBeenCalledWith(17);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});
