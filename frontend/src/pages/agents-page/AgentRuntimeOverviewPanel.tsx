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
      title={localize(lang, "Система запуска агентов", "Agent execution")}
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
            {hasIssues ? <StatusBadge label={localize(lang, `проблем: ${summary.issues}`, `${summary.issues} issues`)} tone="warning" /> : <StatusBadge label={localize(lang, "без проблем", "clear")} tone="success" />}
            {staleCount ? <StatusBadge label={localize(lang, `зависли: ${staleCount}`, `${staleCount} stale`)} tone="warning" /> : null}
            <span className="text-sm font-semibold text-foreground">
              {hasIssues
                ? localize(lang, "Есть проблемы с запусками", "Execution issues detected")
                : localize(lang, "Запуски работают без ошибок", "Runs have no blockers")}
            </span>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {localize(
              lang,
              `Активных запусков: ${summary.active_runs}. В очереди: ${dispatchQueue}. По расписанию ожидают: ${summary.scheduled_due_now}.`,
              `Active runs: ${summary.active_runs}. Queued: ${dispatchQueue}. Due on schedule: ${summary.scheduled_due_now}.`,
            )}
          </p>
        </div>
        <div className="flex min-w-0 flex-col gap-3 lg:min-w-[520px]">
          <div className="grid min-w-0 grid-cols-2 gap-x-5 gap-y-2 text-xs text-muted-foreground sm:grid-cols-4">
            <WorkerFact label={localize(lang, "активные", "active")} value={String(summary.active_runs)} />
            <WorkerFact label={localize(lang, "ожидают", "pending")} value={String(summary.pending_runs)} />
            <WorkerFact label={localize(lang, "в очереди", "queued")} value={String(summary.queued_dispatches)} />
            <WorkerFact label={localize(lang, "взяты", "claimed")} value={String(summary.claimed_dispatches)} />
            <WorkerFact label={localize(lang, "выполняются", "running")} value={String(summary.running_runs)} />
            <WorkerFact label={localize(lang, "ждут ответа", "waiting")} value={String(summary.waiting_runs)} />
            <WorkerFact label={localize(lang, "по расписанию", "scheduled")} value={String(summary.scheduled_agents)} />
            <WorkerFact label={localize(lang, "пора запустить", "due")} value={String(summary.scheduled_due_now)} />
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
                  : localize(lang, "Убрать зависшие", "Clear stale")}
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
                {localize(lang, "Рекомендуемый сервис запуска", "Recommended execution service")}
              </p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {localize(
                  lang,
                  "Один управляемый процесс обслуживает запуски, расписания и отслеживание состояния.",
                  "One managed process handles runs, schedules, and status tracking.",
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
          description={localize(lang, "Выполняются сейчас", "Running now")}
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
          title={localize(lang, "Очередь запусков", "Run queue")}
          description={localize(lang, "Ожидают или уже приняты в работу", "Waiting or already claimed")}
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
              detail={dispatch.claimed_by ? `${localize(lang, "обработчик", "worker")}: ${dispatch.claimed_by}` : ""}
              to={`/agents/run/${dispatch.run_id}`}
              linkLabel={localize(lang, "Запуск", "Run")}
            />
          ))}
        </RuntimeItemList>
      ) : null}

      {scheduledDue.length ? (
        <RuntimeItemList
          title={localize(lang, "Ожидают по расписанию", "Due on schedule")}
          description={localize(lang, "Агенты, которых пора запустить", "Agents ready for a scheduled run")}
        >
          {scheduledDue.slice(0, 5).map((agent) => (
            <RuntimeItemRow
              key={`scheduled-${agent.agent_id}`}
              status={agent.active_run_id ? agent.active_run_status || "active" : "due"}
              tone={agent.active_run_id ? "info" : "warning"}
              title={agent.agent_name}
              meta={[
                agent.server_names?.[0] || localize(lang, `${agent.server_count} серверов`, `${agent.server_count} servers`),
                formatScheduleConfigLabel(agent.schedule_config, agent.schedule_minutes, lang),
                agent.due_age_seconds ? localize(lang, `ожидает ${formatRuntimeAge(agent.due_age_seconds)}`, `due ${formatRuntimeAge(agent.due_age_seconds)}`) : localize(lang, "пора запускать", "due now"),
              ]}
              to={agent.active_run_id ? `/agents/run/${agent.active_run_id}` : undefined}
              linkLabel={agent.active_run_id ? localize(lang, "Открыть", "Open") : undefined}
            />
          ))}
        </RuntimeItemList>
      ) : null}

      {staleCandidates.length ? (
        <RuntimeItemList
          title={localize(lang, "Возможно зависли", "Possibly stale")}
          description={localize(lang, "Запуски без обновлений дольше ожидаемого", "Runs without updates longer than expected")}
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

