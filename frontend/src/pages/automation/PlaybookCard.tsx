import {
  ArrowUpRight,
  Copy,
  Eye,
  FileCode2,
  GitBranch,
  MoreHorizontal,
  Pencil,
  Play,
  Settings2,
  Trash2,
} from "lucide-react";

import type { PlaybookRunStatus, PlaybookSummary } from "@/api/playbooks";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn, relativeTime } from "@/lib/utils";
import { CATEGORY_META, RUN_STATUS_META } from "./constants";

interface PlaybookCardProps {
  playbook: PlaybookSummary;
  lang: string;
  executionReady?: boolean;
  onOpen: () => void;
  onRun: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}

export function PlaybookCard({ playbook, lang, executionReady = true, onOpen, onRun, onDuplicate, onDelete }: PlaybookCardProps) {
  const ru = lang === "ru";
  const canEdit = playbook.capabilities?.can_edit ?? true;
  const canRun = playbook.capabilities?.can_run ?? true;
  const canDuplicate = playbook.capabilities?.can_export ?? true;
  const canDelete = playbook.capabilities?.can_delete ?? true;
  const ready = Boolean(playbook.active_compatibility_revision?.status === "validated" || playbook.compatibility?.ready);
  const runReady = Boolean(ready && executionReady && playbook.published_revision_id);
  const runStatus = playbook.last_run_status ? RUN_STATUS_META[playbook.last_run_status as PlaybookRunStatus] : null;
  const category = CATEGORY_META[playbook.category];
  const isGitLab = playbook.source?.type === "gitlab";
  const sourceLabel = isGitLab
    ? `GitLab · ${playbook.source?.project || (ru ? "проект" : "project")}`
    : playbook.kind === "ansible" ? "Ansible YAML" : "Runbook";
  const sourceContext = isGitLab ? [playbook.source?.ref, playbook.source?.path].filter(Boolean).join(" · ") : "";

  return (
    <article
      role="listitem"
      className="group relative flex min-h-56 flex-col overflow-hidden rounded-xl border border-border/75 bg-card/45 p-5 transition-[border-color,background-color,transform] duration-200 hover:-translate-y-0.5 hover:border-border hover:bg-card/80 motion-reduce:transform-none"
    >
      <span className={cn("absolute inset-y-0 left-0 w-0.5 opacity-70 transition-opacity group-hover:opacity-100", category.bar)} />

      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary/75 text-muted-foreground transition-colors group-hover:text-foreground">
            {isGitLab ? <GitBranch className="h-4 w-4" /> : <FileCode2 className="h-4 w-4" />}
          </span>
          <div className="min-w-0">
            <p className="truncate text-xs font-medium text-muted-foreground" title={sourceLabel}>{sourceLabel}</p>
            {sourceContext ? <p className="mt-0.5 truncate text-2xs text-muted-foreground/70" title={sourceContext}>{sourceContext}</p> : null}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <span className={cn("rounded-full border px-2 py-0.5 text-2xs font-medium", category.kicker)}>
            {ru ? category.labelRu : category.labelEn}
          </span>
          {canDuplicate || canDelete ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="icon" variant="ghost" className="h-7 w-7" aria-label={ru ? "Действия с проектом" : "Project actions"}>
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                {canDuplicate ? <DropdownMenuItem onSelect={onDuplicate}><Copy className="h-4 w-4" />{ru ? "Создать копию" : "Duplicate"}</DropdownMenuItem> : null}
                {canDuplicate && canDelete ? <DropdownMenuSeparator /> : null}
                {canDelete ? <DropdownMenuItem onSelect={onDelete} className="text-destructive focus:text-destructive"><Trash2 className="h-4 w-4" />{ru ? "Удалить" : "Delete"}</DropdownMenuItem> : null}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>

      <button
        type="button"
        onClick={onOpen}
        className="mt-5 min-h-20 flex-1 text-left focus-visible:rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="flex items-start gap-2">
          <span className="min-w-0 flex-1">
            <span className="block text-base font-semibold leading-6 text-foreground">{playbook.name}</span>
            <span className="mt-1.5 line-clamp-2 block max-w-xl text-sm leading-5 text-muted-foreground">
              {playbook.description || (ru ? "Без описания" : "No description")}
            </span>
          </span>
          <ArrowUpRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground/50 transition-[color,transform] group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-foreground motion-reduce:transform-none" />
        </span>
      </button>

      <div className="mt-5 grid grid-cols-2 gap-2 border-t border-border/60 pt-3.5 text-xs">
        <div className="rounded-sm bg-surface-0/55 px-2.5 py-2">
          <span className="block text-2xs uppercase tracking-wider text-muted-foreground">{ru ? "Опубликовано" : "Published"}</span>
          <span className="mt-0.5 block font-medium text-foreground">
            {playbook.published_revision_number ? `#${playbook.published_revision_number}` : ru ? "Нет версии" : "No revision"}
          </span>
        </div>
        <div className="rounded-sm bg-surface-0/55 px-2.5 py-2">
          <span className="block text-2xs uppercase tracking-wider text-muted-foreground">{ru ? "Черновик" : "Draft"}</span>
          <span className="mt-0.5 block font-medium text-foreground">
            {playbook.draft_version != null
              ? `v${playbook.draft_version}${playbook.has_unpublished_draft ? ` · ${ru ? "изменён" : "changed"}` : ""}`
              : ru ? "Нет" : "None"}
          </span>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
        <StatusBadge
          label={runReady ? (ru ? "Готов к запуску" : "Ready to run") : ready ? (ru ? "Ожидает публикации" : "Publish required") : ru ? "Нужна проверка" : "Needs check"}
          tone={runReady ? "success" : "warning"}
          className="normal-case tracking-normal"
        />
        <span className="min-w-0 flex-1 text-right">
          {playbook.last_run_at && runStatus ? (
            <span className={cn("inline-flex items-center gap-1.5", runStatus.className)}>
              <span className={cn("h-1.5 w-1.5 rounded-full", runStatus.dot)} />
              {ru ? runStatus.labelRu : runStatus.labelEn} · {relativeTime(playbook.last_run_at)}
            </span>
          ) : ru ? "Ещё не запускался" : "Never run"}
        </span>
      </div>

      <div className="mt-3 flex items-center justify-end gap-1.5">
        <Button size="sm" variant="ghost" className="h-8 gap-1.5" onClick={onOpen}>
          {canEdit ? <Pencil className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          {canEdit ? (ru ? "Открыть" : "Open") : ru ? "Смотреть" : "View"}
        </Button>
        {canRun ? (
          <Button size="sm" className="h-8 gap-1.5" onClick={onRun}>
            {runReady ? <Play className="h-3.5 w-3.5" /> : <Settings2 className="h-3.5 w-3.5" />}
            {runReady ? (ru ? "Запустить" : "Run") : ru ? "Настроить" : "Configure"}
          </Button>
        ) : null}
      </div>
    </article>
  );
}
