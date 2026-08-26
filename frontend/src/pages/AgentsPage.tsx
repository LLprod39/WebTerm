import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  FileText,
  Plus,
  RefreshCw,
  X,
} from "lucide-react";
import { AgentReportModal } from "@/components/studio/AgentReportModal";
import { Button } from "@/components/ui/button";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { PageShell, StatStrip, StatStripItem } from "@/components/ui/page-shell";
import { SkeletonList } from "@/components/ui/list-state";
import { localize } from "@/lib/i18n";
import { CreateAgentDialog } from "./agents-page/CreateAgentDialog";
import { AgentListSection } from "./agents-page/AgentListSection";
import { AgentSystemHealthSection } from "./agents-page/AgentSystemHealthSection";
import { formatDuration } from "./agents-page/agentPageUtils";
import { useAgentsPageController } from "./useAgentsPageController";

export default function AgentsPage() {
  const {
    t,
    lang,
    queryClient,
    navigate,
    modeFilter,
    setModeFilter,
    createOpen,
    setCreateOpen,
    editingAgent,
    setEditingAgent,
    createdAgentId,
    runningId,
    stoppingId,
    actionError,
    setActionError,
    actionNotice,
    setActionNotice,
    cleaningStale,
    result,
    setResult,
    reportModalOpen,
    setReportModalOpen,
    deleteTarget,
    setDeleteTarget,
    isLoading,
    isAdmin,
    allAgents,
    agents,
    activeAgents,
    scheduledAgents,
    pausedAgents,
    failedAgents,
    executionWarning,
    executionReadiness,
    runtimeOverview,
    activeRunByAgentId,
    showRuntimeOverview,
    scheduledWorker,
    showScheduledWorker,
    openCreate,
    onRun,
    onStop,
    onCleanupStale,
    onDelete,
    onTogglePause,
    copyExecutionCommand,
    confirmDeleteAgent,
    onCreateSaved,
    onEditSaved,
  } = useAgentsPageController();

  if (isLoading) {
    return (
      <PageShell width="7xl" className="space-y-4">
        <SkeletonList rows={6} />
      </PageShell>
    );
  }

  // Worker/ops diagnostics are admin-only. No "healthy services" strip —
  // show only when something is actually broken (and only to staff).
  const healthSection = isAdmin ? (
    <AgentSystemHealthSection
      runtimeOverview={runtimeOverview}
      showRuntimeOverview={showRuntimeOverview}
      executionReadiness={executionReadiness || executionWarning}
      scheduledWorker={scheduledWorker}
      showScheduledWorker={showScheduledWorker}
      lang={lang}
      onCopyCommand={copyExecutionCommand}
      onCleanupStale={onCleanupStale}
      cleaningStale={cleaningStale}
    />
  ) : null;

  return (
    <PageShell width="7xl" className="space-y-5">
      <header className="flex flex-col gap-5 border-b border-border/70 pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-start gap-3.5">
          <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-foreground text-background">
            <Bot className="h-5 w-5" />
          </span>
          <div>
            <h1 className="font-display text-2xl font-semibold tracking-tight text-foreground">
              {t("agent.title")}
              {allAgents.length > 0 ? (
                <span className="ml-2 font-mono text-base font-normal text-muted-foreground">{allAgents.length}</span>
              ) : null}
            </h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              {localize(lang, "Задачи, проверки и запуски по расписанию.", "Tasks, checks, and scheduled runs.")}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="icon"
            variant="ghost"
            className="h-9 w-9"
            onClick={() => queryClient.invalidateQueries({ queryKey: ["agents"] })}
            aria-label={t("udash.refresh")}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button size="sm" className="h-9 gap-1.5" onClick={openCreate}>
            <Plus className="h-4 w-4" />
            {t("agent.new")}
          </Button>
        </div>
      </header>

      {allAgents.length > 0 ? (
        <StatStrip>
          <StatStripItem
            label={localize(lang, "Всего", "Total")}
            value={allAgents.length}
            hint={localize(lang, "агенты", "agents")}
          />
          <StatStripItem
            label={localize(lang, "Выполняется", "Running")}
            value={activeAgents}
            tone={activeAgents > 0 ? "info" : "default"}
            hint={localize(lang, "активные запуски", "active runs")}
          />
          <StatStripItem
            label={localize(lang, "Расписание", "Scheduled")}
            value={scheduledAgents}
            tone={scheduledAgents > 0 ? "success" : "default"}
            hint={
              pausedAgents > 0
                ? localize(lang, `${pausedAgents} на паузе`, `${pausedAgents} paused`)
                : localize(lang, "по расписанию", "on schedule")
            }
          />
          <StatStripItem
            label={localize(lang, "С ошибкой", "Failed")}
            value={failedAgents}
            tone={failedAgents > 0 ? "danger" : "default"}
            hint={localize(lang, "по последнему запуску", "by latest run")}
          />
        </StatStrip>
      ) : null}

      {/* Admin-only: only when workers/runtime have problems (no healthy strip). */}
      {healthSection}

      {actionError ? (
        <div className="rounded-sm border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive shadow-elev-1">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="break-words leading-6">{actionError}</span>
            </div>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7 shrink-0 text-destructive hover:text-destructive"
              onClick={() => setActionError(null)}
              aria-label={localize(lang, "Скрыть ошибку", "Dismiss error")}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      ) : null}

      {actionNotice ? (
        <div className="rounded-sm border border-success/30 bg-success/10 px-4 py-3 text-sm text-foreground shadow-elev-1">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
              <span className="break-words leading-6">{actionNotice}</span>
            </div>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7 shrink-0"
              onClick={() => setActionNotice(null)}
              aria-label={localize(lang, "Скрыть сообщение", "Dismiss notice")}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      ) : null}

      {result && !reportModalOpen && (
        <div className="flex items-center gap-3 rounded-sm border border-border bg-card px-4 py-3 shadow-elev-1">
          <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border ${result.status === "completed" ? "border-success/30 bg-success/15 text-success" : "border-destructive/30 bg-destructive/15 text-destructive"}`}>
            {result.status === "completed" ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-foreground">{result.server_name}</div>
            <div className="text-xs text-muted-foreground">
              {result.status === "completed"
                ? localize(lang, "Успешно", "Completed")
                : localize(lang, "Завершено с ошибкой", "Failed")}
              {" · "}{formatDuration(result.duration_ms)}
            </div>
          </div>
          {result.run_id > 0 ? (
            <Button size="sm" variant="outline" className="h-9 shrink-0 gap-1.5 text-xs" onClick={() => navigate(`/agents/run/${result.run_id}`)}>
              <FileText className="h-3.5 w-3.5" /> {localize(lang, "Открыть результат", "Open result")}
            </Button>
          ) : (
            <Button size="sm" className="h-9 shrink-0 gap-1.5 text-xs" onClick={() => setReportModalOpen(true)}>
              <FileText className="h-3.5 w-3.5" /> {localize(lang, "Открыть результат", "Open result")}
            </Button>
          )}
          <Button
            size="icon"
            variant="ghost"
            className="h-9 w-9 shrink-0 text-muted-foreground"
            onClick={() => setResult(null)}
            aria-label={localize(lang, "Скрыть результат запуска", "Dismiss run result")}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}

      {result && (
        <AgentReportModal result={result} open={reportModalOpen} onClose={() => setReportModalOpen(false)} />
      )}
      <AgentListSection
        agents={agents}
        totalCount={allAgents.length}
        modeFilter={modeFilter}
        onModeFilterChange={setModeFilter}
        lang={lang}
        t={t}
        isAdmin={isAdmin}
        createdAgentId={createdAgentId}
        runningId={runningId}
        stoppingId={stoppingId}
        activeRunByAgentId={activeRunByAgentId}
        onCreate={openCreate}
        onEdit={setEditingAgent}
        onRun={onRun}
        onStop={onStop}
        onDelete={onDelete}
        onTogglePause={onTogglePause}
      />

      <CreateAgentDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSaved={onCreateSaved}
      />
      <CreateAgentDialog
        open={Boolean(editingAgent)}
        initialAgent={editingAgent}
        onClose={() => setEditingAgent(null)}
        onSaved={onEditSaved}
      />
      <DeleteDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={localize(lang, "Удалить агента?", "Delete agent?")}
        description={localize(
          lang,
          `Агент "${deleteTarget?.name || ""}" будет удалён. История уже созданных запусков останется доступной в отчётах.`,
          `Agent "${deleteTarget?.name || ""}" will be removed. Existing run history remains available in reports.`,
        )}
        confirmLabel={localize(lang, "Удалить агента", "Delete agent")}
        cancelLabel={localize(lang, "Отмена", "Cancel")}
        onConfirm={confirmDeleteAgent}
      />
    </PageShell>
  );
}
