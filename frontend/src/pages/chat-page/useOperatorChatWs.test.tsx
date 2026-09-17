import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useOperatorChatWs } from "./useOperatorChatWs";

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: MockWebSocket[] = [];

  readonly url: string;
  readyState = MockWebSocket.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  send = vi.fn();

  constructor(url: string | URL) {
    this.url = String(url);
    MockWebSocket.instances.push(this);
  }

  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }

  emit(payload: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }

  close() {
    if (this.readyState === MockWebSocket.CLOSED) return;
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({} as CloseEvent);
  }
}

describe("useOperatorChatWs", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-25T12:00:00Z"));
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("batches token rendering and flushes every token immediately on completion", () => {
    const onToken = vi.fn();
    const { result } = renderHook(() => useOperatorChatWs({ chatId: 7, onToken }));
    const socket = MockWebSocket.instances[0];

    act(() => {
      socket.emit({ type: "token", text: "one " });
      socket.emit({ type: "token", text: "two" });
    });

    expect(result.current.streamText).toBe("");
    expect(onToken.mock.calls).toEqual([["one "], ["two"]]);

    act(() => vi.advanceTimersByTime(35));
    expect(result.current.streamText).toBe("");

    act(() => vi.advanceTimersByTime(1));
    expect(result.current.streamText).toBe("one two");

    act(() => {
      socket.emit({ type: "token", text: " three" });
      socket.emit({ type: "token", text: " four" });
      socket.emit({ type: "turn_complete", status: "completed" });
    });

    expect(result.current.streamText).toBe("one two three four");
    expect(result.current.busy).toBe(false);
    expect(result.current.phase).toBe("idle");
    expect(result.current.terminalStatus).toBe("completed");

    act(() => vi.runOnlyPendingTimers());
    expect(result.current.streamText).toBe("one two three four");
  });

  it("reconciles snapshots without dropping newer buffered tokens", () => {
    const { result } = renderHook(() => useOperatorChatWs({ chatId: 7 }));
    const socket = MockWebSocket.instances[0];

    act(() => {
      socket.emit({ type: "token", text: "Hello" });
      socket.emit({
        type: "turn_snapshot",
        status: "running",
        busy: true,
        assistant_text: "Hello world",
      });
    });
    expect(result.current.streamText).toBe("Hello world");

    act(() => {
      socket.emit({ type: "token", text: "!" });
      socket.emit({
        type: "turn_snapshot",
        status: "running",
        busy: true,
        assistant_text: "Hello world",
      });
    });

    expect(result.current.streamText).toBe("Hello world!");
    act(() => vi.runOnlyPendingTimers());
    expect(result.current.streamText).toBe("Hello world!");
  });

  it("reduces thinking, token, tool, snapshot, and completion as one lifecycle", () => {
    const { result } = renderHook(() => useOperatorChatWs({ chatId: 7 }));
    const socket = MockWebSocket.instances[0];

    act(() => {
      socket.emit({ type: "ready", chat_id: 7, health: { ok: true } });
      socket.emit({ type: "turn_started" });
      socket.emit({ type: "thinking", iteration: 2, message: "Проверяет данные" });
      socket.emit({ type: "thinking_delta", iteration: 2, text: "internal progress" });
      socket.emit({ type: "token", text: "Ответ" });
      vi.advanceTimersByTime(36);
    });

    expect(result.current).toMatchObject({
      ready: true,
      busy: true,
      phase: "streaming",
      streamText: "Ответ",
      thinkingIteration: 2,
      statusMessage: "Проверяет данные",
      hasReasoningStream: true,
    });

    act(() => {
      socket.emit({ type: "tool_started", call_id: "catalog", name: "list_playbooks" });
      socket.emit({
        type: "tool_result",
        call_id: "catalog",
        name: "list_playbooks",
        ok: true,
        preview: "15 entries",
      });
      socket.emit({
        type: "turn_snapshot",
        status: "running",
        busy: true,
        assistant_text: "Ответ готов",
      });
    });

    expect(result.current.streamText).toBe("Ответ готов");
    expect(result.current.toolSteps).toHaveLength(1);
    expect(result.current.toolSteps[0]).toMatchObject({
      id: "catalog",
      status: "done",
      preview: "15 entries",
    });
    expect(result.current.phase).toBe("streaming");

    act(() => socket.emit({ type: "turn_complete", status: "completed" }));

    expect(result.current.busy).toBe(false);
    expect(result.current.phase).toBe("idle");
    expect(result.current.streamText).toBe("Ответ готов");
    expect(result.current.errorMessage).toBeNull();
    expect(result.current.terminalStatus).toBe("completed");
  });

  it("updates tool steps in place and preserves the turn timer across continuations", () => {
    const { result } = renderHook(() => useOperatorChatWs({ chatId: 7 }));
    const socket = MockWebSocket.instances[0];
    socket.open();

    act(() => socket.emit({ type: "turn_started" }));
    const startedAt = result.current.thinkingStartedAt;
    expect(startedAt).not.toBeNull();

    act(() => {
      socket.emit({ type: "tool_started", id: "first", name: "inventory" });
      socket.emit({ type: "tool_started", id: "second", name: "health" });
    });
    expect(result.current.toolSteps.map((step) => step.id)).toEqual(["first", "second"]);
    expect(result.current.toolSteps[0].startedAt).toBe(
      new Date("2026-08-25T12:00:00Z").getTime(),
    );

    vi.setSystemTime(new Date("2026-08-25T12:01:00Z"));
    act(() => {
      socket.emit({
        type: "tool_result",
        id: "first",
        name: "inventory",
        ok: true,
        preview: "15 entries",
      });
    });
    expect(result.current.toolSteps.map((step) => step.id)).toEqual(["first", "second"]);
    expect(result.current.toolSteps[0]).toMatchObject({
      status: "done",
      preview: "15 entries",
      startedAt: new Date("2026-08-25T12:00:00Z").getTime(),
      completedAt: new Date("2026-08-25T12:01:00Z").getTime(),
    });
    expect(result.current.thinkingStartedAt).toBe(startedAt);

    act(() => {
      socket.emit({ type: "async_started", run_id: 31, async_kind: "agent_run" });
      socket.emit({
        type: "async_done",
        run_id: 31,
        async_kind: "agent_run",
        ok: true,
        status: "completed",
      });
    });
    expect(result.current.toolSteps.map((step) => step.id)).toEqual([
      "first",
      "second",
      "async-31",
    ]);
    expect(result.current.toolSteps[2].status).toBe("done");
    expect(result.current.thinkingStartedAt).toBe(startedAt);

    act(() => {
      socket.emit({
        type: "turn_snapshot",
        status: "awaiting_confirm",
        busy: false,
        pending_action: { id: 42 },
      });
      socket.emit({ type: "confirm_required", action_id: 42 });
    });
    expect(result.current.busy).toBe(false);
    expect(result.current.thinkingStartedAt).toBe(startedAt);

    vi.setSystemTime(new Date("2026-08-25T12:02:00Z"));
    act(() => {
      expect(result.current.confirmAction(42, "CONFIRM")).toBe(true);
      expect(result.current.cancelAction(42)).toBe(true);
    });
    expect(result.current.thinkingStartedAt).toBe(startedAt);

    vi.setSystemTime(new Date("2026-08-25T12:03:00Z"));
    act(() => expect(result.current.sendMessage("next turn")).toBe(true));
    expect(result.current.thinkingStartedAt).toBe(
      new Date("2026-08-25T12:03:00Z").getTime(),
    );
  });

  it("flushes buffered text and closes the indicator on an error", () => {
    const onError = vi.fn();
    const { result } = renderHook(() => useOperatorChatWs({ chatId: 7, onError }));
    const socket = MockWebSocket.instances[0];

    act(() => {
      socket.emit({ type: "turn_started" });
      socket.emit({ type: "thinking", message: "Checking data" });
      socket.emit({ type: "thinking_delta", text: "Safe progress" });
      socket.emit({ type: "tool_started", id: "inventory", name: "list_servers" });
      socket.emit({
        type: "plan_update",
        plan: { title: "Inventory", steps: [{ id: 1, text: "Load", status: "running" }] },
      });
      socket.emit({ type: "token", text: "Partial answer" });
    });
    expect(result.current.streamText).toBe("");
    expect(result.current.toolSteps).toHaveLength(1);
    expect(result.current.thinkingStartedAt).not.toBeNull();

    act(() =>
      socket.emit({
        type: "error",
        message: "Provider\u0000 disconnected\npassword=super-secret api-key:abc123",
      }),
    );

    expect(result.current.streamText).toBe("Partial answer");
    expect(result.current.busy).toBe(false);
    expect(result.current.phase).toBe("idle");
    expect(result.current.thinkingStartedAt).toBeNull();
    expect(result.current.terminalStatus).toBe("error");
    expect(result.current.errorMessage).toBe(
      "Provider disconnected password=••• api-key:•••",
    );
    expect(onError).toHaveBeenCalledOnce();
    expect(onError).toHaveBeenCalledWith(
      "Provider disconnected password=••• api-key:•••",
    );
    expect(result.current.errorMessage).not.toContain("super-secret");
    expect(result.current.errorMessage).not.toContain("abc123");

    act(() => vi.advanceTimersByTime(35));
    expect(result.current.streamText).toBe("Partial answer");

    act(() => vi.advanceTimersByTime(1));
    expect(result.current.streamText).toBe("");
    expect(result.current.toolSteps).toEqual([]);
    expect(result.current.livePlan).toBeNull();
    expect(result.current.reasoningText).toBe("");
    expect(result.current.hasReasoningStream).toBe(false);
    expect(result.current.statusMessage).toBe("");
    expect(result.current.asyncTask).toBeNull();
    expect(result.current.errorMessage).toBe(
      "Provider disconnected password=••• api-key:•••",
    );
    expect(
      Boolean(
        result.current.streamText ||
          result.current.toolSteps.length ||
          result.current.livePlan ||
          result.current.phase !== "idle",
      ),
    ).toBe(false);

    act(() => socket.emit({ type: "turn_started" }));
    expect(result.current.errorMessage).toBeNull();
    expect(result.current.terminalStatus).toBeNull();
  });

  it("ends an active turn from a cancelled snapshot without losing buffered text", () => {
    const { result } = renderHook(() => useOperatorChatWs({ chatId: 7 }));
    const socket = MockWebSocket.instances[0];

    act(() => {
      socket.emit({ type: "turn_started" });
      socket.emit({ type: "token", text: "Stopped partial answer" });
    });
    expect(result.current.streamText).toBe("");
    expect(result.current.busy).toBe(true);

    act(() => {
      socket.emit({
        type: "turn_snapshot",
        status: "cancelled",
        busy: false,
        assistant_text: "",
      });
    });

    expect(result.current.streamText).toBe("Stopped partial answer");
    expect(result.current.busy).toBe(false);
    expect(result.current.phase).toBe("idle");
    expect(result.current.thinkingStartedAt).toBeNull();
    expect(result.current.terminalStatus).toBe("cancelled");
  });

  it.each(["cancelled", "failed", "limit"])(
    "records an empty %s snapshot until the next turn or reset",
    (status) => {
      const { result } = renderHook(() => useOperatorChatWs({ chatId: 7 }));
      const socket = MockWebSocket.instances[0];

      act(() => {
        socket.emit({ type: "turn_started" });
        socket.emit({
          type: "turn_snapshot",
          status,
          busy: false,
          assistant_text: "",
        });
      });

      expect(result.current.streamText).toBe("");
      expect(result.current.busy).toBe(false);
      expect(result.current.phase).toBe("idle");
      expect(result.current.terminalStatus).toBe(status);

      act(() => socket.emit({ type: "turn_started" }));
      expect(result.current.terminalStatus).toBeNull();

      act(() => {
        socket.emit({
          type: "turn_snapshot",
          status,
          busy: false,
          assistant_text: "",
        });
        result.current.resetStream();
      });
      expect(result.current.terminalStatus).toBeNull();
    },
  );

  it("drops raw reasoning bursts after the first safe-stage update", () => {
    let renderCount = 0;
    const { result } = renderHook(() => {
      renderCount += 1;
      return useOperatorChatWs({ chatId: 7 });
    });
    const socket = MockWebSocket.instances[0];

    act(() => socket.emit({ type: "turn_started" }));
    act(() =>
      socket.emit({ type: "thinking_delta", iteration: 2, text: "PRIVATE_CHAIN first" }),
    );
    const rendersAfterSafeStage = renderCount;

    expect(result.current.hasReasoningStream).toBe(true);
    expect(result.current.reasoningText).toBe("");
    expect(result.current.thinkingIteration).toBe(2);

    act(() => {
      for (let index = 0; index < 250; index += 1) {
        socket.emit({
          type: "thinking_delta",
          iteration: 2,
          text: `PRIVATE_CHAIN secret-${index}`,
        });
      }
    });

    expect(result.current.reasoningText).toBe("");
    expect(result.current.thinkingIteration).toBe(2);
    expect(renderCount).toBe(rendersAfterSafeStage);

    act(() =>
      socket.emit({ type: "thinking_delta", iteration: 3, text: "PRIVATE_CHAIN next" }),
    );
    expect(result.current.reasoningText).toBe("");
    expect(result.current.thinkingIteration).toBe(3);
    expect(renderCount).toBe(rendersAfterSafeStage + 1);
  });

  it("ignores disposed socket events and delayed close after a chat switch", () => {
    const { result, rerender } = renderHook(
      ({ chatId }: { chatId: number }) => useOperatorChatWs({ chatId }),
      { initialProps: { chatId: 1 } },
    );
    const firstSocket = MockWebSocket.instances[0];
    const delayedFirstClose = firstSocket.onclose;

    act(() => {
      firstSocket.open();
      firstSocket.emit({ type: "ready", chat_id: 1 });
      rerender({ chatId: 2 });
    });

    const secondSocket = MockWebSocket.instances[1];
    act(() => {
      secondSocket.open();
      secondSocket.emit({ type: "ready", chat_id: 2 });
      firstSocket.emit({ type: "token", text: "stale text" });
      firstSocket.emit({ type: "tool_started", call_id: "stale", name: "stale_tool" });
      delayedFirstClose?.({} as CloseEvent);
    });

    expect(result.current.ready).toBe(true);
    expect(result.current.streamText).toBe("");
    expect(result.current.toolSteps).toEqual([]);

    act(() => expect(result.current.sendMessage("new chat message")).toBe(true));
    expect(firstSocket.send).not.toHaveBeenCalled();
    expect(secondSocket.send).toHaveBeenCalledWith(
      JSON.stringify({ type: "chat.message", message: "new chat message" }),
    );

    act(() => vi.advanceTimersByTime(8_000));
    expect(MockWebSocket.instances).toHaveLength(2);
  });

  it("clears every old-chat signal when chatId changes", () => {
    const { result, rerender } = renderHook(
      ({ chatId }: { chatId: number | null }) => useOperatorChatWs({ chatId }),
      { initialProps: { chatId: 1 } },
    );
    const firstSocket = MockWebSocket.instances[0];

    act(() => {
      firstSocket.emit({
        type: "ready",
        chat_id: 1,
        health: { ok: true, checks: { llm: "ok" } },
      });
      firstSocket.emit({ type: "turn_started" });
      firstSocket.emit({ type: "thinking", iteration: 2, message: "Old status" });
      firstSocket.emit({ type: "thinking_delta", text: "Old reasoning" });
      firstSocket.emit({ type: "tool_started", id: "old-tool", name: "inventory" });
      firstSocket.emit({
        type: "plan_update",
        plan: { title: "Old plan", steps: [{ id: 1, text: "Old", status: "running" }] },
      });
      firstSocket.emit({ type: "usage", usage: { total_tokens: 12 } });
      firstSocket.emit({ type: "async_started", run_id: 9, async_kind: "agent_run" });
      firstSocket.emit({ type: "token", text: "Old answer" });
      vi.advanceTimersByTime(36);
      firstSocket.emit({ type: "token", text: " pending" });
    });

    expect(result.current.ready).toBe(true);
    expect(result.current.streamText).toBe("Old answer");
    expect(result.current.toolSteps.length).toBeGreaterThan(0);
    expect(result.current.livePlan).not.toBeNull();
    expect(result.current.health).not.toBeNull();
    expect(result.current.asyncTask).not.toBeNull();

    act(() => rerender({ chatId: 2 }));

    expect(MockWebSocket.instances).toHaveLength(2);
    expect(result.current.ready).toBe(false);
    expect(result.current.busy).toBe(false);
    expect(result.current.streamText).toBe("");
    expect(result.current.toolSteps).toEqual([]);
    expect(result.current.livePlan).toBeNull();
    expect(result.current.lastUsage).toBeNull();
    expect(result.current.phase).toBe("idle");
    expect(result.current.thinkingStartedAt).toBeNull();
    expect(result.current.thinkingIteration).toBeNull();
    expect(result.current.reasoningText).toBe("");
    expect(result.current.hasReasoningStream).toBe(false);
    expect(result.current.statusMessage).toBe("");
    expect(result.current.health).toBeNull();
    expect(result.current.asyncTask).toBeNull();

    act(() => vi.advanceTimersByTime(36));
    expect(result.current.streamText).toBe("");
  });

  it("keeps flushed text visible while reconnecting", () => {
    const { result } = renderHook(() => useOperatorChatWs({ chatId: 7 }));
    const firstSocket = MockWebSocket.instances[0];

    act(() => {
      firstSocket.emit({ type: "token", text: "Persistent answer" });
      vi.advanceTimersByTime(36);
    });
    expect(result.current.streamText).toBe("Persistent answer");

    act(() => firstSocket.close());
    expect(result.current.streamText).toBe("Persistent answer");

    act(() => vi.advanceTimersByTime(1_000));
    expect(MockWebSocket.instances).toHaveLength(2);
    expect(result.current.streamText).toBe("Persistent answer");

    act(() => {
      MockWebSocket.instances[1].emit({
        type: "turn_snapshot",
        status: "running",
        busy: true,
        assistant_text: "Persistent answer restored",
      });
    });
    expect(result.current.streamText).toBe("Persistent answer restored");
  });
});
