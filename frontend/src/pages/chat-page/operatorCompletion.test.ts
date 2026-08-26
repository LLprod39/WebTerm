import { describe, expect, it, vi } from "vitest";

import {
  filterLiveAssistantMessage,
  findLiveAssistantMessage,
  hasNewDurableUserMessage,
  isQueuedSendForActiveChat,
  isScrollerNearBottom,
  reconcileLiveTurnIdentity,
  reduceScrollPinState,
  shouldReconcileOperatorCompletion,
  shouldReleaseRejectedOptimistic,
  shouldReleaseLiveShell,
} from "./useChatPageOperatorRuntime";
import { isOperatorSendBlocked, shouldDropOptimisticOnStop } from "./useChatPageController";

const assistant = {
  id: 2,
  role: "assistant" as const,
  content: "Grounded playbook summary",
  metadata: {},
  created_at: "2026-08-20T18:25:06Z",
};

const user = {
  id: 1,
  role: "user" as const,
  content: "Show playbooks",
  metadata: {},
  created_at: "2026-08-20T18:25:05Z",
};

describe("operator completion reconciliation", () => {
  it("drops an optimistic row only when stop cancels a still-queued send", () => {
    expect(shouldDropOptimisticOnStop("queued payload")).toBe(true);
    expect(shouldDropOptimisticOnStop(null)).toBe(false);
  });

  it("blocks an immediate retry until the failed optimistic row is reconciled", () => {
    expect(isOperatorSendBlocked(false, "Одинаковый запрос")).toBe(true);
    expect(isOperatorSendBlocked(false, null)).toBe(false);
    expect(isOperatorSendBlocked(true, null)).toBe(true);
  });

  it("never dispatches a queued payload through a different active chat", () => {
    expect(isQueuedSendForActiveChat({
      text: "payload A",
      queuedChatId: 7,
      activeChatId: 8,
    })).toBe(false);
    expect(isQueuedSendForActiveChat({
      text: "payload A",
      queuedChatId: 7,
      activeChatId: 7,
    })).toBe(true);
  });

  it("does not release a rejected row by timeout while its authoritative refresh is unresolved", () => {
    vi.useFakeTimers();
    try {
      const unresolved = { epoch: 2, status: "pending" as const };
      expect(shouldReleaseRejectedOptimistic({
        pendingEpoch: 2,
        pendingChatId: 7,
        reconciliation: { chatId: 7, ...unresolved },
        hasDurableMatch: false,
      })).toBe(false);

      vi.advanceTimersByTime(5_000);
      expect(shouldReleaseRejectedOptimistic({
        pendingEpoch: 2,
        pendingChatId: 7,
        reconciliation: { chatId: 7, ...unresolved },
        hasDurableMatch: false,
      })).toBe(false);
      expect(shouldReleaseRejectedOptimistic({
        pendingEpoch: 2,
        pendingChatId: 7,
        reconciliation: { chatId: 7, epoch: 2, status: "settled" },
        hasDurableMatch: false,
      })).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("ends local writing when a previously open REST turn is durably closed", () => {
    expect(shouldReconcileOperatorCompletion({
      restTurnWasOpen: true,
      operatorBusy: true,
      activeTurn: null,
      lastMessage: assistant,
    })).toBe(true);
  });

  it("does not end a genuinely running turn or a turn without final text", () => {
    expect(shouldReconcileOperatorCompletion({
      restTurnWasOpen: true,
      operatorBusy: true,
      activeTurn: { turn_id: 8, status: "running", busy: true },
      lastMessage: assistant,
    })).toBe(false);
    expect(shouldReconcileOperatorCompletion({
      restTurnWasOpen: false,
      operatorBusy: true,
      activeTurn: null,
      lastMessage: undefined,
    })).toBe(false);
  });
});

describe("operator live-shell reconciliation", () => {
  it("keeps one shell key while REST ids arrive and active_turn later disappears", () => {
    const pending = reconcileLiveTurnIdentity(null, {
      chatId: 7,
      turnId: null,
      assistantMessageId: null,
      startedAt: 1_000,
      nonce: 1,
      keepLiveShell: true,
    });
    const identified = reconcileLiveTurnIdentity(pending, {
      chatId: 7,
      turnId: 91,
      assistantMessageId: 102,
      startedAt: 1_000,
      nonce: 1,
      keepLiveShell: true,
    });
    const reconciling = reconcileLiveTurnIdentity(identified, {
      chatId: 7,
      turnId: null,
      assistantMessageId: null,
      startedAt: null,
      nonce: 1,
      keepLiveShell: true,
    });

    expect(identified?.key).toBe(pending?.key);
    expect(reconciling).toBe(identified);
    expect(reconciling?.assistantMessageId).toBe(102);
    expect(reconcileLiveTurnIdentity(reconciling, {
      chatId: 7,
      turnId: null,
      assistantMessageId: null,
      startedAt: null,
      nonce: 1,
      keepLiveShell: false,
    })).toBeNull();
  });

  it("assigns unique keys to consecutive null-id pending turns across handoff", () => {
    const firstTurn = reconcileLiveTurnIdentity(null, {
      chatId: 7,
      turnId: null,
      assistantMessageId: null,
      startedAt: null,
      nonce: 1,
      keepLiveShell: true,
    });
    const firstHandoff = reconcileLiveTurnIdentity(firstTurn, {
      chatId: 7,
      turnId: null,
      assistantMessageId: null,
      startedAt: null,
      nonce: 1,
      keepLiveShell: true,
    });
    const secondTurn = reconcileLiveTurnIdentity(firstHandoff, {
      chatId: 7,
      turnId: null,
      assistantMessageId: null,
      startedAt: null,
      nonce: 2,
      keepLiveShell: true,
    });

    expect(firstTurn?.key).toBe("operator-turn-7-pending-1");
    expect(firstHandoff).toBe(firstTurn);
    expect(secondTurn?.key).toBe("operator-turn-7-pending-2");
    expect(secondTurn?.key).not.toBe(firstTurn?.key);
  });

  it("hides the matching progressive REST assistant even when it already has body text", () => {
    const messages = [user, assistant];

    expect(filterLiveAssistantMessage({
      messages,
      assistantMessageId: assistant.id,
      keepLiveShell: true,
    })).toEqual([user]);
    expect(filterLiveAssistantMessage({
      messages,
      assistantMessageId: assistant.id,
      keepLiveShell: false,
    })).toBe(messages);
  });

  it("never infers the previous assistant as the current live turn", () => {
    const previousAssistant = { ...assistant, id: 10, content: "Previous answer" };
    const currentUser = { ...user, id: 11, content: "Current request" };

    expect(findLiveAssistantMessage([previousAssistant, currentUser], null)).toBeNull();

    const partialCurrent = { ...assistant, id: 12, content: "Partial current answer" };
    expect(findLiveAssistantMessage([previousAssistant, currentUser, partialCurrent], null))
      .toBe(partialCurrent);
  });

  it("does not bind the previous answer while the new user message is still pending", () => {
    const previousHistory = [user, assistant];
    const inferred = findLiveAssistantMessage(previousHistory, null, {
      allowFallback: false,
    });

    expect(inferred).toBeNull();
    expect(filterLiveAssistantMessage({
      messages: previousHistory,
      assistantMessageId: inferred?.id ?? null,
      keepLiveShell: true,
    })).toBe(previousHistory);
    expect(inferred?.content ?? "").toBe("");

    // A server-provided id is authoritative even before pendingUserText clears.
    expect(findLiveAssistantMessage(previousHistory, assistant.id, {
      allowFallback: false,
    })).toBe(assistant);
  });

  it("requires a post-baseline durable row for a repeated identical prompt", () => {
    const oldUser = { ...user, id: 21, content: "Привет" };
    const oldAssistant = { ...assistant, id: 22, content: "Старый ответ" };
    const baseline = new Set([oldUser.id]);

    expect(hasNewDurableUserMessage([oldUser, oldAssistant], "Привет", baseline)).toBe(false);

    const newUser = { ...oldUser, id: 23 };
    expect(hasNewDurableUserMessage([oldUser, oldAssistant, newUser], "Привет", baseline)).toBe(true);
  });

  it("keeps the shell until a durable payload exists and the active turn is closed", () => {
    expect(shouldReleaseLiveShell({
      streamHold: true,
      operatorBusy: false,
      turnOpen: false,
      settledMessage: null,
    })).toBe(false);
    expect(shouldReleaseLiveShell({
      streamHold: true,
      operatorBusy: false,
      turnOpen: true,
      settledMessage: assistant,
    })).toBe(false);
    expect(shouldReleaseLiveShell({
      streamHold: true,
      operatorBusy: false,
      turnOpen: false,
      settledMessage: assistant,
    })).toBe(true);
    expect(shouldReleaseLiveShell({
      streamHold: true,
      operatorBusy: false,
      turnOpen: false,
      settledMessage: null,
      terminalStatus: "cancelled",
    })).toBe(true);
    expect(shouldReleaseLiveShell({
      streamHold: true,
      operatorBusy: false,
      turnOpen: false,
      settledMessage: null,
      terminalStatus: "completed",
    })).toBe(true);
  });

  it("uses the same bottom threshold as the scroll and sentinel fallbacks", () => {
    expect(isScrollerNearBottom({ scrollHeight: 1000, scrollTop: 821, clientHeight: 100 }))
      .toBe(true);
    expect(isScrollerNearBottom({ scrollHeight: 1000, scrollTop: 820, clientHeight: 100 }))
      .toBe(false);
  });

  it("keeps layout growth pinned but lets a real upward scroll win", () => {
    const pinned = {
      pinned: true,
      userScrolledAway: false,
      lastScrollTop: 900,
    };
    const contentGrew = reduceScrollPinState(pinned, {
      type: "layout",
      isIntersecting: false,
    });
    const samePositionAfterGrowth = reduceScrollPinState(contentGrew, {
      type: "scroll",
      scrollTop: 900,
      nearBottom: false,
    });
    const userScrolledUp = reduceScrollPinState(samePositionAfterGrowth, {
      type: "scroll",
      scrollTop: 700,
      nearBottom: false,
    });
    const laterIntersection = reduceScrollPinState(userScrolledUp, {
      type: "layout",
      isIntersecting: true,
    });

    expect(contentGrew.pinned).toBe(true);
    expect(samePositionAfterGrowth.pinned).toBe(true);
    expect(userScrolledUp).toMatchObject({
      pinned: false,
      userScrolledAway: true,
    });
    expect(laterIntersection).toBe(userScrolledUp);
    expect(reduceScrollPinState(userScrolledUp, {
      type: "pin",
      scrollTop: 900,
    })).toMatchObject({
      pinned: true,
      userScrolledAway: false,
    });
  });

  it("keeps the bottom pin when completion layout collapse clamps scrollTop", () => {
    const next = reduceScrollPinState(
      { pinned: true, userScrolledAway: false, lastScrollTop: 900 },
      { type: "scroll", scrollTop: 820, nearBottom: true },
    );

    expect(next).toEqual({ pinned: true, userScrolledAway: false, lastScrollTop: 820 });
  });
});
