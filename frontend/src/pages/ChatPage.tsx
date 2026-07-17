import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Bot,
  FileCode2,
  Loader2,
  MessageSquare,
  Plus,
  Radio,
  Search,
  Send,
  Shield,
  Sunrise,
} from "lucide-react";

import {
  cancelAssistantAction,
  confirmAssistantAction,
  createAssistantChat,
  fetchAssistantChat,
  fetchAssistantChats,
  requestDutyBriefing,
  sendAssistantChatMessage,
  startAssistantChat,
  updateAssistantChat,
  type AssistantAction,
  type AssistantChatMessage,
  type AssistantChatSession,
} from "@/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { ArtifactWorkbench } from "./chat-page/ArtifactWorkbench";
import { MessageBubble, PlanChecklist } from "./chat-page/ChatMessageViews";
import {
  hasMarkdownTable,
  inferInventorySkeletonKind,
  InventoryPanelSkeleton,
} from "./chat-page/InventoryPanelSkeleton";
import { OperatorMarkdown } from "./chat-page/OperatorMarkdown";
import { OperatorThinkingPanel } from "./chat-page/OperatorThinkingPanel";
import {
  ComposeCommandPalette,
  type ComposePaletteHandle,
  type PinnedServer,
  type PinnedUser,
} from "./chat-page/ComposeCommandPalette";
import { PinnedContextChips } from "./chat-page/PinnedContextChips";
import { QUICK_PROMPT_CARDS, formatDateTime, mergeTurnIntoChat, replaceActionInChat } from "./chat-page/chatHelpers";
import { parseOperatorCompose } from "./chat-page/operatorCompose";
import { useOperatorChatWs } from "./chat-page/useOperatorChatWs";


export default function ChatPage() {
  const { lang } = useI18n();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState("");
  const [caret, setCaret] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [chatFilter, setChatFilter] = useState("");
  const [pinnedServers, setPinnedServers] = useState<PinnedServer[]>([]);
  const [pinnedUsers, setPinnedUsers] = useState<PinnedUser[]>([]);
  /** Keep live stream shell visible until final message lands (avoids flash). */
  const [streamHold, setStreamHold] = useState(false);
  /** Optimistic user bubble until server history refreshes. */
  const [pendingUserText, setPendingUserText] = useState<string | null>(null);
  const [actionWorkingId, setActionWorkingId] = useState<number | null>(null);
  const [pendingSend, setPendingSend] = useState<string | null>(null);
  const [workbenchOpen, setWorkbenchOpen] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const paletteRef = useRef<ComposePaletteHandle | null>(null);
  const activeChatId = Number(searchParams.get("chat") || 0) || null;

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

  const chats = chatsQuery.data?.chats || [];
  const activeChat = activeChatQuery.data;
  const messages = activeChat?.messages || [];

  // Hydrate pins from session.pinned_context
  useEffect(() => {
    const pinned = activeChat?.pinned_context || {};
    const serversRaw = (pinned.servers || pinned.pinned_servers || []) as Array<{
      id?: number;
      name?: string;
      host?: string;
    }>;
    const usersRaw = (pinned.users || []) as Array<{ id?: number; username?: string }>;
    setPinnedServers(
      serversRaw
        .filter((s) => s && s.id && s.name)
        .map((s) => ({ id: Number(s.id), name: String(s.name), host: s.host ? String(s.host) : undefined })),
    );
    setPinnedUsers(
      usersRaw
        .filter((u) => u && u.id && u.username)
        .map((u) => ({ id: Number(u.id), username: String(u.username) })),
    );
  }, [activeChatId, activeChat?.pinned_context]);

  const persistPins = useCallback(
    async (servers: PinnedServer[], users: PinnedUser[]) => {
      if (!activeChatId) return;
      const pinned_context = {
        ...(activeChat?.pinned_context || {}),
        servers: servers.map((s) => ({ id: s.id, name: s.name, host: s.host || "" })),
        users: users.map((u) => ({ id: u.id, username: u.username })),
      };
      try {
        const updated = await updateAssistantChat(activeChatId, { pinned_context });
        queryClient.setQueryData(["assistant", "chat", activeChatId], (prev: AssistantChatSession | undefined) =>
          prev ? { ...prev, pinned_context: updated.pinned_context } : prev,
        );
      } catch {
        // best-effort — local chips still work for the message text
      }
    },
    [activeChatId, activeChat?.pinned_context, queryClient],
  );

  const pinServer = useCallback(
    (server: PinnedServer) => {
      setPinnedServers((prev) => {
        if (prev.some((p) => p.id === server.id)) return prev;
        const next = [...prev, server];
        void persistPins(next, pinnedUsers);
        return next;
      });
    },
    [persistPins, pinnedUsers],
  );

  const unpinServer = useCallback(
    (id: number) => {
      setPinnedServers((prev) => {
        const next = prev.filter((p) => p.id !== id);
        void persistPins(next, pinnedUsers);
        return next;
      });
    },
    [persistPins, pinnedUsers],
  );

  const pinUser = useCallback(
    (user: PinnedUser) => {
      setPinnedUsers((prev) => {
        if (prev.some((p) => p.id === user.id)) return prev;
        const next = [...prev, user];
        void persistPins(pinnedServers, next);
        return next;
      });
    },
    [persistPins, pinnedServers],
  );

  const unpinUser = useCallback(
    (id: number) => {
      setPinnedUsers((prev) => {
        const next = prev.filter((p) => p.id !== id);
        void persistPins(pinnedServers, next);
        return next;
      });
    },
    [persistPins, pinnedServers],
  );

  const refreshChat = useCallback(() => {
    if (activeChatId) {
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", activeChatId] });
    }
    void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
  }, [activeChatId, queryClient]);

  const operatorWs = useOperatorChatWs({
    chatId: activeChatId,
    enabled: Boolean(activeChatId),
    onConfirmRequired: (action) => {
      // Inject confirm card immediately — don't wait for slow refetch
      if (action && "id" in action && action.id) {
        queryClient.setQueryData<AssistantChatSession | undefined>(
          ["assistant", "chat", activeChatId],
          (previous) => replaceActionInChat(previous, action as AssistantAction),
        );
      }
      setStreamHold(true);
      refreshChat();
      setPendingUserText(null);
    },
    onActionUpdate: (action) => {
      queryClient.setQueryData<AssistantChatSession | undefined>(
        ["assistant", "chat", action.chat_id],
        (previous) => replaceActionInChat(previous, action),
      );
    },
    onTurnComplete: (payload) => {
      setStreamHold(true);
      // Merge confirm actions into cache before refetch lands
      if (payload?.actions?.length && activeChatId) {
        for (const action of payload.actions) {
          queryClient.setQueryData<AssistantChatSession | undefined>(
            ["assistant", "chat", activeChatId],
            (previous) => replaceActionInChat(previous, action),
          );
        }
      }
      refreshChat();
      setPendingSend(null);
      setPendingUserText(null);
    },
    onError: (message) => {
      toast({
        title: localize(lang, "Оператор", "Operator"),
        description: message,
        variant: "destructive",
      });
      setPendingSend(null);
      setStreamHold(false);
      setPendingUserText(null);
      refreshChat();
    },
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [
    messages.length,
    activeChatId,
    operatorWs.streamText,
    operatorWs.toolSteps.length,
    operatorWs.busy,
    operatorWs.phase,
    operatorWs.reasoningText,
    streamHold,
    pendingUserText,
  ]);

  // Drop optimistic user bubble once the real message is in history
  useEffect(() => {
    if (!pendingUserText) return;
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser && lastUser.content?.trim() === pendingUserText.trim()) {
      setPendingUserText(null);
    }
  }, [messages, pendingUserText]);

  // Drop held stream once the assistant message with inventory (or any new turn) is in the list.
  useEffect(() => {
    if (!streamHold) return;
    const last = messages[messages.length - 1];
    const tables = (last?.metadata as { tables?: Array<{ kind?: string }> } | undefined)?.tables;
    const hasInventory = Array.isArray(tables) && tables.some((t) => t.kind === "servers" || t.kind === "agents" || t.kind === "alerts" || Boolean(t.kind));
    const hasActions = Array.isArray(last?.metadata?.actions) && last.metadata.actions.length > 0;
    const assistantSettled =
      last?.role === "assistant" && Boolean(last.content || hasInventory || hasActions);
    if (assistantSettled || !operatorWs.busy) {
      const t = window.setTimeout(() => {
        setStreamHold(false);
        operatorWs.resetStream();
      }, assistantSettled ? 180 : 700);
      return () => window.clearTimeout(t);
    }
  }, [streamHold, messages, operatorWs.busy, operatorWs.resetStream]);

  // After creating a new chat for streaming, send once WS is ready
  useEffect(() => {
    if (!pendingSend || !activeChatId || !operatorWs.ready) return;
    const text = pendingSend;
    if (operatorWs.sendMessage(text)) {
      setDraft("");
      setPendingSend(null);
    }
  }, [pendingSend, activeChatId, operatorWs.ready, operatorWs.sendMessage]);

  const sendMutation = useMutation({
    mutationFn: (message: string) => (
      activeChatId ? sendAssistantChatMessage(activeChatId, message) : startAssistantChat(message)
    ),
    onSuccess: (turn) => {
      queryClient.setQueryData<AssistantChatSession>(
        ["assistant", "chat", turn.chat.id],
        (previous) => mergeTurnIntoChat(previous, turn),
      );
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
      setSearchParams({ chat: String(turn.chat.id) });
      setDraft("");
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Чат не ответил", "Chat failed"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
  });

  const createChatMutation = useMutation({
    mutationFn: () => createAssistantChat(),
    onSuccess: (chat) => {
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
      setSearchParams({ chat: String(chat.id) });
      // Persist pins chosen before the chat existed
      if (pinnedServers.length || pinnedUsers.length) {
        void updateAssistantChat(chat.id, {
          pinned_context: {
            servers: pinnedServers.map((s) => ({ id: s.id, name: s.name, host: s.host || "" })),
            users: pinnedUsers.map((u) => ({ id: u.id, username: u.username })),
          },
        }).then((updated) => {
          queryClient.setQueryData(["assistant", "chat", chat.id], {
            ...chat,
            ...updated,
            messages: chat.messages || [],
          });
        });
      }
    },
  });

  const actionMutation = useMutation({
    mutationFn: ({
      actionId,
      intent,
      typedConfirm,
    }: {
      actionId: number;
      intent: "confirm" | "cancel";
      typedConfirm?: string;
    }) => (
      intent === "confirm"
        ? confirmAssistantAction(actionId, typedConfirm)
        : cancelAssistantAction(actionId)
    ),
    onMutate: ({ actionId }) => {
      setActionWorkingId(actionId);
    },
    onSuccess: (action) => {
      queryClient.setQueryData<AssistantChatSession | undefined>(
        ["assistant", "chat", action.chat_id],
        (previous) => replaceActionInChat(previous, action),
      );
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", action.chat_id] });
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Действие не выполнено", "Action failed"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
    onSettled: () => {
      setActionWorkingId(null);
    },
  });

  const isBusy = sendMutation.isPending || operatorWs.busy || createChatMutation.isPending || Boolean(pendingSend);
  const selectedTitle = activeChat?.title || localize(lang, "Оператор", "Operator");
  const usageLabel = activeChat?.total_usage
    ? `${Number(activeChat.total_usage.input_tokens || 0) + Number(activeChat.total_usage.output_tokens || 0)} tok`
    : null;

  const filteredChats = useMemo(() => {
    const q = chatFilter.trim().toLowerCase();
    if (!q) return chats;
    return chats.filter((c) => String(c.title || "").toLowerCase().includes(q));
  }, [chats, chatFilter]);

  const lastAssistantHasInventory = useMemo(() => {
    const last = messages[messages.length - 1];
    if (!last || last.role !== "assistant") return false;
    const tables = (last.metadata as { tables?: Array<{ kind?: string; items?: unknown[] }> } | undefined)
      ?.tables;
    if (!Array.isArray(tables)) return false;
    return tables.some(
      (t) =>
        t.kind === "forecasts" ||
        ((t.kind === "servers" || t.kind === "agents" || t.kind === "alerts") &&
          Array.isArray(t.items) &&
          t.items.length > 0),
    );
  }, [messages]);

  // Show live operator row as soon as we're busy — even before first token
  const showLiveStream = Boolean(
    (operatorWs.busy ||
      streamHold ||
      operatorWs.streamText ||
      operatorWs.toolSteps.length > 0 ||
      operatorWs.livePlan ||
      operatorWs.phase !== "idle") &&
      !(streamHold && lastAssistantHasInventory && !operatorWs.busy),
  );

  /** While tools load inventory or the model streams a markdown table — show matching skeleton. */
  const streamInventoryKind = useMemo(() => {
    if (!showLiveStream) return null;
    const names = operatorWs.toolSteps.map((s) => s.name);
    const inventoryTool = operatorWs.toolSteps.some((s) =>
      /server|agent|alert|fleet|inventory|list_|forecast|prediction/i.test(s.name),
    );
    // Keep skeleton until final message replaces stream
    if (inventoryTool || hasMarkdownTable(operatorWs.streamText)) {
      return inferInventorySkeletonKind(names, operatorWs.streamText) || "list";
    }
    return null;
  }, [showLiveStream, operatorWs.toolSteps, operatorWs.streamText]);

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
    return text;
  };

  const dispatchMessage = (raw: string) => {
    const text = buildMessageWithPins(raw);
    if (!text.trim() || isBusy) return;

    // Instant feedback: show my message + thinking shell before server round-trip
    setPendingUserText(text);
    requestAnimationFrame(() => endRef.current?.scrollIntoView({ block: "end" }));
    setDraft("");
    setPaletteOpen(false);

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
    if (!raw || isBusy) return;
    dispatchMessage(raw);
  };

  const handleConfirm = (actionId: number, typedConfirm?: string) => {
    if (operatorWs.ready && operatorWs.confirmAction(actionId, typedConfirm)) {
      setActionWorkingId(actionId);
      return;
    }
    actionMutation.mutate({ actionId, intent: "confirm", typedConfirm });
  };

  const handleCancel = (actionId: number) => {
    if (operatorWs.ready && operatorWs.cancelAction(actionId)) {
      setActionWorkingId(actionId);
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

  return (
    <div className="relative flex h-[calc(100vh-4rem)] min-h-[620px] overflow-hidden bg-background md:h-screen">
      {/* subtle ops atmosphere */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          background:
            "radial-gradient(900px 420px at 12% -10%, hsl(var(--primary) / 0.07), transparent 55%), radial-gradient(700px 360px at 90% 0%, hsl(var(--ai, 199 89% 48%) / 0.05), transparent 50%)",
        }}
      />

      {/* ── Sidebar ── */}
      <aside className="relative z-[1] hidden w-[17.5rem] shrink-0 border-r border-border bg-card/60 lg:flex lg:flex-col">
        <div className="flex items-center justify-between gap-2 px-3.5 pb-2 pt-4">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="inline-flex h-5 w-5 items-center justify-center rounded-sm bg-primary/15 text-primary">
                <Radio className="h-3 w-3" strokeWidth={2.25} />
              </span>
              <h1 className="truncate font-display text-sm font-semibold tracking-tight text-foreground">
                {localize(lang, "Оператор", "Operator")}
              </h1>
            </div>
            <p className="mt-0.5 pl-6 text-[11px] text-muted-foreground/80">WebTerm</p>
          </div>
          <div className="flex items-center gap-1">
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 rounded-sm"
              onClick={() => {
                void requestDutyBriefing()
                  .then((res) => {
                    const id = res.chat?.id;
                    if (id) {
                      setSearchParams({ chat: String(id) });
                      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
                      void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", id] });
                    }
                    toast({
                      title: localize(lang, "Дежурный", "Duty"),
                      description: localize(lang, "Брифинг обновлён", "Briefing refreshed"),
                    });
                  })
                  .catch((error) => {
                    toast({
                      title: localize(lang, "Дежурный", "Duty"),
                      description: error instanceof Error ? error.message : String(error),
                      variant: "destructive",
                    });
                  });
              }}
              aria-label={localize(lang, "Брифинг дежурного", "Duty briefing")}
              title={localize(lang, "Брифинг дежурного", "Duty briefing")}
            >
              <Sunrise className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              className="h-8 w-8 rounded-sm"
              onClick={() => setSearchParams({})}
              aria-label={localize(lang, "Новый чат", "New chat")}
              title={localize(lang, "Новый чат", "New chat")}
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="px-3 pb-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/70" />
            <input
              value={chatFilter}
              onChange={(e) => setChatFilter(e.target.value)}
              placeholder={localize(lang, "Поиск…", "Search…")}
              className="h-8 w-full rounded-sm border border-border/50 bg-background/50 pl-8 pr-2.5 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-primary/40 focus:ring-1 focus:ring-primary/20"
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {chatsQuery.isLoading ? (
            <div className="flex items-center gap-2 px-3 py-4 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {localize(lang, "Загрузка", "Loading")}
            </div>
          ) : null}
          {!chatsQuery.isLoading && !filteredChats.length ? (
            <div className="mx-1 rounded-sm border border-dashed border-border/50 px-3 py-8 text-center text-xs text-muted-foreground">
              {chats.length
                ? localize(lang, "Ничего не найдено", "No matches")
                : localize(lang, "История пуста", "No history")}
            </div>
          ) : null}
          {filteredChats.map((chat) => {
            const selected = chat.id === activeChatId;
            return (
              <button
                key={chat.id}
                type="button"
                onClick={() => setSearchParams({ chat: String(chat.id) })}
                className={cn(
                  "mb-0.5 grid w-full min-w-0 grid-cols-[1.15rem_minmax(0,1fr)] gap-2 rounded-sm px-2.5 py-2 text-left transition-colors",
                  selected
                    ? "bg-primary/10 text-foreground shadow-[inset_2px_0_0_0_hsl(var(--primary))]"
                    : "text-muted-foreground hover:bg-foreground/[0.04] hover:text-foreground",
                )}
              >
                {chat.kind === "duty" ? (
                  <Shield className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" strokeWidth={1.75} />
                ) : (
                  <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-70" strokeWidth={1.75} />
                )}
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium tracking-tight">
                    {chat.title}
                  </span>
                  <span className="mt-0.5 block truncate font-mono text-[10px] tabular-nums text-muted-foreground/70">
                    {formatDateTime(chat.updated_at, lang)}
                    {chat.kind === "duty" ? (
                      <span className="ml-1.5 text-primary/80">{localize(lang, "duty", "duty")}</span>
                    ) : null}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </aside>

      {/* ── Main ── */}
      <section className="relative z-[1] flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-4 sm:px-5">
          <div className="min-w-0">
            <h2 className="truncate font-display text-[15px] font-semibold tracking-tight text-foreground">
              {selectedTitle}
            </h2>
            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    operatorWs.ready ? "bg-success" : "bg-muted-foreground/40",
                    isBusy && "animate-pulse bg-primary",
                  )}
                />
                {isBusy
                  ? localize(lang, "Работает…", "Working…")
                  : operatorWs.ready
                    ? localize(lang, "Live", "Live")
                    : localize(lang, "Подключение…", "Connecting…")}
              </span>
              {usageLabel ? <span className="font-mono tabular-nums opacity-70">{usageLabel}</span> : null}
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="ghost"
              className="h-8 gap-1.5 rounded-sm px-2.5 text-xs"
              disabled={!activeChatId}
              onClick={() => setWorkbenchOpen((v) => !v)}
              title={localize(lang, "Верстак артефактов", "Artifact workbench")}
            >
              <FileCode2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{localize(lang, "Верстак", "Workbench")}</span>
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-8 gap-1.5 rounded-sm px-2.5 text-xs lg:hidden"
              onClick={() => setSearchParams({})}
            >
              <Plus className="h-3.5 w-3.5" />
              {localize(lang, "Новый", "New")}
            </Button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto flex w-full max-w-[52rem] flex-col gap-4 px-4 py-6 sm:px-6">
            {!messages.length && !activeChatQuery.isLoading ? (
              <div className="mx-auto flex w-full max-w-md flex-col items-center pt-[18vh] text-center animate-in fade-in-0 duration-400">
                <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-sm border border-border/50 bg-card/50 text-muted-foreground">
                  <Bot className="h-4 w-4" strokeWidth={1.75} />
                </div>
                <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                  {localize(lang, "Оператор", "Operator")}
                </h2>
                <p className="mt-2 max-w-sm text-[13px] leading-5 text-muted-foreground">
                  {localize(
                    lang,
                    "Напиши задачу ниже — серверы, метрики, агенты, команды. / для палитры, @ для сервера.",
                    "Type a task below — servers, metrics, agents, commands. / for palette, @ for servers.",
                  )}
                </p>
                <div className="mt-6 grid w-full grid-cols-2 gap-2">
                  {QUICK_PROMPT_CARDS.map((card) => (
                    <button
                      key={card.id}
                      type="button"
                      onClick={() => dispatchMessage(lang === "ru" ? card.promptRu : card.promptEn)}
                      className="group rounded-sm border border-border bg-surface-1/60 px-3 py-2.5 text-left transition-colors hover:border-primary/50 hover:bg-surface-1"
                    >
                      <div className="text-xs font-semibold text-foreground">
                        {lang === "ru" ? card.labelRu : card.labelEn}
                      </div>
                      <div className="mt-0.5 text-2xs text-muted-foreground/70">
                        {lang === "ru" ? card.hintRu : card.hintEn}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {activeChatQuery.isLoading ? (
              <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {localize(lang, "Загрузка чата", "Loading chat")}
              </div>
            ) : null}

            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                actionWorkingId={actionWorkingId}
                onConfirmAction={handleConfirm}
                onCancelAction={handleCancel}
                onUndoAction={handleUndo}
                onSaveRunbook={handleSaveRunbook}
                serverPanelActions={{
                  pinnedIds: pinnedServers.map((s) => s.id),
                  onPin: pinServer,
                  onUnpin: unpinServer,
                  onAsk: (prompt) => dispatchMessage(prompt),
                }}
                agentPanelActions={{
                  onAsk: (prompt) => dispatchMessage(prompt),
                }}
                forecastPanelActions={{
                  onAsk: (prompt) => dispatchMessage(prompt),
                }}
              />
            ))}

            {pendingUserText ? (
              <div className="group flex justify-end gap-3 animate-in fade-in-0 slide-in-from-bottom-1 duration-200">
                <div className="min-w-0 max-w-[min(560px,85%)]">
                  <div className="rounded-sm rounded-br-md bg-primary px-3.5 py-2.5 text-[13px] font-medium leading-5 tracking-tight text-primary-foreground shadow-sm opacity-90">
                    <div className="whitespace-pre-wrap break-words">{pendingUserText}</div>
                  </div>
                  <div className="mt-1 pr-0.5 text-right text-[10px] text-muted-foreground/70">
                    {localize(lang, "отправляется…", "sending…")}
                  </div>
                </div>
              </div>
            ) : null}

            {showLiveStream || isBusy ? (
              <div className="grid grid-cols-[2rem_minmax(0,1fr)] gap-2.5 animate-in fade-in-0 duration-200">
                <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-sm border border-primary/20 bg-primary/10 text-primary">
                  {operatorWs.busy || isBusy ? (
                    <Activity className="h-3.5 w-3.5 animate-pulse" strokeWidth={1.75} />
                  ) : (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  )}
                </div>
                <div className="min-w-0 space-y-2 pt-0.5">
                  <div className="text-[11px] font-semibold tracking-tight text-foreground">
                    {localize(lang, "Оператор", "Operator")}
                  </div>

                  {(operatorWs.phase !== "idle" || isBusy) && !operatorWs.streamText ? (
                    <OperatorThinkingPanel
                      phase={operatorWs.phase === "idle" && isBusy ? "thinking" : operatorWs.phase}
                      startedAt={operatorWs.thinkingStartedAt ?? Date.now()}
                      toolSteps={operatorWs.toolSteps}
                    />
                  ) : null}

                  {operatorWs.streamText && (operatorWs.busy || operatorWs.phase !== "idle") ? (
                    <OperatorThinkingPanel
                      phase={operatorWs.phase === "idle" ? "streaming" : operatorWs.phase}
                      startedAt={operatorWs.thinkingStartedAt}
                      toolSteps={operatorWs.toolSteps}
                      compact
                    />
                  ) : null}

                  {operatorWs.livePlan ? <PlanChecklist plan={operatorWs.livePlan} /> : null}

                  {streamInventoryKind ? (
                    <InventoryPanelSkeleton
                      kind={streamInventoryKind}
                      rows={streamInventoryKind === "alerts" ? 4 : 5}
                    />
                  ) : null}

                  {operatorWs.streamText ? (
                    <div className="max-w-[min(640px,100%)]">
                      <OperatorMarkdown
                        content={operatorWs.streamText}
                        streaming={operatorWs.busy}
                        stripTables={Boolean(streamInventoryKind) || hasMarkdownTable(operatorWs.streamText)}
                      />
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}
            <div ref={endRef} className="h-2" />
          </div>
        </div>

        {/* ── Compose dock ── */}
        <form
          className="shrink-0 border-t border-border/40 bg-background/55 px-3 pb-3 pt-2 sm:px-5 sm:pb-4"
          onSubmit={(event) => {
            event.preventDefault();
            submitMessage();
          }}
        >
          <div className="relative mx-auto max-w-[52rem]">
            <PinnedContextChips
              servers={pinnedServers}
              users={pinnedUsers}
              onUnpinServer={unpinServer}
              onUnpinUser={unpinUser}
            />
            <ComposeCommandPalette
              ref={paletteRef}
              draft={draft}
              caret={caret}
              open={paletteOpen}
              onOpenChange={setPaletteOpen}
              onDraftChange={(next, nextCaret) => {
                setDraft(next);
                if (typeof nextCaret === "number") {
                  setCaret(nextCaret);
                  requestAnimationFrame(() => {
                    const el = textareaRef.current;
                    if (el) {
                      el.focus();
                      el.setSelectionRange(nextCaret, nextCaret);
                    }
                  });
                }
              }}
              onSendMessage={(message) => dispatchMessage(message)}
              pinnedServers={pinnedServers}
              pinnedUsers={pinnedUsers}
              onPinServer={pinServer}
              onUnpinServer={unpinServer}
              onPinUser={pinUser}
              onUnpinUser={unpinUser}
            />
            <div className="rounded-sm border border-border/55 bg-card/70 p-1.5 shadow-[0_8px_30px_-12px_rgba(0,0,0,0.45)] focus-within:border-primary/35 focus-within:shadow-[0_8px_30px_-10px_hsl(var(--primary)/0.18)]">
              <div className="flex items-end gap-1.5">
                <Textarea
                  ref={textareaRef}
                  value={draft}
                  onChange={(event) => {
                    setDraft(event.target.value);
                    setCaret(event.target.selectionStart || 0);
                  }}
                  onSelect={(event) => {
                    setCaret(event.currentTarget.selectionStart || 0);
                  }}
                  onClick={(event) => {
                    setCaret(event.currentTarget.selectionStart || 0);
                  }}
                  onKeyDown={(event) => {
                    if (paletteRef.current?.handleKeyDown(event)) {
                      event.preventDefault();
                      return;
                    }
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder={localize(
                    lang,
                    "Задача оператору…  / команды · @ сервер",
                    "Task for operator…  / commands · @ server",
                  )}
                  className="max-h-40 min-h-12 flex-1 resize-none border-0 bg-transparent px-3 py-2.5 text-[13.5px] leading-5 shadow-none focus-visible:ring-0"
                  disabled={isBusy}
                  rows={1}
                />
                <Button
                  type="submit"
                  size="icon"
                  className="mb-0.5 mr-0.5 h-10 w-10 shrink-0 rounded-sm"
                  disabled={!draft.trim() || isBusy}
                  aria-label={localize(lang, "Отправить", "Send")}
                  title={localize(lang, "Отправить · Enter", "Send · Enter")}
                >
                  {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            <div className="mt-1.5 flex items-center justify-between gap-2 px-1">
              <p className="font-mono text-[10px] text-muted-foreground/65">
                {localize(
                  lang,
                  "Enter — отправить · Shift+Enter — новая строка · / — палитра",
                  "Enter — send · Shift+Enter — newline · / — palette",
                )}
              </p>
              {isBusy ? (
                <span className="inline-flex items-center gap-1 text-[10px] text-primary">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  {localize(lang, "ждём ответ", "waiting")}
                </span>
              ) : null}
            </div>
          </div>
        </form>
      </section>

      <ArtifactWorkbench
        chatId={activeChatId}
        open={workbenchOpen}
        onClose={() => setWorkbenchOpen(false)}
      />
    </div>
  );
}
