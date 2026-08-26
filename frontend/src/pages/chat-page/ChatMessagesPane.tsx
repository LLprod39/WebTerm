import {
  AlertCircle,
  ArrowDown,
  Bot,
  Check,
  ListChecks,
  Loader2,
  Menu,
  Plus,
  X,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useMemo, useRef } from "react";

import type { AssistantChatMessage } from "@/api";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
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
};

export function ChatMessagesPane({ c, onOpenHistory }: ChatMessagesPaneProps) {
  const reduceMotion = useReducedMotion();
  const {
    lang,
    selectedTitle,
    activeChat,
    isBusy,
    operatorWs,
    sessionTokens,
    activePlan,
    tasksPanelOpen,
    setTasksPanelOpen,
    clearLastChatAndNew,
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
    : isBusy
      ? {
          key: "working",
          text: localize(lang, "Работает в фоне…", "Working in background…"),
          className: "text-muted-foreground",
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

  return (
    <>
      <header className="flex min-h-14 shrink-0 items-center justify-between gap-3 border-b border-border/50 bg-card/95 px-3 sm:px-6">
        <div className="flex min-w-0 items-center gap-2.5">
          <Button
            size="icon"
            variant="ghost"
            className="h-9 w-9 shrink-0 rounded-xl lg:hidden"
            onClick={onOpenHistory}
            aria-label={localize(lang, "Открыть историю чатов", "Open chat history")}
          >
            <Menu className="h-4 w-4" />
          </Button>
          <div className="min-w-0">
          <h2 className="truncate text-[14px] font-medium tracking-tight text-foreground">
            {selectedTitle}
          </h2>
          <div className="relative min-h-[1rem] overflow-hidden text-[11px]">
            <AnimatePresence mode="wait" initial={false}>
              <motion.p
                key={headerStatus.key}
                initial={reduceMotion ? false : { opacity: 0, y: 3 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduceMotion ? undefined : { opacity: 0, y: -3 }}
                transition={{ duration: reduceMotion ? 0 : 0.17, ease: CHAT_EASE }}
                className={headerStatus.className}
              >
                {headerStatus.text}
              </motion.p>
            </AnimatePresence>
          </div>
          </div>
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
            onClick={clearLastChatAndNew}
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
                  <motion.button
                    key={card.id}
                    type="button"
                    onClick={() => dispatchMessage(lang === "ru" ? card.promptRu : card.promptEn)}
                    whileHover={reduceMotion ? undefined : { y: -1 }}
                    whileTap={reduceMotion ? undefined : { scale: 0.99 }}
                    transition={{ duration: reduceMotion ? 0 : 0.16, ease: CHAT_EASE }}
                    className="rounded-2xl border border-border/70 bg-transparent px-3.5 py-3 text-left transition-colors hover:bg-muted/40"
                  >
                    <div className="text-[13px] font-medium text-foreground">
                      {lang === "ru" ? card.labelRu : card.labelEn}
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground/75">
                      {lang === "ru" ? card.hintRu : card.hintEn}
                    </div>
                  </motion.button>
                ))}
              </div>
              <div className="mt-5 flex w-full flex-wrap items-center justify-center gap-2 border-t border-border/50 pt-4">
                <Link to="/agents" className="rounded-full border border-border/70 px-3 py-1.5 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground">
                  {localize(lang, "Создать агента", "Create an agent")}
                </Link>
                <Link to="/automation" className="rounded-full border border-border/70 px-3 py-1.5 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground">
                  {localize(lang, "Импортировать Ansible", "Import Ansible")}
                </Link>
                <Link to="/agents" className="rounded-full border border-border/70 px-3 py-1.5 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground">
                  {localize(lang, "Открыть прогресс", "Open progress")}
                </Link>
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
                    onSaveRunbook={stableMessageHandlers.onSaveRunbook}
                    onRetry={
                      !isBusy && message.role === "assistant" && index === visibleMessages.length - 1
                        ? stableMessageHandlers.onRetry
                        : undefined
                    }
                    serverPanelActions={serverPanelActions}
                    agentPanelActions={agentPanelActions}
                    forecastPanelActions={forecastPanelActions}
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
                  <div className="rounded-sm rounded-br-md bg-primary px-3.5 py-2.5 text-[13px] font-medium leading-5 tracking-tight text-primary-foreground shadow-sm opacity-90">
                    <div className="whitespace-pre-wrap break-words">{pendingUserText}</div>
                  </div>
                  <div className="mt-1 pr-0.5 text-right text-[10px] text-muted-foreground/70">
                    {localize(lang, "отправляется…", "sending…")}
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
                    onSaveRunbook={stableMessageHandlers.onSaveRunbook}
                    onRetry={isReconcilingLiveTurn ? stableMessageHandlers.onRetry : undefined}
                    serverPanelActions={serverPanelActions}
                    agentPanelActions={agentPanelActions}
                    forecastPanelActions={forecastPanelActions}
                    streaming={!isReconcilingLiveTurn && (operatorWs.busy || isBusy)}
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
                          <OperatorThinkingPanel
                            phase={
                              (operatorTurn?.phase ?? operatorWs.phase) === "idle" && isBusy
                                ? "thinking"
                                : (operatorTurn?.phase ?? operatorWs.phase) === "idle"
                                  ? "streaming"
                                  : (operatorTurn?.phase ?? operatorWs.phase)
                            }
                            startedAt={operatorTurn?.startedAt ?? operatorWs.thinkingStartedAt}
                            iteration={operatorTurn?.iteration ?? operatorWs.thinkingIteration}
                            reasoningText={operatorWs.reasoningText}
                            hasReasoningStream={operatorWs.hasReasoningStream}
                            statusMessage={operatorTurn?.statusMessage ?? operatorWs.statusMessage}
                            toolSteps={operatorTurn?.toolSteps ?? operatorWs.toolSteps}
                            compact={Boolean(liveText)}
                          />

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
                                  "flex items-center gap-2.5 rounded-2xl border px-3 py-2.5 text-[13px]",
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
                                className={cn(tasksPanelOpen && "lg:hidden")}
                              >
                                <PlanChecklist plan={operatorWs.livePlan} />
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
              className="pointer-events-auto absolute -top-12 left-1/2 flex h-9 -translate-x-1/2 items-center gap-2 rounded-full border border-border/80 bg-background/95 px-3 text-[11px] font-medium text-muted-foreground shadow-md backdrop-blur-sm transition-colors hover:text-foreground"
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
