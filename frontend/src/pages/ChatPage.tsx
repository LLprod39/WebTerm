import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  Bot,
  Check,
  ListChecks,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  Search,
  Send,
  Shield,
  Square,
  Sunrise,
  Trash2,
  X,
} from "lucide-react";

import {
  cancelAssistantAction,
  confirmAssistantAction,
  createAssistantChat,
  deleteAssistantChat,
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

import { PlanTasksPanel, type PlanData } from "./chat-page/PlanTasksPanel";
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
import { OperatorSessionDock } from "./chat-page/OperatorSessionDock";
import {
  EMPTY_OPERATOR_SESSION,
  isSshToolName,
  type OperatorSessionLine,
  type OperatorSessionState,
} from "./chat-page/operatorSessionTypes";
import { useOperatorChatWs } from "./chat-page/useOperatorChatWs";

const LAST_CHAT_KEY = "operator_last_chat_id";

function newSessionLine(
  partial: Omit<OperatorSessionLine, "id" | "at"> & { id?: string; at?: number },
): OperatorSessionLine {
  return {
    id: partial.id || `L-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    at: partial.at || Date.now(),
    source: partial.source,
    kind: partial.kind,
    text: partial.text,
  };
}

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
    onSshSession: (payload) => {
      const sid = Number(payload.server_id || 0);
      if (sid <= 0) return;
      openSessionDock({
        serverId: sid,
        serverName: String(payload.server_name || ""),
        host: String(payload.host || ""),
        mode: "agent",
      });
      const cmd = String(payload.command || payload.cmd || "").trim();
      if (cmd) {
        pushSessionLine({ source: "agent", kind: "cmd", text: cmd });
      } else {
        pushSessionLine({
          source: "system",
          kind: "note",
          text: localize(lang, "SSH-активность…", "SSH activity…"),
        });
      }
    },
    onToolResultDetail: (payload) => {
      // Side dock is SSH-only. Metrics / resolve / inventory must never open it
      // or dump JSON as "session opened".
      const name = String(payload.name || payload.action_type || "");
      if (!isSshToolName(name)) return;
      const sid = Number(payload.server_id || 0);
      if (sid > 0) {
        openSessionDock({
          serverId: sid,
          serverName: String(payload.server_name || ""),
          host: String(payload.host || ""),
          mode: "agent",
        });
      }
      const cmd = String(payload.command || payload.cmd || "").trim();
      if (cmd) pushSessionLine({ source: "agent", kind: "cmd", text: cmd });
      const out = String(payload.output || "").trim();
      if (out) {
        pushSessionLine({
          source: "agent",
          kind: payload.ok === false ? "err" : "out",
          text: out.slice(0, 4000),
        });
      }
    },
    onConfirmRequired: (action) => {
      // Inject confirm card immediately — don't wait for slow refetch
      if (action && "id" in action && action.id) {
        queryClient.setQueryData<AssistantChatSession | undefined>(
          ["assistant", "chat", activeChatId],
          (previous) => replaceActionInChat(previous, action as AssistantAction),
        );
        const input = (action as AssistantAction).input || {};
        const sid = Number((input as { server_id?: number }).server_id || 0);
        if (sid > 0 && isSshToolName(String((action as AssistantAction).action_type || ""))) {
          openSessionDock({
            serverId: sid,
            serverName: String((input as { server_name?: string }).server_name || ""),
            mode: "agent",
          });
          const cmd = String((input as { command?: string; cmd?: string }).command || (input as { cmd?: string }).cmd || "");
          if (cmd) {
            pushSessionLine({
              source: "agent",
              kind: "cmd",
              text: cmd,
            });
            pushSessionLine({
              source: "system",
              kind: "note",
              text: localize(lang, "ждёт подтверждения…", "awaiting confirm…"),
            });
          }
        }
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
      if (action.status === "completed" || action.status === "failed" || action.status === "cancelled" || action.status === "running") {
        setActionWorkingId((cur) => (cur === action.id ? null : cur));
      }
      // After confirmed SSH tool — show output in dock
      if (action.status === "completed" || action.status === "failed") {
        const result = (action.result || {}) as Record<string, unknown>;
        const sid = Number(result.server_id || (action.input as { server_id?: number })?.server_id || 0);
        if (sid > 0 && isSshToolName(String(action.action_type || ""))) {
          openSessionDock({
            serverId: sid,
            serverName: String(result.server_name || ""),
            mode: "agent",
          });
          const cmd = String(
            result.command ||
              (action.input as { command?: string; cmd?: string })?.command ||
              (action.input as { cmd?: string })?.cmd ||
              "",
          );
          if (cmd) pushSessionLine({ source: "agent", kind: "cmd", text: cmd });
          const out = String(result.output || result.error || "");
          if (out) {
            pushSessionLine({
              source: "agent",
              kind: action.status === "failed" ? "err" : "out",
              text: out.slice(0, 4000),
            });
          }
        }
      }
    },
    onTurnComplete: (payload) => {
      setStreamHold(true);
      setActionWorkingId(null);
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
    onSnapshot: (payload) => {
      if (payload.userText && !pendingUserText) {
        // User already in history after reconnect — only show optimistic if missing
        const hasUser = messages.some(
          (m) => m.role === "user" && m.content?.trim() === payload.userText?.trim(),
        );
        if (!hasUser && payload.busy) setPendingUserText(payload.userText);
      }
      if (payload.busy) setStreamHold(true);
      if (payload.action && "id" in payload.action && payload.action.id) {
        queryClient.setQueryData<AssistantChatSession | undefined>(
          ["assistant", "chat", activeChatId],
          (previous) => replaceActionInChat(previous, payload.action as AssistantAction),
        );
      }
      if (payload.busy || payload.status === "awaiting_confirm") {
        refreshChat();
      }
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
  const {
    busy: operatorBusy,
    hydrateFromSnapshot: hydrateOperatorSnapshot,
    ready: operatorReady,
    resetStream: resetOperatorStream,
    sendMessage: sendOperatorMessage,
    stopTurn: stopOperatorTurn,
    streamText: operatorStreamText,
  } = operatorWs;

  // Resume mid-turn after navigation: hydrate from REST active_turn
  useEffect(() => {
    const turn = activeTurn;
    if (!turn) return;
    if (turn.busy || turn.status === "running" || turn.status === "resuming" || turn.status === "awaiting_async") {
      const text = String(turn.assistant_text || "");
      // Prefer longer server text (poll progress) over a short local stream buffer
      if (!operatorStreamText || text.length >= operatorStreamText.length) {
        hydrateOperatorSnapshot(text, {
          busy: true,
          iteration: turn.iteration,
        });
      } else {
        hydrateOperatorSnapshot(operatorStreamText, {
          busy: true,
          iteration: turn.iteration,
        });
      }
      setStreamHold(true);
    }
  }, [
    activeTurn,
    hydrateOperatorSnapshot,
    operatorStreamText,
  ]);

  // While turn runs (even after leaving/rejoining), poll history for progressive text
  useEffect(() => {
    if (!activeChatId) return;
    const turnBusy =
      operatorWs.busy ||
      Boolean(activeChat?.active_turn?.busy) ||
      activeChat?.active_turn?.status === "running" ||
      activeChat?.active_turn?.status === "resuming";
    if (!turnBusy) return;
    const t = window.setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", activeChatId] });
    }, 2500);
    return () => window.clearInterval(t);
  }, [
    activeChatId,
    operatorWs.busy,
    activeChat?.active_turn?.busy,
    activeChat?.active_turn?.status,
    queryClient,
  ]);

  const handleScrollerScroll = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    setAtBottom(distance < 80);
  }, []);

  /** Scroll only the message pane — never the page (scrollIntoView scrolls ancestors). */
  const scrollToEnd = useCallback((smooth = false) => {
    const el = scrollerRef.current;
    if (!el) return;
    if (smooth && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      return;
    }
    el.scrollTop = el.scrollHeight;
  }, []);

  // Autoscroll only while pinned to bottom — never yank the view mid-reading
  useEffect(() => {
    if (!atBottom) return;
    // rAF so DOM has the new bubble/stream height before we jump.
    const id = window.requestAnimationFrame(() => scrollToEnd(false));
    return () => window.cancelAnimationFrame(id);
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
    scrollToEnd,
  ]);

  // Chat switch always lands at the newest message.
  // Keep pendingSend/pendingUserText — new-chat create assigns an id and
  // needs those to survive so the first message still goes out.
  useEffect(() => {
    setAtBottom(true);
    setStreamHold(false);
    const id = window.requestAnimationFrame(() => scrollToEnd(false));
    return () => window.cancelAnimationFrame(id);
  }, [activeChatId, scrollToEnd]);

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
    const matchesPending = (raw: string) => {
      const stored = (raw || "").trim();
      if (!stored) return false;
      if (stored === pending) return true;
      if (stored.startsWith(pending)) return true;
      // Strip backend-only context blocks before compare
      const head = stored
        .split(/\n\nКонтекст серверов:|\n\n\[Human terminal on |\nКонтекст пользователей:/)[0]
        .trim();
      return head === pending || head.startsWith(pending) || pending.startsWith(head);
    };
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser && matchesPending(lastUser.content || "")) {
      setPendingUserText(null);
      return;
    }
    // Safety: if operator is already working, the send landed — drop optimistic UI
    if (operatorBusy) {
      const anyMatch = messages.some((m) => m.role === "user" && matchesPending(m.content || ""));
      if (anyMatch) setPendingUserText(null);
    }
  }, [messages, pendingUserText, operatorBusy]);

  // Drop held stream once the assistant message with inventory (or any new turn) is in the list.
  useEffect(() => {
    if (!streamHold) return;
    const last = messages[messages.length - 1];
    const tables = (last?.metadata as { tables?: Array<{ kind?: string }> } | undefined)?.tables;
    const hasInventory = Array.isArray(tables) && tables.some((t) => t.kind === "servers" || t.kind === "agents" || t.kind === "alerts" || Boolean(t.kind));
    const hasActions = Array.isArray(last?.metadata?.actions) && last.metadata.actions.length > 0;
    const assistantSettled =
      last?.role === "assistant" && Boolean(last.content || hasInventory || hasActions);
    if (assistantSettled || !operatorBusy) {
      const t = window.setTimeout(() => {
        setStreamHold(false);
        resetOperatorStream();
      }, assistantSettled ? 180 : 700);
      return () => window.clearTimeout(t);
    }
  }, [streamHold, messages, operatorBusy, resetOperatorStream]);

  // After creating a new chat for streaming, send once WS is ready
  useEffect(() => {
    if (!pendingSend || !activeChatId || !operatorReady) return;
    const text = pendingSend;
    if (sendOperatorMessage(text)) {
      setDraft("");
      setPendingSend(null);
    }
  }, [pendingSend, activeChatId, operatorReady, sendOperatorMessage]);

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

  const sessionTokens = useMemo(() => {
    const usage = (activeChat?.total_usage || {}) as { input_tokens?: number; output_tokens?: number };
    const total = Number(usage.input_tokens || 0) + Number(usage.output_tokens || 0);
    if (!total) return null;
    return total >= 1000 ? `${(total / 1000).toFixed(total >= 10_000 ? 0 : 1)}k` : String(total);
  }, [activeChat?.total_usage]);

  const turnOpen =
    Boolean(activeTurn?.busy) ||
    activeTurn?.status === "running" ||
    activeTurn?.status === "resuming" ||
    activeTurn?.status === "awaiting_async";
  const isBusy =
    sendMutation.isPending ||
    operatorWs.busy ||
    createChatMutation.isPending ||
    Boolean(pendingSend) ||
    turnOpen;
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
      turnOpen ||
      operatorWs.streamText ||
      operatorWs.toolSteps.length > 0 ||
      operatorWs.livePlan ||
      operatorWs.phase !== "idle") &&
      !(streamHold && lastAssistantHasInventory && !operatorWs.busy && !turnOpen),
  );

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

  // While streaming a brand-new empty assistant row, hide the DB stub and show
  // the live stream. Never hide a settled bubble (content / actions / tables) —
  // that was wiping the whole answer on confirm and looking like "messages gone".
  const displayMessages = useMemo(() => {
    const turn = activeTurn;
    const liveAssistantId = turn?.assistant_message_id;
    if (!liveAssistantId) return messages;
    if (!(isBusy || streamHold || showLiveStream)) return messages;

    const status = String(turn?.status || "");
    if (status === "awaiting_confirm" || status === "awaiting_async") {
      return messages;
    }

    const dbMsg = messages.find((m) => m.id === liveAssistantId);
    if (dbMsg) {
      const actions = dbMsg.metadata?.actions;
      const tables = (dbMsg.metadata as { tables?: unknown[] } | undefined)?.tables;
      const hasActions = Array.isArray(actions) && actions.length > 0;
      const hasTables = Array.isArray(tables) && tables.length > 0;
      const hasBody = Boolean((dbMsg.content || "").trim());
      if (hasActions || hasTables || hasBody) {
        return messages;
      }
    }

    // Empty/stub assistant row still being filled by the live stream
    return messages.filter((m) => m.id !== liveAssistantId);
  }, [
    messages,
    activeTurn,
    isBusy,
    streamHold,
    showLiveStream,
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

  const renameMutation = useMutation({
    mutationFn: ({ chatId, title }: { chatId: number; title: string }) =>
      updateAssistantChat(chatId, { title }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
      if (activeChatId) {
        void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", activeChatId] });
      }
      setRenamingChatId(null);
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Не удалось переименовать", "Rename failed"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
  });

  const deleteChatMutation = useMutation({
    mutationFn: (chatId: number) => deleteAssistantChat(chatId),
    onSuccess: (_res, chatId) => {
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
      queryClient.removeQueries({ queryKey: ["assistant", "chat", chatId] });
      if (chatId === activeChatId) {
        try {
          localStorage.removeItem(LAST_CHAT_KEY);
        } catch {
          // ignore
        }
        setSearchParams({});
      }
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Не удалось удалить чат", "Delete failed"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
  });

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
  // Still show them for a brand-new / empty session even if a previous turn flag
  // left isBusy briefly true without any messages.
  const hasConversationContent =
    messages.length > 0 || Boolean(pendingUserText) || Boolean(pendingSend) || showLiveStream;
  const showEmptyStarter =
    !activeChatQuery.isLoading && !hasConversationContent && !pendingUserText && !pendingSend;

  return (
    // Row layout: chat list | conversation. Must NOT be flex-col — the sidebar
    // with h-full would eat the full height and hide messages + composer.
    <div className="flex h-[calc(100dvh-5rem)] max-h-[calc(100dvh-5rem)] w-full overflow-hidden bg-card text-foreground">
      {/* ── Sidebar ── */}
      <aside className="relative z-[1] hidden h-full w-[15.5rem] shrink-0 flex-col border-r border-border/60 bg-card lg:flex">
        <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-3.5">
          <h1 className="truncate text-[13px] font-semibold tracking-tight text-foreground">
            {localize(lang, "Чаты", "Chats")}
          </h1>
          <div className="flex items-center gap-0.5">
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 rounded-lg"
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
              variant="ghost"
              className="h-8 w-8 rounded-lg"
              onClick={() => {
                try {
                  localStorage.removeItem(LAST_CHAT_KEY);
                } catch {
                  // ignore
                }
                setSearchParams({});
              }}
              aria-label={localize(lang, "Новый чат", "New chat")}
              title={localize(lang, "Новый чат", "New chat")}
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="px-2.5 pb-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/60" />
            <input
              value={chatFilter}
              onChange={(e) => setChatFilter(e.target.value)}
              placeholder={localize(lang, "Поиск…", "Search…")}
              className="h-8 w-full rounded-lg border-0 bg-muted/40 pl-8 pr-2.5 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/55 focus:bg-muted/60"
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
          {chatGroups.map((group) => (
            <div key={group.id}>
              <div className="px-2.5 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/55">
                {lang === "ru" ? group.labelRu : group.labelEn}
              </div>
              {group.chats.map((chat) => {
                const selected = chat.id === activeChatId;
                if (renamingChatId === chat.id) {
                  return (
                    <div key={chat.id} className="mb-0.5 flex items-center gap-1 rounded-lg bg-muted px-2 py-1.5">
                      <input
                        autoFocus
                        value={renameDraft}
                        onChange={(e) => setRenameDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") commitRename();
                          if (e.key === "Escape") setRenamingChatId(null);
                        }}
                        className="h-6 w-full min-w-0 flex-1 bg-transparent text-[13px] text-foreground outline-none"
                      />
                      <button
                        type="button"
                        onClick={commitRename}
                        className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground"
                        aria-label={localize(lang, "Сохранить", "Save")}
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setRenamingChatId(null)}
                        className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground"
                        aria-label={localize(lang, "Отмена", "Cancel")}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  );
                }
                return (
                  <div key={chat.id} className="group/chat relative mb-0.5">
                    <button
                      type="button"
                      onClick={() => setSearchParams({ chat: String(chat.id) })}
                      className={cn(
                        "grid w-full min-w-0 grid-cols-[1rem_minmax(0,1fr)] gap-2 rounded-lg px-2.5 py-2 pr-14 text-left transition-colors",
                        selected
                          ? "bg-muted text-foreground"
                          : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                      )}
                    >
                      {chat.kind === "duty" ? (
                        <Shield className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-70" strokeWidth={1.75} />
                      ) : (
                        <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-50" strokeWidth={1.75} />
                      )}
                      <span className="min-w-0">
                        <span className="block truncate text-[13px] font-medium tracking-tight">
                          {chat.title}
                        </span>
                        <span className="mt-0.5 block truncate text-[10px] text-muted-foreground/65">
                          {formatDateTime(chat.updated_at, lang)}
                        </span>
                      </span>
                    </button>
                    <div className="absolute right-1.5 top-1/2 hidden -translate-y-1/2 items-center gap-0.5 group-hover/chat:flex">
                      <button
                        type="button"
                        onClick={() => startRename(chat)}
                        className="rounded p-1 text-muted-foreground/70 hover:bg-muted hover:text-foreground"
                        aria-label={localize(lang, "Переименовать", "Rename")}
                        title={localize(lang, "Переименовать", "Rename")}
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          const ok = window.confirm(
                            localize(
                              lang,
                              `Удалить чат «${chat.title}»? Действие необратимо.`,
                              `Delete chat "${chat.title}"? This cannot be undone.`,
                            ),
                          );
                          if (ok) deleteChatMutation.mutate(chat.id);
                        }}
                        className="rounded p-1 text-muted-foreground/70 hover:bg-muted hover:text-destructive"
                        aria-label={localize(lang, "Удалить", "Delete")}
                        title={localize(lang, "Удалить", "Delete")}
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </aside>

      {/* ── Main conversation column ── */}
      <section className="relative z-[1] flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border/40 px-4 sm:px-6">
          <div className="min-w-0">
            <h2 className="truncate text-[14px] font-medium tracking-tight text-foreground">
              {selectedTitle}
            </h2>
            {activeChat?.active_turn?.status === "awaiting_async" ||
            (isBusy && operatorWs.statusMessage?.includes("Жду")) ? (
              <p className="text-[11px] text-info">
                {localize(
                  lang,
                  "Жду агента/задачу — напишу, когда отработает",
                  "Waiting on agent/task — will report when done",
                )}
              </p>
            ) : isBusy ? (
              <p className="text-[11px] text-muted-foreground">
                {localize(lang, "Работает в фоне…", "Working in background…")}
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-1">
            {sessionTokens ? (
              <span
                className="mr-1 hidden rounded-full border border-border/50 px-2 py-0.5 font-mono text-[10px] tabular-nums text-muted-foreground/70 sm:inline"
                title={localize(lang, "Токены за сессию (вход + выход)", "Session tokens (in + out)")}
              >
                {sessionTokens} tok
              </span>
            ) : null}
            {activePlan ? (
              <Button
                size="sm"
                variant="ghost"
                className={cn(
                  "h-8 gap-1.5 rounded-full px-2.5 text-xs",
                  tasksPanelOpen && "text-primary",
                )}
                onClick={() => setTasksPanelOpen((v) => !v)}
                title={localize(lang, "Панель задач", "Tasks panel")}
              >
                <ListChecks className="h-3.5 w-3.5" />
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="ghost"
              className="h-8 gap-1.5 rounded-full px-2.5 text-xs lg:hidden"
              onClick={() => {
                try {
                  localStorage.removeItem(LAST_CHAT_KEY);
                } catch {
                  // ignore
                }
                setSearchParams({});
              }}
            >
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </div>
        </header>

        <div
          ref={scrollerRef}
          onScroll={handleScrollerScroll}
          className="relative min-h-0 flex-1 overflow-y-auto overscroll-contain"
        >
          {/* Always render a real content tree so the pane never paints blank. */}
          {showEmptyStarter ? (
            <div className="flex min-h-[min(100%,32rem)] flex-col items-center justify-center px-4 py-10">
              <div className="mx-auto flex w-full max-w-md flex-col items-center text-center">
                <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <Bot className="h-4 w-4" strokeWidth={1.75} />
                </div>
                <h2 className="text-lg font-semibold tracking-tight text-foreground">
                  {localize(lang, "Чем помочь?", "How can I help?")}
                </h2>
                <p className="mt-1.5 max-w-sm text-[13px] leading-5 text-muted-foreground">
                  {localize(
                    lang,
                    "Серверы, метрики, агенты, диагностика. Напишите @ — выбрать сервер.",
                    "Servers, metrics, agents, diagnostics. Type @ to pick a server.",
                  )}
                </p>
                <div className="mt-6 grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
                  {QUICK_PROMPT_CARDS.map((card) => (
                    <button
                      key={card.id}
                      type="button"
                      onClick={() => dispatchMessage(lang === "ru" ? card.promptRu : card.promptEn)}
                      className="rounded-2xl border border-border/70 bg-transparent px-3.5 py-3 text-left transition-colors hover:bg-muted/40"
                    >
                      <div className="text-[13px] font-medium text-foreground">
                        {lang === "ru" ? card.labelRu : card.labelEn}
                      </div>
                      <div className="mt-0.5 text-[11px] text-muted-foreground/75">
                        {lang === "ru" ? card.hintRu : card.hintEn}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="mx-auto flex w-full max-w-[42rem] flex-col gap-5 px-4 py-6 sm:px-6">
              {operatorWs.health && !operatorWs.health.ok ? (
                <div className="rounded-sm border border-warning/40 bg-warning/10 px-3 py-2 text-[12.5px] text-warning-foreground">
                  <div className="font-medium">
                    {localize(lang, "Оператор не готов", "Operator not ready")}
                  </div>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-muted-foreground">
                    {(operatorWs.health.issues || []).map((issue, i) => (
                      <li key={i}>{issue}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {activeChatQuery.isLoading ? (
                <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {localize(lang, "Загрузка чата", "Loading chat")}
                </div>
              ) : null}

              {!activeChatQuery.isLoading &&
              !displayMessages.length &&
              !pendingUserText &&
              !showLiveStream &&
              !isBusy ? (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  {localize(lang, "Сообщений пока нет — напишите ниже.", "No messages yet — type below.")}
                </div>
              ) : null}

              {displayMessages.map((message, index) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  actionWorkingId={actionWorkingId}
                  onConfirmAction={handleConfirm}
                  onCancelAction={handleCancel}
                  onUndoAction={handleUndo}
                  onSaveRunbook={handleSaveRunbook}
                  onRetry={
                    !isBusy && message.role === "assistant" && index === displayMessages.length - 1
                      ? handleRetry
                      : undefined
                  }
                  serverPanelActions={{
                    pinnedIds: pinnedServers.map((s) => s.id),
                    onPin: pinServer,
                    onUnpin: unpinServer,
                    onAsk: (prompt) => dispatchMessage(prompt),
                    onOpenSession: (server) =>
                      openSessionDock({
                        serverId: server.id,
                        serverName: server.name,
                        host: server.host,
                        mode: "live",
                      }),
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
                <div className="min-w-0 space-y-2.5 animate-in fade-in-0 duration-200">
                  {(operatorWs.phase !== "idle" || isBusy) &&
                  (operatorWs.hasReasoningStream || operatorWs.toolSteps.length > 0 || !operatorWs.streamText) ? (
                    <OperatorThinkingPanel
                      phase={
                        operatorWs.phase === "idle" && isBusy
                          ? "thinking"
                          : operatorWs.phase === "idle"
                            ? "streaming"
                            : operatorWs.phase
                      }
                      startedAt={operatorWs.thinkingStartedAt ?? Date.now()}
                      iteration={operatorWs.thinkingIteration}
                      reasoningText={operatorWs.reasoningText}
                      hasReasoningStream={operatorWs.hasReasoningStream}
                      statusMessage={operatorWs.statusMessage}
                      toolSteps={operatorWs.toolSteps}
                      compact={Boolean(operatorWs.streamText)}
                    />
                  ) : null}

                  {/* Distinct card for a long-running spawned task (agent / pipeline run). */}
                  {operatorWs.asyncTask ? (
                    <div
                      className={cn(
                        "flex items-center gap-2.5 rounded-2xl border px-3 py-2.5 text-[13px]",
                        operatorWs.asyncTask.status === "failed"
                          ? "border-destructive/30 bg-destructive/[0.06]"
                          : operatorWs.asyncTask.status === "done"
                            ? "border-success/30 bg-success/[0.06]"
                            : "border-primary/30 bg-primary/[0.05]",
                      )}
                    >
                      {operatorWs.asyncTask.status === "running" ? (
                        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
                      ) : operatorWs.asyncTask.status === "done" ? (
                        <Check className="h-4 w-4 shrink-0 text-success" />
                      ) : (
                        <X className="h-4 w-4 shrink-0 text-destructive" />
                      )}
                      <div className="min-w-0">
                        <div className="font-medium text-foreground">
                          {operatorWs.asyncTask.status === "running"
                            ? localize(lang, "Фоновая задача выполняется", "Background task running")
                            : operatorWs.asyncTask.status === "done"
                              ? localize(lang, "Фоновая задача завершена", "Background task finished")
                              : localize(lang, "Фоновая задача упала", "Background task failed")}
                        </div>
                        <div className="truncate font-mono text-[11px] text-muted-foreground">
                          {operatorWs.asyncTask.kind}
                          {operatorWs.asyncTask.runId ? ` · #${operatorWs.asyncTask.runId}` : ""}
                          {operatorWs.asyncTask.status === "running"
                            ? localize(lang, " · работает отдельный агент…", " · a separate agent is working…")
                            : ""}
                        </div>
                      </div>
                    </div>
                  ) : null}

                  {/* On lg+ the plan lives in the right-side PlanTasksPanel. */}
                  {operatorWs.livePlan ? (
                    <div className={cn(tasksPanelOpen && "lg:hidden")}>
                      <PlanChecklist plan={operatorWs.livePlan} />
                    </div>
                  ) : null}

                  {/* Text first, cards below — same order as the settled MessageBubble,
                      so the answer doesn't jump from under the cards to the top on turn end. */}
                  {operatorWs.streamText ? (
                    <div className="max-w-[min(42rem,100%)]">
                      <OperatorMarkdown
                        content={operatorWs.streamText}
                        streaming={operatorWs.busy || isBusy}
                        stripTables={Boolean(streamInventoryKind) || hasMarkdownTable(operatorWs.streamText)}
                      />
                    </div>
                  ) : null}

                  {streamInventoryKind ? (
                    <InventoryPanelSkeleton
                      kind={streamInventoryKind}
                      rows={streamInventoryKind === "alerts" ? 4 : 5}
                    />
                  ) : null}
                </div>
              ) : null}
              <div ref={endRef} className="h-2 shrink-0" aria-hidden />
            </div>
          )}
        </div>

        {!atBottom && !showEmptyStarter ? (
          <div className="pointer-events-none relative z-[2]">
            <button
              type="button"
              onClick={() => {
                setAtBottom(true);
                scrollToEnd(true);
              }}
              className="pointer-events-auto absolute -top-12 left-1/2 flex h-8 w-8 -translate-x-1/2 items-center justify-center rounded-full border border-border bg-background text-muted-foreground shadow-sm transition-colors hover:text-foreground"
              aria-label={localize(lang, "Вниз", "Scroll to bottom")}
            >
              <ArrowDown className="h-4 w-4" />
            </button>
          </div>
        ) : null}

        {/* ── Compose dock — always pinned under the message pane ── */}
        <form
          className="shrink-0 border-t border-border/50 bg-card px-3 pb-4 pt-2 sm:px-6 sm:pb-5"
          onSubmit={(event) => {
            event.preventDefault();
            submitMessage();
          }}
        >
          <div className="relative mx-auto max-w-[42rem]">
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
              pinnedServers={pinnedServers}
              onPinServer={pinServer}
              onUnpinServer={unpinServer}
            />
            <div className="rounded-3xl border border-border/70 bg-muted/25 p-1.5 shadow-sm focus-within:border-border focus-within:bg-muted/35">
              <div className="flex items-end gap-1">
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
                    if (event.key === "Escape" && isBusy) {
                      event.preventDefault();
                      handleStop();
                      return;
                    }
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      if (!isBusy) event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder={
                    isBusy
                      ? localize(lang, "Оператор работает… Esc — остановить", "Operator is working… Esc to stop")
                      : localize(lang, "Спросите что угодно…", "Ask anything…")
                  }
                  className="max-h-40 min-h-12 flex-1 resize-none border-0 bg-transparent px-3.5 py-2.5 text-[15px] leading-6 shadow-none focus-visible:ring-0"
                  rows={1}
                />
                {isBusy ? (
                  <Button
                    type="button"
                    size="icon"
                    variant="secondary"
                    className="mb-1 mr-1 h-9 w-9 shrink-0 rounded-full"
                    onClick={handleStop}
                    aria-label={localize(lang, "Остановить", "Stop")}
                    title={localize(lang, "Остановить · Esc", "Stop · Esc")}
                  >
                    <Square className="h-3.5 w-3.5 fill-current" />
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    size="icon"
                    className="mb-1 mr-1 h-9 w-9 shrink-0 rounded-full"
                    disabled={!draft.trim()}
                    aria-label={localize(lang, "Отправить", "Send")}
                    title={localize(lang, "Отправить · Enter", "Send · Enter")}
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
            <p className="mt-2 px-1 text-center text-[11px] text-muted-foreground/60">
              {localize(
                lang,
                "Диалог продолжается в фоне, если уйти со страницы",
                "Conversation keeps running if you leave the page",
              )}
            </p>
          </div>
        </form>
      </section>

      <OperatorSessionDock
        session={sessionDock}
        onClose={() => setSessionDock((s) => ({ ...s, open: false }))}
        onModeChange={(mode) => setSessionDock((s) => ({ ...s, mode }))}
        onHumanCommand={handleHumanCommand}
      />

      <PlanTasksPanel
        plan={activePlan}
        open={tasksPanelOpen}
        onClose={() => setTasksPanelOpen(false)}
      />
    </div>
  );
}
