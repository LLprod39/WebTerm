import {
  CheckCircle2,
  Clock,
  Copy,
  Loader2,
  MoreHorizontal,
  Play,
  Trash2,
  XCircle,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { formatActivityDetail, formatActivityLabel, formatRelativeTime } from "@/components/studio/StudioActivityText";
import { getPipelineActivityState } from "@/components/pipeline/pipelineActivity";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { PipelineListItem } from "@/lib/api";

function RunStatusBadge({ status, lang }: { status: string; lang: string }) {
  const normalized = status.toLowerCase();
  if (normalized === "completed") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-emerald-500/20 bg-emerald-500/10 px-1.5 py-0.5 text-xs font-semibold text-emerald-400">
        <CheckCircle2 className="h-2.5 w-2.5" /> {localize(lang, "Завершен", "Completed")}
      </span>
    );
  }
  if (normalized === "failed") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-red-500/20 bg-red-500/10 px-1.5 py-0.5 text-xs font-semibold text-red-400">
        <XCircle className="h-2.5 w-2.5" /> {localize(lang, "Ошибка", "Failed")}
      </span>
    );
  }
  if (normalized === "running") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-primary/20 bg-primary/10 px-1.5 py-0.5 text-xs font-semibold text-primary">
        <Loader2 className="h-2.5 w-2.5 animate-spin" /> {localize(lang, "Выполняется", "Running")}
      </span>
    );
  }
  return (
    <span className="rounded-md border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
      {status}
    </span>
  );
}

type PipelineCardProps = {
  pipeline: PipelineListItem;
  onOpen: () => void;
  onRun: () => void;
  onClone: () => void;
  onDelete: () => void;
  running: boolean;
  cloning: boolean;
  lang: string;
};

export function PipelineCard({
  pipeline,
  onOpen,
  onRun,
  onClone,
  onDelete,
  running,
  cloning,
  lang,
}: PipelineCardProps) {
  const tags = Array.isArray(pipeline.tags) ? pipeline.tags.slice(0, 2) : [];
  const activityState = getPipelineActivityState({
    lastRun: pipeline.last_run,
    triggerSummary: pipeline.trigger_summary,
    graphVersion: pipeline.graph_version,
  });
  const activityToneClass =
    activityState.icon === "running"
      ? "border-primary/30 bg-primary/10 text-primary"
      : activityState.icon === "warning"
        ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
        : "border-border bg-secondary/30 text-muted-foreground";
  const ActivityIcon =
    activityState.icon === "running"
      ? Loader2
      : activityState.icon === "pending"
        ? Clock
        : activityState.icon === "manual"
          ? Play
          : activityState.icon === "schedule"
            ? Clock
            : activityState.icon === "warning"
              ? XCircle
              : Zap;

  const isRunning = pipeline.last_run?.status === "running" || running;

  return (
    <article
      className={cn(
        "group cursor-pointer overflow-hidden rounded-xl border bg-card p-4 shadow-sm transition-all duration-150 hover:shadow-md",
        isRunning
          ? "border-primary/30 hover:border-primary/50 bg-primary/3"
          : "border-border hover:border-primary/25 hover:bg-secondary/15",
      )}
      onClick={onOpen}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-sm font-semibold text-primary">
          {pipeline.icon || "W"}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between">
            <div className="min-w-0 flex-1 pr-2">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-foreground">{pipeline.name}</h3>
                {pipeline.last_run && <RunStatusBadge status={pipeline.last_run.status} lang={lang} />}
              </div>
              <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
                {pipeline.description || localize(lang, "Описание не задано", "No description")}
              </p>
            </div>

            <div onClick={(event) => event.stopPropagation()}>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-9 w-9 text-muted-foreground"
                    aria-label={localize(lang, `Действия для ${pipeline.name}`, `Actions for ${pipeline.name}`)}
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={onOpen}>{localize(lang, "Открыть редактор", "Open editor")}</DropdownMenuItem>
                  <DropdownMenuItem onClick={onClone}>
                    <Copy className="mr-1.5 h-3.5 w-3.5" /> {localize(lang, "Клонировать", "Clone")}
                  </DropdownMenuItem>
                  <DropdownMenuItem className="text-destructive" onClick={onDelete}>
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" /> {localize(lang, "Удалить", "Delete")}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          {tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {tags.map((tag) => (
                <span key={tag} className="inline-flex items-center rounded border border-border px-1.5 py-0 text-xs text-muted-foreground">
                  {tag}
                </span>
              ))}
            </div>
          )}

          <div className="mt-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">
                {formatRelativeTime(pipeline.updated_at, lang)}
              </span>
              {activityState.label && (
                <span className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-medium", activityToneClass)}>
                  <ActivityIcon className={cn("h-2.5 w-2.5", activityState.icon === "running" && "animate-spin")} />
                  {formatActivityLabel(activityState.label, lang)}
                </span>
              )}
            </div>

            <div className="flex items-center gap-2" onClick={(event) => event.stopPropagation()}>
              <Button size="sm" className="h-9 gap-1.5 px-3 text-xs" onClick={onRun} disabled={running}>
                {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                {localize(lang, "Запуск", "Run")}
              </Button>
            </div>
          </div>
          <p className="mt-2 line-clamp-2 text-xs leading-4 text-muted-foreground">
            {formatActivityDetail(activityState.detail, lang)}
          </p>

          {cloning && <p className="mt-2 text-xs text-primary">{localize(lang, "Создаю копию...", "Creating a copy...")}</p>}
        </div>
      </div>
    </article>
  );
}
