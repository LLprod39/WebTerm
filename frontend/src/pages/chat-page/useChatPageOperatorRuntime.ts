import { useCallback, useEffect, useMemo, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import type { QueryClient } from "@tanstack/react-query";

import type { AssistantChatMessage, AssistantChatSession, ProviderBinding } from "@/api";
import type { useToast } from "@/hooks/use-toast";

import { hasMarkdownTable, inferInventorySkeletonKind } from "./InventoryPanelSkeleton";
import type { PlanData } from "./PlanTasksPanel";
import { createChatOperatorHandlers } from "./chatPageOperatorHandlers";
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

export type UseChatPageOperatorRuntimeParams = {
  activeChatId: number | null;
  lang: Lang;
  toast: ToastFn;
  queryClient: QueryClient;
  messages: AssistantChatMessage[];
  activeTurn: ActiveTurn;
  activeChat: AssistantChatSession | undefined;
  pendingUserText: string | null;
  setPendingUserText: Dispatch<SetStateAction<string | null>>;
  streamHold: boolean;
  setStreamHold: Dispatch<SetStateAction<boolean>>;
  setPendingSend: Dispatch<SetStateAction<string | null>>;
  pendingSend: string | null;
  setActionWorkingId: Dispatch<SetStateAction<number | null>>;
  setDraft: Dispatch<SetStateAction<string>>;
  openSessionDock: OpenSessionDock;
  pushSessionLine: PushSessionLine;
  refreshChat: () => void;
  scrollerRef: MutableRefObject<HTMLDivElement | null>;
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
  sendMutationPending,
  createChatMutationPending,
  providerBinding,
}: UseChatPageOperatorRuntimeParams) {
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
    setStreamHold,
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
  }, [scrollerRef, setAtBottom]);

  /** Scroll only the message pane — never the page (scrollIntoView scrolls ancestors). */
  const scrollToEnd = useCallback((smooth = false) => {
    const el = scrollerRef.current;
    if (!el) return;
    if (smooth && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      return;
    }
    el.scrollTop = el.scrollHeight;
  }, [scrollerRef]);

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
  }, [activeChatId, scrollToEnd, setAtBottom, setStreamHold]);

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
  }, [messages, pendingUserText, operatorBusy, setPendingUserText]);

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
  }, [streamHold, messages, operatorBusy, resetOperatorStream, setStreamHold]);

  // After creating a new chat for streaming, send once WS is ready
  useEffect(() => {
    if (!pendingSend || !activeChatId || !operatorReady) return;
    const text = pendingSend;
    if (sendOperatorMessage(text, providerBinding)) {
      setDraft("");
      setPendingSend(null);
    }
  }, [pendingSend, activeChatId, operatorReady, providerBinding, sendOperatorMessage, setDraft, setPendingSend]);

  const turnOpen =
    Boolean(activeTurn?.busy) ||
    activeTurn?.status === "running" ||
    activeTurn?.status === "resuming" ||
    activeTurn?.status === "awaiting_async";
  const isBusy =
    sendMutationPending ||
    operatorWs.busy ||
    createChatMutationPending ||
    Boolean(pendingSend) ||
    turnOpen;

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
    activePlan,
    displayMessages,
    streamInventoryKind,
  };
}
