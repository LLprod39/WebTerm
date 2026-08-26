import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchAssistantChat,
  fetchAssistantChats,
  updateAssistantChat,
  type AssistantChatMessage,
  type AssistantChatSession,
} from "@/api";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";

import type { ComposePaletteHandle } from "./ComposeCommandPalette";
import { LAST_CHAT_KEY, newSessionLine } from "./chatPageSession";
import { parseOperatorCompose } from "./operatorCompose";
import {
  EMPTY_OPERATOR_SESSION,
  type OperatorSessionLine,
  type OperatorSessionState,
} from "./operatorSessionTypes";
import { useChatPageMutations } from "./useChatPageMutations";
import { useChatPageOperatorRuntime } from "./useChatPageOperatorRuntime";
import { useChatPagePins } from "./useChatPagePins";
import {
  getScopedPending,
  promotePendingChat,
  setScopedPending,
  type ScopedPendingMap,
  type ScopedPendingSend,
  type ScopedPendingUser,
} from "./chatPendingState";

export function shouldDropOptimisticOnStop(pendingSend: string | null) {
  // A queued payload has not reached the socket yet. Once dispatched, the
  // optimistic row must stay until the matching durable REST message arrives.
  return pendingSend != null;
}

/**
 * Wait for the previous optimistic user row to reconcile before another turn.
 * Without a server-provided user-message id, a late identical row from turn A
 * cannot otherwise be distinguished from an immediate retry B.
 */
export function isOperatorSendBlocked(isBusy: boolean, pendingUserText: string | null) {
  return isBusy || Boolean(pendingUserText?.trim());
}

export function useChatPageController() {
  const { lang } = useI18n();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState("");
  const [caret, setCaret] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [chatFilter, setChatFilter] = useState("");
  /** Handoff tails are scoped so an active shell cannot flash in another chat. */
  const [streamHolds, setStreamHolds] = useState<ScopedPendingMap<boolean>>({});
  /** Optimistic and queued state is isolated per chat during navigation. */
  const pendingEpochRef = useRef(0);
  const [pendingUsers, setPendingUsers] = useState<ScopedPendingMap<ScopedPendingUser>>({});
  const [pendingSends, setPendingSends] = useState<ScopedPendingMap<ScopedPendingSend>>({});
  const [actionWorkingId, setActionWorkingId] = useState<number | null>(null);
  const [tasksPanelOpen, setTasksPanelOpen] = useState(true);
  /** True while the view is pinned to the newest message — gates autoscroll. */
  const [atBottom, setAtBottom] = useState(true);
  const [renamingChatId, setRenamingChatId] = useState<number | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [sessionDock, setSessionDock] = useState<OperatorSessionState>(EMPTY_OPERATOR_SESSION);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const paletteRef = useRef<ComposePaletteHandle | null>(null);
  const humanTrailRef = useRef<Array<{ cmd: string; at: number }>>([]);
  const activeChatId = Number(searchParams.get("chat") || 0) || null;
  const activePendingUser = getScopedPending(pendingUsers, activeChatId);
  const activePendingSend = getScopedPending(pendingSends, activeChatId);
  const pendingUserText = activePendingUser?.text ?? null;
  const pendingUserEpoch = activePendingUser?.epoch ?? 0;
  const pendingUserBaselineIds = activePendingUser?.baselineIds ?? [];
  const pendingSend = activePendingSend?.text ?? null;
  const streamHold = Boolean(getScopedPending(streamHolds, activeChatId));

  const setStreamHold = useCallback<Dispatch<SetStateAction<boolean>>>(
    (nextValue) => {
      setStreamHolds((current) => {
        const currentValue = Boolean(getScopedPending(current, activeChatId));
        const next = typeof nextValue === "function" ? nextValue(currentValue) : nextValue;
        return setScopedPending(current, activeChatId, next ? true : null);
      });
    },
    [activeChatId],
  );

  const setPendingUserText = useCallback<Dispatch<SetStateAction<string | null>>>(
    (nextValue) => {
      setPendingUsers((current) => {
        const scoped = getScopedPending(current, activeChatId);
        const currentText = scoped?.text ?? null;
        const nextText = typeof nextValue === "function" ? nextValue(currentText) : nextValue;
        if (nextText == null) return setScopedPending(current, activeChatId, null);
        const epoch = scoped?.epoch ?? (pendingEpochRef.current += 1);
        return setScopedPending(current, activeChatId, {
          chatId: activeChatId,
          text: nextText,
          epoch,
          baselineIds: scoped?.baselineIds ?? [],
        });
      });
    },
    [activeChatId],
  );

  const setPendingSend = useCallback<Dispatch<SetStateAction<string | null>>>(
    (nextValue) => {
      setPendingSends((current) => {
        const scoped = getScopedPending(current, activeChatId);
        const currentText = scoped?.text ?? null;
        const nextText = typeof nextValue === "function" ? nextValue(currentText) : nextValue;
        if (nextText == null) return setScopedPending(current, activeChatId, null);
        return setScopedPending(current, activeChatId, {
          chatId: activeChatId,
          text: nextText,
          epoch: activePendingUser?.epoch ?? scoped?.epoch ?? pendingEpochRef.current,
        });
      });
    },
    [activeChatId, activePendingUser?.epoch],
  );

  const promoteNewPendingChat = useCallback((chatId: number) => {
    setPendingUsers((current) => promotePendingChat(current, chatId));
    setPendingSends((current) => promotePendingChat(current, chatId));
    setStreamHolds((current) => {
      if (!getScopedPending(current, null)) return current;
      return setScopedPending(setScopedPending(current, null, null), chatId, true);
    });
  }, []);

  const openSessionDock = useCallback(
    (opts: { serverId: number; serverName?: string; host?: string; mode?: "agent" | "live" }) => {
      if (!opts.serverId || opts.serverId <= 0) return;
      setSessionDock((prev) => ({
        ...prev,
        open: true,
        serverId: opts.serverId,
        serverName: opts.serverName || prev.serverName || `server #${opts.serverId}`,
        host: opts.host || prev.host || "",
        mode: opts.mode || prev.mode || "agent",
        lines: prev.serverId === opts.serverId ? prev.lines : [],
      }));
    },
    [],
  );

  const pushSessionLine = useCallback((line: Omit<OperatorSessionLine, "id" | "at"> & { id?: string }) => {
    setSessionDock((prev) => {
      if (!prev.open) return prev;
      const next = [...prev.lines, newSessionLine(line)];
      return { ...prev, lines: next.slice(-200) };
    });
  }, []);

  const handleHumanCommand = useCallback(
    (cmd: string) => {
      const entry = { cmd, at: Date.now() };
      humanTrailRef.current = [...humanTrailRef.current, entry].slice(-30);
      setSessionDock((prev) => ({
        ...prev,
        humanTrail: humanTrailRef.current,
        lines: [
          ...prev.lines,
          newSessionLine({ source: "you", kind: "cmd", text: cmd }),
        ].slice(-200),
      }));
      // Persist a short trail for the model (merge into existing pins)
      if (activeChatId) {
        const trail = humanTrailRef.current.slice(-12);
        const prevPinned =
          (queryClient.getQueryData(["assistant", "chat", activeChatId]) as AssistantChatSession | undefined)
            ?.pinned_context || {};
        void updateAssistantChat(activeChatId, {
          pinned_context: {
            ...(typeof prevPinned === "object" && prevPinned ? prevPinned : {}),
            terminal_activity: {
              server_id: sessionDock.serverId,
              server_name: sessionDock.serverName,
              recent_commands: trail.map((t) => t.cmd),
              updated_at: new Date().toISOString(),
            },
          },
        }).catch(() => {
          /* best-effort */
        });
      }
    },
    [activeChatId, queryClient, sessionDock.serverId, sessionDock.serverName],
  );

  // Restore last chat when opening /chat without ?chat=
  useEffect(() => {
    if (searchParams.get("chat")) return;
    try {
      const saved = Number(localStorage.getItem(LAST_CHAT_KEY) || 0);
      if (saved > 0) {
        setSearchParams({ chat: String(saved) }, { replace: true });
      }
    } catch {
      // ignore storage errors
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Remember active dialog so leaving/returning continues the same session
  useEffect(() => {
    if (!activeChatId) return;
    try {
      localStorage.setItem(LAST_CHAT_KEY, String(activeChatId));
    } catch {
      // ignore
    }
  }, [activeChatId]);

  const resizeComposer = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(160, Math.max(48, el.scrollHeight))}px`;
  }, []);

  useEffect(() => {
    resizeComposer();
  }, [draft, resizeComposer]);

  const chatsQuery = useQuery({
    queryKey: ["assistant", "chats"],
    queryFn: fetchAssistantChats,
    staleTime: 20_000,
  });

  const activeChatQuery = useQuery({
    queryKey: ["assistant", "chat", activeChatId],
    queryFn: () => fetchAssistantChat(activeChatId as number),
    enabled: Boolean(activeChatId),
    staleTime: 10_000,
  });
  const chats = useMemo(() => chatsQuery.data?.chats || [], [chatsQuery.data?.chats]);
  const activeChat = activeChatQuery.data;
  const messages = useMemo(() => activeChat?.messages || [], [activeChat?.messages]);
  const activeTurn = activeChat?.active_turn;
  const {
    pinnedServers,
    pinnedUsers,
    pinServer,
    unpinServer,
    unpinUser,
    pinnedPlaybook,
  } = useChatPagePins({
    activeChatId,
    activeChat,
    queryClient,
  });

  const refreshChat = useCallback(async () => {
    const refreshes: Promise<unknown>[] = [];
    if (activeChatId) {
      refreshes.push(
        queryClient.invalidateQueries({ queryKey: ["assistant", "chat", activeChatId] }),
      );
    }
    refreshes.push(queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] }));
    await Promise.all(refreshes);
  }, [activeChatId, queryClient]);

  const {
    sendMutation,
    createChatMutation,
    actionMutation,
    renameMutation,
    deleteChatMutation,
  } = useChatPageMutations({
    activeChatId,
    lang,
    toast,
    queryClient,
    setSearchParams,
    setDraft,
    pendingUserText,
    setPendingUserText,
    setPendingSend,
    promoteNewPendingChat,
    setActionWorkingId,
    setRenamingChatId,
    pinnedServers,
    pinnedUsers,
    pinnedPlaybook,
  });

  const {
    operatorWs,
    operatorReady,
    stopOperatorTurn,
    handleScrollerScroll,
    scrollToEnd,
    isBusy,
    showLiveStream,
    operatorTurn,
    liveTurnKey,
    liveAssistantMessageId,
    settledLiveMessage,
    activePlan,
    displayMessages,
    streamInventoryKind,
  } = useChatPageOperatorRuntime({
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
    pendingSendChatId: activePendingSend?.chatId ?? null,
    setActionWorkingId,
    setDraft,
    openSessionDock,
    pushSessionLine,
    refreshChat,
    scrollerRef,
    bottomSentinelRef: endRef,
    atBottom,
    setAtBottom,
    sendMutationPending: sendMutation.isPending,
    createChatMutationPending: createChatMutation.isPending,
    providerBinding: null,
  });

  const sessionTokens = useMemo(() => {
    const usage = (activeChat?.total_usage || {}) as { input_tokens?: number; output_tokens?: number };
    const total = Number(usage.input_tokens || 0) + Number(usage.output_tokens || 0);
    if (!total) return null;
    return total >= 1000 ? `${(total / 1000).toFixed(total >= 10_000 ? 0 : 1)}k` : String(total);
  }, [activeChat?.total_usage]);

  const selectedTitle = activeChat?.title || localize(lang, "Оператор", "Operator");

  const filteredChats = useMemo(() => {
    const q = chatFilter.trim().toLowerCase();
    if (!q) return chats;
    return chats.filter((c) => String(c.title || "").toLowerCase().includes(q));
  }, [chats, chatFilter]);

  const chatGroups = useMemo(() => {
    const now = new Date();
    const dayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const DAY = 86_400_000;
    const buckets: Array<{ id: string; labelRu: string; labelEn: string; chats: AssistantChatSession[] }> = [
      { id: "today", labelRu: "Сегодня", labelEn: "Today", chats: [] },
      { id: "yesterday", labelRu: "Вчера", labelEn: "Yesterday", chats: [] },
      { id: "week", labelRu: "За неделю", labelEn: "This week", chats: [] },
      { id: "older", labelRu: "Раньше", labelEn: "Older", chats: [] },
    ];
    for (const chat of filteredChats) {
      const t = new Date(chat.updated_at).getTime();
      if (Number.isNaN(t) || t < dayStart - 6 * DAY) buckets[3].chats.push(chat);
      else if (t >= dayStart) buckets[0].chats.push(chat);
      else if (t >= dayStart - DAY) buckets[1].chats.push(chat);
      else buckets[2].chats.push(chat);
    }
    return buckets.filter((b) => b.chats.length > 0);
  }, [filteredChats]);

  // Deep-link: /chat?q=... or /chat?prompt=... pre-fills compose
  useEffect(() => {
    const prefill = searchParams.get("q") || searchParams.get("prompt") || "";
    if (prefill && !draft) {
      setDraft(prefill);
    }
  }, [searchParams]); // eslint-disable-line react-hooks/exhaustive-deps

  const buildMessageWithPins = (raw: string) => {
    const parsed = parseOperatorCompose(raw);
    let text = parsed.message;
    if (pinnedServers.length) {
      const names = pinnedServers.map((s) => `@${s.name}`).join(", ");
      if (!text.includes(names)) {
        text = `${text}\n\nКонтекст серверов: ${names} (ids: ${pinnedServers.map((s) => s.id).join(",")}).`;
      }
    }
    if (pinnedUsers.length) {
      text += `\nКонтекст пользователей: ${pinnedUsers.map((u) => u.username).join(", ")}.`;
    }
    if (pinnedPlaybook) {
      text += `\n\nКонтекст playbook: ${pinnedPlaybook.name} (playbook_id: ${pinnedPlaybook.id}).`;
    }
    // Human commands from the live side shell — operator must see them
    const trail = humanTrailRef.current.slice(-10);
    if (trail.length && sessionDock.serverId) {
      const lines = trail.map((t) => `- $ ${t.cmd}`).join("\n");
      text += `\n\n[Human terminal on ${sessionDock.serverName || `server #${sessionDock.serverId}`}]\n${lines}`;
    }
    return text;
  };

  const dispatchMessage = (raw: string, opts?: { skipPins?: boolean }) => {
    const displayText = raw.trim();
    // Enrich for the model (pins + human shell trail) — never show that junk in the bubble.
    const text = opts?.skipPins ? raw : buildMessageWithPins(raw);
    if (!text.trim() || isOperatorSendBlocked(isBusy, pendingUserText)) return;

    // Instant feedback: show clean user text only.
    const epoch = pendingEpochRef.current + 1;
    pendingEpochRef.current = epoch;
    setPendingUsers((current) => setScopedPending(current, activeChatId, {
      chatId: activeChatId,
      text: displayText,
      epoch,
      baselineIds: messages.filter((message) => message.role === "user").map((message) => message.id),
    }));
    setAtBottom(true);
    setDraft("");
    setPaletteOpen(false);
    requestAnimationFrame(() => scrollToEnd(true));

    // Prefer WS always for operator chat — HTTP path used to leave orphan user messages
    // when the loop failed mid-request. Queue until socket is ready after chat switch.
    if (!activeChatId) {
      setPendingSend(text);
      createChatMutation.mutate();
      return;
    }
    if (operatorWs.ready && operatorWs.sendMessage(text)) {
      return;
    }
    // Socket not ready yet (just switched chat / reconnecting) — queue for WS effect
    setPendingSend(text);
  };

  const submitMessage = () => {
    const raw = draft.trim();
    if (!raw || isOperatorSendBlocked(isBusy, pendingUserText)) return;
    dispatchMessage(raw);
  };

  const handleStop = useCallback(() => {
    const queuedOnly = shouldDropOptimisticOnStop(pendingSend);
    setPendingSend(null);
    if (queuedOnly) setPendingUserText(null);
    if (!queuedOnly && operatorReady) stopOperatorTurn();
  }, [operatorReady, pendingSend, setPendingSend, setPendingUserText, stopOperatorTurn]);

  /** Re-send the latest user message (retry after error / weak answer). */
  const handleRetry = useCallback(() => {
    if (isOperatorSendBlocked(isBusy, pendingUserText)) return;
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser?.content?.trim()) {
      // Message already carries pinned context from the original send
      dispatchMessage(lastUser.content.trim(), { skipPins: true });
    }
  }, [isBusy, messages, pendingUserText]); // eslint-disable-line react-hooks/exhaustive-deps

  const startRename = (chat: AssistantChatSession) => {
    setRenamingChatId(chat.id);
    setRenameDraft(chat.title || "");
  };

  const commitRename = () => {
    const title = renameDraft.trim();
    if (renamingChatId && title) {
      renameMutation.mutate({ chatId: renamingChatId, title });
    } else {
      setRenamingChatId(null);
    }
  };

  const handleConfirm = (actionId: number, typedConfirm?: string) => {
    if (operatorWs.ready && operatorWs.confirmAction(actionId, typedConfirm)) {
      setActionWorkingId(actionId);
      setStreamHold(true);
      // Keep the existing bubble; only show a quiet "working" state on the card.
      return;
    }
    actionMutation.mutate({ actionId, intent: "confirm", typedConfirm });
  };

  const handleCancel = (actionId: number) => {
    if (operatorWs.ready && operatorWs.cancelAction(actionId)) {
      setActionWorkingId(actionId);
      setStreamHold(true);
      return;
    }
    actionMutation.mutate({ actionId, intent: "cancel" });
  };

  const handleUndo = (actionId: number) => {
    const text = localize(
      lang,
      `Откати действие #${actionId} через operator.undo_last`,
      `Undo action #${actionId} via operator.undo_last`,
    );
    if (activeChatId && operatorWs.ready && operatorWs.sendMessage(text)) return;
    if (activeChatId) sendMutation.mutate(text);
  };

  const handleSaveRunbook = (message: AssistantChatMessage) => {
    const steps = (message.metadata.actions || [])
      .filter((a) => a.status === "completed" && a.risk !== "read")
      .map((a) => {
        const cmd = (a.input as { command?: string; cmd?: string })?.command
          || (a.input as { command?: string; cmd?: string })?.cmd
          || a.action_type;
        return { command: String(cmd), description: a.title || a.action_type };
      });
    const title = `runbook-${new Date().toISOString().slice(0, 10)}`;
    const text = localize(
      lang,
      `Сохрани как runbook «${title}» шаги: ${JSON.stringify(steps)}`,
      `Save as runbook "${title}" steps: ${JSON.stringify(steps)}`,
    );
    if (activeChatId && operatorWs.ready && operatorWs.sendMessage(text)) return;
    if (activeChatId) sendMutation.mutate(text);
  };

  // Hide starter cards the moment a send is in flight — don't wait for history.
  const hasConversationContent =
    messages.length > 0 || Boolean(pendingUserText) || Boolean(pendingSend) || showLiveStream;
  const showEmptyStarter =
    !activeChatQuery.isLoading && !hasConversationContent && !pendingUserText && !pendingSend;

  const clearLastChatAndNew = useCallback(() => {
    try {
      localStorage.removeItem(LAST_CHAT_KEY);
    } catch {
      // ignore
    }
    setSearchParams({});
  }, [setSearchParams]);

  return {
    lang,
    toast,
    queryClient,
    setSearchParams,
    draft,
    setDraft,
    caret,
    setCaret,
    paletteOpen,
    setPaletteOpen,
    chatFilter,
    setChatFilter,
    pinnedServers,
    pinnedUsers,
    pinnedPlaybook,
    pendingUserText,
    pendingUserEpoch,
    pendingUserBaselineIds,
    actionWorkingId,
    tasksPanelOpen,
    setTasksPanelOpen,
    atBottom,
    setAtBottom,
    renamingChatId,
    setRenamingChatId,
    renameDraft,
    setRenameDraft,
    sessionDock,
    setSessionDock,
    scrollerRef,
    endRef,
    textareaRef,
    paletteRef,
    activeChatId,
    openSessionDock,
    handleHumanCommand,
    chatsQuery,
    activeChatQuery,
    chats,
    activeChat,
    pinServer,
    unpinServer,
    unpinUser,
    operatorWs,
    handleScrollerScroll,
    scrollToEnd,
    isBusy,
    selectedTitle,
    filteredChats,
    chatGroups,
    sessionTokens,
    showLiveStream,
    operatorTurn,
    liveTurnKey,
    liveAssistantMessageId,
    settledLiveMessage,
    activePlan,
    displayMessages,
    streamInventoryKind,
    dispatchMessage,
    submitMessage,
    handleStop,
    handleRetry,
    deleteChatMutation,
    startRename,
    commitRename,
    handleConfirm,
    handleCancel,
    handleUndo,
    handleSaveRunbook,
    showEmptyStarter,
    clearLastChatAndNew,
  };
}

export type ChatPageController = ReturnType<typeof useChatPageController>;
