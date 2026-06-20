import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchAgents,
  deleteAgent,
  runAgent,
  stopAgent,
  type AgentItem,
  type AgentRunResult,
} from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import {
  Bot, Plus, Play, Trash2, RefreshCw, Clock, Eye,
  FileText, Server, X, Square,
  Settings2, CheckCircle2,
  AlertTriangle, Activity,
} from "lucide-react";
import { AgentReportModal } from "@/components/studio/AgentReportModal";
import { Button } from "@/components/ui/button";
import { EmptyState, MetricCard, MetricGrid, PageHero, PageShell, QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { CreateAgentDialog } from "./agents-page/CreateAgentDialog";
import {
  AGENT_ICONS,
  agentModeLabel,
  formatDuration,
  formatScheduleConfigLabel,
  isAgentScheduled,
  relativeTime,
  sudoAgentOption,
} from "./agents-page/agentPageUtils";

export default function AgentsPage() {
  const { t, lang } = useI18n();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [modeFilter, setModeFilter] = useState<"all" | "mini" | "full" | "multi">("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentItem | null>(null);
  const [createdAgentId, setCreatedAgentId] = useState<number | null>(null);
  const [runningId, setRunningId] = useState<number | null>(null);
  const [result, setResult] = useState<AgentRunResult | null>(null);
  const [reportModalOpen, setReportModalOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["agents", "list"],
    queryFn: () => fetchAgents(),
    refetchInterval: 10_000,
  });

  const allAgents = data?.agents || [];
  const agents = allAgents.filter(
    (a) => modeFilter === "all" || a.mode === modeFilter,
  );
  const activeAgents = allAgents.filter((agent) => agent.active_run_id).length;
  const scheduledAgents = allAgents.filter(isAgentScheduled).length;
  const serverScopeCount = allAgents.reduce((sum, agent) => sum + agent.server_count, 0);

  const onRun = async (ag: AgentItem) => {
    setRunningId(ag.id);
    setResult(null);
    try {
      const res = await runAgent(ag.id);
      if (res.runs?.length > 0) {
        setResult(res.runs[0]);
        setReportModalOpen(true);
      }
      if ((ag.mode === "full" || ag.mode === "multi") && res.run_id) {
        navigate(`/agents/run/${res.run_id}`);
        return;
      }
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    } catch {
      setResult({
        run_id: 0,
        server_name: localize(lang, "Ошибка запуска", "Run error"),
        status: "failed",
        ai_analysis: localize(lang, "Агент не запустился. Проверьте доступ к серверу и настройки агента.", "The agent did not start. Check server access and agent settings."),
        duration_ms: 0,
        commands_output: [],
      });
    } finally {
      setRunningId(null);
    }
  };

  const onStop = async (ag: AgentItem) => {
    await stopAgent(ag.id);
    await queryClient.invalidateQueries({ queryKey: ["agents"] });
  };

  const onDelete = async (id: number) => {
    if (!confirm(t("agent.delete_confirm"))) return;
    await deleteAgent(id);
    await queryClient.invalidateQueries({ queryKey: ["agents"] });
  };

  if (isLoading) return <QueryStateBlock loading loadingText={t("loading")} className="p-6">{null}</QueryStateBlock>;

  return (
    <PageShell width="6xl">
      <PageHero
        kicker="Automation"
        title={t("agent.title")}
        description={localize(
          lang,
          `${allAgents.length} настроено · ${activeAgents} выполняется · ${scheduledAgents} по расписанию`,
          `${allAgents.length} configured · ${activeAgents} running · ${scheduledAgents} scheduled`,
        )}
        actions={
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center sm:justify-end">
            <div className="inline-flex min-h-10 rounded-lg border border-border bg-secondary/20 p-0.5 text-xs font-semibold">
              {(["all", "mini", "full", "multi"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  aria-pressed={modeFilter === m}
                  onClick={() => setModeFilter(m)}
                  className={`rounded-md px-3 py-1.5 transition-all duration-150 ${modeFilter === m ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                >{agentModeLabel(m, lang)}</button>
              ))}
            </div>
            <Button size="icon" variant="ghost" className="h-10 w-10" onClick={() => queryClient.invalidateQueries({ queryKey: ["agents"] })} aria-label={t("udash.refresh")}>
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Button size="sm" className="h-10 gap-1.5 text-sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" /> {t("agent.new")}
            </Button>
          </div>
        }
      />

      <MetricGrid className="grid-cols-2 xl:grid-cols-4">
        <MetricCard label={t("agent.title")} value={allAgents.length} description={t("agent.view_all")} icon={<Bot className="h-4 w-4" />} />
        <MetricCard label={t("agent.active_runs")} value={activeAgents} description={activeAgents > 0 ? t("agent.working_on") : t("agent.manual")} icon={<Activity className="h-4 w-4" />} tone={activeAgents > 0 ? "info" : "default"} />
        <MetricCard label={t("agent.schedule")} value={scheduledAgents} description={scheduledAgents > 0 ? t("agent.every") : t("agent.manual")} icon={<Clock className="h-4 w-4" />} />
        <MetricCard label={t("nav.servers")} value={serverScopeCount} description={t("agent.servers_lc")} icon={<Server className="h-4 w-4" />} />
      </MetricGrid>

      {result && !reportModalOpen && (
        <div className="bg-card border border-border rounded-lg px-4 py-3 flex items-center gap-3">
          <div className={`h-8 w-8 rounded-lg flex items-center justify-center shrink-0 ${result.status === "completed" ? "bg-primary/20 text-primary" : "bg-destructive/20 text-destructive"}`}>
            {result.status === "completed" ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-foreground">{result.server_name}</div>
            <div className="text-xs text-muted-foreground">{result.status} · {formatDuration(result.duration_ms)}</div>
          </div>
          <Button size="sm" className="h-9 shrink-0 gap-1.5 text-xs" onClick={() => setReportModalOpen(true)}>
            <FileText className="h-3.5 w-3.5" /> {t("agent.report")}
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-9 w-9 shrink-0 text-muted-foreground"
            onClick={() => setResult(null)}
            aria-label={localize(lang, "Скрыть результат запуска", "Dismiss run result")}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}

      {result && (
        <AgentReportModal result={result} open={reportModalOpen} onClose={() => setReportModalOpen(false)} />
      )}
      {agents.length === 0 ? (
        <EmptyState
          icon={<Bot className="h-5 w-5" />}
          title={t("agent.empty")}
          description={modeFilter !== "all" ? t("agent.no_recent") : t("agent.custom_desc")}
          actions={
            <Button size="sm" onClick={() => setCreateOpen(true)} className="gap-1">
              <Plus className="h-3 w-3" /> {t("agent.create_first")}
            </Button>
          }
        />
      ) : (
        <SectionCard title={t("agent.title")} description={localize(lang, `Показано: ${agents.length}`, `${agents.length} visible`)} icon={<Bot className="h-4 w-4" />} bodyClassName="p-0">
          <div className="divide-y divide-border/40">
            {agents.map((ag) => {
              const AgentIcon = AGENT_ICONS[ag.agent_type] || Settings2;
              const isRunning = runningId === ag.id || !!ag.active_run_id;
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
                      <span className="rounded-md border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                        {agentModeLabel(ag.mode, lang)}
                      </span>
                      {ag.active_run_id && (
                        <StatusBadge label="running" tone="info" />
                      )}
                      <span className="rounded-md border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                        sudo: {localize(lang, sudoAgentOption(ag.sudo_policy).labelRu, sudoAgentOption(ag.sudo_policy).labelEn)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-muted-foreground mt-0.5">
                      <span className="flex items-center gap-0.5"><Server className="h-2.5 w-2.5" /> {ag.server_count}</span>
                      {ag.last_run_at && <span className="flex items-center gap-0.5"><Clock className="h-2.5 w-2.5" /> {relativeTime(ag.last_run_at)}</span>}
                      {isAgentScheduled(ag) && <span className="flex items-center gap-0.5"><RefreshCw className="h-2.5 w-2.5" /> {formatScheduleConfigLabel(ag.schedule_config, ag.schedule_minutes, lang)}</span>}
                    </div>
                    {ag.goal && <p className="text-[10px] text-muted-foreground mt-0.5 truncate max-w-md">{ag.goal}</p>}
                  </div>
                  <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto sm:shrink-0">
                    {ag.active_run_id ? (
                      <>
                        <Button asChild size="xs" variant="outline" className="gap-1">
                          <Link to={`/agents/run/${ag.active_run_id}`}>
                            <Eye className="h-3 w-3" /> {localize(lang, "Следить", "Watch")}
                          </Link>
                        </Button>
                        <Button size="xs" variant="outline" className="gap-1 text-red-400" onClick={() => onStop(ag)}>
                          <Square className="h-3 w-3" /> {t("agent.stop")}
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
                        <Button size="xs" variant="ghost" className="gap-1 text-muted-foreground hover:text-foreground" onClick={() => setEditingAgent(ag)}>
                          <Settings2 className="h-3 w-3" /> {localize(lang, "Править", "Edit")}
                        </Button>
                        <Button size="xs" variant="outline" className="gap-1" disabled={isRunning} onClick={() => onRun(ag)}>
                          {isRunning ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} {t("agent.run")}
                        </Button>
                      </>
                    )}
                    {ag.active_run_id && (
                      <Button size="xs" variant="ghost" className="gap-1 text-muted-foreground hover:text-foreground" onClick={() => setEditingAgent(ag)}>
                        <Settings2 className="h-3 w-3" /> {localize(lang, "Править", "Edit")}
                      </Button>
                    )}
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 text-muted-foreground hover:text-red-400"
                      onClick={() => onDelete(ag.id)}
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

      <CreateAgentDialog open={createOpen} onClose={() => setCreateOpen(false)}
        onSaved={async ({ id, mode }) => {
          setModeFilter("all");
          setCreatedAgentId(id);
          setCreateOpen(false);
          await queryClient.invalidateQueries({ queryKey: ["agents", "list"] });
          if (mode === "full" || mode === "multi") {
            navigate("/agents");
          }
          window.setTimeout(() => setCreatedAgentId((current) => (current === id ? null : current)), 8000);
        }} />
      <CreateAgentDialog
        open={Boolean(editingAgent)}
        initialAgent={editingAgent}
        onClose={() => setEditingAgent(null)}
        onSaved={async ({ id }) => {
          setCreatedAgentId(id);
          setEditingAgent(null);
          await queryClient.invalidateQueries({ queryKey: ["agents", "list"] });
          window.setTimeout(() => setCreatedAgentId((current) => (current === id ? null : current)), 8000);
        }}
      />
    </PageShell>
  );
}
