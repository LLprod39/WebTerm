import { Copy, Pencil, Play, Trash2 } from "lucide-react";
import type { PlaybookSummary } from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import { cn, relativeTime } from "@/lib/utils";
import { CATEGORY_META, RUN_STATUS_META } from "./constants";
import type { PlaybookRunStatus } from "@/api/playbooks";

interface PlaybookCardProps {
  playbook: PlaybookSummary;
  lang: string;
  onOpen: () => void;
  onRun: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}

export function PlaybookCard({ playbook, lang, onOpen, onRun, onDuplicate, onDelete }: PlaybookCardProps) {
  const cat = CATEGORY_META[playbook.category] || CATEGORY_META.custom;
  const lastStatus = (playbook.last_run_status || "") as PlaybookRunStatus;
  const statusMeta = lastStatus ? RUN_STATUS_META[lastStatus] : null;
  const ru = lang === "ru";

  return (
    <article
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-md border border-border bg-card",
        "transition-[border-color,box-shadow] duration-150 hover:border-primary/35 hover:shadow-elev-2",
      )}
    >
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-[3px]", cat.bar)} />

      <div className="flex flex-1 flex-col gap-2.5 p-4 pl-5">
        <div className="flex items-start justify-between gap-2">
          <button
            type="button"
            onClick={onOpen}
            className="min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
            title={ru ? "Открыть playbook" : "Open playbook"}
          >
            <h3 className="truncate font-display text-[0.9375rem] font-semibold tracking-tight text-foreground transition-colors group-hover:text-primary">
              {playbook.name}
            </h3>
            <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
              {playbook.description || (ru ? "Без описания" : "No description")}
            </p>
          </button>
          <span
            className={cn(
              "shrink-0 rounded-full border px-2 py-0.5 text-2xs font-medium",
              cat.kicker,
            )}
          >
            {ru ? cat.labelRu : cat.labelEn}
          </span>
        </div>

        <div className="flex items-center gap-2 text-2xs text-muted-foreground">
          <span className="font-mono">
            {playbook.task_count} {ru ? "задач" : "tasks"}
          </span>
          <span aria-hidden className="text-border">·</span>
          {playbook.last_run_at && statusMeta ? (
            <span className="inline-flex min-w-0 items-center gap-1.5">
              <span aria-hidden className={cn("h-1.5 w-1.5 shrink-0 rounded-full", statusMeta.dot)} />
              <span className={statusMeta.className}>{ru ? statusMeta.labelRu : statusMeta.labelEn}</span>
              <span className="truncate opacity-70">{relativeTime(playbook.last_run_at)}</span>
            </span>
          ) : (
            <span className="opacity-70">{ru ? "Ещё не запускался" : "Never run"}</span>
          )}
        </div>

        <div className="mt-auto flex items-center justify-between gap-2 border-t border-border/70 pt-2.5">
          <div className="flex items-center gap-0.5">
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
              onClick={onOpen}
              aria-label={ru ? "Редактировать" : "Edit"}
              title={ru ? "Редактировать" : "Edit"}
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
              onClick={onDuplicate}
              aria-label={ru ? "Дублировать" : "Duplicate"}
              title={ru ? "Дублировать" : "Duplicate"}
            >
              <Copy className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
              onClick={onDelete}
              aria-label={ru ? "Удалить" : "Delete"}
              title={ru ? "Удалить" : "Delete"}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
          <Button size="sm" className="h-8 gap-1.5 px-3 shadow-elev-1" onClick={onRun}>
            <Play className="h-3.5 w-3.5" />
            {ru ? "Запустить" : "Run"}
          </Button>
        </div>
      </div>
    </article>
  );
}
