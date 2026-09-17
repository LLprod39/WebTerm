import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Circle, Loader2 } from "lucide-react";

import { StatusBadge } from "@/components/system/StatusBadge";
import type { AgentRunActivityFilters, AgentRunActivityV2Item, AgentRunActivityV2Response } from "@/lib/api";

import { reportTone, type ReportViewModel } from "./reportViewModel";

function time(value: string | null) {
  if (!value) return "";
  return new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value));
}

const statusLabels: Record<string, string> = {
  succeeded: "Готово",
  success: "Готово",
  completed: "Готово",
  failed: "Ошибка",
  error: "Ошибка",
  running: "В работе",
  pending: "Ожидает",
  unknown: "—",
};

function titleOf(item: AgentRunActivityV2Item, n: number) {
  if (item.title && !/^[a-z0-9_.:/-]+$/.test(item.title.trim())) return item.title;
  if (item.kind === "command") return `Команда ${n}`;
  if (item.kind === "tool") return `Операция ${n}`;
  return `Шаг ${n}`;
}

/**
 * Только операторские шаги — как compact timeline в остальных экранах WebTrerm.
 * Фильтры и фазы убраны: шум мешал. Итерации модели — в details.
 */
export function AgentRunExecutionV2({
  viewModel,
  response,
  loading,
  error,
}: {
  viewModel: ReportViewModel;
  response?: AgentRunActivityV2Response;
  loading: boolean;
  error: unknown;
  filters?: AgentRunActivityFilters;
  setFilters?: (patch: Partial<AgentRunActivityFilters>) => void;
}) {
  const all = response?.items || viewModel.embedded.activity;
  const operations = all.filter((item) => item.kind !== "iteration");
  const iterations = all.filter((item) => item.kind === "iteration");
  const done = operations.filter((item) => item.success === true || ["succeeded", "success", "completed"].includes(item.status)).length;
  const progress = operations.length ? Math.round((done / operations.length) * 100) : 0;

  if (loading && !operations.length) {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Загружаем шаги…
      </p>
    );
  }

  if (error && !operations.length) {
    return (
      <p role="alert" className="rounded-sm border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
        {error instanceof Error ? error.message : "Шаги недоступны."}
      </p>
    );
  }

  if (!operations.length && !iterations.length) {
    return (
      <div className="rounded-sm border border-border bg-card p-5 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">{viewModel.run.isActive ? "Агент готовит план" : "Шаги не сохранены"}</p>
        <p className="mt-1">Команды и проверки появятся здесь по ходу работы.</p>
      </div>
    );
  }

  return (
    <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1" aria-labelledby="steps-heading">
      <div className="border-b border-border px-4 py-3 sm:px-5">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <h2 id="steps-heading" className="text-sm font-semibold text-foreground">
              Ход работы
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {done} из {operations.length || "—"} шагов
            </p>
          </div>
          {operations.length ? <span className="font-mono text-xs text-muted-foreground">{progress}%</span> : null}
        </div>
        {operations.length ? (
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-secondary">
            <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${progress}%` }} />
          </div>
        ) : null}
      </div>

      <ol className="divide-y divide-border">
        {operations.map((item, index) => (
          <StepRow key={item.id} item={item} index={index + 1} runId={viewModel.run.id} />
        ))}
      </ol>

      {iterations.length ? (
        <details className="border-t border-border bg-surface-0/50">
          <summary className="cursor-pointer px-4 py-3 text-xs font-medium text-muted-foreground sm:px-5">
            Техжурнал модели · {iterations.length}
          </summary>
          <ol className="divide-y divide-border border-t border-border">
            {iterations.map((item, index) => (
              <StepRow key={item.id} item={item} index={index + 1} runId={viewModel.run.id} compact />
            ))}
          </ol>
        </details>
      ) : null}
    </section>
  );
}

function StepRow({
  item,
  index,
  runId,
  compact = false,
}: {
  item: AgentRunActivityV2Item;
  index: number;
  runId: number;
  compact?: boolean;
}) {
  const tone = item.success === true ? "success" : item.success === false ? "danger" : reportTone(item.status);
  const Icon = tone === "success" ? CheckCircle2 : tone === "danger" ? AlertTriangle : item.status === "running" ? Loader2 : Circle;
  const open = item.status === "running" || item.success === false;
  const evidence = item.evidence_refs?.[0];

  return (
    <li>
      <details open={open && !compact}>
        <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 sm:px-5">
          <Icon
            className={`h-4 w-4 shrink-0 ${tone === "danger" ? "text-destructive" : tone === "success" ? "text-success" : item.status === "running" ? "animate-spin text-info" : "text-muted-foreground"}`}
            aria-hidden
          />
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{titleOf(item, index)}</span>
          <StatusBadge label={statusLabels[item.status] || "—"} tone={tone} />
          {item.started_at ? <time className="hidden font-mono text-xs text-muted-foreground sm:inline">{time(item.started_at)}</time> : null}
        </summary>
        {!compact ? (
          <div className="space-y-2 border-t border-border bg-surface-0/40 px-11 py-3 text-sm">
            {item.command ? <pre className="overflow-x-auto rounded-sm border border-border bg-background p-3 font-mono text-xs text-foreground">{item.command}</pre> : null}
            {item.summary ? <p className="text-muted-foreground">{item.summary}</p> : null}
            {item.error ? <p className="whitespace-pre-wrap text-destructive">{item.error}</p> : null}
            {evidence ? (
              <Link
                className="inline-block text-xs font-medium text-primary underline-offset-4 hover:underline"
                to={`/agents/run/${runId}?tab=materials&view=${(evidence.kind || "").includes("artifact") ? "files" : "tech"}&evidence=${encodeURIComponent(evidence.ref)}`}
              >
                {evidence.label || "Материал →"}
              </Link>
            ) : null}
          </div>
        ) : item.summary ? (
          <p className="border-t border-border px-11 py-2 text-xs text-muted-foreground">{item.summary}</p>
        ) : null}
      </details>
    </li>
  );
}
