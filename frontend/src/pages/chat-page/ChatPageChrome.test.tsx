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
    pinnedPlaybook: null,
    setPinnedPlaybook: vi.fn(),
    playbookOptions: [],
    unpinServer: vi.fn(),
    unpinUser: vi.fn(),
    pinServer: vi.fn(),
    paletteRef: createRef<ComposePaletteHandle>(),
    textareaRef: createRef<HTMLTextAreaElement>(),
    isBusy: false,
    handleStop: vi.fn(),
    submitMessage: vi.fn(),
    providerOptions: [],
    providerOverride: "",
    setProviderOverride: vi.fn(),
    ...overrides,
  } as unknown as ChatPageController;
}

describe("chat page chrome", () => {
  it("makes server context and the external file/project flow explicit", () => {
    const setDraft = vi.fn();
    const setCaret = vi.fn();
    const setPaletteOpen = vi.fn();

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ChatComposerForm c={composerController({ setDraft, setCaret, setPaletteOpen })} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Выбрать сервер для контекста" }));
    expect(setDraft).toHaveBeenCalledWith("Проверь @");
    expect(setCaret).toHaveBeenCalledWith(9);
    expect(setPaletteOpen).toHaveBeenCalledWith(true);
    expect(screen.getByRole("link", { name: "Файл / проект" })).toHaveAttribute("href", "/automation");
    expect(screen.queryByText("Модель")).not.toBeInTheDocument();
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

  it("shows the selected playbook as explicit chat context", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ChatComposerForm
            c={composerController({
              pinnedPlaybook: { id: 17, name: "Base Linux server configuration and hardening", kind: "ansible" },
              playbookOptions: [{ id: 17, name: "Base Linux server configuration and hardening", kind: "ansible" }],
            })}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("combobox", { name: "Выбрать playbook для контекста" })).toBeInTheDocument();
    expect(screen.getAllByText(/Base Linux server configuration and hardening/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Убрать playbook из контекста" })).toBeInTheDocument();
  });
});
