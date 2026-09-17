import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import {
  createChatOperatorHandlers,
  type ChatOperatorHandlerCtx,
} from "./chatPageOperatorHandlers";

function setupHandlers(pendingUserText: string | null = "Привет") {
  const setPendingUserText = vi.fn();
  const refreshChat = vi.fn(async () => {});
  const refreshTerminalChat = vi.fn(async () => {});
  const handlers = createChatOperatorHandlers({
    activeChatId: 7,
    lang: "ru",
    toast: vi.fn(),
    queryClient: new QueryClient(),
    messages: [],
    pendingUserText,
    setPendingUserText,
    setStreamHold: vi.fn(),
    setPendingSend: vi.fn(),
    setActionWorkingId: vi.fn(),
    openSessionDock: vi.fn(),
    pushSessionLine: vi.fn(),
    refreshChat,
    refreshTerminalChat,
  } as unknown as ChatOperatorHandlerCtx);
  return { handlers, refreshChat, refreshTerminalChat, setPendingUserText };
}

describe("chat operator optimistic handoff", () => {
  it("keeps the optimistic user row through completion, confirmation, and provider error", () => {
    const { handlers, refreshChat, refreshTerminalChat, setPendingUserText } = setupHandlers();

    handlers.onTurnComplete({ status: "completed" });
    handlers.onConfirmRequired({ id: 42 });
    handlers.onError("Provider unavailable");

    expect(refreshChat).toHaveBeenCalledTimes(1);
    expect(refreshTerminalChat).toHaveBeenCalledTimes(2);
    expect(setPendingUserText).not.toHaveBeenCalled();
  });

  it("sanitizes backend-only context before restoring snapshot user text", () => {
    const { handlers, setPendingUserText } = setupHandlers(null);

    handlers.onSnapshot({
      busy: true,
      userText: "Привет\n\nКонтекст серверов: @prod-api (ids: 1).",
    });

    expect(setPendingUserText).toHaveBeenCalledWith("Привет");
    expect(setPendingUserText).not.toHaveBeenCalledWith(expect.stringContaining("Контекст серверов"));
  });
});
