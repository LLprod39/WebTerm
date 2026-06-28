import { useMemo, useState } from "react";
import { ListFilter, Search } from "lucide-react";

import type { AgentRunReportResponse, AgentRunReportStep } from "@/lib/api";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { formatCompactDateTime, formatDuration } from "./formatters";
import { _severityRank, eventDot, severityTone } from "./reportShared";


export function AgentStepsTab({ report, steps }: { report: AgentRunReportResponse; steps: AgentRunReportStep[] }) {
  const [filter, setFilter] = useState<"all" | "active" | "problems" | "done">("all");
  const [query, setQuery] = useState("");
  const stats = useMemo(() => buildStepStats(steps), [steps]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return steps.filter((step) => {
      if (filter === "active" && !stepIsActive(step)) return false;
      if (filter === "problems" && !stepIsProblem(step)) return false;
      if (filter === "done" && !stepIsDone(step)) return false;
      if (!q) return true;
      return stepSearchText(step).includes(q);
    });
  }, [filter, query, steps]);

  return (
    <div className="enterprise-panel overflow-hidden">
      <div className="border-b border-border/70 p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-foreground">Ход агента</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {steps.length ? `${stats.done} из ${steps.length} шагов завершено` : "Шаги появятся после планирования или выполнения команд."}
            </p>
          </div>
          {steps.length ? (
            <div className="grid min-w-[420px] grid-cols-4 gap-2 max-sm:min-w-0 max-sm:grid-cols-2">
              <StepMiniStat label="Готово" value={stats.done} />
              <StepMiniStat label="Активно" value={stats.active} />
              <StepMiniStat label="Риски" value={stats.problems} />
              <StepMiniStat label="Прогресс" value={`${stats.progress}%`} />
            </div>
          ) : null}
        </div>

        {steps.length ? (
          <>
            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between gap-3 text-xs text-muted-foreground">
                <span className="truncate">{stats.current?.title || "Все шаги обработаны"}</span>
                <span className="font-mono">{stats.progress}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full border border-border/70 bg-background/65">
                <div className="h-full rounded-full bg-info transition-[width]" style={{ width: `${stats.progress}%` }} />
              </div>
            </div>

            <div className="mt-4 overflow-x-auto pb-1">
              <ol className="grid min-w-max auto-cols-[180px] grid-flow-col gap-2">
                {steps.map((step) => (
                  <li key={step.id} className={cn("rounded-lg border p-3", stepRailClass(step))}>
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="font-mono text-xs">{String(step.index).padStart(2, "0")}</span>
                      <span className={cn("h-2 w-2 rounded-full", eventDot(step.severity))} />
                    </div>
                    <p className="line-clamp-2 min-h-10 text-xs font-medium leading-5">{step.title}</p>
                    <p className="mt-1 truncate text-[11px] text-muted-foreground">{step.status_label || step.status}</p>
                  </li>
                ))}
              </ol>
            </div>

            <div className="mt-4 flex flex-col gap-3 xl:flex-row xl:items-center">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Поиск по шагам, командам и результатам"
                  className="pl-9"
                />
              </div>
              <div className="flex flex-wrap items-center gap-1 rounded-lg border border-border/70 bg-background/45 p-1">
                <ListFilter className="ml-1 h-3.5 w-3.5 text-muted-foreground" />
                {(["all", "active", "problems", "done"] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setFilter(item)}
                    className={cn(
                      "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                      filter === item ? "bg-card text-foreground" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {stepFilterLabel[item]}
                  </button>
                ))}
              </div>
            </div>
          </>
        ) : null}
      </div>

      <div className="p-4">
        {steps.length ? (
          filtered.length ? (
            <ol className="space-y-3">
              {filtered.map((step, index) => (
                <StepTimelineItem key={step.id} step={step} last={index === filtered.length - 1} />
              ))}
            </ol>
          ) : (
            <div className="workspace-empty text-sm text-muted-foreground">Шаги по текущему фильтру не найдены.</div>
          )
        ) : (
          <EmptyRunDataPanel report={report} kind="steps" />
        )}
      </div>
    </div>
  );
}

const stepFilterLabel = {
  all: "Все",
  active: "Активные",
  problems: "Риски",
  done: "Готово",
};

function StepMiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-border/70 bg-background/45 px-3 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 font-mono text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}

function StepTimelineItem({ step, last }: { step: AgentRunReportStep; last: boolean }) {
  const hasDetails = Boolean(step.description || step.command || step.details || step.error);
  return (
    <li className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
      <div className="relative flex justify-center">
        <span className={cn("mt-4 flex h-7 w-7 items-center justify-center rounded-full border bg-background font-mono text-[11px]", stepIndexClass(step))}>
          {step.index}
        </span>
        {!last ? <span className="absolute top-12 bottom-0 w-px bg-border/70" /> : null}
      </div>
      <article className="min-w-0 rounded-lg border border-border/70 bg-background/45">
        <details className="group" open={stepIsActive(step) || stepIsProblem(step)}>
          <summary className="flex cursor-pointer list-none flex-col gap-3 p-4 lg:flex-row lg:items-center">
            <StatusBadge label={step.status_label || step.status} tone={severityTone[step.severity]} />
            <div className="min-w-0 flex-1">
              <p className="break-words text-sm font-medium leading-6 text-foreground">{step.title}</p>
              {step.command ? <p className="truncate font-mono text-xs text-muted-foreground">{step.command}</p> : null}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {step.started_at ? <span>{formatCompactDateTime(step.started_at)}</span> : null}
              <span className="font-mono">{formatDuration(step.duration_ms)}</span>
            </div>
          </summary>

          <div className="border-t border-border/70 p-4">
            {hasDetails ? (
              <>
                {step.description ? <p className="mb-3 text-sm leading-6 text-muted-foreground">{step.description}</p> : null}
                {step.command ? (
                  <pre className="mb-3 max-h-48 overflow-auto rounded-lg border border-border/70 bg-card/65 p-3 font-mono text-xs leading-5 text-primary">
                    {step.command}
                  </pre>
                ) : null}
                {step.details ? (
                  <p className="whitespace-pre-wrap break-words text-sm leading-6 text-foreground/82">{step.details}</p>
                ) : null}
                {step.error ? (
                  <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-destructive">Ошибка</p>
                    <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-destructive">{step.error}</p>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Детали шага ещё не сохранены.</p>
            )}
          </div>
        </details>
      </article>
    </li>
  );
}

function buildStepStats(steps: AgentRunReportStep[]) {
  const done = steps.filter(stepIsDone).length;
  const active = steps.filter(stepIsActive).length;
  const problems = steps.filter(stepIsProblem).length;
  const current =
    steps.find((step) => step.status === "running" || step.status === "waiting") ||
    steps.find(stepIsProblem) ||
    steps.find((step) => step.status === "pending") ||
    steps[steps.length - 1] ||
    null;
  const progress = steps.length ? Math.round((done / steps.length) * 100) : 0;
  return { done, active, problems, current, progress };
}

function stepIsDone(step: AgentRunReportStep) {
  return ["done", "completed", "success"].includes(step.status) || step.severity === "success";
}

function stepIsProblem(step: AgentRunReportStep) {
  return step.status === "failed" || _severityRank(step.severity) >= _severityRank("warning");
}

function stepIsActive(step: AgentRunReportStep) {
  return ["running", "pending", "waiting", "plan_review"].includes(step.status);
}

function stepSearchText(step: AgentRunReportStep) {
  return [step.title, step.description, step.command, step.status, step.status_label, step.details, step.error]
    .filter(Boolean)
    .join("\n")
    .toLowerCase();
}

function stepRailClass(step: AgentRunReportStep) {
  if (stepIsProblem(step)) return "border-destructive/35 bg-destructive/10 text-destructive";
  if (step.status === "running") return "border-info/35 bg-info/10 text-info";
  if (stepIsDone(step)) return "border-success/35 bg-success/10 text-success";
  return "border-border/70 bg-background/45 text-muted-foreground";
}

function stepIndexClass(step: AgentRunReportStep) {
  if (stepIsProblem(step)) return "border-destructive/40 text-destructive";
  if (step.status === "running") return "border-info/40 text-info";
  if (stepIsDone(step)) return "border-success/40 text-success";
  return "border-border/70 text-muted-foreground";
}

function EmptyRunDataPanel({ report, kind }: { report: AgentRunReportResponse; kind: "logs" | "steps" }) {
  const active = !report.report_state?.is_terminal && !report.report_state?.report_ready;
  const title = kind === "logs" ? "Логи ещё не записаны" : "Шаги агента ещё не сохранены";
  const terminalTitle = kind === "logs" ? "Логи не найдены" : "Шаги агента не найдены";
  const description = active
    ? report.report_state?.next_expected || "Данные появятся после того, как агент начнёт выполнять команды и задачи."
    : "В этом запуске backend не сохранил данные для этой вкладки.";

  return (
    <div className="workspace-empty text-sm text-muted-foreground">
      <p className="font-medium text-foreground">{active ? title : terminalTitle}</p>
      <p className="mt-1 max-w-2xl leading-6">{description}</p>
    </div>
  );
}

