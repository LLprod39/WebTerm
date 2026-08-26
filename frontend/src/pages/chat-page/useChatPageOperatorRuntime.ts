import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";
import type { QueryClient } from "@tanstack/react-query";

import type { AssistantChatMessage, AssistantChatSession, ProviderBinding } from "@/api";
import type { useToast } from "@/hooks/use-toast";

import { hasMarkdownTable, inferInventorySkeletonKind } from "./InventoryPanelSkeleton";
import type { PlanData } from "./PlanTasksPanel";
import { createChatOperatorHandlers } from "./chatPageOperatorHandlers";
import { pendingChatKey } from "./chatPendingState";
import { isNewOptimisticUserTurn } from "./optimisticUserTurn";
import type { OperatorSessionLine } from "./operatorSessionTypes";
import { useOperatorChatWs } from "./useOperatorChatWs";

type ToastFn = ReturnType<typeof useToast>["toast"];
type Lang = "ru" | "en" | string;

type OpenSessionDock = (opts: {
  serverId: number;
  serverName?: string;
  host?: string;
  mode?: "agent" | "live";
}) => void;

type PushSessionLine = (line: Omit<OperatorSessionLine, "id" | "at"> & { id?: string }) => void;

type ActiveTurn = AssistantChatSession["active_turn"];

export type LiveTurnIdentity = {
  chatId: number;
  key: string;
  turnId: number | null;
  assistantMessageId: number | null;
  startedAt: number | null;
  nonce: number;
};

function createLiveTurnKey(
  chatId: number,
  turnId: number | null,
  startedAt: number | null,
  nonce: number,
) {
  const turnEpoch =
    startedAt != null
      ? `started-${startedAt}`
      : turnId != null
        ? `turn-${turnId}`
        : `pending-${nonce}`;
  return `operator-turn-${chatId}-${turnEpoch}`;
}

export function reconcileLiveTurnIdentity(
  previous: LiveTurnIdentity | null,
  {
    chatId,
    turnId,
    assistantMessageId,
    startedAt,
    nonce,
    keepLiveShell,
  }: {
    chatId: number | null;
    turnId: number | null;
    assistantMessageId: number | null;
    startedAt: number | null;
    nonce: number;
    keepLiveShell: boolean;
  },
) {
  if (!chatId || !keepLiveShell) return null;

  const sameTurn =
    previous?.chatId === chatId &&
    previous.nonce === nonce &&
    (turnId == null || previous.turnId == null || previous.turnId === turnId) &&
    (startedAt == null || previous.startedAt == null || previous.startedAt === startedAt);
  if (sameTurn && previous) {
    const nextTurnId = turnId ?? previous.turnId;
    const nextAssistantMessageId = assistantMessageId ?? previous.assistantMessageId;
    const nextStartedAt = startedAt ?? previous.startedAt;
    if (
      nextTurnId === previous.turnId &&
      nextAssistantMessageId === previous.assistantMessageId &&
      nextStartedAt === previous.startedAt
    ) {
      return previous;
    }
    return {
      ...previous,
      turnId: nextTurnId,
      assistantMessageId: nextAssistantMessageId,
      startedAt: nextStartedAt,
    };
  }

  return {
    chatId,
    key: createLiveTurnKey(chatId, turnId, startedAt, nonce),
    turnId,
    assistantMessageId,
    startedAt,
    nonce,
  };
}

export type OperatorTurnViewModel = {
  key: string;
  turnId: number | null;
  assistantMessageId: number | null;
  active: boolean;
  reconciling: boolean;
  text: string;
  phase: ReturnType<typeof useOperatorChatWs>["phase"];
  startedAt: number | null;
  iteration: number | null;
  statusMessage: string;
  toolSteps: ReturnType<typeof useOperatorChatWs>["toolSteps"];
  error: string | null;
  terminalStatus: string | null;
  persistedMessage: AssistantChatMessage | null;
};

export function isOperatorTurnOpen(activeTurn: ActiveTurn) {
  return Boolean(
    activeTurn?.busy ||
      activeTurn?.status === "running" ||
      activeTurn?.status === "resuming" ||
      activeTurn?.status === "awaiting_async",
  );
}

/**
 * Resolve only an assistant row belonging to the current user turn. Falling
 * back to the latest assistant after the latest user avoids accidentally
 * binding a live shell to the previous completed answer.
 */
export function findLiveAssistantMessage(
  messages: AssistantChatMessage[],
  assistantMessageId: number | null,
  { allowFallback = true }: { allowFallback?: boolean } = {},
) {
  if (assistantMessageId != null) {
    return messages.find((message) => message.id === assistantMessageId && message.role === "assistant") ?? null;
  }
  if (!allowFallback) return null;

  let latestUserIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === "user") {
      latestUserIndex = index;
      break;
    }
  }
  if (latestUserIndex < 0) return null;

  for (let index = messages.length - 1; index > latestUserIndex; index -= 1) {
    if (messages[index]?.role === "assistant") return messages[index];
  }
  return null;
}

export function hasSettledAssistantPayload(message: AssistantChatMessage | null) {
  if (!message) return false;
  const actions = message.metadata?.actions;
  const tables = (message.metadata as { tables?: unknown[] } | undefined)?.tables;
  return Boolean(
    message.content?.trim() ||
      (Array.isArray(actions) && actions.length > 0) ||
      (Array.isArray(tables) && tables.length > 0),
  );
}

export function filterLiveAssistantMessage({
  messages,
  assistantMessageId,
  keepLiveShell,
}: {
  messages: AssistantChatMessage[];
  assistantMessageId: number | null;
  keepLiveShell: boolean;
}) {
  if (!keepLiveShell || assistantMessageId == null) return messages;
  return messages.filter((message) => message.id !== assistantMessageId);
}

export function matchesDurableUserMessage(raw: string, pending: string) {
  const stored = String(raw || "").trim();
  const expected = String(pending || "").trim();
  if (!stored || !expected) return false;
  if (stored === expected || stored.startsWith(expected)) return true;
  const visibleHead = stored
    .split(/\n\nКонтекст серверов:|\n\nКонтекст playbook:|\n\n\[Human terminal on |\nКонтекст пользователей:/)[0]
    .trim();
  return (
    visibleHead === expected ||
    visibleHead.startsWith(expected) ||
    expected.startsWith(visibleHead)
  );
}

export function hasNewDurableUserMessage(
  messages: AssistantChatMessage[],
  pending: string,
  baselineIds: ReadonlySet<number>,
) {
  return messages.some(
    (message) =>
      message.role === "user" &&
      !baselineIds.has(message.id) &&
      matchesDurableUserMessage(message.content, pending),
  );
}

export type TerminalUserReconciliation = {
  chatId: number | null;
  epoch: number;
  status: "pending" | "settled" | "failed";
};

export function shouldReleaseRejectedOptimistic({
  pendingEpoch,
  pendingChatId,
  reconciliation,
  hasDurableMatch,
}: {
  pendingEpoch: number;
  pendingChatId: number | null;
  reconciliation: TerminalUserReconciliation | null;
  hasDurableMatch: boolean;
}) {
  return Boolean(
    !hasDurableMatch &&
      reconciliation?.chatId === pendingChatId &&
      reconciliation?.epoch === pendingEpoch &&
      reconciliation.status === "settled",
  );
}

export function isQueuedSendForActiveChat({
  text,
  queuedChatId,
  activeChatId,
}: {
  text: string | null;
  queuedChatId: number | null;
  activeChatId: number | null;
}) {
  return Boolean(text) && queuedChatId === activeChatId;
}

export function isScrollerNearBottom(
  metrics: Pick<HTMLDivElement, "scrollHeight" | "scrollTop" | "clientHeight">,
  threshold = 80,
) {
  return metrics.scrollHeight - metrics.scrollTop - metrics.clientHeight < threshold;
}

export type ScrollPinState = {
  pinned: boolean;
  userScrolledAway: boolean;
  lastScrollTop: number | null;
};

export type ScrollPinEvent =
  | { type: "layout"; isIntersecting: boolean }
  | { type: "scroll"; scrollTop: number; nearBottom: boolean }
  | { type: "pin"; scrollTop?: number | null };

/**
 * Intersection changes describe layout, not user intent. Only an upward
 * scroll can release an existing bottom pin; content growth keeps it active
 * until the queued autoscroll catches up.
 */
export function reduceScrollPinState(
  state: ScrollPinState,
  event: ScrollPinEvent,
): ScrollPinState {
  if (event.type === "pin") {
    return {
      pinned: true,
      userScrolledAway: false,
      lastScrollTop: event.scrollTop ?? state.lastScrollTop,
    };
  }

  if (event.type === "layout") {
    if (state.userScrolledAway) return state;
    if (state.pinned || event.isIntersecting) {
      return state.pinned
        ? state
        : { ...state, pinned: true };
    }
    return state;
  }

  const scrolledUp =
    state.lastScrollTop != null && event.scrollTop < state.lastScrollTop - 0.5;
  // Layout collapse can clamp scrollTop downward while the viewport remains at
  // the end. Near-bottom wins over the direction heuristic in that case.
  if (event.nearBottom) {
    return {
      pinned: true,
      userScrolledAway: false,
      lastScrollTop: event.scrollTop,
    };
  }
  if (scrolledUp) {
    return {
      pinned: false,
      userScrolledAway: true,
      lastScrollTop: event.scrollTop,
    };
  }
  return {
    ...state,
    pinned: state.userScrolledAway ? false : state.pinned,
    lastScrollTop: event.scrollTop,
  };
}

const TERMINAL_OPERATOR_STATUSES = new Set([
  "completed",
  "done",
  "failed",
  "limit",
  "cancelled",
  "stopped",
  "error",
]);

export function isTerminalOperatorStatus(status: string | null | undefined) {
  return TERMINAL_OPERATOR_STATUSES.has(String(status || "").toLowerCase());
}

export function shouldReleaseLiveShell({
  streamHold,
  operatorBusy,
  turnOpen,
  settledMessage,
  terminalStatus = null,
}: {
  streamHold: boolean;
  operatorBusy: boolean;
  turnOpen: boolean;
  settledMessage: AssistantChatMessage | null;
  terminalStatus?: string | null;
}) {
  return Boolean(
    streamHold &&
      !operatorBusy &&
      !turnOpen &&
      (hasSettledAssistantPayload(settledMessage) || isTerminalOperatorStatus(terminalStatus)),
  );
}

export function shouldReconcileOperatorCompletion({
  restTurnWasOpen,
  operatorBusy,
  activeTurn,
  lastMessage,
}: {
  restTurnWasOpen: boolean;
  operatorBusy: boolean;
  activeTurn: ActiveTurn;
  lastMessage?: AssistantChatMessage;
}) {
  const restStillOpen = isOperatorTurnOpen(activeTurn);
  return Boolean(
    restTurnWasOpen &&
    operatorBusy &&
    !restStillOpen &&
    lastMessage?.role === "assistant" &&
    lastMessage.content?.trim(),
  );
}

export type UseChatPageOperatorRuntimeParams = {
  activeChatId: number | null;
  lang: Lang;
  toast: ToastFn;
  queryClient: QueryClient;
  messages: AssistantChatMessage[];
  activeTurn: ActiveTurn;
  activeChat: AssistantChatSession | undefined;
  pendingUserText: string | null;
  pendingUserEpoch: number;
  pendingUserBaselineIds: readonly number[];
  setPendingUserText: Dispatch<SetStateAction<string | null>>;
  streamHold: boolean;
  setStreamHold: Dispatch<SetStateAction<boolean>>;
  setPendingSend: Dispatch<SetStateAction<string | null>>;
  pendingSend: string | null;
  pendingSendChatId: number | null;
  setActionWorkingId: Dispatch<SetStateAction<number | null>>;
  setDraft: Dispatch<SetStateAction<string>>;
  openSessionDock: OpenSessionDock;
  pushSessionLine: PushSessionLine;
  refreshChat: () => Promise<void>;
  scrollerRef: MutableRefObject<HTMLDivElement | null>;
  bottomSentinelRef?: MutableRefObject<HTMLDivElement | null>;
  atBottom: boolean;
  setAtBottom: Dispatch<SetStateAction<boolean>>;
  sendMutationPending: boolean;
  createChatMutationPending: boolean;
  providerBinding: ProviderBinding | null;
};

export function useChatPageOperatorRuntime({
  activeChatId,
  lang,
  toast,
  queryClient,
  messages,
  activeTurn,
  activeChat,
  pendingUserText,
  pendingUserEpoch,
  pendingUserBaselineIds,
  setPendingUserText,
  streamHold,
  setStreamHold,
  setPendingSend,
  pendingSend,
  pendingSendChatId,
  setActionWorkingId,
  setDraft,
  openSessionDock,
  pushSessionLine,
  refreshChat,
  scrollerRef,
  bottomSentinelRef,
  atBottom,
  setAtBottom,
  sendMutationPending,
  createChatMutationPending,
  providerBinding,
}: UseChatPageOperatorRuntimeParams) {
  const terminalRefreshRequestRef = useRef<Record<string, number>>({});
  const [terminalUserReconciliations, setTerminalUserReconciliations] =
    useState<Record<string, TerminalUserReconciliation>>({});
  const terminalUserReconciliation =
    terminalUserReconciliations[pendingChatKey(activeChatId)] ?? null;
  const refreshTerminalChat = useCallback(async () => {
    const key = pendingChatKey(activeChatId);
    const requestId = (terminalRefreshRequestRef.current[key] ?? 0) + 1;
    terminalRefreshRequestRef.current[key] = requestId;
    const epoch = pendingUserEpoch;
    const chatId = activeChatId;
    setTerminalUserReconciliations((current) => ({
      ...current,
      [key]: { chatId, epoch, status: "pending" },
    }));
    try {
      await refreshChat();
      if (terminalRefreshRequestRef.current[key] === requestId) {
        setTerminalUserReconciliations((current) => ({
          ...current,
          [key]: { chatId, epoch, status: "settled" },
        }));
      }
    } catch {
      if (terminalRefreshRequestRef.current[key] === requestId) {
        // Fail closed: an unresolved authoritative refresh must not let a late
        // row from turn A reconcile against retry B.
        setTerminalUserReconciliations((current) => ({
          ...current,
          [key]: { chatId, epoch, status: "failed" },
        }));
      }
    }
  }, [activeChatId, pendingUserEpoch, refreshChat]);

  // Handlers recreated each render; useOperatorChatWs stores them in a ref.
  const handlers = createChatOperatorHandlers({
    activeChatId,
    lang,
    toast,
    queryClient,
    messages,
    pendingUserText,
    setPendingUserText,
    setStreamHold,
    setPendingSend,
    setActionWorkingId,
    openSessionDock,
    pushSessionLine,
    refreshChat,
    refreshTerminalChat,
  });

  const operatorWs = useOperatorChatWs({
    chatId: activeChatId,
    enabled: Boolean(activeChatId),
    ...handlers,
  });
  const {
    busy: operatorBusy,
    hydrateFromSnapshot: hydrateOperatorSnapshot,
    ready: operatorReady,
    resetStream: resetOperatorStream,
    sendMessage: sendOperatorMessage,
    stopTurn: stopOperatorTurn,
    endTurn: finishOperatorTurn,
  } = operatorWs;
  const restTurnWasOpenRef = useRef(false);
  const atBottomRef = useRef(atBottom);
  const scrollPinStateRef = useRef<ScrollPinState>({
    pinned: atBottom,
    userScrolledAway: !atBottom,
    lastScrollTop: null,
  });
  const autoScrollFrameRef = useRef<number | null>(null);
  const scrollStateFrameRef = useRef<number | null>(null);
  const turnNonceRef = useRef(0);
  const turnStartSignalRef = useRef(false);
  const liveUserTextRef = useRef<string | null>(pendingUserText);
  const liveUserChatIdRef = useRef(activeChatId);
  const durableUserIdsRef = useRef(
    new Set(messages.filter((message) => message.role === "user").map((message) => message.id)),
  );
  const liveUserBaselineIdsRef = useRef(
    new Set(
      pendingUserText
        ? pendingUserBaselineIds
        : messages.filter((message) => message.role === "user").map((message) => message.id),
    ),
  );
  const pendingUserWasPresentRef = useRef(Boolean(pendingUserText));
  const pendingUserEpochRef = useRef(pendingUserEpoch);
  const [liveTurnIdentity, setLiveTurnIdentity] = useState<LiveTurnIdentity | null>(null);

  const newOptimisticUserTurn = isNewOptimisticUserTurn({
    pendingText: pendingUserText,
    wasPresent: pendingUserWasPresentRef.current,
    previousEpoch: pendingUserEpochRef.current,
    nextEpoch: pendingUserEpoch,
  });
  if (liveUserChatIdRef.current !== activeChatId) {
    liveUserChatIdRef.current = activeChatId;
    if (!pendingUserText || newOptimisticUserTurn) {
      liveUserTextRef.current = pendingUserText;
      durableUserIdsRef.current = new Set(
        messages.filter((message) => message.role === "user").map((message) => message.id),
      );
      liveUserBaselineIdsRef.current = new Set(
        pendingUserText ? pendingUserBaselineIds : durableUserIdsRef.current,
      );
    }
  } else if (!pendingUserText) {
    durableUserIdsRef.current = new Set(
      messages.filter((message) => message.role === "user").map((message) => message.id),
    );
  } else if (newOptimisticUserTurn) {
    liveUserTextRef.current = pendingUserText;
    durableUserIdsRef.current = new Set(
      messages.filter((message) => message.role === "user").map((message) => message.id),
    );
    liveUserBaselineIdsRef.current = new Set(pendingUserBaselineIds);
  }
  pendingUserWasPresentRef.current = Boolean(pendingUserText);
  pendingUserEpochRef.current = pendingUserEpoch;

  const turnOpen = isOperatorTurnOpen(activeTurn);
  const isBusy =
    sendMutationPending ||
    operatorWs.busy ||
    createChatMutationPending ||
    Boolean(pendingSend) ||
    turnOpen;
  // streamHold is deliberately excluded: it is the handoff tail of the old
  // turn. A new pending/busy edge during that tail must allocate a new key
  // before WebSocket startedAt or REST ids exist.
  const turnStartSignal = Boolean(isBusy || pendingUserText != null);
  if ((turnStartSignal && !turnStartSignalRef.current) || newOptimisticUserTurn) {
    turnNonceRef.current += 1;
  }
  turnStartSignalRef.current = turnStartSignal;
  const liveTurnNonce = turnNonceRef.current;
  const hasLiveTurnSignal = Boolean(
    isBusy ||
      streamHold ||
      operatorWs.streamText ||
      operatorWs.toolSteps.length > 0 ||
      operatorWs.livePlan ||
      operatorWs.errorMessage ||
      operatorWs.terminalStatus ||
      operatorWs.phase !== "idle",
  );

  useEffect(() => {
    atBottomRef.current = atBottom;
    scrollPinStateRef.current = atBottom
      ? reduceScrollPinState(scrollPinStateRef.current, { type: "pin" })
      : {
          ...scrollPinStateRef.current,
          pinned: false,
          userScrolledAway: true,
        };
  }, [atBottom]);

  useEffect(() => {
    setLiveTurnIdentity((previous) => reconcileLiveTurnIdentity(previous, {
      chatId: activeChatId,
      turnId: activeTurn?.turn_id ?? null,
      assistantMessageId: activeTurn?.assistant_message_id ?? null,
      startedAt: operatorWs.thinkingStartedAt,
      nonce: liveTurnNonce,
      keepLiveShell: hasLiveTurnSignal,
    }));
  }, [
    activeChatId,
    activeTurn?.assistant_message_id,
    activeTurn?.turn_id,
    hasLiveTurnSignal,
    liveTurnNonce,
    operatorWs.thinkingStartedAt,
  ]);

  const identityMatchesCurrentTurn = Boolean(
    liveTurnIdentity?.chatId === activeChatId &&
      liveTurnIdentity?.nonce === liveTurnNonce &&
      (activeTurn?.turn_id == null ||
        liveTurnIdentity?.turnId == null ||
        liveTurnIdentity.turnId === activeTurn.turn_id) &&
      (operatorWs.thinkingStartedAt == null ||
        liveTurnIdentity?.startedAt == null ||
        liveTurnIdentity.startedAt === operatorWs.thinkingStartedAt),
  );
  const trackedAssistantMessageId =
    activeTurn?.assistant_message_id ??
    (identityMatchesCurrentTurn ? liveTurnIdentity?.assistantMessageId : null) ??
    null;
  const durableLiveUserExists = liveUserTextRef.current
    ? hasNewDurableUserMessage(
        messages,
        liveUserTextRef.current,
        liveUserBaselineIdsRef.current,
      )
    : true;
  const allowAssistantFallback = pendingUserText == null && durableLiveUserExists;
  const inferredLiveMessage = useMemo(
    () => findLiveAssistantMessage(messages, trackedAssistantMessageId, {
      allowFallback: allowAssistantFallback,
    }),
    [allowAssistantFallback, messages, trackedAssistantMessageId],
  );
  const liveAssistantMessageId = trackedAssistantMessageId ?? inferredLiveMessage?.id ?? null;
  const settledLiveMessage = useMemo(
    () => findLiveAssistantMessage(messages, liveAssistantMessageId, {
      allowFallback: allowAssistantFallback,
    }),
    [allowAssistantFallback, messages, liveAssistantMessageId],
  );
  const liveTurnKey = hasLiveTurnSignal
    ? identityMatchesCurrentTurn && liveTurnIdentity
      ? liveTurnIdentity.key
      : activeChatId
        ? createLiveTurnKey(
            activeChatId,
            activeTurn?.turn_id ?? null,
            operatorWs.thinkingStartedAt,
            liveTurnNonce,
          )
        : `operator-turn-pending-${liveTurnNonce}`
    : null;

  // Resume mid-turn after navigation: hydrate from REST active_turn
  useEffect(() => {
    if (!turnOpen) return;
    // Snapshot merging is monotonic inside useOperatorChatWs: an empty or
    // shorter REST snapshot never clears a newer WebSocket buffer.
    hydrateOperatorSnapshot(String(activeTurn?.assistant_text || ""), {
      busy: true,
      iteration: activeTurn?.iteration,
    });
    setStreamHold(true);
  }, [
    activeTurn?.assistant_text,
    activeTurn?.iteration,
    activeTurn?.status,
    activeTurn?.turn_id,
    activeTurn?.busy,
    hydrateOperatorSnapshot,
    setStreamHold,
    turnOpen,
  ]);

  // WS completion is transient; REST is durable. If polling observed an open
  // turn and now sees no active turn plus the final assistant row, reconcile
  // the local busy flag instead of leaving the composer in «Пишет» forever.
  useEffect(() => {
    const restOpen = turnOpen;
    if (restOpen) {
      restTurnWasOpenRef.current = true;
      return;
    }
    if (shouldReconcileOperatorCompletion({
      restTurnWasOpen: restTurnWasOpenRef.current,
      operatorBusy,
      activeTurn,
      lastMessage: settledLiveMessage ?? messages[messages.length - 1],
    })) {
      restTurnWasOpenRef.current = false;
      finishOperatorTurn();
      setStreamHold(true);
      void refreshChat();
    } else if (!operatorBusy) {
      restTurnWasOpenRef.current = false;
    }
  }, [
    activeTurn,
    finishOperatorTurn,
    messages,
    operatorBusy,
    refreshChat,
    setStreamHold,
    settledLiveMessage,
    turnOpen,
  ]);

  // While turn runs (even after leaving/rejoining), poll history for progressive text
  useEffect(() => {
    if (!activeChatId) return;
    const turnBusy =
      operatorWs.busy ||
      streamHold ||
      Boolean(activeChat?.active_turn?.busy) ||
      activeChat?.active_turn?.status === "running" ||
      activeChat?.active_turn?.status === "resuming" ||
      activeChat?.active_turn?.status === "awaiting_async";
    if (!turnBusy) return;
    const t = window.setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", activeChatId] });
    }, 2500);
    return () => window.clearInterval(t);
  }, [
    activeChatId,
    operatorWs.busy,
    streamHold,
    activeChat?.active_turn?.busy,
    activeChat?.active_turn?.status,
    queryClient,
  ]);

  const handleScrollerScroll = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const previous = scrollPinStateRef.current;
    const next = reduceScrollPinState(previous, {
      type: "scroll",
      scrollTop: el.scrollTop,
      nearBottom: isScrollerNearBottom(el),
    });
    scrollPinStateRef.current = next;
    // Update the imperative gate synchronously so an already queued autoscroll
    // cannot pull the user back down after they start reading older messages.
    atBottomRef.current = next.pinned;
    if (previous.pinned && !next.pinned) {
      setAtBottom(false);
      return;
    }
    if (scrollStateFrameRef.current != null) return;
    scrollStateFrameRef.current = window.requestAnimationFrame(() => {
      scrollStateFrameRef.current = null;
      const next = atBottomRef.current;
      setAtBottom((current) => (current === next ? current : next));
    });
  }, [scrollerRef, setAtBottom]);

  /** Scroll only the message pane — never the page (scrollIntoView scrolls ancestors). */
  const scrollToEnd = useCallback((smooth = false) => {
    const el = scrollerRef.current;
    if (!el) return;
    scrollPinStateRef.current = reduceScrollPinState(scrollPinStateRef.current, {
      type: "pin",
      scrollTop: el.scrollTop,
    });
    atBottomRef.current = true;
    if (smooth && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      return;
    }
    el.scrollTop = el.scrollHeight;
    scrollPinStateRef.current = {
      ...scrollPinStateRef.current,
      lastScrollTop: el.scrollTop,
    };
  }, [scrollerRef]);

  const schedulePinnedScroll = useCallback(() => {
    if (!atBottomRef.current || autoScrollFrameRef.current != null) return;
    autoScrollFrameRef.current = window.requestAnimationFrame(() => {
      autoScrollFrameRef.current = null;
      // User scroll always wins, including when it happens after this frame
      // was scheduled but before the callback runs.
      if (!atBottomRef.current) return;
      scrollToEnd(false);
    });
  }, [scrollToEnd]);

  // Autoscroll only while pinned to bottom — never yank the view mid-reading
  useEffect(() => {
    schedulePinnedScroll();
  }, [
    messages.length,
    operatorWs.streamText,
    operatorWs.toolSteps.length,
    operatorWs.busy,
    operatorWs.phase,
    operatorWs.reasoningText,
    streamHold,
    pendingUserText,
    atBottom,
    schedulePinnedScroll,
  ]);

  useEffect(
    () => () => {
      if (autoScrollFrameRef.current != null) {
        window.cancelAnimationFrame(autoScrollFrameRef.current);
        autoScrollFrameRef.current = null;
      }
      if (scrollStateFrameRef.current != null) {
        window.cancelAnimationFrame(scrollStateFrameRef.current);
        scrollStateFrameRef.current = null;
      }
    },
    [],
  );

  // Chat switch always lands at the newest message.
  // Pending/stream state is chat-scoped; switching only resets scroll state.
  useEffect(() => {
    atBottomRef.current = true;
    scrollPinStateRef.current = reduceScrollPinState(scrollPinStateRef.current, {
      type: "pin",
      scrollTop: scrollerRef.current?.scrollTop ?? null,
    });
    setAtBottom(true);
    schedulePinnedScroll();
  }, [activeChatId, schedulePinnedScroll, scrollerRef, setAtBottom]);

  // Drop optimistic «отправляется…» bubble once the real user message is in history.
  // Sent payload may be enriched (pins / terminal trail) so exact content match fails —
  // that left a second stuck "sending" bubble next to the real one.
  useEffect(() => {
    if (!pendingUserText) return;
    const pending = pendingUserText.trim();
    if (!pending) {
      setPendingUserText(null);
      return;
    }
    if (hasNewDurableUserMessage(messages, pending, liveUserBaselineIdsRef.current)) {
      setPendingUserText(null);
      return;
    }
    // Safety: if operator is already working, the send landed — drop optimistic UI
    if (operatorBusy) {
      const anyMatch = hasNewDurableUserMessage(
        messages,
        pending,
        liveUserBaselineIdsRef.current,
      );
      if (anyMatch) setPendingUserText(null);
    }
  }, [messages, pendingUserText, operatorBusy, setPendingUserText]);

  // Preflight failures can happen before the server persists the user row.
  // Keep the optimistic bubble until the post-terminal REST refetch actually
  // settles. A fixed timeout can release retry B before a late durable row
  // from failed turn A arrives, which recreates the duplicate/handoff bug.
  useEffect(() => {
    if (!pendingUserText || pendingSend || operatorBusy || turnOpen) return;
    const terminal = String(operatorWs.terminalStatus || "").toLowerCase();
    const terminalBeforePersistence =
      Boolean(operatorWs.errorMessage) ||
      ["done", "completed", "error", "failed", "limit", "cancelled", "stopped"].includes(
        terminal,
      );
    if (!terminalBeforePersistence) return;
    const pending = pendingUserText;
    const hasDurableMatch = hasNewDurableUserMessage(
      messages,
      pending,
      liveUserBaselineIdsRef.current,
    );
    if (shouldReleaseRejectedOptimistic({
      pendingEpoch: pendingUserEpoch,
      pendingChatId: activeChatId,
      reconciliation: terminalUserReconciliation,
      hasDurableMatch,
    })) {
      setPendingUserText(null);
    }
  }, [
    messages,
    activeChatId,
    operatorBusy,
    operatorWs.errorMessage,
    operatorWs.terminalStatus,
    pendingSend,
    pendingUserEpoch,
    pendingUserText,
    setPendingUserText,
    terminalUserReconciliation,
    turnOpen,
  ]);

  // Keep the live shell mounted until the durable assistant row is available.
  // Clearing merely because local busy became false creates a blank frame when
  // REST polling lands after the final WebSocket event.
  useEffect(() => {
    if (!shouldReleaseLiveShell({
      // Reconnect snapshots may restore a parked turn without toggling the
      // controller-owned hold flag. Their restored text is still a live shell
      // and must reconcile through the same no-blank handoff.
      streamHold:
        streamHold ||
        Boolean(operatorWs.streamText) ||
        Boolean(operatorWs.errorMessage) ||
        Boolean(operatorWs.terminalStatus),
      operatorBusy,
      turnOpen,
      settledMessage: settledLiveMessage,
      terminalStatus: operatorWs.terminalStatus,
    })) {
      return;
    }
    const normalizedTerminal = String(operatorWs.terminalStatus || "").toLowerCase();
    const releaseDelay = hasSettledAssistantPayload(settledLiveMessage)
      ? 180
      : normalizedTerminal === "error"
        ? 2000
        : ["completed", "done"].includes(normalizedTerminal)
        ? 1800
        : 900;
    const timer = window.setTimeout(() => {
      // React batches these updates: the persisted bubble appears in the same
      // commit in which the live stream disappears.
      setStreamHold(false);
      resetOperatorStream();
    }, releaseDelay);
    return () => window.clearTimeout(timer);
  }, [
    operatorBusy,
    operatorWs.errorMessage,
    operatorWs.streamText,
    operatorWs.terminalStatus,
    resetOperatorStream,
    setStreamHold,
    settledLiveMessage,
    streamHold,
    turnOpen,
  ]);

  // After creating a new chat for streaming, send once WS is ready
  useEffect(() => {
    if (
      !isQueuedSendForActiveChat({ text: pendingSend, queuedChatId: pendingSendChatId, activeChatId }) ||
      !activeChatId ||
      !operatorReady
    ) return;
    const text = pendingSend;
    if (sendOperatorMessage(text, providerBinding)) {
      setDraft("");
      setPendingSend(null);
    }
  }, [
    pendingSend,
    pendingSendChatId,
    activeChatId,
    operatorReady,
    providerBinding,
    sendOperatorMessage,
    setDraft,
    setPendingSend,
  ]);

  // Show live operator row as soon as we're busy — even before first token
  const showLiveStream = hasLiveTurnSignal;

  // Prefer IntersectionObserver when the pane exposes its bottom sentinel.
  // Scroll-distance checks in handleScrollerScroll remain the fallback for
  // older callers and test environments without IntersectionObserver.
  useEffect(() => {
    const root = scrollerRef.current;
    const sentinel = bottomSentinelRef?.current;
    if (!root || !sentinel || typeof window.IntersectionObserver !== "function") return;

    const observer = new window.IntersectionObserver(
      ([entry]) => {
        const isIntersecting = Boolean(entry?.isIntersecting);
        const previous = scrollPinStateRef.current;
        const next = reduceScrollPinState(previous, {
          type: "layout",
          isIntersecting,
        });
        scrollPinStateRef.current = next;
        atBottomRef.current = next.pinned;
        if (next.pinned !== previous.pinned) {
          setAtBottom(next.pinned);
        }
        // A false entry while still pinned means the stream grew below the
        // viewport. Catch up in the shared rAF instead of treating it as a
        // manual scroll-away.
        if (!isIntersecting && next.pinned) schedulePinnedScroll();
      },
      {
        root,
        rootMargin: "0px 0px 80px 0px",
        threshold: 0.01,
      },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [
    activeChatId,
    bottomSentinelRef,
    messages.length,
    scrollerRef,
    schedulePinnedScroll,
    setAtBottom,
    showLiveStream,
  ]);

  // Current plan for the right-side task tracker: prefer the live plan, else the
  // most recent message that carries one (so it persists after the turn ends).
  const activePlan = useMemo<PlanData | null>(() => {
    const live = operatorWs.livePlan as PlanData | null;
    if (live && (live.steps?.length || 0) > 0) return live;
    for (let i = messages.length - 1; i >= 0; i--) {
      const plan = (messages[i]?.metadata as { plan?: PlanData } | undefined)?.plan;
      if (plan && (plan.steps?.length || 0) > 0) return plan;
    }
    return null;
  }, [operatorWs.livePlan, messages]);

  // The live WebSocket shell is the single renderer for this assistant turn.
  // Hide its REST counterpart even after progressive content/cards arrive;
  // settledLiveMessage lets the shell render that durable metadata in place.
  const displayMessages = useMemo(() => {
    return filterLiveAssistantMessage({
      messages,
      assistantMessageId: liveAssistantMessageId,
      keepLiveShell: showLiveStream || isBusy || streamHold,
    });
  }, [
    messages,
    liveAssistantMessageId,
    isBusy,
    streamHold,
    showLiveStream,
  ]);

  const operatorTurn = useMemo<OperatorTurnViewModel | null>(() => {
    if (!showLiveStream || !liveTurnKey) return null;
    return {
      key: liveTurnKey,
      turnId:
        activeTurn?.turn_id ??
        (identityMatchesCurrentTurn ? liveTurnIdentity?.turnId : null) ??
        null,
      assistantMessageId: liveAssistantMessageId,
      active: operatorBusy || turnOpen,
      reconciling: streamHold && !operatorBusy && !turnOpen,
      text:
        operatorWs.streamText ||
        String(activeTurn?.assistant_text || "") ||
        settledLiveMessage?.content ||
        "",
      phase: operatorWs.phase,
      startedAt: operatorWs.thinkingStartedAt,
      iteration: operatorWs.thinkingIteration,
      statusMessage: operatorWs.statusMessage,
      toolSteps: operatorWs.toolSteps,
      error: operatorWs.errorMessage,
      terminalStatus: operatorWs.terminalStatus,
      persistedMessage: settledLiveMessage,
    };
  }, [
    activeTurn?.assistant_text,
    activeTurn?.turn_id,
    identityMatchesCurrentTurn,
    liveAssistantMessageId,
    liveTurnIdentity?.turnId,
    liveTurnKey,
    operatorBusy,
    operatorWs.errorMessage,
    operatorWs.phase,
    operatorWs.statusMessage,
    operatorWs.streamText,
    operatorWs.terminalStatus,
    operatorWs.thinkingIteration,
    operatorWs.thinkingStartedAt,
    operatorWs.toolSteps,
    settledLiveMessage,
    showLiveStream,
    streamHold,
    turnOpen,
  ]);

  /** While tools load inventory or the model streams a markdown table — show matching skeleton. */
  const streamInventoryKind = useMemo(() => {
    if (!showLiveStream) return null;
    const names = operatorWs.toolSteps.map((s) => s.name);
    // Skeleton only for tools that usually attach inventory cards — not resolve/SSH/metrics.
    const inventoryTool = operatorWs.toolSteps.some((s) => {
      const n = s.name.toLowerCase();
      if (/resolve_server|server_info|server_metrics|run_command|run_fanout|metric_series/.test(n)) {
        return false;
      }
      return /list_servers|list_alerts|list_agents|agents\.list|fleet_status|server_forecasts|forecast|prediction|inventory/i.test(
        n,
      );
    });
    // Keep skeleton until final message replaces stream
    if (inventoryTool || hasMarkdownTable(operatorWs.streamText)) {
      return inferInventorySkeletonKind(names, operatorWs.streamText) || "list";
    }
    return null;
  }, [showLiveStream, operatorWs.toolSteps, operatorWs.streamText]);

  return {
    operatorWs,
    operatorBusy,
    operatorReady,
    sendOperatorMessage,
    stopOperatorTurn,
    handleScrollerScroll,
    scrollToEnd,
    turnOpen,
    isBusy,
    showLiveStream,
    operatorTurn,
    liveTurnKey,
    liveAssistantMessageId,
    settledLiveMessage,
    activePlan,
    displayMessages,
    streamInventoryKind,
  };
}
