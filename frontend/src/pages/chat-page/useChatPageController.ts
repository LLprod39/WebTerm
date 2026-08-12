import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  aiProviderQueryKeys,
  fetchAssistantChat,
  fetchAssistantChats,
  fetchAiProviderConnections,
  fetchAiProviderPools,
  updateAssistantChat,
  type AssistantChatMessage,
  type AssistantChatSession,
  type ProviderBinding,
} from "@/api";
import type { AuthSessionResponse } from "@/api/auth";
import { useToast } from "@/hooks/use-toast";
import { hasFeatureAccess } from "@/lib/featureAccess";
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

export function useChatPageController() {
  const { lang } = useI18n();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState("");
  const [caret, setCaret] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [chatFilter, setChatFilter] = useState("");
  /** Keep live stream shell visible until final message lands (avoids flash). */
  const [streamHold, setStreamHold] = useState(false);
  /** Optimistic user bubble until server history refreshes. */
  const [pendingUserText, setPendingUserText] = useState<string | null>(null);
  const [actionWorkingId, setActionWorkingId] = useState<number | null>(null);
  const [pendingSend, setPendingSend] = useState<string | null>(null);
  const [providerOverride, setProviderOverride] = useState("");
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
  const authData = queryClient.getQueryData<AuthSessionResponse>(["auth", "session"]);
  const canUseProviderPools = hasFeatureAccess(authData?.user, "ai_connections_admin");

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
  const providerConnectionsQuery = useQuery({
    queryKey: aiProviderQueryKeys.connections,
    queryFn: fetchAiProviderConnections,
    staleTime: 30_000,
  });
  const providerPoolsQuery = useQuery({
    queryKey: aiProviderQueryKeys.pools,
    queryFn: fetchAiProviderPools,
    enabled: canUseProviderPools,
    staleTime: 30_000,
  });

  const chats = useMemo(() => chatsQuery.data?.chats || [], [chatsQuery.data?.chats]);
  const activeChat = activeChatQuery.data;
  const messages = useMemo(() => activeChat?.messages || [], [activeChat?.messages]);
  const activeTurn = activeChat?.active_turn;
  const providerOptions = useMemo(() => [
    ...(providerConnectionsQuery.data?.connections ?? [])
      .filter((item) => item.access.interactive && item.status === "connected")
      .map((item) => ({
        key: `connection:${item.id}`,
        label: `${item.name} · ${item.target_id}`,
        binding: { target_id: item.target_id, connection_id: item.id } as ProviderBinding,
      })),
    ...(providerPoolsQuery.data?.pools ?? [])
      .filter((item) => item.enabled && item.members.some((member) => member.access?.interactive))
      .map((item) => ({
      key: `pool:${item.id}`,
      label: `${item.name} · пул`,
      binding: { target_id: item.target_id, pool_id: item.id } as ProviderBinding,
    })),
  ], [providerConnectionsQuery.data?.connections, providerPoolsQuery.data?.pools]);
  const selectedProviderBinding = useMemo(
    () => providerOptions.find((item) => item.key === providerOverride)?.binding ?? null,
    [providerOptions, providerOverride],
  );

  useEffect(() => {
    const binding = activeChat?.provider_binding;
    if (binding?.connection_id) setProviderOverride(`connection:${binding.connection_id}`);
    else if (binding?.pool_id) setProviderOverride(`pool:${binding.pool_id}`);
    else setProviderOverride("");
  }, [activeChatId, activeChat?.provider_binding]);

  const handleProviderOverrideChange = useCallback((nextValue: string) => {
    if (nextValue || !activeChatId) {
      setProviderOverride(nextValue);
      return;
    }
    void updateAssistantChat(activeChatId, { provider_binding: {} })
      .then((updated) => {
        queryClient.setQueryData(["assistant", "chat", activeChatId], (current: AssistantChatSession | undefined) => ({
          ...(current || updated),
          ...updated,
        }));
        setProviderOverride("");
      })
      .catch((error: unknown) => {
        toast({
          title: localize(lang, "Не удалось сбросить провайдера", "Could not reset provider"),
          description: error instanceof Error ? error.message : String(error),
          variant: "destructive",
        });
      });
  }, [activeChatId, lang, queryClient, toast]);

  const { pinnedServers, pinnedUsers, pinServer, unpinServer, unpinUser } = useChatPagePins({
    activeChatId,
    activeChat,
    queryClient,
  });

  const refreshChat = useCallback(() => {
    if (activeChatId) {
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", activeChatId] });
    }
    void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
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
    setActionWorkingId,
    setRenamingChatId,
    pinnedServers,
    pinnedUsers,
  });

  const {
    operatorWs,
    operatorReady,
    stopOperatorTurn,
    handleScrollerScroll,
    scrollToEnd,
    isBusy,
    showLiveStream,
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
    setPendingUserText,
    streamHold,
    setStreamHold,
    setPendingSend,
    pendingSend,
    setActionWorkingId,
    setDraft,
    openSessionDock,
    pushSessionLine,
    refreshChat,
    scrollerRef,
    atBottom,
    setAtBottom,
    sendMutationPending: sendMutation.isPending,
    createChatMutationPending: createChatMutation.isPending,
    providerBinding: selectedProviderBinding,
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
    if (!text.trim() || isBusy) return;

    // Instant feedback: show clean user text only.
    setPendingUserText(displayText);
    setAtBottom(true);
    setDraft("");
    setPaletteOpen(false);
    requestAnimationFrame(() => {
      const el = scrollerRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });

    // Prefer WS always for operator chat — HTTP path used to leave orphan user messages
    // when the loop failed mid-request. Queue until socket is ready after chat switch.
    if (!activeChatId) {
      setPendingSend(text);
      createChatMutation.mutate();
      return;
    }
    if (operatorWs.ready && operatorWs.sendMessage(text, selectedProviderBinding)) {
      return;
    }
    // Socket not ready yet (just switched chat / reconnecting) — queue for WS effect
    setPendingSend(text);
  };

  const submitMessage = () => {
    const raw = draft.trim();
    if (!raw || isBusy) return;
    dispatchMessage(raw);
  };

  const handleStop = useCallback(() => {
    setPendingSend(null);
    setPendingUserText(null);
    if (operatorReady) stopOperatorTurn();
  }, [operatorReady, stopOperatorTurn]);

  /** Re-send the latest user message (retry after error / weak answer). */
  const handleRetry = useCallback(() => {
    if (isBusy) return;
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser?.content?.trim()) {
      // Message already carries pinned context from the original send
      dispatchMessage(lastUser.content.trim(), { skipPins: true });
    }
  }, [isBusy, messages]); // eslint-disable-line react-hooks/exhaustive-deps

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
    pendingUserText,
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
    providerOptions,
    providerOverride,
    setProviderOverride: handleProviderOverrideChange,
    showLiveStream,
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
