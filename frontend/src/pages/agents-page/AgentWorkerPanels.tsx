import type { ReactNode } from "react";
import { Copy, Cpu } from "lucide-react";

import type { AgentExecutionReadiness, BackgroundWorkerStateRecord } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { formatWorkerTime, readinessTone, workerStateTone, workerSummaryEntries } from "./agentRuntimeShared";


export function ExecutionWorkerPanel({
  readiness,
  lang,
  onCopyCommand,
}: {
  readiness: AgentExecutionReadiness;
  lang: "ru" | "en";
  onCopyCommand: (command: string) => void;
}) {
  const worker = readiness.worker;
  const summaryEntries = workerSummaryEntries(worker?.last_summary);
  const command = readiness.next_action.replace(/^.*?:\s*/, "").trim();
  const tone = readinessTone(readiness);

  return (
    <SectionCard
      title={localize(lang, "Сервис выполнения", "Execution service")}
      description={localize(
        lang,
        "Состояние очереди автономных агентов",
        "Autonomous agent queue status",
      )}
      icon={<Cpu className="h-4 w-4" />}
      bodyClassName="space-y-4"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={readiness.status} tone={tone} />
            {worker?.is_stale ? <StatusBadge label={localize(lang, "Нет обновлений", "Stale")} tone="warning" /> : null}
            <span className="text-sm font-semibold text-foreground">{readiness.title}</span>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{readiness.description}</p>
          {readiness.next_action ? (
            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
              <code className="min-w-0 flex-1 break-words rounded-md border border-border/60 bg-background/50 px-2.5 py-2 text-xs text-amber-200">
                {command || readiness.next_action}
              </code>
              <Button
                size="sm"
                variant="outline"
                className="h-9 shrink-0 gap-1.5"
                onClick={() => onCopyCommand(command || readiness.next_action)}
              >
                <Copy className="h-3.5 w-3.5" />
                {localize(lang, "Скопировать", "Copy")}
              </Button>
            </div>
          ) : null}
        </div>
        <div className="grid min-w-0 grid-cols-2 gap-x-5 gap-y-2 text-xs text-muted-foreground sm:grid-cols-3 lg:min-w-[420px]">
          <WorkerFact label={localize(lang, "Обработчик", "Worker")} value={worker?.worker_key || "default"} />
          <WorkerFact label={localize(lang, "Узел", "Host")} value={worker?.hostname || "—"} />
          <WorkerFact label="PID" value={worker?.pid ? String(worker.pid) : "—"} />
          <WorkerFact label={localize(lang, "Последний сигнал", "Heartbeat")} value={formatWorkerTime(worker?.heartbeat_at, lang)} />
          <WorkerFact label={localize(lang, "Резерв до", "Lease until")} value={formatWorkerTime(worker?.lease_expires_at, lang)} />
          <WorkerFact label={localize(lang, "Последний цикл", "Last cycle")} value={formatWorkerTime(worker?.last_cycle_finished_at, lang)} />
        </div>
      </div>
      {worker?.last_error ? (
        <div className="rounded-md border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs leading-5 text-destructive">
          {worker.last_error}
        </div>
      ) : null}
      {summaryEntries.length ? (
        <div className="flex flex-wrap gap-2">
          {summaryEntries.map(([key, value]) => (
            <span key={key} className="rounded-md border border-border/60 bg-secondary/20 px-2 py-1 text-xs text-muted-foreground">
              <span className="font-mono text-foreground">{key}</span>: {String(value)}
            </span>
          ))}
        </div>
      ) : null}
    </SectionCard>
  );
}

export function WorkerRuntimePanel({
  title,
  description,
  statusTitle,
  statusDescription,
  worker,
  command,
  icon,
  lang,
  onCopyCommand,
}: {
  title: string;
  description: string;
  statusTitle: string;
  statusDescription: string;
  worker?: BackgroundWorkerStateRecord;
  command: string;
  icon: ReactNode;
  lang: "ru" | "en";
  onCopyCommand: (command: string) => void;
}) {
  const summaryEntries = workerSummaryEntries(worker?.last_summary);
  const status = worker?.status || "missing";
  const tone = workerStateTone(worker);
  const shouldShowCommand = !worker || worker.is_stale || worker.status === "missing" || worker.status === "stopped" || worker.status === "error";

  return (
    <SectionCard
      title={title}
      description={description}
      icon={icon}
      bodyClassName="space-y-4"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={status} tone={tone} />
            {worker?.is_stale ? <StatusBadge label={localize(lang, "Нет обновлений", "Stale")} tone="warning" /> : null}
            <span className="text-sm font-semibold text-foreground">{statusTitle}</span>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{statusDescription}</p>
          {shouldShowCommand ? (
            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
              <code className="min-w-0 flex-1 break-words rounded-md border border-border/60 bg-background/50 px-2.5 py-2 text-xs text-amber-200">
                {command}
              </code>
              <Button
                size="sm"
                variant="outline"
                className="h-9 shrink-0 gap-1.5"
                onClick={() => onCopyCommand(command)}
              >
                <Copy className="h-3.5 w-3.5" />
                {localize(lang, "Скопировать", "Copy")}
              </Button>
            </div>
          ) : null}
        </div>
        <div className="grid min-w-0 grid-cols-2 gap-x-5 gap-y-2 text-xs text-muted-foreground sm:grid-cols-3 lg:min-w-[420px]">
          <WorkerFact label={localize(lang, "Обработчик", "Worker")} value={worker?.worker_key || "default"} />
          <WorkerFact label={localize(lang, "Узел", "Host")} value={worker?.hostname || "—"} />
          <WorkerFact label="PID" value={worker?.pid ? String(worker.pid) : "—"} />
          <WorkerFact label={localize(lang, "Последний сигнал", "Heartbeat")} value={formatWorkerTime(worker?.heartbeat_at, lang)} />
          <WorkerFact label={localize(lang, "Резерв до", "Lease until")} value={formatWorkerTime(worker?.lease_expires_at, lang)} />
          <WorkerFact label={localize(lang, "Последний цикл", "Last cycle")} value={formatWorkerTime(worker?.last_cycle_finished_at, lang)} />
        </div>
      </div>
      {worker?.last_error ? (
        <div className="rounded-md border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs leading-5 text-destructive">
          {worker.last_error}
        </div>
      ) : null}
      {summaryEntries.length ? (
        <div className="flex flex-wrap gap-2">
          {summaryEntries.map(([key, value]) => (
            <span key={key} className="rounded-md border border-border/60 bg-secondary/20 px-2 py-1 text-xs text-muted-foreground">
              <span className="font-mono text-foreground">{key}</span>: {String(value)}
            </span>
          ))}
        </div>
      ) : null}
    </SectionCard>
  );
}

export function WorkerFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-medium text-muted-foreground/70">{label}</p>
      <p className="mt-0.5 truncate text-foreground">{value}</p>
    </div>
  );
}
