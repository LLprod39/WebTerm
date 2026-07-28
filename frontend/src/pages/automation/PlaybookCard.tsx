import {
  ArrowUpRight,
  Copy,
  Eye,
  FileCode2,
  GitBranch,
  ListChecks,
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

function tasksLabel(count: number, ru: boolean) {
  if (!ru) return `${count} ${count === 1 ? "task" : "tasks"}`;
  const mod100 = count % 100;
  const mod10 = count % 10;
  const word = mod100 >= 11 && mod100 <= 14 ? "задач" : mod10 === 1 ? "задача" : mod10 >= 2 && mod10 <= 4 ? "задачи" : "задач";
  return `${count} ${word}`;
}

export function PlaybookCard({ playbook, lang, executionReady = true, onOpen, onRun, onDuplicate, onDelete }: PlaybookCardProps) {
  const ru = lang === "ru";
  const canEdit = playbook.capabilities?.can_edit ?? true;
  const canRun = playbook.capabilities?.can_run ?? true;
  const canDuplicate = playbook.capabilities?.can_export ?? true;
  const canDelete = playbook.capabilities?.can_delete ?? true;
  const ready = Boolean(playbook.active_compatibility_revision?.status === "validated" || playbook.compatibility?.ready);
  const runStatus = playbook.last_run_status ? RUN_STATUS_META[playbook.last_run_status as PlaybookRunStatus] : null;
  const category = CATEGORY_META[playbook.category];
  const isGitLab = playbook.source?.type === "gitlab";
  const sourceLabel = isGitLab
    ? `GitLab · ${playbook.source?.project || (ru ? "проект" : "project")}`
    : playbook.kind === "ansible" ? "Ansible YAML" : "Runbook";
  const sourceContext = isGitLab
    ? [playbook.source?.ref, playbook.source?.path].filter(Boolean).join(" · ")
    : playbook.published_revision_number
      ? `${ru ? "Версия" : "Version"} #${playbook.published_revision_number}`
      : "";

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
                <Button size="icon" variant="ghost" className="h-7 w-7" aria-label={ru ? "Действия с playbook" : "Playbook actions"}>
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
              {playbook.description || (ru ? "Описание проекта пока не добавлено." : "No project description yet.")}
            </span>
          </span>
          <ArrowUpRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground/50 transition-[color,transform] group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-foreground motion-reduce:transform-none" />
        </span>
      </button>

      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border/60 pt-3.5 text-xs text-muted-foreground">
        <StatusBadge
          label={ready ? (ru ? "Готов" : "Ready") : ru ? "Нужна проверка" : "Needs check"}
          tone={ready ? "success" : "warning"}
          className="normal-case tracking-normal"
        />
        <span className="inline-flex items-center gap-1.5">
          <ListChecks className="h-3.5 w-3.5" />
          {tasksLabel(playbook.task_count, ru)}
        </span>
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
            {executionReady ? <Play className="h-3.5 w-3.5" /> : <Settings2 className="h-3.5 w-3.5" />}
            {executionReady ? (ru ? "Запустить" : "Run") : ru ? "Настроить" : "Configure"}
          </Button>
        ) : null}
      </div>
    </article>
  );
}
