import {
  AlertCircle,
  ArrowDown,
  Check,
  ListChecks,
  Loader2,
  Menu,
  MoreHorizontal,
  PanelLeft,
  PanelLeftClose,
  Plus,
  Share2,
  Terminal,
  X,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useCallback, useMemo, useRef } from "react";

import type { AssistantAction, AssistantChatMessage } from "@/api";
import { Breadcrumb, BreadcrumbItem } from "@/boardui/components/base/breadcrumb/breadcrumb";
import { Button } from "@/components/ui/button";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { MessageBubble, PlanChecklist } from "./ChatMessageViews";
import {
  hasMarkdownTable,
  InventoryPanelSkeleton,
} from "./InventoryPanelSkeleton";
import { OperatorThinkingPanel } from "./OperatorThinkingPanel";
import { QUICK_PROMPT_CARDS } from "./chatHelpers";
import { visibleOperatorUserText } from "./operatorUserText";
import { isNewOptimisticUserTurn } from "./optimisticUserTurn";
import { CHAT_EASE, CHAT_MOTION } from "./chatMotion";
import type { AgentPanelActions } from "./InteractiveAgentsPanel";
import type { ForecastPanelActions } from "./InteractiveForecastsPanel";
import type { ServerPanelActions } from "./InteractiveServersPanel";
import type { ChatPageController } from "./useChatPageController";

type ChatMessagesPaneProps = {
  c: ChatPageController;
  onOpenHistory?: () => void;
  historyCollapsed?: boolean;
  onToggleHistoryCollapsed?: () => void;
};

export function ChatMessagesPane({
  c,
  onOpenHistory,
  historyCollapsed = false,
  onToggleHistoryCollapsed,
}: ChatMessagesPaneProps) {
  const reduceMotion = useReducedMotion();
  const {
    lang,
    selectedTitle,
    activeChat,
    isBusy,
    operatorWs,
    sessionTokens,
    activePlan,
    contextRail,
    contextRailOpen,
    toggleContextRailTab,
    clearLastChatAndNew,
    sessionDock,
    scrollerRef,
    handleScrollerScroll,
    showEmptyStarter,
    dispatchMessage,
    activeChatQuery,
    displayMessages,
    actionWorkingId,
    handleConfirm,
    handleCancel,
    handleUndo,
    handleSaveRunbook,
    handleRetry,
    pinnedServers,
    pinServer,
    unpinServer,
    openSessionDock,
    handleHumanCommand,
    openActionDetails,
    pendingUserText,
    pendingUserEpoch,
    pendingUserBaselineIds,
    showLiveStream,
    operatorTurn,
    liveTurnKey,
    liveAssistantMessageId,
    settledLiveMessage,
    streamInventoryKind,
    endRef,
    atBottom,
    setAtBottom,
    scrollToEnd,
  } = c;

  // Busy "Thinking…" lives once (composer AgentThinking / in-thread activity) — not in the header.
  const headerStatus = activeChat?.active_turn?.status === "awaiting_async" ||
    (isBusy && operatorWs.statusMessage?.includes("Жду"))
    ? {
        key: "waiting",
        text: localize(
          lang,
          "Жду агента/задачу — напишу, когда отработает",
          "Waiting on agent/task — will report when done",
        ),
        className: "text-info",
      }
    : {
        key: "ready",
        text: pinnedServers.length
          ? localize(
              lang,
              `Выбран через @: ${pinnedServers.map((server) => server.name).join(", ")}`,
              `Selected via @: ${pinnedServers.map((server) => server.name).join(", ")}`,
            )
          : localize(
              lang,
              "Плейбуки, запуски, логи и агенты доступны по запросу",
              "Playbooks, runs, logs, and agents are available on request",
            ),
        className: "text-muted-foreground/70",
      };

  const reconciledMessageKeysRef = useRef(new Map<number, string>());
  const optimisticUserSequenceRef = useRef(0);
  const optimisticUserWasPresentRef = useRef(false);
  const optimisticUserEpochRef = useRef(pendingUserEpoch);
  const optimisticUserKeyRef = useRef("pending-user-message-0");
  const optimisticBaselineIdsRef = useRef(new Set<number>());
  if (isNewOptimisticUserTurn({
    pendingText: pendingUserText,
    wasPresent: optimisticUserWasPresentRef.current,
    previousEpoch: optimisticUserEpochRef.current,
    nextEpoch: pendingUserEpoch,
  })) {
    optimisticUserSequenceRef.current += 1;
    optimisticUserKeyRef.current = `pending-user-message-${optimisticUserSequenceRef.current}`;
    // Baseline is captured at dispatch and scoped to the originating chat, so
    // navigation cannot make an older identical prompt look like this send.
    optimisticBaselineIdsRef.current = new Set(pendingUserBaselineIds);
  }
  optimisticUserWasPresentRef.current = Boolean(pendingUserText);
  optimisticUserEpochRef.current = pendingUserEpoch;
  const optimisticUserKey = optimisticUserKeyRef.current;
  const pendingPersistedUser = pendingUserText
    ? [...displayMessages]
        .reverse()
        .find(
          (message) =>
            message.role === "user" &&
            !optimisticBaselineIdsRef.current.has(message.id) &&
            visibleOperatorUserText(message.content) === pendingUserText.trim(),
        )
    : undefined;
  const visibleMessages = pendingPersistedUser
    ? displayMessages.filter((message) => message.id !== pendingPersistedUser.id)
    : displayMessages;
  const liveText = operatorTurn?.text || operatorWs.streamText;
  if (pendingPersistedUser) {
    // The durable user row inherits the optimistic wrapper key so the bubble
    // never exits/re-enters while REST catches up with the send.
    for (const [messageId, key] of reconciledMessageKeysRef.current) {
      if (messageId !== pendingPersistedUser.id && key === optimisticUserKey) {
        reconciledMessageKeysRef.current.delete(messageId);
      }
    }
    reconciledMessageKeysRef.current.set(pendingPersistedUser.id, optimisticUserKey);
  }
  if (liveAssistantMessageId && liveTurnKey) {
    reconciledMessageKeysRef.current.set(liveAssistantMessageId, liveTurnKey);
  }
  const messageMotionKey = (message: AssistantChatMessage) =>
    reconciledMessageKeysRef.current.get(message.id) ?? `message-${message.id}`;

  const messageHandlersRef = useRef({
    handleConfirm,
    handleCancel,
    handleUndo,
    handleSaveRunbook,
    handleRetry,
    pinServer,
    unpinServer,
    dispatchMessage,
    openSessionDock,
    openActionDetails,
  });
  messageHandlersRef.current = {
    handleConfirm,
    handleCancel,
    handleUndo,
    handleSaveRunbook,
    handleRetry,
    pinServer,
    unpinServer,
    dispatchMessage,
    openSessionDock,
    openActionDetails,
  };

  const stableMessageHandlers = useMemo(
    () => ({
      onConfirm: (actionId: number, typedConfirm?: string) =>
        messageHandlersRef.current.handleConfirm(actionId, typedConfirm),
      onCancel: (actionId: number) => messageHandlersRef.current.handleCancel(actionId),
      onUndo: (actionId: number) => messageHandlersRef.current.handleUndo(actionId),
      onSaveRunbook: (message: AssistantChatMessage) =>
        messageHandlersRef.current.handleSaveRunbook(message),
      onRetry: () => messageHandlersRef.current.handleRetry(),
      onAsk: (prompt: string) => messageHandlersRef.current.dispatchMessage(prompt),
      onOpenActionDetails: (action: AssistantAction) =>
        messageHandlersRef.current.openActionDetails(action),
    }),
    [],
  );
  const pinnedServerIds = useMemo(() => pinnedServers.map((server) => server.id), [pinnedServers]);
  const serverPanelActions = useMemo<ServerPanelActions>(
    () => ({
      pinnedIds: pinnedServerIds,
      onPin: (server) => messageHandlersRef.current.pinServer(server),
      onUnpin: (id) => messageHandlersRef.current.unpinServer(id),
      onAsk: stableMessageHandlers.onAsk,
      onOpenSession: (server) =>
        messageHandlersRef.current.openSessionDock({
          serverId: server.id,
          serverName: server.name,
          host: server.host,
          mode: "live",
          osType: server.os_type === "windows" ? "windows" : "linux",
        }),
    }),
    [pinnedServerIds, stableMessageHandlers.onAsk],
  );
  const agentPanelActions = useMemo<AgentPanelActions>(
    () => ({ onAsk: stableMessageHandlers.onAsk }),
    [stableMessageHandlers.onAsk],
  );
  const forecastPanelActions = useMemo<ForecastPanelActions>(
    () => ({ onAsk: stableMessageHandlers.onAsk }),
    [stableMessageHandlers.onAsk],
  );
  const onSendToTerminal = useCallback(
    (code: string) => {
      const command = code.trim();
      if (!command) return;
      const pinned = pinnedServers[0];
      const serverId = sessionDock.serverId || pinned?.id;
      if (!serverId) return;
      if (!sessionDock.open || sessionDock.serverId !== serverId) {
        openSessionDock({
          serverId,
          serverName: pinned?.name || sessionDock.serverName,
          host: pinned?.host || sessionDock.host,
          mode: "live",
        });
      }
      handleHumanCommand(command);
    },
    [
      handleHumanCommand,
      openSessionDock,
      pinnedServers,
      sessionDock.host,
      sessionDock.open,
      sessionDock.serverId,
      sessionDock.serverName,
    ],
  );
  const isReconcilingLiveTurn = Boolean(operatorTurn?.reconciling && settledLiveMessage);
  const liveTurnError = operatorTurn?.error ?? operatorWs.errorMessage;
  const liveTerminalStatus = String(
    operatorTurn?.terminalStatus ?? operatorWs.terminalStatus ?? "",
  ).toLowerCase();
  const terminalNotice =
    liveTerminalStatus === "cancelled" || liveTerminalStatus === "stopped"
      ? {
          text: localize(lang, "Генерация остановлена", "Generation stopped"),
          destructive: false,
        }
      : liveTerminalStatus === "limit"
        ? {
            text: localize(lang, "Достигнут лимит выполнения", "Execution limit reached"),
            destructive: true,
          }
        : liveTerminalStatus === "failed" || liveTerminalStatus === "error"
          ? {
              text: localize(lang, "Ответ не удалось завершить", "Response could not be completed"),
              destructive: true,
            }
          : (liveTerminalStatus === "completed" || liveTerminalStatus === "done") && !liveText.trim()
            ? {
                text: localize(lang, "Ответ завершён", "Response completed"),
                destructive: false,
              }
            : null;
  const hasDurablePlan = Boolean(settledLiveMessage?.metadata.plan);
  const hasDurableInventory = Boolean(
    settledLiveMessage?.metadata.table ||
      (Array.isArray(settledLiveMessage?.metadata.tables) &&
        settledLiveMessage.metadata.tables.length > 0),
  );
  const liveShellMessage = useMemo<AssistantChatMessage>(() => {
    if (settledLiveMessage) {
      return {
        ...settledLiveMessage,
        content: liveText || settledLiveMessage.content,
      };
    }
    return {
      id: liveAssistantMessageId ?? -1,
      role: "assistant",
      content: liveText,
      metadata: {},
      created_at: "",
    };
  }, [
    liveAssistantMessageId,
    liveText,
    settledLiveMessage,
  ]);

  const shareChat = () => {
    const url = window.location.href;
    void navigator.clipboard?.writeText(url).catch(() => undefined);
  };

  return (
    <>
      <header className="flex min-h-11 shrink-0 items-center justify-between gap-2 px-3 pt-2.5 sm:px-5">
        <div className="flex min-w-0 items-center gap-2">
          <Button
            size="icon"
            variant="ghost"
            className="h-9 w-9 shrink-0 rounded-full lg:hidden"
            onClick={onOpenHistory}
            aria-label={localize(lang, "Открыть историю чатов", "Open chat history")}
          >
            <Menu className="h-4 w-4" />
          </Button>
          {onToggleHistoryCollapsed ? (
            <Button
              size="icon"
              variant="ghost"
              className="hidden h-8 w-8 shrink-0 rounded-full lg:inline-flex"
              onClick={onToggleHistoryCollapsed}
              aria-label={
                historyCollapsed
                  ? localize(lang, "Показать историю чатов", "Show chat history")
                  : localize(lang, "Скрыть историю чатов", "Hide chat history")
              }
              title={localize(lang, "История · Ctrl/⌘B", "History · Ctrl/⌘B")}
            >
              {historyCollapsed ? <PanelLeft className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
            </Button>
          ) : null}
          <nav className="min-w-0 flex-1">
            <Breadcrumb aria-label={localize(lang, "Местоположение чата", "Chat location")}>
              <BreadcrumbItem href="/chat">
                {localize(lang, "Оператор", "Operator")}
              </BreadcrumbItem>
              <BreadcrumbItem current>{selectedTitle}</BreadcrumbItem>
            </Breadcrumb>
            <div className="relative mt-0.5 min-h-[1rem] overflow-hidden text-[11px]">
              <AnimatePresence mode="wait" initial={false}>
                {isBusy && headerStatus.key !== "waiting" ? null : (
                  <motion.p
                    key={headerStatus.key}
                    initial={reduceMotion ? false : { opacity: 0, y: 3 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduceMotion ? undefined : { opacity: 0, y: -3 }}
                    transition={{ duration: reduceMotion ? 0 : 0.17, ease: CHAT_EASE }}
                    className={cn("flex items-center gap-1.5", headerStatus.className)}
                  >
                    {headerStatus.key === "waiting" ? (
                      <span className="inline-flex items-center gap-[3px]" aria-hidden="true">
                        {[0, 1, 2].map((i) => (
                          <span
                            key={i}
                            className={cn(
                              "h-1 w-1 rounded-full bg-muted-foreground/55",
                              !reduceMotion && "animate-bounce",
                            )}
                            style={
                              reduceMotion
                                ? undefined
                                : { animationDelay: `${i * 0.16}s`, animationDuration: "1.05s" }
                            }
                          />
                        ))}
                      </span>
                    ) : null}
                    {headerStatus.text}
                  </motion.p>
                )}
              </AnimatePresence>
            </div>
          </nav>
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          {sessionTokens ? (
            <span
              className="mr-1 hidden rounded-full border border-border/50 px-2 py-0.5 font-mono text-[10px] tabular-nums text-muted-foreground/70 sm:inline"
              title={localize(lang, "Токены за сессию (вход + выход)", "Session tokens (in + out)")}
            >
              {sessionTokens} tok
            </span>
          ) : null}
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-full"
            onClick={shareChat}
            aria-label={localize(lang, "Поделиться чатом", "Share chat")}
            title={localize(lang, "Скопировать ссылку", "Copy link")}
          >
            <Share2 className="h-3.5 w-3.5" />
          </Button>
          {activePlan ? (
            <Button
              size="icon"
              variant="ghost"
              className={cn(
                "h-8 w-8 rounded-full",
                contextRail.open && contextRail.tab === "tasks" && "text-primary",
              )}
              onClick={() => toggleContextRailTab("tasks")}
              title={localize(lang, "Панель задач", "Tasks panel")}
              aria-label={localize(lang, "Панель задач", "Tasks panel")}
              aria-pressed={contextRail.open && contextRail.tab === "tasks"}
            >
              <ListChecks className="h-3.5 w-3.5" />
            </Button>
          ) : null}
          {sessionDock.open && sessionDock.serverId ? (
            <Button
              size="icon"
              variant="ghost"
              className={cn(
                "h-8 w-8 rounded-full",
                contextRail.open && contextRail.tab === "terminal" && "text-primary",
              )}
              onClick={() => toggleContextRailTab("terminal")}
              title={localize(lang, "Терминал", "Terminal")}
              aria-label={localize(lang, "Терминал", "Terminal")}
              aria-pressed={contextRail.open && contextRail.tab === "terminal"}
            >
              <Terminal className="h-3.5 w-3.5" />
            </Button>
          ) : (
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 rounded-full"
              onClick={() => toggleContextRailTab("details")}
              aria-label={localize(lang, "Ещё", "More options")}
              title={localize(lang, "Контекст", "Context")}
            >
              <MoreHorizontal className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-full lg:hidden"
            onClick={clearLastChatAndNew}
            aria-label={localize(lang, "Новый чат", "New chat")}
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
            <div className="mx-auto flex w-full max-w-[768px] flex-col items-center text-center">
              <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                WebTerm
              </p>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground">
                {localize(lang, "Чем помочь?", "How can I help?")}
              </h2>
              <p className="mt-2 max-w-md text-[13px] leading-5 text-muted-foreground">
                {localize(
                  lang,
                  "Серверы, метрики, агенты, диагностика. Напишите @ — выбрать сервер.",
                  "Servers, metrics, agents, diagnostics. Type @ to pick a server.",
                )}
              </p>
              <div className="mt-7 flex w-full max-w-lg flex-wrap justify-center gap-2">
                {QUICK_PROMPT_CARDS.slice(0, 4).map((card) => (
                  <motion.button
                    key={card.id}
                    type="button"
                    onClick={() => dispatchMessage(lang === "ru" ? card.promptRu : card.promptEn)}
                    whileHover={reduceMotion ? undefined : { y: -1 }}
                    whileTap={reduceMotion ? undefined : { scale: 0.985 }}
                    transition={{ duration: reduceMotion ? 0 : 0.16, ease: CHAT_EASE }}
                    className="rounded-full border border-border/65 bg-muted/25 px-3.5 py-1.5 text-[13px] font-medium text-foreground transition-colors hover:bg-muted/50"
                  >
                    {lang === "ru" ? card.labelRu : card.labelEn}
                  </motion.button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-[768px] flex-col gap-5 px-4 py-6 sm:px-6">
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
                <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
                {localize(lang, "Загрузка чата", "Loading chat")}
              </div>
            ) : null}

            {!activeChatQuery.isLoading &&
            !visibleMessages.length &&
            !pendingUserText &&
            !showLiveStream &&
            !isBusy ? (
              <div className="py-12 text-center text-sm text-muted-foreground">
                {localize(lang, "Сообщений пока нет — напишите ниже.", "No messages yet — type below.")}
              </div>
            ) : null}

            <AnimatePresence key={activeChat?.id ?? "new-chat"} initial={false} mode="popLayout">
              {[
                ...visibleMessages.map((message, index) => (
                <motion.div
                  key={messageMotionKey(message)}
                  layout="position"
                  initial={reduceMotion ? false : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduceMotion ? undefined : { opacity: 0, y: -2 }}
                  transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.enter}
                >
                  <MessageBubble
                    message={message}
                    actionWorkingId={actionWorkingId}
                    onConfirmAction={stableMessageHandlers.onConfirm}
                    onCancelAction={stableMessageHandlers.onCancel}
                    onUndoAction={stableMessageHandlers.onUndo}
                    onOpenActionDetails={stableMessageHandlers.onOpenActionDetails}
                    onSaveRunbook={stableMessageHandlers.onSaveRunbook}
                    onRetry={
                      !isBusy && message.role === "assistant" && index === visibleMessages.length - 1
                        ? stableMessageHandlers.onRetry
                        : undefined
                    }
                    serverPanelActions={serverPanelActions}
                    agentPanelActions={agentPanelActions}
                    forecastPanelActions={forecastPanelActions}
                    onSendToTerminal={onSendToTerminal}
                  />
                </motion.div>
                )),

                pendingUserText ? (
              <motion.div
                key={optimisticUserKey}
                layout="position"
                initial={reduceMotion ? false : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduceMotion ? undefined : { opacity: 0 }}
                transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.enter}
                className="group flex justify-end gap-3"
              >
                <div className="min-w-0 max-w-[min(560px,85%)]">
                  <div className="rounded-2xl rounded-br-md border border-border/70 bg-muted/55 px-3.5 py-2.5 text-[14px] font-medium leading-[1.55] tracking-tight text-foreground shadow-sm opacity-90">
                    <div className="whitespace-pre-wrap break-words">{pendingUserText}</div>
                  </div>
                  <div className="mt-1 pr-0.5 text-right text-[10px] text-muted-foreground/70">
                    {isBusy
                      ? localize(lang, "принято", "accepted")
                      : localize(lang, "отправляется…", "sending…")}
                  </div>
                </div>
              </motion.div>
                ) : null,

                showLiveStream || isBusy ? (
                <motion.div
                  key={liveTurnKey ?? `operator-turn-${activeChat?.active_turn?.turn_id ?? activeChat?.id ?? "pending"}`}
                  layout="position"
                  initial={reduceMotion ? false : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduceMotion ? undefined : { opacity: 0, y: -2 }}
                  transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.enter}
                  className="min-w-0"
                  data-operator-turn={operatorTurn?.reconciling ? "reconciling" : "live"}
                >
                  <MessageBubble
                    message={liveShellMessage}
                    actionWorkingId={actionWorkingId}
                    onConfirmAction={stableMessageHandlers.onConfirm}
                    onCancelAction={stableMessageHandlers.onCancel}
                    onUndoAction={stableMessageHandlers.onUndo}
                    onOpenActionDetails={stableMessageHandlers.onOpenActionDetails}
                    onSaveRunbook={stableMessageHandlers.onSaveRunbook}
                    onRetry={isReconcilingLiveTurn ? stableMessageHandlers.onRetry : undefined}
                    serverPanelActions={serverPanelActions}
                    agentPanelActions={agentPanelActions}
                    forecastPanelActions={forecastPanelActions}
                    onSendToTerminal={onSendToTerminal}
                    streaming={
                      !isReconcilingLiveTurn &&
                      (operatorWs.busy || isBusy) &&
                      Boolean((operatorTurn?.text ?? operatorWs.streamText ?? "").trim())
                    }
                    animateSupportingContent
                    streamStripTables={
                      !isReconcilingLiveTurn &&
                      (Boolean(streamInventoryKind) || hasMarkdownTable(liveText))
                    }
                    turnActivity={
                      isReconcilingLiveTurn ? undefined : (
                        liveTurnError ? (
                          <motion.div
                            layout={!reduceMotion}
                            role="alert"
                            initial={reduceMotion ? false : { opacity: 0, y: 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.status}
                            className="flex max-w-[min(42rem,100%)] items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/[0.06] px-3 py-2.5 text-[12px]"
                          >
                            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                            <div className="min-w-0">
                              <div className="font-medium text-foreground">
                                {localize(lang, "Ответ не завершён", "Response did not finish")}
                              </div>
                              <div className="mt-0.5 break-words text-muted-foreground">
                                {liveTurnError}
                              </div>
                            </div>
                          </motion.div>
                        ) : liveTerminalStatus ? (
                          terminalNotice ? (
                            <motion.div
                              layout={!reduceMotion}
                              role={terminalNotice.destructive ? "alert" : "status"}
                              initial={reduceMotion ? false : { opacity: 0, y: 4 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.status}
                              className={cn(
                                "flex max-w-[min(42rem,100%)] items-center gap-2 rounded-lg border px-3 py-2 text-[12px]",
                                terminalNotice.destructive
                                  ? "border-destructive/30 bg-destructive/[0.06] text-destructive"
                                  : "border-border/60 bg-muted/20 text-muted-foreground",
                              )}
                            >
                              {terminalNotice.destructive ? (
                                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                              ) : (
                                <Check className="h-3.5 w-3.5 shrink-0" />
                              )}
                              <span className="font-medium">{terminalNotice.text}</span>
                            </motion.div>
                          ) : undefined
                        ) : (
                        <>
                          {isBusy || operatorWs.busy ? (
                            <OperatorThinkingPanel
                              phase={(() => {
                                const raw = operatorTurn?.phase ?? operatorWs.phase;
                                return raw === "idle" && (isBusy || operatorWs.busy)
                                  ? "thinking"
                                  : raw;
                              })()}
                              startedAt={operatorTurn?.startedAt ?? operatorWs.thinkingStartedAt}
                              iteration={operatorTurn?.iteration ?? operatorWs.thinkingIteration}
                              reasoningText={operatorWs.reasoningText}
                              hasReasoningStream={operatorWs.hasReasoningStream}
                              statusMessage={operatorTurn?.statusMessage ?? operatorWs.statusMessage}
                              toolSteps={operatorTurn?.toolSteps ?? operatorWs.toolSteps}
                              compact={Boolean(liveText)}
                              preferExpanded
                            />
                          ) : null}

                          <AnimatePresence initial={false} mode="popLayout">
                            {operatorWs.asyncTask ? (
                              <motion.div
                                key="async-task"
                                layout
                                initial={reduceMotion ? false : { opacity: 0, y: 4 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={reduceMotion ? undefined : { opacity: 0 }}
                                transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.status}
                                className={cn(
                                  "flex items-center gap-2.5 rounded-sm border px-3 py-2.5 text-[13px]",
                                  operatorWs.asyncTask.status === "failed"
                                    ? "border-destructive/30 bg-destructive/[0.06]"
                                    : operatorWs.asyncTask.status === "done"
                                      ? "border-success/30 bg-success/[0.06]"
                                      : "border-primary/30 bg-primary/[0.05]",
                                )}
                              >
                                {operatorWs.asyncTask.status === "running" ? (
                                  <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary motion-reduce:animate-none" />
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
                              </motion.div>
                            ) : null}

                            {operatorWs.livePlan && !hasDurablePlan ? (
                              <motion.div
                                key="live-plan"
                                layout
                                initial={reduceMotion ? false : { opacity: 0, y: 4 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={reduceMotion ? undefined : { opacity: 0 }}
                                transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.status}
                                className={cn("max-w-[min(28rem,100%)]", contextRailOpen && "lg:hidden")}
                              >
                                <PlanChecklist
                                  plan={operatorWs.livePlan}
                                  turnActive={Boolean(operatorWs.busy || isBusy)}
                                />
                              </motion.div>
                            ) : null}
                          </AnimatePresence>
                        </>
                        )
                      )
                    }
                    turnTrailing={
                      !isReconcilingLiveTurn && streamInventoryKind && !hasDurableInventory ? (
                        <motion.div
                          key={`inventory-${streamInventoryKind}`}
                          layout
                          initial={reduceMotion ? false : { opacity: 0, y: 4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={reduceMotion ? undefined : { opacity: 0 }}
                          transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.status}
                        >
                          <InventoryPanelSkeleton
                            kind={streamInventoryKind}
                            rows={streamInventoryKind === "alerts" ? 4 : 5}
                          />
                        </motion.div>
                      ) : undefined
                    }
                  />
                </motion.div>
                ) : null,
              ]}
            </AnimatePresence>
            <div ref={endRef} className="h-2 shrink-0" aria-hidden />
          </div>
        )}
      </div>

      <AnimatePresence initial={false}>
        {!atBottom && !showEmptyStarter ? (
          <div className="pointer-events-none relative z-[2]">
            <motion.button
              type="button"
              initial={reduceMotion ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduceMotion ? undefined : { opacity: 0, y: 4 }}
              whileTap={reduceMotion ? undefined : { scale: 0.98 }}
              transition={{ duration: reduceMotion ? 0 : 0.18, ease: CHAT_EASE }}
              onClick={() => {
                setAtBottom(true);
                scrollToEnd(true);
              }}
              className="pointer-events-auto absolute -top-12 left-1/2 flex h-9 -translate-x-1/2 items-center gap-2 rounded-full border border-border bg-card px-3 text-[11px] font-medium text-muted-foreground shadow-elev-1 transition-colors hover:text-foreground"
              aria-label={localize(lang, "К новому сообщению", "Jump to new message")}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
              {localize(lang, "К новому сообщению", "New message")}
              <ArrowDown className="h-3.5 w-3.5" />
            </motion.button>
          </div>
        ) : null}
      </AnimatePresence>
    </>
  );
}
