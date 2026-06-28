import { Link } from "react-router-dom";
import { Activity, Bot, Clock, Eye, FileText, MessageSquare, Play, Plus, RefreshCw, Server, Settings2, Square, Trash2 } from "lucide-react";

import type { AgentItem, AgentRuntimeRunItem } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { EmptyState, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import {
  AGENT_ICONS,
  agentModeLabel,
  formatScheduleConfigLabel,
  isAgentScheduled,
  relativeTime,
  sudoAgentOption,
} from "./agentPageUtils";
import { activeRunStatus, formatRuntimeAge, readinessTone, runBlockedReason } from "./agentRuntimeShared";

type AgentListSectionProps = {
  agents: AgentItem[];
  modeFilter: "all" | "mini" | "full" | "multi";
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
};

export function AgentListSection({
  agents,
  modeFilter,
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
}: AgentListSectionProps) {
  return (
    <>
      {agents.length === 0 ? (
        <EmptyState
          icon={<Bot className="h-5 w-5" />}
          title={t("agent.empty")}
          description={modeFilter !== "all" ? t("agent.no_recent") : t("agent.custom_desc")}
          actions={
            <Button size="sm" onClick={() => onCreate()} className="gap-1">
              <Plus className="h-3 w-3" /> {t("agent.create_first")}
            </Button>
          }
        />
      ) : (
        <SectionCard title={t("agent.title")} description={localize(lang, `Показано: ${agents.length}`, `${agents.length} visible`)} icon={<Bot className="h-4 w-4" />} bodyClassName="p-0">
          <div className="divide-y divide-border/40">
            {agents.map((ag) => {
              const AgentIcon = AGENT_ICONS[ag.agent_type] || Settings2;
              const isStarting = runningId === ag.id;
              const isStopping = stoppingId === ag.id;
              const isRunning = isStarting || !!ag.active_run_id;
              const blockedReason = runBlockedReason(ag, lang);
              const activeRun = activeRunByAgentId.get(ag.id);
              const activeRunMeta = activeRunStatus(activeRun, ag.active_run_id, lang);
              const activeRunQuestion = String(activeRun?.pending_question || "").trim();
              const activeRunAge = formatRuntimeAge(activeRun?.age_seconds);
              const activeRunCta = activeRunMeta.status === "waiting"
                ? localize(lang, "Ответить", "Answer")
                : activeRunMeta.status === "plan_review"
                  ? localize(lang, "План", "Plan")
                  : localize(lang, "Следить", "Watch");
              return (
                <div
                  key={ag.id}
                  className={`flex flex-col gap-3 px-4 py-3 transition-colors sm:flex-row sm:items-center ${
                    createdAgentId === ag.id
                      ? "bg-primary/8 ring-1 ring-inset ring-primary/25"
                      : "hover:bg-secondary/20"
                  }`}
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border/60 bg-secondary/30 transition-colors group-hover:bg-secondary/60">
                    <AgentIcon className="h-4 w-4 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-sm font-medium text-foreground">{ag.name}</span>
                      <span className="rounded-md border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-xs font-semibold text-muted-foreground">
                        {agentModeLabel(ag.mode, lang)}
                      </span>
                      {ag.active_run_id && (
                        <StatusBadge label={activeRunMeta.label} tone={activeRunMeta.tone} />
                      )}
                      {ag.execution_readiness?.required ? (
                        <StatusBadge
                          label={ag.execution_readiness.ready ? "worker ok" : "worker wait"}
                          tone={readinessTone(ag.execution_readiness)}
                        />
                      ) : null}
                      <span className="rounded-md border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-xs font-semibold text-muted-foreground">
                        sudo: {localize(lang, sudoAgentOption(ag.sudo_policy).labelRu, sudoAgentOption(ag.sudo_policy).labelEn)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                      <span className="flex items-center gap-0.5"><Server className="h-2.5 w-2.5" /> {ag.server_count}</span>
                      {ag.last_run_at && <span className="flex items-center gap-0.5"><Clock className="h-2.5 w-2.5" /> {relativeTime(ag.last_run_at)}</span>}
                      {activeRun ? (
                        <span className="flex items-center gap-0.5">
                          <Activity className="h-2.5 w-2.5" />
                          run #{activeRun.run_id} · {activeRunAge}
                        </span>
                      ) : null}
                      {isAgentScheduled(ag) && <span className="flex items-center gap-0.5"><RefreshCw className="h-2.5 w-2.5" /> {formatScheduleConfigLabel(ag.schedule_config, ag.schedule_minutes, lang)}</span>}
                    </div>
                    {ag.goal && <p className="text-xs text-muted-foreground mt-0.5 truncate max-w-md">{ag.goal}</p>}
                    {activeRunQuestion ? (
                      <p className="mt-1 flex max-w-2xl items-start gap-1.5 rounded-md border border-amber-500/20 bg-amber-500/8 px-2 py-1.5 text-xs leading-5 text-amber-100">
                        <MessageSquare className="mt-0.5 h-3 w-3 shrink-0 text-amber-300" />
                        <span className="min-w-0 break-words">
                          {localize(lang, "Вопрос агента:", "Agent question:")} {activeRunQuestion}
                        </span>
                      </p>
                    ) : null}
                    {!ag.active_run_id && blockedReason ? (
                      <p className="mt-1 max-w-2xl break-words font-mono text-xs leading-5 text-amber-300">{blockedReason}</p>
                    ) : null}
                  </div>
                  <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto sm:shrink-0">
                    {ag.active_run_id ? (
                      <>
                        <Button asChild size="xs" variant="outline" className="gap-1">
                          <Link to={`/agents/run/${ag.active_run_id}`}>
                            {activeRunMeta.status === "waiting" ? <MessageSquare className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                            {activeRunCta}
                          </Link>
                        </Button>
                        <Button size="xs" variant="outline" className="gap-1 text-red-400" disabled={isStopping} onClick={() => onStop(ag)}>
                          {isStopping ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Square className="h-3 w-3" />} {t("agent.stop")}
                        </Button>
                      </>
                    ) : (
                      <>
                        {ag.last_run_id && (
                          <Button asChild size="xs" variant="ghost" className="gap-1 text-muted-foreground hover:text-foreground">
                            <Link to={`/agents/run/${ag.last_run_id}`}>
                              <FileText className="h-3 w-3" /> {t("agent.report")}
                            </Link>
                          </Button>
                        )}
                        <Button size="xs" variant="ghost" className="gap-1 text-muted-foreground hover:text-foreground" onClick={() => onEdit(ag)}>
                          <Settings2 className="h-3 w-3" /> {localize(lang, "Править", "Edit")}
                        </Button>
                        <Button
                          size="xs"
                          variant="outline"
                          className="gap-1"
                          disabled={isRunning || Boolean(blockedReason)}
                          title={blockedReason || undefined}
                          onClick={() => onRun(ag)}
                        >
                          {isStarting ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} {t("agent.run")}
                        </Button>
                      </>
                    )}
                    {ag.active_run_id && (
                      <Button size="xs" variant="ghost" className="gap-1 text-muted-foreground hover:text-foreground" onClick={() => onEdit(ag)}>
                        <Settings2 className="h-3 w-3" /> {localize(lang, "Править", "Edit")}
                      </Button>
                    )}
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 text-muted-foreground hover:text-red-400"
                      onClick={() => onDelete(ag)}
                      aria-label={localize(lang, `Удалить ${ag.name}`, `Delete ${ag.name}`)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>
      )}
    </>
  );
}
