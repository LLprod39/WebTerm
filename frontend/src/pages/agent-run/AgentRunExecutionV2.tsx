import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Circle, Loader2 } from "lucide-react";

import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import type {
  AgentRunActivityFilters,
  AgentRunActivityV2Item,
  AgentRunActivityV2Response,
} from "@/lib/api";

import { reportTone, type ReportPhaseViewModel, type ReportViewModel } from "./reportViewModel";

function time(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value));
}

const activityStatusLabels: Record<string, string> = {
  succeeded: "Выполнено",
  success: "Выполнено",
  completed: "Завершено",
  failed: "Ошибка",
  error: "Ошибка",
  running: "Выполняется",
  pending: "Ожидает",
  unknown: "Неизвестно",
};
const phaseStatusLabels: Record<string, string> = { completed: "Завершено", active: "В работе", problem: "Есть проблема", active_problem: "В работе · есть проблема", pending: "Ожидает" };

function visibleActivityTitle(item: AgentRunActivityV2Item, displayOrdinal: number) {
  const rawLooking = !item.title || /^[a-z0-9_.:/-]+$/.test(item.title.trim());
  if (!rawLooking) return item.title;
  if (item.kind === "command") return `Команда ${displayOrdinal}`;
  if (item.kind === "tool") return `Операция ${displayOrdinal}`;
  if (item.kind === "iteration") return `Итерация ${displayOrdinal}`;
  return `Шаг ${displayOrdinal}`;
}

function visibleActivitySummary(item: AgentRunActivityV2Item) {
  if (item.kind === "step" && item.summary && item.summary.length <= 220) return item.summary;
  if (item.success === true) return "Операция завершена; результат сохранён в доказательствах.";
  if (item.success === false) return "Операция завершилась ошибкой; подробности сохранены.";
  if (["running", "pending"].includes(item.status)) return "Операция ещё выполняется.";
  return "Статус старой записи не подтверждён; подробности сохранены.";
}

function ActivityItem({ item, runId, displayOrdinal }: { item: AgentRunActivityV2Item; runId: number; displayOrdinal: number }) {
  const tone = item.success === true ? "success" : item.success === false ? "danger" : reportTone(item.status);
  const Icon = tone === "success" ? CheckCircle2 : tone === "danger" ? AlertTriangle : Circle;
  const raw = [
    item.title ? `Операция: ${item.title}` : "",
    item.tool ? `Инструмент: ${item.tool}` : "",
    item.server ? `Сервер: ${item.server}` : "",
    item.command ? `Команда:\n${item.command}` : "",
    item.summary ? `Сохранённый вывод:\n${item.summary}` : "",
    item.exit_code != null ? `Код выхода: ${item.exit_code}` : "",
    item.error ? `Ошибка:\n${item.error}` : "",
  ].filter(Boolean).join("\n\n");

  return (
    <li className="relative grid gap-1 border-l border-border pb-4 pl-6 last:pb-0">
      <Icon className={`absolute -left-2 top-1 h-4 w-4 bg-background ${tone === "danger" ? "text-destructive" : tone === "success" ? "text-success" : "text-muted-foreground"}`} aria-hidden />
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h4 className="font-medium leading-6 text-foreground">{visibleActivityTitle(item, displayOrdinal)}</h4>
          <p className="text-sm leading-6 text-foreground/80">{visibleActivitySummary(item)}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <StatusBadge label={activityStatusLabels[item.status] || "Неизвестно"} tone={tone} />
          <time className="font-mono text-xs text-foreground/80" dateTime={item.started_at || undefined}>{time(item.started_at)}</time>
        </div>
      </div>
      {item.evidence_refs?.length ? (
        <div className="flex flex-wrap gap-2 py-1">
          {item.evidence_refs.map((ref) => {
            const view = ref.kind === "event" ? "events" : ref.kind === "artifact" ? "artifacts" : ref.kind === "document" ? "document" : "activity";
            return (
              <Link key={`${ref.kind}-${ref.ref}`} className="text-xs font-medium text-primary underline underline-offset-4" to={`/agents/run/${runId}?tab=evidence&view=${view}&evidence=${encodeURIComponent(ref.ref)}`}>
                {ref.label || ref.ref}
              </Link>
            );
          })}
        </div>
      ) : null}
      {raw ? (
        <details className="mt-1 rounded-sm border border-border bg-surface-0">
          <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
            Технические детали
          </summary>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words border-t border-border p-3 font-mono text-xs leading-5 text-foreground">{raw}</pre>
        </details>
      ) : null}
    </li>
  );
}

function PhaseContent({ phase, activity, viewModel }: { phase: ReportPhaseViewModel; activity: AgentRunActivityV2Item[]; viewModel: ReportViewModel }) {
  if (phase.id === "goal") {
    return <p className="text-sm leading-6 text-foreground/80">{phase.summary !== "Нет записей" ? phase.summary : viewModel.header.summary}</p>;
  }
  if (phase.id === "action") {
    const operations = activity.filter((item) => item.kind !== "iteration");
    const iterations = activity.filter((item) => item.kind === "iteration");
    if (!operations.length && !iterations.length) return <p className="text-sm text-muted-foreground">Действия пока не записаны.</p>;
    return (
      <div className="space-y-3">
        {operations.length ? <ol className="mt-1 pl-2">{operations.map((item, index) => <ActivityItem key={item.id} item={item} runId={viewModel.run.id} displayOrdinal={index + 1} />)}</ol> : null}
        {iterations.length ? (
          <details className="rounded-sm border border-border bg-surface-0">
            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
              Технический журнал · {iterations.length} итераций
            </summary>
            <ol className="border-t border-border p-4 pl-6">{iterations.map((item, index) => <ActivityItem key={item.id} item={item} runId={viewModel.run.id} displayOrdinal={index + 1} />)}</ol>
          </details>
        ) : null}
      </div>
    );
  }
  if (phase.id === "observation") {
    return viewModel.findings.length ? (
      <ul className="space-y-2 text-sm text-muted-foreground">
        {viewModel.findings.slice(0, 5).map((finding) => <li key={finding.id} className="flex gap-2"><span aria-hidden>•</span><span>{finding.title}{finding.summary ? `: ${finding.summary}` : ""}</span></li>)}
      </ul>
    ) : <p className="text-sm text-muted-foreground">Наблюдения пока не выделены.</p>;
  }
  return <p className="text-sm leading-6 text-muted-foreground">{viewModel.header.summary}</p>;
}

export function AgentRunExecutionV2({
  viewModel,
  response,
  loading,
  error,
  filters,
  setFilters,
}: {
  viewModel: ReportViewModel;
  response?: AgentRunActivityV2Response;
  loading: boolean;
  error: unknown;
  filters: AgentRunActivityFilters;
  setFilters: (patch: Partial<AgentRunActivityFilters>) => void;
}) {
  const activity = response?.items || viewModel.embedded.activity;
  const totalOperations = viewModel.counts.activities;
  const processedOperations = Math.min(viewModel.counts.processedActivities, totalOperations || viewModel.counts.processedActivities);
  const progressMax = Math.max(totalOperations, 1);
  return (
    <section aria-labelledby="execution-heading" className="space-y-4">
      <div className="flex flex-col gap-3 rounded-sm border border-border bg-card p-4 shadow-elev-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 id="execution-heading" className="font-display text-lg font-semibold text-foreground">Выполнение</h2>
          <p className="mt-1 text-sm text-foreground/80">Цель, действия, наблюдения и итог без шума от сырых инструментов. Всего {totalOperations} операций.</p>
        </div>
        <div className="flex flex-wrap gap-2" aria-label="Фильтры активности">
          <label className="grid gap-1 text-xs text-foreground/80">
            Тип
            <select
              className="h-9 rounded-sm border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={filters.kind?.[0] || ""}
              onChange={(event) => setFilters({ kind: event.target.value ? [event.target.value] : undefined })}
            >
              <option value="">Все</option><option value="step">Шаги</option><option value="tool">Инструменты</option><option value="command">Команды</option><option value="iteration">Итерации</option>
            </select>
          </label>
          <label className="grid gap-1 text-xs text-foreground/80">
            Статус
            <select
              className="h-9 rounded-sm border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={filters.status?.[0] || ""}
              onChange={(event) => setFilters({ status: event.target.value ? [event.target.value] : undefined })}
            >
              <option value="">Все</option><option value="succeeded">Успешно</option><option value="failed">Ошибка</option><option value="unknown">Неизвестно</option>
            </select>
          </label>
        </div>
      </div>

      <div className="rounded-sm border border-border bg-surface-0 p-3">
        <div className="mb-2 flex items-center justify-between gap-3 text-xs text-muted-foreground"><span>{processedOperations} обработано</span><span>{totalOperations} операций</span></div>
        <div role="progressbar" aria-label="Обработанные операции" aria-valuemin={0} aria-valuemax={progressMax} aria-valuenow={processedOperations} className="h-2 overflow-hidden rounded-full bg-surface-2">
          <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${Math.min(100, (processedOperations / progressMax) * 100)}%` }} />
        </div>
      </div>

      {loading ? <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />Загружаем активность…</p> : null}
      {error ? <p role="alert" className="rounded-sm border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error instanceof Error ? error.message : "Активность недоступна."}</p> : null}

      <div className="grid gap-3">
        {viewModel.phases.map((phase, index) => (
          <section key={phase.id} data-testid={`execution-phase-${phase.id}`} aria-labelledby={`phase-${phase.id}-heading`} className="rounded-sm border border-border bg-card p-4 shadow-elev-1">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-full border border-border bg-surface-0 font-mono text-xs font-semibold text-muted-foreground">{index + 1}</span>
              <h3 id={`phase-${phase.id}-heading`} className="font-semibold text-foreground">{phase.label}</h3>
              <StatusBadge label={phaseStatusLabels[phase.status] || "Ожидает"} tone={phase.tone} />
            </div>
            <PhaseContent phase={phase} activity={activity} viewModel={viewModel} />
          </section>
        ))}
      </div>

      {response?.page ? (
        <nav aria-label="Страницы активности" className="flex items-center justify-between gap-3 rounded-sm border border-border bg-surface-0 p-2">
          <Button type="button" size="sm" variant="ghost" disabled={!response.page.prev_cursor} onClick={() => setFilters({ cursor: response.page.prev_cursor, direction: "newer" })}>
            <ChevronLeft className="mr-1 h-4 w-4" aria-hidden />Новее
          </Button>
          <span className="text-xs text-muted-foreground">Показано {activity.length} из {response.total}</span>
          <Button type="button" size="sm" variant="ghost" disabled={!response.page.has_more || !response.page.next_cursor} onClick={() => setFilters({ cursor: response.page.next_cursor, direction: "older" })}>
            Старше<ChevronRight className="ml-1 h-4 w-4" aria-hidden />
          </Button>
        </nav>
      ) : null}
    </section>
  );
}
