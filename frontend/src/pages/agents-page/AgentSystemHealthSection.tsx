import { useState } from "react";
import { AlertTriangle, ChevronDown, Clock, Wrench } from "lucide-react";

import type {
  AgentExecutionReadiness,
  AgentRuntimeOverview,
  BackgroundWorkerStateRecord,
} from "@/lib/api";
import { localize } from "@/lib/i18n";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { StatusBadge } from "@/components/ui/page-shell";
import { cn } from "@/lib/utils";
import { AgentRuntimeOverviewPanel } from "./AgentRuntimeOverviewPanel";
import { ExecutionWorkerPanel, WorkerRuntimePanel } from "./AgentWorkerPanels";

/** Counts problems across runtime queue, execution worker and scheduler. */
export function countAgentSystemProblems({
  runtimeOverview,
  executionReadiness,
  scheduledWorker,
  showScheduledWorker,
}: {
  runtimeOverview?: AgentRuntimeOverview;
  executionReadiness?: AgentExecutionReadiness;
  scheduledWorker?: BackgroundWorkerStateRecord;
  showScheduledWorker: boolean;
}): number {
  const issueCount = runtimeOverview?.summary.issues || 0;
  const staleCount = runtimeOverview?.items?.stale_candidates?.length || 0;
  const executionNotReady = Boolean(executionReadiness?.required && !executionReadiness.ready);
  const schedulerNotConfirmed =
    showScheduledWorker && !(scheduledWorker?.status === "running" && !scheduledWorker?.is_stale);
  return issueCount + (staleCount > 0 ? 1 : 0) + (executionNotReady ? 1 : 0) + (schedulerNotConfirmed ? 1 : 0);
}

/**
 * Ops diagnostics (runtime queue, execution worker, scheduler).
 * Shown only when there are problems — no "all healthy" strip for operators.
 */
export function AgentSystemHealthSection({
  runtimeOverview,
  showRuntimeOverview,
  executionReadiness,
  scheduledWorker,
  showScheduledWorker,
  lang,
  onCopyCommand,
  onCleanupStale,
  cleaningStale,
}: {
  runtimeOverview?: AgentRuntimeOverview;
  showRuntimeOverview: boolean;
  executionReadiness?: AgentExecutionReadiness;
  scheduledWorker?: BackgroundWorkerStateRecord;
  showScheduledWorker: boolean;
  lang: "ru" | "en";
  onCopyCommand: (command: string) => void;
  onCleanupStale: () => void;
  cleaningStale: boolean;
}) {
  const problems = countAgentSystemProblems({
    runtimeOverview,
    executionReadiness,
    scheduledWorker,
    showScheduledWorker,
  });

  const [userExpanded, setUserExpanded] = useState<boolean | null>(null);
  // Default open when there are problems; user can collapse.
  const open = userExpanded ?? true;

  const hasAnyPanel = showRuntimeOverview || Boolean(executionReadiness) || showScheduledWorker;
  // Hide entirely when healthy — no "Служебные процессы работают" noise.
  if (!hasAnyPanel || problems === 0) return null;

  return (
    <Collapsible open={open} onOpenChange={(next) => setUserExpanded(next)}>
      <div className="overflow-hidden rounded-xl border border-warning/25 bg-warning/5 transition-colors">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-warning/10"
            aria-label={localize(lang, "Служебные процессы агентов", "Agent background services")}
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-warning/10 text-warning">
              <AlertTriangle className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold text-foreground">
                {localize(lang, "Агенты могут не запускаться", "Agents may fail to start")}
              </span>
              <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                {localize(
                  lang,
                  "Проблемы со служебными процессами. Откройте, чтобы исправить.",
                  "Background services have problems. Open to fix.",
                )}
              </span>
            </span>
            <StatusBadge
              label={localize(lang, `проблем: ${problems}`, `${problems} problem${problems === 1 ? "" : "s"}`)}
              tone="warning"
            />
            <ChevronDown
              className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200", open && "rotate-180")}
              aria-hidden
            />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="space-y-4 border-t border-border/60 bg-surface-0/40 p-4">
            {showRuntimeOverview && runtimeOverview ? (
              <AgentRuntimeOverviewPanel
                overview={runtimeOverview}
                lang={lang}
                onCopyCommand={onCopyCommand}
                onCleanupStale={onCleanupStale}
                cleaningStale={cleaningStale}
              />
            ) : null}
            {executionReadiness ? (
              <ExecutionWorkerPanel readiness={executionReadiness} lang={lang} onCopyCommand={onCopyCommand} />
            ) : null}
            {showScheduledWorker ? (
              <WorkerRuntimePanel
                title={localize(lang, "Планировщик", "Scheduler")}
                description={localize(lang, "Автоматический запуск агентов по расписанию", "Automatic scheduled agent runs")}
                statusTitle={localize(
                  lang,
                  scheduledWorker?.status === "running" && !scheduledWorker?.is_stale
                    ? "Планировщик принимает расписания"
                    : "Планировщик не подтверждён",
                  scheduledWorker?.status === "running" && !scheduledWorker?.is_stale
                    ? "Scheduler is active"
                    : "Scheduler is unavailable",
                )}
                statusDescription={localize(
                  lang,
                  scheduledWorker?.status === "running" && !scheduledWorker?.is_stale
                    ? "Агенты с расписанием будут запущены автоматически."
                    : "Агенты с расписанием не стартуют автоматически, пока процесс не активен.",
                  scheduledWorker?.status === "running" && !scheduledWorker?.is_stale
                    ? "Agents will start automatically when their schedules are due."
                    : "Scheduled agents will not start automatically until the service is restored.",
                )}
                worker={scheduledWorker}
                command="python manage.py run_scheduled_agents --daemon --worker-key default"
                icon={<Clock className="h-4 w-4" />}
                lang={lang}
                onCopyCommand={onCopyCommand}
              />
            ) : null}
            <p className="flex items-center gap-1.5 text-2xs text-muted-foreground/70">
              <Wrench className="h-3 w-3" aria-hidden />
              {localize(
                lang,
                "Диагностика и команды восстановления доступны администраторам.",
                "Diagnostics and recovery commands are available to administrators.",
              )}
            </p>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
