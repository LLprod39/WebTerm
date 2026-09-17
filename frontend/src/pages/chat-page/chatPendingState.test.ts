import { describe, expect, it } from "vitest";

import {
  getScopedPending,
  promotePendingChat,
  setScopedPending,
  type ScopedPendingMap,
  type ScopedPendingSend,
  type ScopedPendingUser,
} from "./chatPendingState";

describe("chat-scoped optimistic state", () => {
  it("hides pending A in chat B and restores it when returning to A", () => {
    const pendingA: ScopedPendingUser = {
      chatId: 7,
      text: "Запрос A",
      epoch: 1,
      baselineIds: [2, 4],
    };
    const state = setScopedPending<ScopedPendingUser>({}, 7, pendingA);

    expect(getScopedPending(state, 8)).toBeNull();
    expect(getScopedPending(state, 7)).toEqual(pendingA);
  });

  it("never exposes queued A to chat B and returns it exactly once in A", () => {
    const queuedA: ScopedPendingSend = { chatId: 7, text: "payload A", epoch: 1 };
    const state = setScopedPending<ScopedPendingSend>({}, 7, queuedA);

    expect(getScopedPending(state, 8)).toBeNull();
    expect(getScopedPending(state, 7)?.text).toBe("payload A");
    const consumed = setScopedPending(state, 7, null);
    expect(getScopedPending(consumed, 7)).toBeNull();
  });

  it("promotes a new-chat optimistic row and queue to the assigned id", () => {
    const user: ScopedPendingMap<ScopedPendingUser> = {
      new: { chatId: null, text: "Первое", epoch: 4, baselineIds: [] },
    };
    const queued: ScopedPendingMap<ScopedPendingSend> = {
      new: { chatId: null, text: "payload", epoch: 4 },
    };

    expect(getScopedPending(promotePendingChat(user, 19), 19)).toEqual({
      chatId: 19,
      text: "Первое",
      epoch: 4,
      baselineIds: [],
    });
    expect(getScopedPending(promotePendingChat(queued, 19), 19)?.text).toBe("payload");
  });
});
