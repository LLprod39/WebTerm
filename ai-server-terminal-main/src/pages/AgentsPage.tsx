import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchAgents,
  fetchAgentTemplates,
  fetchFrontendBootstrap,
  createAgent,
  deleteAgent,
  runAgent,
  stopAgent,
  type AgentItem,
  type AgentTemplate,
  type AgentRunResult,
} from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import {
  Bot, Plus, Play, Trash2, RefreshCw, Clock, Zap, Eye,
  FileText, Server, X, Square,
  Brain, Target, Settings2, Layers, CheckCircle2,
  AlertTriangle, Activity,
  Shield,
  type LucideIcon,
} from "lucide-react";
import { AgentReportModal } from "@/components/studio/AgentReportModal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogBody, DialogFooter,
} from "@/components/ui/dialog";
import { EmptyState, MetricCard, MetricGrid, PageHero, PageShell, QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";

function formatDuration(ms: number): string {
  if (!ms) return "—";
  if (ms < 1000) return `${ms}ms`;
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  return `${mins}m ${secs % 60}s`;
}

const MODE_ICONS: Record<string, typeof Bot> = { mini: Zap, full: Brain, multi: Layers };
const AGENT_ICONS: Record<string, LucideIcon> = {
  security_audit: Shield,
  security_patrol: Shield,
  log_analyzer: FileText,
  log_investigator: FileText,
  performance: Activity,
  disk_report: Server,
  docker_status: Layers,
  service_health: Settings2,
  deploy_watcher: Zap,
  infra_scout: Server,
  multi_health: Activity,
  custom: Settings2,
};
const FULL_AGENT_TOOL_OPTIONS = [
  { key: "open_connection", label: "Open connection" },
  { key: "close_connection", label: "Close connection" },
  { key: "ssh_execute", label: "SSH execute" },
  { key: "read_console", label: "Read console" },
  { key: "wait_for_output", label: "Wait for output" },
  { key: "send_ctrl_c", label: "Send Ctrl+C" },
  { key: "report", label: "Progress report" },
  { key: "ask_user", label: "Ask user" },
  { key: "analyze_output", label: "Analyze output" },
  { key: "list_skills", label: "List skills" },
  { key: "read_skill", label: "Read skill" },
] as const;

function buildDefaultToolsConfig() {
  return Object.fromEntries(FULL_AGENT_TOOL_OPTIONS.map((tool) => [tool.key, true]));
}

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function formatRoleLabel(role: string): string {
  return role
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export default function AgentsPage() {
  const { t, lang } = useI18n();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [modeFilter, setModeFilter] = useState<"all" | "mini" | "full" | "multi">("all");
  const [createOpen, setCreateOpen] = useState(false);
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
  const scheduledAgents = allAgents.filter((agent) => agent.schedule_minutes > 0).length;
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
                >{m === "all" ? t("agent.all") : m === "mini" ? "Mini" : m === "full" ? "Full" : "Pipeline"}</button>
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
                        {ag.mode === "multi" ? "Pipeline" : ag.mode}
                      </span>
                      {ag.active_run_id && (
                        <StatusBadge label="running" tone="info" />
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-muted-foreground mt-0.5">
                      <span className="flex items-center gap-0.5"><Server className="h-2.5 w-2.5" /> {ag.server_count}</span>
                      {ag.last_run_at && <span className="flex items-center gap-0.5"><Clock className="h-2.5 w-2.5" /> {relativeTime(ag.last_run_at)}</span>}
                      {ag.schedule_minutes > 0 && <span className="flex items-center gap-0.5"><RefreshCw className="h-2.5 w-2.5" /> {ag.schedule_minutes}m</span>}
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
                        <Button size="xs" variant="outline" className="gap-1" disabled={isRunning} onClick={() => onRun(ag)}>
                          {isRunning ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} {t("agent.run")}
                        </Button>
                      </>
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
        onCreated={async ({ id, mode }) => {
          setModeFilter("all");
          setCreatedAgentId(id);
          setCreateOpen(false);
          await queryClient.invalidateQueries({ queryKey: ["agents", "list"] });
          if (mode === "full" || mode === "multi") {
            navigate("/agents");
          }
          window.setTimeout(() => setCreatedAgentId((current) => (current === id ? null : current)), 8000);
        }} />
    </PageShell>
  );
}
// ---------------------------------------------------------------------------

function CreateAgentDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (created: { id: number; mode: "mini" | "full" | "multi" }) => Promise<void> | void;
}) {
  const { t, lang } = useI18n();
  const [step, setStep] = useState<"template" | "config">("template");
  const [mode, setMode] = useState<"mini" | "full" | "multi">("mini");
  const [selectedType, setSelectedType] = useState("");
  const [name, setName] = useState("");
  const [commands, setCommands] = useState("");
  const [aiPrompt, setAiPrompt] = useState("");
  const [goal, setGoal] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [maxIter, setMaxIter] = useState(20);
  const [multiServer, setMultiServer] = useState(false);
  const [toolsConfig, setToolsConfig] = useState<Record<string, boolean>>(() => buildDefaultToolsConfig());
  const [stopConditionsText, setStopConditionsText] = useState("");
  const [sessionTimeoutSeconds, setSessionTimeoutSeconds] = useState(600);
  const [maxConnections, setMaxConnections] = useState(5);
  const [selectedServers, setSelectedServers] = useState<number[]>([]);
  const [schedule, setSchedule] = useState(0);
  const [saving, setSaving] = useState(false);

  const { data: tplData } = useQuery({ queryKey: ["agents", "templates"], queryFn: fetchAgentTemplates, enabled: open });
  const { data: bootstrapData } = useQuery({ queryKey: ["frontend", "bootstrap"], queryFn: fetchFrontendBootstrap, staleTime: 30_000 });

  const templates = (tplData?.templates || []).filter((template) => template.mode === mode || (mode === "multi" && template.mode === "full"));
  const servers = bootstrapData?.servers || [];

  const onSelectTemplate = (tpl: AgentTemplate) => {
    setSelectedType(tpl.type);
    setName(tpl.name);
    setCommands(tpl.commands.join("\n"));
    setAiPrompt(tpl.ai_prompt);
    if (tpl.mode === "full" || mode === "multi") {
      setGoal(tpl.goal || "");
      setSystemPrompt(tpl.system_prompt || "");
      setMultiServer(tpl.allow_multi_server || false);
      setStopConditionsText((tpl.stop_conditions || []).join("\n"));
    }
    setStep("config");
  };

  const onSave = async () => {
    setSaving(true);
    try {
      const cmdList = commands.split("\n").map((c) => c.trim()).filter(Boolean);
      const created = await createAgent({
        name: name || localize(lang, "Новый агент", "Custom Agent"),
        mode,
        agent_type: selectedType || "custom",
        server_ids: selectedServers,
        commands: cmdList,
        ai_prompt: aiPrompt,
        schedule_minutes: schedule,
        goal,
        system_prompt: systemPrompt,
        max_iterations: maxIter,
        allow_multi_server: multiServer,
        tools_config: mode === "mini" ? {} : toolsConfig,
        stop_conditions: stopConditionsText.split("\n").map((item) => item.trim()).filter(Boolean),
        session_timeout_seconds: sessionTimeoutSeconds,
        max_connections: maxConnections,
      });
      await onCreated({ id: created.id, mode });
      resetForm();
    } finally { setSaving(false); }
  };

  const resetForm = () => {
    setStep("template"); setMode("mini"); setSelectedType(""); setName("");
    setCommands(""); setAiPrompt(""); setGoal(""); setSystemPrompt("");
    setMaxIter(20); setMultiServer(false); setSelectedServers([]); setSchedule(0);
    setToolsConfig(buildDefaultToolsConfig()); setStopConditionsText(""); setSessionTimeoutSeconds(600); setMaxConnections(5);
  };

  const toggleServer = (id: number) => setSelectedServers((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  const selectAll = () => { if (selectedServers.length === servers.length) setSelectedServers([]); else setSelectedServers(servers.map((s) => s.id)); };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {step === "template"
              ? t("agent.create")
              : localize(
                lang,
                `Настроить ${mode === "multi" ? "пайплайн" : mode === "full" ? "полного агента" : "mini-агента"}`,
                `Configure ${mode === "multi" ? "Pipeline" : mode === "full" ? "Full" : "Mini"} Agent`,
              )}
          </DialogTitle>
          <DialogDescription>
            {step === "template"
              ? localize(lang, "Выберите тип агента или начните с ручной настройки.", "Choose an agent type or start with a custom setup.")
              : localize(lang, "Настройте цель, лимиты, доступ к инструментам и серверы для запуска.", "Set the goal, limits, tool access, and servers for this run.")}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="max-h-[70vh] overflow-y-auto">
          {step === "template" ? (
            <div className="space-y-4">
              {/* Mode selector */}
              <div className="flex gap-3 flex-wrap">
                <button
                  type="button"
                  aria-pressed={mode === "mini"}
                  onClick={() => setMode("mini")}
                  className={`flex-1 min-w-[140px] text-left border rounded-lg p-4 transition-colors ${mode === "mini" ? "border-primary bg-primary/10" : "border-border hover:border-primary/40"}`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Zap className="h-4 w-4 text-primary" />
                    <span className="text-sm font-semibold">{localize(lang, "Mini-агент", "Mini Agent")}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">{localize(lang, "Выполняет список команд и готовит краткий разбор.", "Runs commands and returns a short analysis.")}</p>
                </button>
                <button
                  type="button"
                  aria-pressed={mode === "full"}
                  onClick={() => setMode("full")}
                  className={`flex-1 min-w-[140px] text-left border rounded-lg p-4 transition-colors ${mode === "full" ? "border-primary bg-primary/10" : "border-border hover:border-primary/40"}`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Brain className="h-4 w-4 text-primary" />
                    <span className="text-sm font-semibold">{localize(lang, "Полный агент", "Full Agent")}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">{localize(lang, "Сам выбирает шаги, инструменты и проверки.", "Chooses steps, tools, and checks.")}</p>
                </button>
                <button
                  type="button"
                  aria-pressed={mode === "multi"}
                  onClick={() => setMode("multi")}
                  className={`flex-1 min-w-[140px] text-left border rounded-lg p-4 transition-colors ${mode === "multi" ? "border-primary bg-primary/10" : "border-border hover:border-primary/40"}`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Layers className="h-4 w-4 text-primary" />
                    <span className="text-sm font-semibold">Pipeline</span>
                  </div>
                  <p className="text-xs text-muted-foreground">{localize(lang, "Координирует несколько агентов и серверов.", "Coordinates multiple agents and servers.")}</p>
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {templates.map((tpl) => (
                  <button
                    key={tpl.type}
                    type="button"
                    onClick={() => onSelectTemplate(tpl)}
                    className="text-left bg-secondary/40 border border-border rounded-lg p-4 hover:border-primary/50 transition-colors">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-background text-muted-foreground">
                        {(() => {
                          const TemplateIcon = AGENT_ICONS[tpl.type] || Settings2;
                          return <TemplateIcon className="h-4 w-4" />;
                        })()}
                      </span>
                      <span className="text-sm font-semibold text-foreground">{tpl.name}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {tpl.mode === "full"
                        ? ((tpl.goal || localize(lang, "Автономная OPS-задача", "Autonomous OPS task")).slice(0, 80))
                        : localize(lang, `${tpl.command_count} команд`, `${tpl.command_count} commands`)}
                    </p>
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => { setSelectedType("custom"); setStep("config"); }}
                  className="text-left bg-secondary/40 border border-dashed border-border rounded-lg p-4 hover:border-primary/50 transition-colors">
                  <div className="flex items-center gap-3 mb-2">
                    <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-background text-muted-foreground">
                      <Settings2 className="h-4 w-4" />
                    </span>
                    <span className="text-sm font-semibold text-foreground">{localize(lang, "Настроить вручную", "Custom Agent")}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">{localize(lang, "Задайте команды, цель и серверы сами.", "Define commands, goal, and servers yourself.")}</p>
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">{localize(lang, "Название", "Name")}</label>
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={localize(lang, "Проверка места на диске", "Disk space check")} className="bg-secondary/30 h-10" />
              </div>

              {(mode === "full" || mode === "multi") && (
                <>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground flex items-center gap-2">
                      <Target className="h-4 w-4 text-primary" /> {localize(lang, "Цель", "Goal")}
                    </label>
                    <Textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} className="bg-secondary/30 text-sm"
                      placeholder={mode === "multi" ? localize(lang, "Что нужно проверить или исправить. Оркестратор разложит цель на шаги.", "What to check or fix. The orchestrator will split it into steps.") : localize(lang, "Что должен сделать агент и какой результат вернуть.", "What the agent should do and report back.")} />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground flex items-center gap-2"><Settings2 className="h-4 w-4 text-muted-foreground" /> {localize(lang, "Системные инструкции", "System instructions")}</label>
                    <Textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={2} className="bg-secondary/30 text-sm"
                      placeholder={localize(lang, "Роль, ограничения, формат отчёта. Необязательно.", "Role, limits, report format. Optional.")} />
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <div className="flex-1 space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">{localize(lang, "Макс. итераций", "Max iterations")}</label>
                      <Input type="number" min={1} max={100} value={maxIter} onChange={(e) => setMaxIter(Number(e.target.value))} className="bg-secondary/50 h-8 text-sm" />
                    </div>
                    <div className="flex-1 space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">{localize(lang, "Таймаут сессии, сек.", "Session timeout, sec")}</label>
                      <Input type="number" min={30} max={3600} value={sessionTimeoutSeconds} onChange={(e) => setSessionTimeoutSeconds(Number(e.target.value))} className="bg-secondary/50 h-8 text-sm" />
                    </div>
                    <div className="flex-1 space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">{localize(lang, "Макс. подключений", "Max connections")}</label>
                      <Input type="number" min={1} max={10} value={maxConnections} onChange={(e) => setMaxConnections(Number(e.target.value))} className="bg-secondary/50 h-8 text-sm" />
                    </div>
                    <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer rounded-lg border border-border/50 bg-secondary/30 px-3 py-2 xl:mt-5">
                      <input type="checkbox" checked={multiServer} onChange={(e) => setMultiServer(e.target.checked)} className="rounded" />
                      {localize(lang, "Несколько серверов", "Multi-server")}
                    </label>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">{localize(lang, "Условия остановки", "Stop conditions")}</label>
                    <Textarea
                      value={stopConditionsText}
                      onChange={(e) => setStopConditionsText(e.target.value)}
                      rows={3}
                      className="bg-secondary/50 text-xs"
                      placeholder={localize(lang, "По одному условию на строку. Например: health checks зелёные", "One condition per line. Example: health checks are green")}
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-medium text-muted-foreground">{localize(lang, "Доступ к инструментам", "Tool access")}</label>
                      <button
                        type="button"
                        className="min-h-8 rounded-md px-2 text-xs font-medium text-primary transition-colors hover:bg-primary/10"
                        onClick={() => setToolsConfig(buildDefaultToolsConfig())}
                      >
                        {localize(lang, "Включить все", "Enable all")}
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-2 rounded-lg border border-border/70 bg-secondary/20 p-3">
                      {FULL_AGENT_TOOL_OPTIONS.map((tool) => (
                        <label key={tool.key} className="flex items-center gap-2 text-xs text-muted-foreground">
                          <input
                            type="checkbox"
                            checked={Boolean(toolsConfig[tool.key])}
                            onChange={(event) =>
                              setToolsConfig((current) => ({ ...current, [tool.key]: event.target.checked }))
                            }
                          />
                          {tool.label}
                        </label>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {mode === "mini" && (
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">{t("agent.commands_label")}</label>
                  <Textarea value={commands} onChange={(e) => setCommands(e.target.value)} rows={5} className="bg-secondary/50 font-mono text-[11px]"
                    placeholder="hostname&#10;uptime&#10;free -m" />
                </div>
              )}

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{localize(lang, "Инструкции к анализу", "Analysis instructions")}</label>
                <Textarea value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} rows={2} className="bg-secondary/50 text-xs"
                  placeholder={localize(lang, "На что обратить внимание в выводе команд. Необязательно.", "What to focus on in command output. Optional.")} />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t("nav.servers")}</label>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={selectAll} className={`min-h-8 rounded-md border px-3 py-1 text-xs font-medium transition-colors ${selectedServers.length === servers.length ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>{t("agent.all")}</button>
                  {servers.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      aria-pressed={selectedServers.includes(s.id)}
                      onClick={() => toggleServer(s.id)}
                      className={`min-h-8 rounded-md border px-3 py-1 text-xs font-medium transition-colors ${selectedServers.includes(s.id) ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                      {s.name}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-muted-foreground">{t("agent.schedule")}</label>
                  <span className="text-xs font-mono text-foreground">{schedule === 0 ? t("agent.manual") : `${schedule} min`}</span>
                </div>
                <input type="range" min={0} max={1440} step={5} value={schedule} onChange={(e) => setSchedule(Number(e.target.value))}
                  className="w-full h-1.5 bg-secondary rounded-full appearance-none cursor-pointer accent-primary" />
              </div>
            </div>
          )}
        </DialogBody>
        {step === "config" && (
          <DialogFooter>
            <Button size="sm" variant="outline" className="min-w-24" onClick={() => setStep("template")}>{t("agent.back")}</Button>
            <Button size="sm" className="min-w-32" onClick={onSave} disabled={saving || !selectedServers.length}>
              {saving ? localize(lang, "Создаём...", "Creating...") : t("agent.create")}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
