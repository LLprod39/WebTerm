import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createAssistantChat,
  updateAssistantChat,
  type AssistantActiveTurn,
  type AssistantChatMessage,
  type AssistantChatSession,
} from "@/api";

import { useChatPageMutations } from "./useChatPageMutations";

vi.mock("@/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api")>();
  return { ...actual, createAssistantChat: vi.fn(), updateAssistantChat: vi.fn() };
});

const session = (overrides: Partial<AssistantChatSession> = {}): AssistantChatSession => ({
  id: 7,
  title: "Новый чат",
  created_at: "2026-08-25T10:00:00Z",
  updated_at: "2026-08-25T10:00:00Z",
  messages: [],
  active_turn: null,
  ...overrides,
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe("useChatPageMutations", () => {
  beforeEach(() => vi.clearAllMocks());

  it("releases the first-message optimistic state when chat creation is rejected", async () => {
    vi.mocked(createAssistantChat).mockRejectedValueOnce(new Error("Session unavailable"));
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    });
    const setDraft = vi.fn();
    const setPendingSend = vi.fn();
    const setPendingUserText = vi.fn();
    const toast = vi.fn();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(
      () =>
        useChatPageMutations({
          activeChatId: null,
          lang: "ru",
          toast,
          queryClient,
          setSearchParams: vi.fn(),
          setDraft,
          pendingUserText: "Первое сообщение",
          setPendingUserText,
          setPendingSend,
          promoteNewPendingChat: vi.fn(),
          setActionWorkingId: vi.fn(),
          setRenamingChatId: vi.fn(),
          pinnedServers: [],
          pinnedUsers: [],
          pinnedPlaybook: null,
        }),
      { wrapper },
    );

    act(() => result.current.createChatMutation.mutate());
    await waitFor(() => expect(result.current.createChatMutation.isError).toBe(true));

    expect(setPendingSend).toHaveBeenCalledWith(null);
    expect(setPendingUserText).toHaveBeenCalledWith(null);
    expect(setDraft).toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Чат не создан", variant: "destructive" }),
    );
  });

  it("keeps messages and the active turn that arrive while initial pins are saved", async () => {
    const pinUpdate = deferred<AssistantChatSession>();
    const created = session();
    vi.mocked(createAssistantChat).mockResolvedValueOnce(created);
    vi.mocked(updateAssistantChat).mockReturnValueOnce(pinUpdate.promise);
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(
      () =>
        useChatPageMutations({
          activeChatId: null,
          lang: "ru",
          toast: vi.fn(),
          queryClient,
          setSearchParams: vi.fn(),
          setDraft: vi.fn(),
          pendingUserText: "Первое сообщение",
          setPendingUserText: vi.fn(),
          setPendingSend: vi.fn(),
          promoteNewPendingChat: vi.fn(),
          setActionWorkingId: vi.fn(),
          setRenamingChatId: vi.fn(),
          pinnedServers: [{ id: 3, name: "prod", host: "10.0.0.3" }],
          pinnedUsers: [],
          pinnedPlaybook: null,
        }),
      { wrapper },
    );

    act(() => result.current.createChatMutation.mutate());
    await waitFor(() => expect(updateAssistantChat).toHaveBeenCalledTimes(1));

    const message: AssistantChatMessage = {
      id: 81,
      role: "user",
      content: "Первое сообщение",
      metadata: {},
      created_at: "2026-08-25T10:00:01Z",
    };
    const activeTurn: AssistantActiveTurn = {
      turn_id: 92,
      status: "running",
      busy: true,
      assistant_text: "Проверяю",
    };
    queryClient.setQueryData(
      ["assistant", "chat", created.id],
      session({ messages: [message], active_turn: activeTurn }),
    );

    await act(async () => {
      pinUpdate.resolve(session({ pinned_context: { servers: [{ id: 3, name: "prod" }] } }));
      await pinUpdate.promise;
    });
    await waitFor(() => {
      const cached = queryClient.getQueryData<AssistantChatSession>([
        "assistant",
        "chat",
        created.id,
      ]);
      expect(cached?.messages).toEqual([message]);
      expect(cached?.active_turn).toEqual(activeTurn);
      expect(cached?.pinned_context).toEqual({ servers: [{ id: 3, name: "prod" }] });
    });
  });
});
