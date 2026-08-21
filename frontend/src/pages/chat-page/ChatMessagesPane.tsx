import {
  ArrowDown,
  Bot,
  Check,
  ListChecks,
  Loader2,
  Menu,
  Plus,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { MessageBubble, PlanChecklist } from "./ChatMessageViews";
import {
  hasMarkdownTable,
  InventoryPanelSkeleton,
} from "./InventoryPanelSkeleton";
import { OperatorMarkdown } from "./OperatorMarkdown";
import { OperatorThinkingPanel } from "./OperatorThinkingPanel";
import { QUICK_PROMPT_CARDS } from "./chatHelpers";
import type { ChatPageController } from "./useChatPageController";

type ChatMessagesPaneProps = {
  c: ChatPageController;
  onOpenHistory?: () => void;
};

export function ChatMessagesPane({ c, onOpenHistory }: ChatMessagesPaneProps) {
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
    pinnedPlaybook,
    pinServer,
    unpinServer,
    openSessionDock,
    pendingUserText,
    showLiveStream,
    streamInventoryKind,
    endRef,
    atBottom,
    setAtBottom,
    scrollToEnd,
  } = c;

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
          ) : (
            <p className="text-[11px] text-muted-foreground/70">
              {pinnedPlaybook
                ? localize(lang, `Playbook в контексте: ${pinnedPlaybook.name} · #${pinnedPlaybook.id}`, `Playbook in context: ${pinnedPlaybook.name} · #${pinnedPlaybook.id}`)
                : pinnedServers.length
                ? localize(lang, `${pinnedServers.length} сервер(а) в контексте`, `${pinnedServers.length} server(s) in context`)
                : localize(lang, "Контекст: весь доступный флот", "Context: all accessible servers")}
            </p>
          )}
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
              <div className="group flex justify-end gap-3">
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
              <div className="min-w-0 space-y-2.5">
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
    </>
  );
}
