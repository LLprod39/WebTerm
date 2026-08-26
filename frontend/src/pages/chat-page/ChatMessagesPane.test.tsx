import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { AssistantChatMessage } from "@/api";

import { ChatMessagesPane } from "./ChatMessagesPane";
import type { ChatPageController } from "./useChatPageController";

function controller(overrides: Partial<ChatPageController> = {}): ChatPageController {
  return {
    lang: "ru",
    selectedTitle: "Привет",
    activeChat: { id: 7, title: "Привет", created_at: "", updated_at: "", messages: [] },
    isBusy: false,
    operatorWs: {
      busy: false,
      phase: "idle",
      statusMessage: "",
      streamText: "",
      reasoningText: "",
      hasReasoningStream: false,
      thinkingStartedAt: null,
      thinkingIteration: null,
      toolSteps: [],
      livePlan: null,
      asyncTask: null,
      health: null,
    },
    sessionTokens: null,
    activePlan: null,
    tasksPanelOpen: false,
    setTasksPanelOpen: vi.fn(),
    clearLastChatAndNew: vi.fn(),
    scrollerRef: { current: null },
    handleScrollerScroll: vi.fn(),
    showEmptyStarter: false,
    dispatchMessage: vi.fn(),
    activeChatQuery: { isLoading: false },
    displayMessages: [],
    actionWorkingId: null,
    handleConfirm: vi.fn(),
    handleCancel: vi.fn(),
    handleUndo: vi.fn(),
    handleSaveRunbook: vi.fn(),
    handleRetry: vi.fn(),
    pinnedServers: [],
    pinServer: vi.fn(),
    unpinServer: vi.fn(),
    openSessionDock: vi.fn(),
    pendingUserText: null,
    pendingUserEpoch: 0,
    pendingUserBaselineIds: [],
    showLiveStream: false,
    streamInventoryKind: null,
    endRef: { current: null },
    atBottom: true,
    setAtBottom: vi.fn(),
    scrollToEnd: vi.fn(),
    ...overrides,
  } as unknown as ChatPageController;
}

function renderPane(c: ChatPageController) {
  return render(
    <MemoryRouter>
      <ChatMessagesPane c={c} />
    </MemoryRouter>,
  );
}

describe("ChatMessagesPane streaming presentation", () => {
  it("hands an optimistic user bubble to its persisted message without duplicating text", () => {
    const persisted: AssistantChatMessage = {
      id: 41,
      role: "user",
      content: "Привет\n\nКонтекст серверов: @prod-api (ids: 1).",
      metadata: {},
      created_at: "2026-08-25T12:00:00Z",
    };

    renderPane(
      controller({
        selectedTitle: "Чат",
        pendingUserText: "Привет",
        displayMessages: [persisted],
      }),
    );

    expect(screen.getAllByText("Привет")).toHaveLength(1);
    expect(screen.queryByText(/Контекст серверов/)).not.toBeInTheDocument();
  });

  it("keeps the optimistic wrapper mounted through REST handoff and gives the next send a new wrapper", () => {
    const first: AssistantChatMessage = {
      id: 41,
      role: "user",
      content: "Первый",
      metadata: {},
      created_at: "2026-08-25T12:00:00Z",
    };
    const view = renderPane(controller({ pendingUserText: "Первый" }));
    const optimisticWrapper = screen.getByText("Первый").closest(".group");

    view.rerender(
      <MemoryRouter>
        <ChatMessagesPane
          c={controller({ pendingUserText: "Первый", displayMessages: [first] })}
        />
      </MemoryRouter>,
    );
    expect(screen.getAllByText("Первый")).toHaveLength(1);

    view.rerender(
      <MemoryRouter>
        <ChatMessagesPane c={controller({ pendingUserText: null, displayMessages: [first] })} />
      </MemoryRouter>,
    );
    const persistedWrapper = screen.getByText("Первый").closest(".group")?.parentElement;
    expect(persistedWrapper).toBe(optimisticWrapper);

    view.rerender(
      <MemoryRouter>
        <ChatMessagesPane
          c={controller({ pendingUserText: "Второй", displayMessages: [first] })}
        />
      </MemoryRouter>,
    );
    const nextWrapper = screen.getByText("Второй").closest(".group");
    expect(nextWrapper).not.toBe(persistedWrapper);
    expect(screen.getAllByText("Первый")).toHaveLength(1);
    expect(screen.getAllByText("Второй")).toHaveLength(1);
  });

  it("gives an immediate retry its own wrapper even while the failed row is still pending", () => {
    const view = renderPane(controller({ pendingUserText: "Запрос A", pendingUserEpoch: 1 }));
    const failedWrapper = screen.getByText("Запрос A").closest(".group");

    view.rerender(
      <MemoryRouter>
        <ChatMessagesPane
          c={controller({ pendingUserText: "Запрос B", pendingUserEpoch: 2 })}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Запрос B").closest(".group")).not.toBe(failedWrapper);
  });

  it("does not hide or reuse the key of an older identical user prompt", () => {
    const oldPrompt: AssistantChatMessage = {
      id: 41,
      role: "user",
      content: "Привет",
      metadata: {},
      created_at: "2026-08-25T12:00:00Z",
    };
    const newPrompt: AssistantChatMessage = {
      ...oldPrompt,
      id: 42,
      created_at: "2026-08-25T12:05:00Z",
    };
    const view = renderPane(controller({ selectedTitle: "Чат", displayMessages: [oldPrompt] }));

    view.rerender(
      <MemoryRouter>
        <ChatMessagesPane
          c={controller({
            selectedTitle: "Чат",
            pendingUserText: "Привет",
            pendingUserBaselineIds: [oldPrompt.id],
            displayMessages: [oldPrompt],
          })}
        />
      </MemoryRouter>,
    );
    const optimisticWrapper = screen
      .getAllByText("Привет")
      .find((node) => node.closest(".group")?.textContent?.includes("отправляется"))
      ?.closest(".group");
    expect(screen.getAllByText("Привет")).toHaveLength(2);
    expect(optimisticWrapper).not.toBeNull();

    view.rerender(
      <MemoryRouter>
        <ChatMessagesPane
          c={controller({
            pendingUserText: "Привет",
            pendingUserBaselineIds: [oldPrompt.id],
            selectedTitle: "Чат",
            displayMessages: [oldPrompt, newPrompt],
          })}
        />
      </MemoryRouter>,
    );
    expect(screen.getAllByText("Привет")).toHaveLength(2);

    view.rerender(
      <MemoryRouter>
        <ChatMessagesPane
          c={controller({ selectedTitle: "Чат", pendingUserText: null, displayMessages: [oldPrompt, newPrompt] })}
        />
      </MemoryRouter>,
    );
    const settledWrappers = screen.getAllByText("Привет").map((node) => node.closest(".group")?.parentElement);
    expect(settledWrappers).toHaveLength(2);
    expect(new Set(settledWrappers).size).toBe(2);
    expect(settledWrappers[1]).toBe(optimisticWrapper);
  });

  it("renders one stable live operator shell for streamed text", () => {
    const c = controller({
      activeChat: {
        id: 7,
        title: "Привет",
        created_at: "",
        updated_at: "",
        active_turn: {
          turn_id: 19,
          assistant_message_id: 52,
          status: "running",
          busy: true,
        },
      },
      isBusy: true,
      showLiveStream: true,
      operatorWs: {
        ...controller().operatorWs,
        busy: true,
        phase: "streaming",
        streamText: "Единый поток ответа",
        statusMessage: "Формирую ответ…",
        thinkingStartedAt: Date.now() - 1000,
      },
    });

    const { container } = renderPane(c);

    expect(container.querySelectorAll('[data-operator-turn="live"]')).toHaveLength(1);
    expect(screen.getAllByText("Единый поток ответа")).toHaveLength(1);
  });

  it("renders an empty cancelled turn as terminal instead of a stuck composing state", () => {
    const c = controller({
      showLiveStream: true,
      operatorWs: {
        ...controller().operatorWs,
        terminalStatus: "cancelled",
      },
    });

    renderPane(c);

    expect(screen.getByRole("status")).toHaveTextContent("Генерация остановлена");
    expect(screen.queryByText("Формирует ответ")).not.toBeInTheDocument();
  });

  it("preserves the inner markdown DOM through WS, REST reconciliation, and history handoff", () => {
    const finalMessage: AssistantChatMessage = {
      id: 52,
      role: "assistant",
      content: "Стабильный ответ без перемонтирования",
      metadata: {},
      created_at: "2026-08-25T12:00:01Z",
    };
    const liveKey = "operator-turn-chat-7-turn-19";
    const liveController = controller({
      isBusy: true,
      showLiveStream: true,
      liveTurnKey: liveKey,
      liveAssistantMessageId: 52,
      operatorTurn: {
        key: liveKey,
        turnId: 19,
        assistantMessageId: 52,
        active: true,
        reconciling: false,
        text: finalMessage.content,
        persistedMessage: null,
      },
      operatorWs: {
        ...controller().operatorWs,
        busy: true,
        phase: "streaming",
        streamText: finalMessage.content,
        statusMessage: "Формирую ответ…",
        thinkingStartedAt: Date.now() - 1000,
      },
    });
    const view = renderPane(liveController);
    const liveMarkdown = view.container.querySelector("[data-message-markdown]");
    const liveParagraph = liveMarkdown?.querySelector("p");

    expect(liveMarkdown).toBeInTheDocument();
    expect(liveParagraph).toHaveTextContent(finalMessage.content);

    view.rerender(
      <MemoryRouter>
        <ChatMessagesPane
          c={controller({
            showLiveStream: true,
            liveTurnKey: liveKey,
            liveAssistantMessageId: 52,
            settledLiveMessage: finalMessage,
            operatorTurn: {
              key: liveKey,
              turnId: 19,
              assistantMessageId: 52,
              active: false,
              reconciling: true,
              text: finalMessage.content,
              persistedMessage: finalMessage,
            },
            operatorWs: {
              ...controller().operatorWs,
              phase: "completed",
              streamText: finalMessage.content,
            },
          })}
        />
      </MemoryRouter>,
    );

    expect(view.container.querySelector("[data-message-markdown]")).toBe(liveMarkdown);
    expect(view.container.querySelector("[data-message-markdown] p")).toBe(liveParagraph);

    view.rerender(
      <MemoryRouter>
        <ChatMessagesPane
          c={controller({
            displayMessages: [finalMessage],
            showLiveStream: false,
            liveTurnKey: null,
            liveAssistantMessageId: null,
            settledLiveMessage: null,
            operatorTurn: null,
          })}
        />
      </MemoryRouter>,
    );

    expect(view.container.querySelector("[data-message-markdown]")).toBe(liveMarkdown);
    expect(view.container.querySelector("[data-message-markdown] p")).toBe(liveParagraph);
    expect(screen.getAllByText(finalMessage.content)).toHaveLength(1);
  });

  it("offers an explicit jump to the newest message when reading history", () => {
    renderPane(controller({ atBottom: false }));

    expect(screen.getByRole("button", { name: "К новому сообщению" })).toBeInTheDocument();
  });
});
