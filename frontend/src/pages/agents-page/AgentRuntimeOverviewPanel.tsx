import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Activity, AlertTriangle, Copy, Eye, RefreshCw } from "lucide-react";

import type { AgentRuntimeOverview } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { formatScheduleConfigLabel } from "./agentPageUtils";
import { formatRuntimeAge, severityTone } from "./agentRuntimeShared";
import { WorkerFact } from "./AgentWorkerPanels";


export function AgentRuntimeOverviewPanel({
  overview,
  lang,
  onCopyCommand,
  onCleanupStale,
  cleaningStale,
}: {
  overview: AgentRuntimeOverview;
  lang: "ru" | "en";
  onCopyCommand: (command: string) => void;
  onCleanupStale: () => void;
  cleaningStale: boolean;
}) {
  const summary = overview.summary;
  const hasIssues = overview.issues.length > 0;
  const dispatchQueue = summary.queued_dispatches + summary.claimed_dispatches;
  const staleCount = overview.items?.stale_candidates?.length || 0;
  const supervisorCommand = overview.commands?.ops_supervisor || "";

  return (
    <SectionCard
      title={localize(lang, "Agent runtime", "Agent runtime")}
      description={localize(
        lang,
        "Очередь запусков, расписание и блокеры выполнения",
        "Run queue, schedule, and execution blockers",
      )}
      icon={<Activity className="h-4 w-4" />}
      bodyClassName="space-y-4"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={overview.status} tone={severityTone(overview.severity)} />
            {hasIssues ? <StatusBadge label={`${summary.issues} issues`} tone="warning" /> : <StatusBadge label="clear" tone="success" />}
            {staleCount ? <StatusBadge label={`${staleCount} stale`} tone="warning" /> : null}
            <span className="text-sm font-semibold text-foreground">
              {hasIssues
                ? localize(lang, "Есть runtime-блокеры", "Runtime blockers detected")
                : localize(lang, "Очередь без блокеров", "Queue has no blockers")}
            </span>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {localize(
              lang,
              `${summary.active_runs} активных запусков, ${dispatchQueue} dispatch в очереди, ${summary.scheduled_due_now} due по расписанию.`,
              `${summary.active_runs} active runs, ${dispatchQueue} queued dispatches, ${summary.scheduled_due_now} due scheduled agents.`,
            )}
          </p>
        </div>
        <div className="flex min-w-0 flex-col gap-3 lg:min-w-[520px]">
          <div className="grid min-w-0 grid-cols-2 gap-x-5 gap-y-2 text-xs text-muted-foreground sm:grid-cols-4">
            <WorkerFact label="active" value={String(summary.active_runs)} />
            <WorkerFact label="pending" value={String(summary.pending_runs)} />
            <WorkerFact label="queued" value={String(summary.queued_dispatches)} />
            <WorkerFact label="claimed" value={String(summary.claimed_dispatches)} />
            <WorkerFact label="running" value={String(summary.running_runs)} />
            <WorkerFact label="waiting" value={String(summary.waiting_runs)} />
            <WorkerFact label="scheduled" value={String(summary.scheduled_agents)} />
            <WorkerFact label="due" value={String(summary.scheduled_due_now)} />
          </div>
          {staleCount ? (
            <div className="flex justify-start sm:justify-end">
              <Button
                size="sm"
                variant="outline"
                className="h-9 shrink-0 gap-1.5 border-amber-500/30 text-amber-200 hover:text-amber-100"
                disabled={cleaningStale}
                onClick={onCleanupStale}
              >
                {cleaningStale ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                {cleaningStale
                  ? localize(lang, "Очищаем", "Cleaning")
                  : localize(lang, "Очистить stale", "Clean stale")}
              </Button>
            </div>
          ) : null}
        </div>
      </div>
      {hasIssues && supervisorCommand ? (
        <div className="rounded-md border border-primary/20 bg-primary/8 px-3 py-3">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">
                {localize(lang, "Рекомендуемый production worker", "Recommended production worker")}
              </p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {localize(
                  lang,
                  "Supervisor держит execution-plane, расписания и watchers одним управляемым процессом.",
                  "Supervisor keeps execution-plane, schedules, and watchers under one managed process.",
                )}
              </p>
            </div>
            <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center lg:min-w-[520px]">
              <code className="min-w-0 flex-1 break-words rounded-md border border-border/60 bg-background/50 px-2 py-1.5 text-xs text-primary">
                {supervisorCommand}
              </code>
              <Button
                size="xs"
                variant="outline"
                className="shrink-0 gap-1"
                onClick={() => onCopyCommand(supervisorCommand)}
              >
                <Copy className="h-3 w-3" />
                {localize(lang, "Копировать", "Copy")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
      {hasIssues ? (
        <div className="grid gap-2 lg:grid-cols-2">
          {overview.issues.slice(0, 4).map((issue) => (
            <div key={issue.id} className="rounded-md border border-amber-500/20 bg-amber-500/8 px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge label={issue.severity} tone={severityTone(issue.severity)} />
                <span className="text-sm font-semibold text-foreground">{issue.title}</span>
              </div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{issue.description}</p>
              {issue.next_action ? (
                <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
                  <code className="min-w-0 flex-1 break-words rounded-md border border-border/60 bg-background/50 px-2 py-1.5 text-xs text-amber-200">
                    {issue.next_action}
                  </code>
                  <Button
                    size="xs"
                    variant="outline"
                    className="shrink-0 gap-1"
                    onClick={() => onCopyCommand(issue.next_action)}
                  >
                    <Copy className="h-3 w-3" />
                    {localize(lang, "Копировать", "Copy")}
                  </Button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
      <AgentRuntimeItems overview={overview} lang={lang} />
    </SectionCard>
  );
}

function AgentRuntimeItems({ overview, lang }: { overview: AgentRuntimeOverview; lang: "ru" | "en" }) {
  const items = overview.items || {
    active_runs: [],
    queued_dispatches: [],
    scheduled_due: [],
    stale_candidates: [],
  };
  const activeRuns = items.active_runs || [];
  const queuedDispatches = items.queued_dispatches || [];
  const scheduledDue = items.scheduled_due || [];
  const staleCandidates = items.stale_candidates || [];
  const hasItems = activeRuns.length || queuedDispatches.length || scheduledDue.length || staleCandidates.length;

  if (!hasItems) return null;

  return (
    <div className="grid gap-3 xl:grid-cols-3">
      {activeRuns.length ? (
        <RuntimeItemList
          title={localize(lang, "Активные запуски", "Active runs")}
          description={localize(lang, "Что сейчас занимает execution slot", "Currently occupying execution slots")}
        >
          {activeRuns.slice(0, 5).map((run) => (
            <RuntimeItemRow
              key={`run-${run.run_id}`}
              status={run.is_stale_candidate ? "stale" : run.status}
              tone={run.is_stale_candidate ? "warning" : severityTone(run.status === "running" ? "success" : "info")}
              title={run.agent_name}
              meta={[
                `#${run.run_id}`,
                run.server_name || localize(lang, "сервер не указан", "no server"),
                formatRuntimeAge(run.age_seconds),
              ]}
              to={`/agents/run/${run.run_id}`}
              linkLabel={localize(lang, "Следить", "Watch")}
            />
          ))}
        </RuntimeItemList>
      ) : null}

      {queuedDispatches.length ? (
        <RuntimeItemList
          title={localize(lang, "Очередь dispatch", "Dispatch queue")}
          description={localize(lang, "Что ждёт или взято worker'ом", "Queued or claimed by a worker")}
        >
          {queuedDispatches.slice(0, 5).map((dispatch) => (
            <RuntimeItemRow
              key={`dispatch-${dispatch.dispatch_id}`}
              status={dispatch.status}
              tone={severityTone(dispatch.status === "claimed" ? "info" : "warning")}
              title={dispatch.agent_name}
              meta={[
                dispatch.dispatch_kind,
                `run #${dispatch.run_id}`,
                localize(lang, `в очереди ${formatRuntimeAge(dispatch.queued_age_seconds)}`, `queued ${formatRuntimeAge(dispatch.queued_age_seconds)}`),
              ]}
              detail={dispatch.claimed_by ? `worker: ${dispatch.claimed_by}` : ""}
              to={`/agents/run/${dispatch.run_id}`}
              linkLabel={localize(lang, "Run", "Run")}
            />
          ))}
        </RuntimeItemList>
      ) : null}

      {scheduledDue.length ? (
        <RuntimeItemList
          title={localize(lang, "Due расписание", "Due schedule")}
          description={localize(lang, "Кого пора запускать по расписанию", "Agents due for scheduled launch")}
        >
          {scheduledDue.slice(0, 5).map((agent) => (
            <RuntimeItemRow
              key={`scheduled-${agent.agent_id}`}
              status={agent.active_run_id ? agent.active_run_status || "active" : "due"}
              tone={agent.active_run_id ? "info" : "warning"}
              title={agent.agent_name}
              meta={[
                agent.server_names?.[0] || `${agent.server_count} servers`,
                formatScheduleConfigLabel(agent.schedule_config, agent.schedule_minutes, lang),
                agent.due_age_seconds ? localize(lang, `due ${formatRuntimeAge(agent.due_age_seconds)}`, `due ${formatRuntimeAge(agent.due_age_seconds)}`) : "due now",
              ]}
              to={agent.active_run_id ? `/agents/run/${agent.active_run_id}` : undefined}
              linkLabel={agent.active_run_id ? localize(lang, "Открыть", "Open") : undefined}
            />
          ))}
        </RuntimeItemList>
      ) : null}

      {staleCandidates.length ? (
        <RuntimeItemList
          title={localize(lang, "Зависшие кандидаты", "Stale candidates")}
          description={localize(lang, "Активные строки старше runtime threshold", "Active rows older than runtime threshold")}
        >
          {staleCandidates.slice(0, 5).map((run) => (
            <RuntimeItemRow
              key={`stale-${run.run_id}`}
              status="stale"
              tone="warning"
              title={run.agent_name}
              meta={[`#${run.run_id}`, run.status, formatRuntimeAge(run.age_seconds)]}
              to={`/agents/run/${run.run_id}`}
              linkLabel={localize(lang, "Проверить", "Inspect")}
            />
          ))}
        </RuntimeItemList>
      ) : null}
    </div>
  );
}

function RuntimeItemList({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-md border border-border/70 bg-background/35">
      <div className="border-b border-border/60 px-3 py-2">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{description}</p>
      </div>
      <div className="divide-y divide-border/50">{children}</div>
    </div>
  );
}

function RuntimeItemRow({
  status,
  tone,
  title,
  meta,
  detail,
  to,
  linkLabel,
}: {
  status: string;
  tone: "neutral" | "success" | "warning" | "danger" | "info";
  title: string;
  meta: string[];
  detail?: string;
  to?: string;
  linkLabel?: string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <StatusBadge label={status} tone={tone} />
          <span className="truncate text-sm font-medium text-foreground">{title}</span>
        </div>
        <p className="mt-1 truncate text-xs text-muted-foreground">{meta.filter(Boolean).join(" · ")}</p>
        {detail ? <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{detail}</p> : null}
      </div>
      {to && linkLabel ? (
        <Button asChild size="xs" variant="ghost" className="h-7 shrink-0 gap-1 text-muted-foreground hover:text-foreground">
          <Link to={to}>
            <Eye className="h-3 w-3" />
            {linkLabel}
          </Link>
        </Button>
      ) : null}
    </div>
  );
}

