import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ChatThreadSidebar } from "./ChatThreadSidebar";
import type { ChatPageController } from "./useChatPageController";

function sidebarController(overrides: Partial<ChatPageController> = {}): ChatPageController {
  const chat = {
    id: 17,
    title: "Очень длинный заголовок чата который должен обрезаться",
    kind: "chat" as const,
    created_at: "2026-08-20T10:00:00Z",
    updated_at: "2026-08-20T11:00:00Z",
  };
  return {
    lang: "ru",
    setSearchParams: vi.fn(),
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
    activeChat: chat,
    ...overrides,
  } as unknown as ChatPageController;
}

describe("ChatThreadSidebar", () => {
  it("uses Chat chrome without automations/settings and a single search field", () => {
    render(
      <MemoryRouter>
        <ChatThreadSidebar c={sidebarController()} />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("chat-thread-sidebar")).toHaveAttribute("data-chat-sidebar", "expanded");
    expect(screen.getByRole("heading", { name: "Чат" })).toBeInTheDocument();
    expect(screen.queryByText("Агент")).not.toBeInTheDocument();
    expect(screen.queryByText("Автоматизации")).not.toBeInTheDocument();
    expect(screen.queryByText("Настроить")).not.toBeInTheDocument();
    expect(screen.getAllByPlaceholderText("Поиск…")).toHaveLength(1);
    expect(screen.getByTitle("Очень длинный заголовок чата который должен обрезаться")).toBeInTheDocument();
    expect(document.querySelector("svg.absolute")).toBeNull();
  });

  it("renders a flush collapsed rail with new-chat control", () => {
    render(
      <MemoryRouter>
        <ChatThreadSidebar c={sidebarController()} collapsed onExpand={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("chat-thread-sidebar")).toHaveAttribute("data-chat-sidebar", "collapsed");
    expect(screen.getByRole("button", { name: "Новый чат" })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Поиск…")).not.toBeInTheDocument();
  });
});
