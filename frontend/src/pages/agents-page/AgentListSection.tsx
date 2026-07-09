import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bot,
  FileText,
  MessageSquare,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  Search,
  Settings2,
  Square,
  Trash2,
} from "lucide-react";

import type { AgentItem, AgentRuntimeRunItem } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/page-shell";
import { cn } from "@/lib/utils";
import {
  agentModeLabel,
  formatScheduleConfigLabel,
  isAgentScheduled,
  relativeTime,
} from "./agentPageUtils";
import { activeRunStatus, formatRuntimeAge, runBlockedReason } from "./agentRuntimeShared";

type AgentMode = "all" | "mini" | "full" | "multi";

type AgentListSectionProps = {
  agents: AgentItem[];
  totalCount: number;
  modeFilter: AgentMode;
  onModeFilterChange: (mode: AgentMode) => void;
  lang: "ru" | "en";
  t: (key: string) => string;
  createdAgentId: number | null;
  runningId: number | null;
  stoppingId: number | null;
  activeRunByAgentId: Map<number, AgentRuntimeRunItem>;
  onCreate: () => void;
  onEdit: (agent: AgentItem) => void;
  onRun: (agent: AgentItem) => void;
  onStop: (agent: AgentItem) => void;
  onDelete: (agent: AgentItem) => void;
  onTogglePause?: (agent: AgentItem) => void;
};

/** Quiet per-mode text colour: mini = teal, full = violet, multi = blue. */
const MODE_TEXT: Record<Exclude<AgentMode, "all">, string> = {
  mini: "text-primary",
  full: "text-ai",
  multi: "text-info",
};

/** Status dot for the last/current run — the single most useful signal per row. */
function runDot(ag: AgentItem): { className: string; pulse: boolean } {
  if (ag.active_run_id) return { className: "bg-info", pulse: true };
  if (!ag.last_run_at) return { className: "bg-muted-foreground/40", pulse: false };
  const status = String(ag.last_run_status || "").toLowerCase();
  if (["completed", "succeeded", "success"].includes(status)) return { className: "bg-success", pulse: false };
  if (["failed", "error", "stopped"].includes(status)) return { className: "bg-destructive", pulse: false };
  return { className: "bg-muted-foreground/40", pulse: false };
}

function lastRunLabel(ag: AgentItem, lang: "ru" | "en"): string {
  if (!ag.last_run_at) return localize(lang, "ещё не запускался", "never ran");
  const status = String(ag.last_run_status || "").toLowerCase();
  const when = relativeTime(ag.last_run_at);
  if (["completed", "succeeded", "success"].includes(status)) return localize(lang, `успешно · ${when}`, `succeeded · ${when}`);
  if (["failed", "error"].includes(status)) return localize(lang, `ошибка · ${when}`, `failed · ${when}`);
  if (status === "stopped") return localize(lang, `остановлен · ${when}`, `stopped · ${when}`);
  return when;
}

function nextDueLabel(ag: AgentItem, lang: "ru" | "en"): string | null {
  if (!isAgentScheduled(ag) || ag.schedule_state === "paused") return null;
  if (ag.due_now) return localize(lang, "запуск сейчас", "due now");
  const seconds = ag.next_due_in_seconds;
  if (seconds === null || seconds === undefined || seconds <= 0) return null;
  return localize(lang, `след. через ${formatRuntimeAge(seconds)}`, `next in ${formatRuntimeAge(seconds)}`);
}

function serverLabel(ag: AgentItem): string {
  if (!ag.server_names.length) return "—";
  if (ag.server_names.length > 1) return `${ag.server_names[0]} +${ag.server_names.length - 1}`;
  return ag.server_names[0];
}

export function AgentListSection({
  agents,
  totalCount,
  modeFilter,
  onModeFilterChange,
  lang,
  t,
  createdAgentId,
  runningId,
  stoppingId,
  activeRunByAgentId,
  onCreate,
  onEdit,
  onRun,
  onStop,
  onDelete,
  onTogglePause,
}: AgentListSectionProps) {
  const [search, setSearch] = useState("");
  const showFilters = totalCount >= 4;
  const showSearch = totalCount >= 6;

  const visibleAgents = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return agents;
    return agents.filter(
      (ag) =>
        ag.name.toLowerCase().includes(query) ||
        (ag.goal || "").toLowerCase().includes(query) ||
        ag.server_names.some((name) => name.toLowerCase().includes(query)),
    );
  }, [agents, search]);

  if (totalCount === 0) {
    return (
      <EmptyState
        icon={<Bot className="h-5 w-5" />}
        title={t("agent.empty")}
        description={localize(
          lang,
          "Создайте первого агента — он выполнит команды или задачу на выбранных серверах.",
          "Create your first agent — it will run commands or a task on the selected servers.",
        )}
        actions={
          <Button size="sm" onClick={() => onCreate()} className="gap-1.5">
            <Plus className="h-4 w-4" /> {t("agent.create_first")}
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-2.5">
      {(showFilters || showSearch) && (
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          {showFilters ? (
            <div className="flex items-center gap-0.5 text-sm">
              {(["all", "mini", "full", "multi"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  aria-pressed={modeFilter === m}
                  onClick={() => onModeFilterChange(m)}
                  className={cn(
                    "rounded-md px-2.5 py-1 transition-colors",
                    modeFilter === m
                      ? "bg-surface-2 font-medium text-foreground shadow-elev-1"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {agentModeLabel(m, lang)}
                </button>
              ))}
            </div>
          ) : (
            <span />
          )}
          {showSearch ? (
            <div className="relative w-full max-w-64 sm:w-64">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={localize(lang, "Поиск…", "Search…")}
                className="h-8 pl-8 text-sm"
              />
            </div>
          ) : null}
        </div>
      )}

      {visibleAgents.length === 0 ? (
        <EmptyState
          icon={<Bot className="h-5 w-5" />}
          title={localize(lang, "Ничего не найдено", "Nothing found")}
          description={localize(lang, "Измените поиск или фильтр.", "Change the search or filter.")}
          actions={
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setSearch("");
                onModeFilterChange("all");
              }}
            >
              {localize(lang, "Сбросить", "Reset")}
            </Button>
          }
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-border/50 bg-surface-1/60 shadow-elev-1">
          {/* Column headers — wide screens only */}
          <div className="hidden border-b border-border/40 bg-surface-2/30 px-4 py-2 text-2xs font-semibold uppercase tracking-wide text-muted-foreground/70 lg:grid lg:grid-cols-[minmax(0,1.6fr)_minmax(7rem,0.7fr)_minmax(9rem,0.9fr)_minmax(8rem,0.8fr)_auto] lg:gap-3 lg:items-center">
            <span>{localize(lang, "Агент", "Agent")}</span>
            <span>{localize(lang, "Серверы", "Servers")}</span>
            <span>{localize(lang, "Последний запуск", "Last run")}</span>
            <span>{localize(lang, "Расписание", "Schedule")}</span>
            <span className="sr-only">{localize(lang, "Действия", "Actions")}</span>
          </div>

          <div className="divide-y divide-border/40">
            {visibleAgents.map((ag) => {
              const isStarting = runningId === ag.id;
              const isStopping = stoppingId === ag.id;
              const isRunning = isStarting || !!ag.active_run_id;
              const isPaused = ag.schedule_state === "paused";
              const blockedReason = runBlockedReason(ag, lang);
              const activeRun = activeRunByAgentId.get(ag.id);
              const activeRunMeta = activeRunStatus(activeRun, ag.active_run_id, lang);
              const activeRunQuestion = String(activeRun?.pending_question || "").trim();
              const activeRunCta = activeRunMeta.status === "waiting"
                ? localize(lang, "Ответить", "Answer")
                : activeRunMeta.status === "plan_review"
                  ? localize(lang, "Открыть план", "Open plan")
                  : localize(lang, "Следить", "Watch");
              const dot = runDot(ag);
              const dueLabel = nextDueLabel(ag, lang);
              const summary = ag.goal
                || (ag.commands.length
                  ? localize(lang, `${ag.commands.length} команд(ы)`, `${ag.commands.length} command(s)`)
                  : "");
              const scheduled = isAgentScheduled(ag);
              const runMeta = ag.active_run_id
                ? localize(lang, `выполняется · ${formatRuntimeAge(activeRun?.age_seconds)}`, `running · ${formatRuntimeAge(activeRun?.age_seconds)}`)
                : lastRunLabel(ag, lang);
              const scheduleMeta = isPaused
                ? localize(lang, "на паузе", "paused")
                : scheduled
                  ? [formatScheduleConfigLabel(ag.schedule_config, ag.schedule_minutes, lang), dueLabel].filter(Boolean).join(" · ")
                  : localize(lang, "вручную", "manual");

              return (
                <div
                  key={ag.id}
                  className={cn(
                    "group px-3 py-2.5 transition-colors sm:px-4",
                    createdAgentId === ag.id ? "bg-primary/5" : "hover:bg-surface-2/40",
                    isPaused && "opacity-70",
                  )}
                >
                  <div className="flex items-start gap-2.5 sm:items-center lg:grid lg:grid-cols-[minmax(0,1.6fr)_minmax(7rem,0.7fr)_minmax(9rem,0.9fr)_minmax(8rem,0.8fr)_auto] lg:gap-3 lg:items-center">
                    <div className="flex min-w-0 flex-1 items-start gap-2.5 sm:items-center">
                      <span className="relative mt-1.5 flex h-2 w-2 shrink-0 sm:mt-0" aria-hidden>
                        {dot.pulse ? (
                          <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", dot.className)} />
                        ) : null}
                        <span className={cn("relative inline-flex h-2 w-2 rounded-full", dot.className)} />
                      </span>

                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                          <span className="text-sm font-semibold leading-5 text-foreground">{ag.name}</span>
                          <span className={cn("text-2xs font-semibold uppercase tracking-wide", MODE_TEXT[ag.mode] || MODE_TEXT.mini)}>
                            {agentModeLabel(ag.mode, lang)}
                          </span>
                        </div>
                        {summary ? (
                          <p className="mt-0.5 truncate text-[13px] leading-4 text-muted-foreground">{summary}</p>
                        ) : null}
                        {/* Compact meta under name on small screens */}
                        <p className="mt-0.5 truncate text-xs text-muted-foreground/70 lg:hidden">
                          {[runMeta, serverLabel(ag), scheduleMeta].filter(Boolean).join(" · ")}
                        </p>
                        {activeRunQuestion ? (
                          <p className="mt-1.5 flex max-w-2xl items-start gap-1.5 rounded-md bg-warning/10 px-2 py-1 text-xs leading-4 text-foreground">
                            <MessageSquare className="mt-0.5 h-3 w-3 shrink-0 text-warning" aria-hidden />
                            <span className="min-w-0 break-words">{activeRunQuestion}</span>
                          </p>
                        ) : null}
                        {!ag.active_run_id && blockedReason ? (
                          <p className="mt-1 max-w-2xl break-words text-xs leading-4 text-warning/90">{blockedReason}</p>
                        ) : null}
                      </div>
                    </div>

                    <div className="hidden min-w-0 truncate text-[13px] leading-4 text-muted-foreground lg:block" title={ag.server_names.join(", ")}>
                      {serverLabel(ag)}
                    </div>
                    <div className="hidden min-w-0 truncate text-[13px] leading-4 text-muted-foreground lg:block">
                      {runMeta}
                    </div>
                    <div className="hidden min-w-0 truncate text-[13px] leading-4 text-muted-foreground lg:block">
                      {scheduleMeta}
                    </div>

                    <div className="flex shrink-0 items-center gap-0.5 self-center">
                      {ag.active_run_id ? (
                        <Button asChild size="sm" className="h-8 gap-1.5">
                          <Link to={`/agents/run/${ag.active_run_id}`}>
                            {activeRunMeta.status === "waiting" ? <MessageSquare className="h-3.5 w-3.5" /> : null}
                            {activeRunCta}
                          </Link>
                        </Button>
                      ) : (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8 text-muted-foreground hover:text-primary"
                          disabled={isRunning || Boolean(blockedReason)}
                          onClick={() => onRun(ag)}
                          aria-label={localize(lang, `Запустить ${ag.name}`, `Run ${ag.name}`)}
                          title={blockedReason || t("agent.run")}
                        >
                          <Play className={cn("h-4 w-4", isStarting && "animate-pulse")} />
                        </Button>
                      )}

                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8 text-muted-foreground hover:text-foreground"
                            aria-label={localize(lang, `Действия для ${ag.name}`, `Actions for ${ag.name}`)}
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-52">
                          {ag.last_run_id ? (
                            <DropdownMenuItem asChild>
                              <Link to={`/agents/run/${ag.last_run_id}`} className="flex items-center gap-2">
                                <FileText className="h-3.5 w-3.5" /> {t("agent.report")}
                              </Link>
                            </DropdownMenuItem>
                          ) : null}
                          <DropdownMenuItem onClick={() => onEdit(ag)} className="gap-2">
                            <Settings2 className="h-3.5 w-3.5" /> {localize(lang, "Настроить", "Configure")}
                          </DropdownMenuItem>
                          {scheduled && onTogglePause ? (
                            <DropdownMenuItem onClick={() => onTogglePause(ag)} className="gap-2">
                              {isPaused ? (
                                <>
                                  <Play className="h-3.5 w-3.5" /> {localize(lang, "Возобновить расписание", "Resume schedule")}
                                </>
                              ) : (
                                <>
                                  <Pause className="h-3.5 w-3.5" /> {localize(lang, "Поставить на паузу", "Pause schedule")}
                                </>
                              )}
                            </DropdownMenuItem>
                          ) : null}
                          {ag.active_run_id ? (
                            <DropdownMenuItem onClick={() => onStop(ag)} disabled={isStopping} className="gap-2">
                              <Square className="h-3.5 w-3.5" /> {t("agent.stop")}
                            </DropdownMenuItem>
                          ) : null}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={() => onDelete(ag)}
                            className="gap-2 text-destructive focus:text-destructive"
                          >
                            <Trash2 className="h-3.5 w-3.5" /> {localize(lang, "Удалить", "Delete")}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
