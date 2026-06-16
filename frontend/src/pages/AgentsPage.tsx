import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchAgents,
  fetchAgentTemplates,
  fetchFrontendBootstrap,
  createAgent,
  updateAgent,
  deleteAgent,
  runAgent,
  stopAgent,
  studioSkills,
  type AgentItem,
  type AgentInputArtifact,
  type AgentScheduleConfig,
  type AgentScheduleMode,
  type AgentTemplate,
  type AgentRunResult,
  type StudioSkill,
} from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import {
  Bot, Plus, Play, Trash2, RefreshCw, Clock, Zap, Eye,
  FileText, Server, X, Square,
  Brain, Target, Settings2, Layers, CheckCircle2,
  AlertTriangle, Activity,
  Shield, CalendarDays, BookOpen, Upload, FileCode2, Send,
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

function agentModeLabel(mode: "all" | "mini" | "full" | "multi" | string, lang: string) {
  if (mode === "all") return localize(lang, "Все", "All");
  if (mode === "mini") return localize(lang, "Мини", "Mini");
  if (mode === "full") return localize(lang, "Полный", "Full");
  if (mode === "multi") return localize(lang, "Пайплайн", "Pipeline");
  return mode;
}

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
  { key: "report", label: "Progress report" },
  { key: "ask_user", label: "Ask user" },
  { key: "analyze_output", label: "Analyze output" },
  { key: "list_skills", label: "List skills" },
  { key: "read_skill", label: "Read skill" },
] as const;

type AgentSudoPolicy = "disabled" | "ask" | "approved";

const SUDO_AGENT_OPTIONS: Array<{
  value: AgentSudoPolicy;
  labelRu: string;
  labelEn: string;
  hintRu: string;
  hintEn: string;
}> = [
  {
    value: "disabled",
    labelRu: "Без sudo",
    labelEn: "No sudo",
    hintRu: "Команды с sudo будут заблокированы.",
    hintEn: "Commands with sudo are blocked.",
  },
  {
    value: "ask",
    labelRu: "Спросить при необходимости",
    labelEn: "Ask when needed",
    hintRu: "Агент остановится и попросит разрешение, если ему понадобится sudo.",
    hintEn: "The agent stops and asks when sudo is needed.",
  },
  {
    value: "approved",
    labelRu: "Разрешить на запуск",
    labelEn: "Approve for run",
    hintRu: "Sudo разрешён для запусков этого агента; backend выполнит его как sudo -n.",
    hintEn: "Sudo is approved for this agent's runs; backend enforces sudo -n.",
  },
];

function sudoAgentOption(value: string | undefined) {
  return SUDO_AGENT_OPTIONS.find((item) => item.value === value) || SUDO_AGENT_OPTIONS[0];
}

const SCHEDULE_PRESETS = [
  {
    minutes: 0,
    labelRu: "Вручную",
    labelEn: "Manual",
    hintRu: "Только кнопкой запуска",
    hintEn: "Run only from button",
  },
  {
    minutes: 15,
    labelRu: "15 минут",
    labelEn: "15 minutes",
    hintRu: "Частый мониторинг",
    hintEn: "Frequent checks",
  },
  {
    minutes: 30,
    labelRu: "30 минут",
    labelEn: "30 minutes",
    hintRu: "Оперативные проверки",
    hintEn: "Operational checks",
  },
  {
    minutes: 60,
    labelRu: "1 час",
    labelEn: "1 hour",
    hintRu: "Стандартный режим",
    hintEn: "Standard cadence",
  },
  {
    minutes: 180,
    labelRu: "3 часа",
    labelEn: "3 hours",
    hintRu: "Периодический обзор",
    hintEn: "Periodic review",
  },
  {
    minutes: 360,
    labelRu: "6 часов",
    labelEn: "6 hours",
    hintRu: "Несколько раз в день",
    hintEn: "Several times a day",
  },
  {
    minutes: 720,
    labelRu: "12 часов",
    labelEn: "12 hours",
    hintRu: "Утро и вечер",
    hintEn: "Morning and evening",
  },
  {
    minutes: 1440,
    labelRu: "1 день",
    labelEn: "1 day",
    hintRu: "Ежедневная проверка",
    hintEn: "Daily check",
  },
] as const;

const SCHEDULE_MODES: Array<{ mode: AgentScheduleMode; labelRu: string; labelEn: string; hintRu: string; hintEn: string }> = [
  { mode: "manual", labelRu: "Вручную", labelEn: "Manual", hintRu: "Только кнопкой", hintEn: "Button only" },
  { mode: "interval", labelRu: "Интервал", labelEn: "Interval", hintRu: "Каждые N минут", hintEn: "Every N minutes" },
  { mode: "daily", labelRu: "Ежедневно", labelEn: "Daily", hintRu: "В выбранное время", hintEn: "At selected time" },
  { mode: "weekly", labelRu: "По дням", labelEn: "Weekly", hintRu: "Дни недели", hintEn: "Weekdays" },
  { mode: "monthly", labelRu: "Месяц", labelEn: "Monthly", hintRu: "День месяца", hintEn: "Day of month" },
  { mode: "once", labelRu: "Разово", labelEn: "Once", hintRu: "Дата и время", hintEn: "Date and time" },
];

const WEEKDAYS = [
  { value: 0, ru: "Пн", en: "Mon" },
  { value: 1, ru: "Вт", en: "Tue" },
  { value: 2, ru: "Ср", en: "Wed" },
  { value: 3, ru: "Чт", en: "Thu" },
  { value: 4, ru: "Пт", en: "Fri" },
  { value: 5, ru: "Сб", en: "Sat" },
  { value: 6, ru: "Вс", en: "Sun" },
] as const;

const QUICK_TIMES = ["08:00", "09:00", "10:00", "18:00"] as const;

const ARTIFACT_KINDS: Array<{ kind: AgentInputArtifact["kind"]; labelRu: string; labelEn: string; icon: LucideIcon }> = [
  { kind: "document", labelRu: "Документ", labelEn: "Document", icon: FileText },
  { kind: "task_list", labelRu: "Список задач", labelEn: "Task list", icon: CheckCircle2 },
  { kind: "script", labelRu: "Скрипт", labelEn: "Script", icon: FileCode2 },
];

type AgentTaskDraft = NonNullable<AgentInputArtifact["tasks"]>[number];

function artifactKindLabel(kind: AgentInputArtifact["kind"], lang: string) {
  const match = ARTIFACT_KINDS.find((item) => item.kind === kind);
  return match ? localize(lang, match.labelRu, match.labelEn) : kind;
}

function artifactKindIcon(kind: AgentInputArtifact["kind"]) {
  return ARTIFACT_KINDS.find((item) => item.kind === kind)?.icon || FileText;
}

function parseTasksFromContent(content: string): AgentTaskDraft[] {
  return String(content || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const clean = line.replace(/^[-*]\s*(\[[ xX]\])?\s*/, "");
      const [title, ...detailsParts] = clean.split(/\s+[—-]\s+/);
      return {
        title: (title || clean).trim(),
        details: detailsParts.join(" - ").trim(),
        done: /^\s*[-*]\s*\[[xX]\]/.test(line),
      };
    })
    .filter((task) => task.title);
}

function tasksToContent(tasks: AgentTaskDraft[] | undefined): string {
  return (tasks || [])
    .filter((task) => task.title.trim() || (task.details || "").trim())
    .map((task) => {
      const details = (task.details || "").trim();
      return `- [${task.done ? "x" : " "}] ${task.title.trim()}${details ? ` — ${details}` : ""}`;
    })
    .join("\n");
}

function normalizeArtifactDraft(item: AgentInputArtifact): AgentInputArtifact {
  if (item.kind !== "task_list") return item;
  const tasks = item.tasks?.length ? item.tasks : parseTasksFromContent(item.content || "");
  return { ...item, tasks };
}

function prepareArtifactForSave(item: AgentInputArtifact): AgentInputArtifact {
  const name = item.name.trim();
  const run_hint = (item.run_hint || "").trim();
  if (item.kind === "task_list") {
    const tasks = (item.tasks || [])
      .map((task) => ({
        title: task.title.trim(),
        details: (task.details || "").trim(),
        done: Boolean(task.done),
      }))
      .filter((task) => task.title || task.details);
    return {
      ...item,
      name,
      run_hint,
      tasks,
      content: tasksToContent(tasks),
    };
  }
  return { ...item, name, run_hint, content: item.content.trim() };
}

function artifactSummary(item: AgentInputArtifact, lang: string) {
  if (item.kind === "task_list") {
    const total = item.tasks?.length || parseTasksFromContent(item.content || "").length;
    return localize(lang, `${total} задач`, `${total} tasks`);
  }
  const chars = (item.content || "").length;
  if (item.size_bytes) {
    const kb = Math.max(1, Math.round(item.size_bytes / 1024));
    return `${kb} KB · ${chars} chars`;
  }
  return `${chars} chars`;
}

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

function formatScheduleLabel(minutes: number, lang: string): string {
  if (!minutes) return localize(lang, "Только ручной запуск", "Manual only");
  if (minutes < 60) return localize(lang, `Каждые ${minutes} мин`, `Every ${minutes} min`);
  if (minutes % 1440 === 0) {
    const days = minutes / 1440;
    return localize(lang, days === 1 ? "Каждый день" : `Каждые ${days} дн.`, days === 1 ? "Daily" : `Every ${days} days`);
  }
  if (minutes % 60 === 0) {
    const hours = minutes / 60;
    return localize(lang, hours === 1 ? "Каждый час" : `Каждые ${hours} ч`, hours === 1 ? "Hourly" : `Every ${hours} h`);
  }
  return localize(lang, `Каждые ${minutes} мин`, `Every ${minutes} min`);
}

function browserTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

function defaultScheduleConfig(): AgentScheduleConfig {
  return {
    mode: "manual",
    timezone: browserTimezone(),
    interval_minutes: 0,
    time: "09:00",
    weekdays: [0, 1, 2, 3, 4],
    day_of_month: 1,
    run_at: "",
  };
}

function scheduleConfigFromMinutes(minutes: number): AgentScheduleConfig {
  const base = defaultScheduleConfig();
  if (!minutes) return base;
  return { ...base, mode: "interval", interval_minutes: minutes };
}

function deriveScheduleMinutes(config: AgentScheduleConfig): number {
  if (config.mode === "manual") return 0;
  if (config.mode === "interval") return Math.max(0, Number(config.interval_minutes || 0));
  if (config.mode === "daily") return 1440;
  if (config.mode === "weekly" || config.mode === "monthly") return 10080;
  if (config.mode === "once") return 1;
  return 0;
}

function finalizeScheduleConfig(config: AgentScheduleConfig, intervalMinutes: number): AgentScheduleConfig {
  const base = defaultScheduleConfig();
  const next: AgentScheduleConfig = {
    ...base,
    ...config,
    timezone: config.timezone || browserTimezone(),
    time: config.time || "09:00",
    weekdays: Array.isArray(config.weekdays) && config.weekdays.length ? config.weekdays : [0, 1, 2, 3, 4],
    day_of_month: Math.min(31, Math.max(1, Number(config.day_of_month || 1))),
    run_at: config.run_at || "",
  };
  if (next.mode === "manual") next.interval_minutes = 0;
  if (next.mode === "interval") next.interval_minutes = Math.max(0, Number(intervalMinutes || next.interval_minutes || 0));
  return next;
}

function formatScheduleConfigLabel(config: AgentScheduleConfig | undefined, minutes: number, lang: string): string {
  const current = config || scheduleConfigFromMinutes(minutes);
  if (current.mode === "manual") return localize(lang, "Только ручной запуск", "Manual only");
  if (current.mode === "interval") return formatScheduleLabel(Number(current.interval_minutes || minutes || 0), lang);
  if (current.mode === "daily") return localize(lang, `Каждый день в ${current.time || "09:00"}`, `Daily at ${current.time || "09:00"}`);
  if (current.mode === "weekly") return localize(lang, `По дням недели в ${current.time || "09:00"}`, `Weekly at ${current.time || "09:00"}`);
  if (current.mode === "monthly") return localize(lang, `${current.day_of_month || 1} числа в ${current.time || "09:00"}`, `Day ${current.day_of_month || 1} at ${current.time || "09:00"}`);
  if (current.mode === "once") return localize(lang, "Разовый запуск", "One-time run");
  return formatScheduleLabel(minutes, lang);
}

function isAgentScheduled(agent: AgentItem): boolean {
  const mode = agent.schedule_config?.mode || (agent.schedule_minutes > 0 ? "interval" : "manual");
  return mode !== "manual";
}

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
// ---------------------------------------------------------------------------

function CreateAgentDialog({
  open,
  onClose,
  onSaved,
  initialAgent = null,
}: {
  open: boolean;
  onClose: () => void;
  initialAgent?: AgentItem | null;
  onSaved: (saved: { id: number; mode: "mini" | "full" | "multi"; action: "create" | "update" }) => Promise<void> | void;
}) {
  const { t, lang } = useI18n();
  const isEditing = Boolean(initialAgent);
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
  const [sudoPolicy, setSudoPolicy] = useState<AgentSudoPolicy>("disabled");
  const [stopConditionsText, setStopConditionsText] = useState("");
  const [sessionTimeoutSeconds, setSessionTimeoutSeconds] = useState(600);
  const [maxConnections, setMaxConnections] = useState(5);
  const [selectedServers, setSelectedServers] = useState<number[]>([]);
  const [schedule, setSchedule] = useState(0);
  const [scheduleConfig, setScheduleConfig] = useState<AgentScheduleConfig>(() => defaultScheduleConfig());
  const [selectedSkillSlugs, setSelectedSkillSlugs] = useState<string[]>([]);
  const [inputArtifacts, setInputArtifacts] = useState<AgentInputArtifact[]>([]);
  const [activeArtifactIndex, setActiveArtifactIndex] = useState<number | null>(null);
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [telegramChatId, setTelegramChatId] = useState("");
  const [saving, setSaving] = useState(false);

  const { data: tplData } = useQuery({ queryKey: ["agents", "templates"], queryFn: fetchAgentTemplates, enabled: open });
  const { data: bootstrapData } = useQuery({ queryKey: ["frontend", "bootstrap"], queryFn: fetchFrontendBootstrap, staleTime: 30_000 });
  const { data: availableSkills = [] } = useQuery<StudioSkill[]>({ queryKey: ["studio", "skills", "agent-picker"], queryFn: studioSkills.list, enabled: open });

  const templates = (tplData?.templates || []).filter((template) => template.mode === mode || (mode === "multi" && template.mode === "full"));
  const servers = bootstrapData?.servers || [];
  const allServerIds = servers.map((server) => server.id);

  const resetForm = () => {
    setStep("template"); setMode("mini"); setSelectedType(""); setName("");
    setCommands(""); setAiPrompt(""); setGoal(""); setSystemPrompt("");
    setMaxIter(20); setMultiServer(false); setSelectedServers([]); setSchedule(0);
    setScheduleConfig(defaultScheduleConfig()); setSelectedSkillSlugs([]); setInputArtifacts([]);
    setActiveArtifactIndex(null);
    setTelegramEnabled(false); setTelegramChatId("");
    setSudoPolicy("disabled");
    setToolsConfig(buildDefaultToolsConfig()); setStopConditionsText(""); setSessionTimeoutSeconds(600); setMaxConnections(5);
  };

  useEffect(() => {
    if (!open) return;
    if (!initialAgent) {
      resetForm();
      return;
    }

    setStep("config");
    setMode(initialAgent.mode);
    setSelectedType(initialAgent.agent_type || "custom");
    setName(initialAgent.name || "");
    setCommands((initialAgent.commands || []).join("\n"));
    setAiPrompt(initialAgent.ai_prompt || "");
    setGoal(initialAgent.goal || "");
    setSystemPrompt(initialAgent.system_prompt || "");
    setMaxIter(initialAgent.max_iterations || 20);
    setMultiServer(Boolean(initialAgent.allow_multi_server));
    setToolsConfig({ ...buildDefaultToolsConfig(), ...(initialAgent.tools_config || {}) });
    setSudoPolicy(sudoAgentOption(initialAgent.sudo_policy).value);
    setStopConditionsText((initialAgent.stop_conditions || []).join("\n"));
    setSessionTimeoutSeconds(initialAgent.session_timeout_seconds || 600);
    setMaxConnections(initialAgent.max_connections || 5);
    setSelectedServers(initialAgent.server_ids || []);
    setSchedule(initialAgent.schedule_minutes || 0);
    const nextScheduleConfig = initialAgent.schedule_config || scheduleConfigFromMinutes(initialAgent.schedule_minutes || 0);
    setScheduleConfig(nextScheduleConfig);
    setSelectedSkillSlugs(initialAgent.skill_slugs || []);
    setInputArtifacts((initialAgent.input_artifacts || []).map(normalizeArtifactDraft));
    setActiveArtifactIndex(null);
    const telegram = initialAgent.report_delivery?.telegram;
    setTelegramEnabled(Boolean(telegram?.enabled));
    setTelegramChatId(telegram?.chat_id || "");
  }, [open, initialAgent]);

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
      const normalizedSchedule = finalizeScheduleConfig(scheduleConfig, schedule);
      const payload = {
        name: name || localize(lang, "Новый агент", "Custom Agent"),
        mode,
        agent_type: selectedType || "custom",
        server_ids: selectedServers,
        commands: cmdList,
        ai_prompt: aiPrompt,
        schedule_minutes: deriveScheduleMinutes(normalizedSchedule),
        schedule_config: normalizedSchedule,
        goal,
        system_prompt: systemPrompt,
        max_iterations: maxIter,
        allow_multi_server: multiServer,
        tools_config: mode === "mini" ? {} : toolsConfig,
        sudo_policy: sudoPolicy,
        stop_conditions: stopConditionsText.split("\n").map((item) => item.trim()).filter(Boolean),
        skill_slugs: selectedSkillSlugs,
        input_artifacts: inputArtifacts
          .map(prepareArtifactForSave)
          .filter((item) => item.name && (item.content || item.tasks?.length)),
        report_delivery: {
          telegram: {
            enabled: telegramEnabled,
            chat_id: telegramChatId.trim(),
            format: "brief",
            include_link: true,
          },
        },
        session_timeout_seconds: sessionTimeoutSeconds,
        max_connections: maxConnections,
      };
      if (initialAgent) {
        await updateAgent(initialAgent.id, payload);
        await onSaved({ id: initialAgent.id, mode, action: "update" });
      } else {
        const created = await createAgent(payload);
        await onSaved({ id: created.id, mode, action: "create" });
        resetForm();
      }
    } finally { setSaving(false); }
  };

  const toggleServer = (id: number) => setSelectedServers((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  const setScheduleMode = (modeValue: AgentScheduleMode) => {
    const nextInterval = modeValue === "interval" ? (schedule || scheduleConfig.interval_minutes || 60) : 0;
    setSchedule(nextInterval);
    setScheduleConfig(finalizeScheduleConfig({ ...scheduleConfig, mode: modeValue, interval_minutes: nextInterval }, nextInterval));
  };
  const updateSchedule = (patch: Partial<AgentScheduleConfig>) => {
    setScheduleConfig((current) => finalizeScheduleConfig({ ...current, ...patch }, schedule));
  };
  const toggleWeekday = (day: number) => {
    setScheduleConfig((current) => {
      const currentDays = current.weekdays || [];
      const weekdays = currentDays.includes(day) ? currentDays.filter((item) => item !== day) : [...currentDays, day].sort();
      return finalizeScheduleConfig({ ...current, weekdays: weekdays.length ? weekdays : [day] }, schedule);
    });
  };
  const toggleSkill = (slug: string) => {
    setSelectedSkillSlugs((current) => current.includes(slug) ? current.filter((item) => item !== slug) : [...current, slug]);
  };
  const addArtifact = (kind: AgentInputArtifact["kind"]) => {
    const labels = {
      document: localize(lang, "Документ", "Document"),
      task_list: localize(lang, "Список задач", "Task list"),
      script: localize(lang, "Скрипт", "Script"),
    };
    const artifact: AgentInputArtifact = kind === "task_list"
      ? { kind, name: labels[kind], content: "", run_hint: "", tasks: [{ title: "", details: "", done: false }] }
      : { kind, name: labels[kind], content: "", run_hint: "" };
    const next = [...inputArtifacts, artifact].slice(0, 10);
    setInputArtifacts(next);
    setActiveArtifactIndex(next.length - 1);
  };
  const updateArtifact = (index: number, patch: Partial<AgentInputArtifact>) => {
    setInputArtifacts((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  };
  const removeArtifact = (index: number) => {
    setInputArtifacts((current) => current.filter((_, itemIndex) => itemIndex !== index));
    setActiveArtifactIndex((current) => {
      if (current === null) return null;
      if (current === index) return null;
      return current > index ? current - 1 : current;
    });
  };
  const updateArtifactTask = (artifactIndex: number, taskIndex: number, patch: Partial<AgentTaskDraft>) => {
    setInputArtifacts((current) => current.map((artifact, index) => {
      if (index !== artifactIndex) return artifact;
      const tasks = artifact.tasks?.length ? artifact.tasks : [{ title: "", details: "", done: false }];
      return {
        ...artifact,
        tasks: tasks.map((task, itemIndex) => itemIndex === taskIndex ? { ...task, ...patch } : task),
      };
    }));
  };
  const addArtifactTask = (artifactIndex: number) => {
    setInputArtifacts((current) => current.map((artifact, index) => (
      index === artifactIndex
        ? { ...artifact, tasks: [...(artifact.tasks || []), { title: "", details: "", done: false }] }
        : artifact
    )));
  };
  const removeArtifactTask = (artifactIndex: number, taskIndex: number) => {
    setInputArtifacts((current) => current.map((artifact, index) => {
      if (index !== artifactIndex) return artifact;
      const tasks = (artifact.tasks || []).filter((_, itemIndex) => itemIndex !== taskIndex);
      return { ...artifact, tasks: tasks.length ? tasks : [{ title: "", details: "", done: false }] };
    }));
  };
  const onMaterialFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    const added: AgentInputArtifact[] = [];
    for (const file of Array.from(files).slice(0, Math.max(0, 10 - inputArtifacts.length))) {
      const content = await file.text();
      const lowerName = file.name.toLowerCase();
      const kind: AgentInputArtifact["kind"] = lowerName.match(/\.(sh|py|js|ts|sql|ps1)$/) ? "script" : "document";
      added.push({
        kind,
        name: file.name,
        source_name: file.name,
        size_bytes: file.size,
        content: content.slice(0, 12_000),
        run_hint: kind === "script" ? localize(lang, "Проверить и запускать только если требуется задачей", "Review and run only when required") : "",
      });
    }
    const next = [...inputArtifacts, ...added].slice(0, 10);
    setInputArtifacts(next);
    if (added.length) setActiveArtifactIndex(Math.min(inputArtifacts.length, next.length - 1));
  };
  const selectAll = () => {
    if (!allServerIds.length) return;
    const hasAllServers = allServerIds.every((id) => selectedServers.includes(id));
    setSelectedServers(hasAllServers ? [] : allServerIds);
  };
  const hasAllServersSelected = allServerIds.length > 0 && allServerIds.every((id) => selectedServers.includes(id));
  const activeArtifact = activeArtifactIndex !== null ? inputArtifacts[activeArtifactIndex] : null;

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            {isEditing
              ? localize(lang, "Редактировать агента", "Edit agent")
              : step === "template"
              ? t("agent.create")
              : localize(
                lang,
                `Настроить ${mode === "multi" ? "пайплайн" : mode === "full" ? "полного агента" : "mini-агента"}`,
                `Configure ${mode === "multi" ? "Pipeline" : mode === "full" ? "Full" : "Mini"} Agent`,
              )}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? localize(lang, "Измените серверы, расписание, команды, инструкции и лимиты запуска.", "Update servers, schedule, commands, instructions, and run limits.")
              : step === "template"
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
                      placeholder={mode === "multi" ? localize(lang, "Что нужно проверить или исправить. Задача будет разложена на шаги.", "What to check or fix. The task will be split into steps.") : localize(lang, "Что должен сделать агент и какой результат вернуть.", "What the agent should do and report back.")} />
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

              <div className="space-y-3 rounded-lg border border-border/70 bg-secondary/20 p-3">
                <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <Shield className="h-3.5 w-3.5 text-primary" /> Controlled sudo
                </label>
                <div className="grid gap-2 sm:grid-cols-3">
                  {SUDO_AGENT_OPTIONS.map((option) => {
                    const active = sudoPolicy === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setSudoPolicy(option.value)}
                        className={`min-h-[58px] rounded-lg border px-3 py-2 text-left transition-colors ${
                          active
                            ? "border-primary bg-primary/10 text-foreground"
                            : "border-border/70 bg-background/35 text-muted-foreground hover:border-primary/40 hover:text-foreground"
                        }`}
                      >
                        <span className="block text-xs font-semibold">{localize(lang, option.labelRu, option.labelEn)}</span>
                        <span className="mt-0.5 block text-[11px] leading-4 text-muted-foreground">
                          {localize(lang, option.hintRu, option.hintEn)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t("nav.servers")}</label>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={selectAll} className={`min-h-8 rounded-md border px-3 py-1 text-xs font-medium transition-colors ${hasAllServersSelected ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>{t("agent.all")}</button>
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

              <div className="space-y-3 rounded-lg border border-border/70 bg-secondary/20 p-3">
                <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                  <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    <CalendarDays className="h-3.5 w-3.5 text-primary" /> {t("agent.schedule")}
                  </label>
                  <span className="inline-flex min-h-7 items-center rounded-md border border-primary/25 bg-primary/10 px-2 text-xs font-medium text-primary">
                    {formatScheduleConfigLabel(scheduleConfig, schedule, lang)}
                  </span>
                </div>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {SCHEDULE_MODES.map((option) => {
                    const active = scheduleConfig.mode === option.mode;
                    return (
                      <button
                        key={option.mode}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setScheduleMode(option.mode)}
                        className={`min-h-[58px] rounded-lg border px-3 py-2 text-left transition-colors ${
                          active
                            ? "border-primary bg-primary/10 text-foreground"
                            : "border-border/70 bg-background/35 text-muted-foreground hover:border-primary/40 hover:text-foreground"
                        }`}
                      >
                        <span className="block text-xs font-semibold">{localize(lang, option.labelRu, option.labelEn)}</span>
                        <span className="mt-0.5 block text-[11px] leading-4 text-muted-foreground">{localize(lang, option.hintRu, option.hintEn)}</span>
                      </button>
                    );
                  })}
                </div>
                {scheduleConfig.mode === "interval" && (
                  <>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                      {SCHEDULE_PRESETS.filter((option) => option.minutes > 0).map((option) => {
                        const active = schedule === option.minutes;
                        return (
                          <button
                            key={option.minutes}
                            type="button"
                            aria-pressed={active}
                            onClick={() => {
                              setSchedule(option.minutes);
                              setScheduleConfig(finalizeScheduleConfig({ ...scheduleConfig, mode: "interval", interval_minutes: option.minutes }, option.minutes));
                            }}
                            className={`min-h-[54px] rounded-lg border px-3 py-2 text-left transition-colors ${
                              active
                                ? "border-primary bg-primary/10 text-foreground"
                                : "border-border/70 bg-background/35 text-muted-foreground hover:border-primary/40 hover:text-foreground"
                            }`}
                          >
                            <span className="block text-xs font-semibold">{localize(lang, option.labelRu, option.labelEn)}</span>
                            <span className="mt-0.5 block text-[11px] leading-4 text-muted-foreground">{localize(lang, option.hintRu, option.hintEn)}</span>
                          </button>
                        );
                      })}
                    </div>
                    <div className="grid gap-2 sm:grid-cols-[1fr_160px] sm:items-end">
                      <div>
                        <div className="text-xs font-medium text-muted-foreground">{localize(lang, "Свой интервал", "Custom interval")}</div>
                        <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
                          {localize(lang, "Если нужен другой период, укажите количество минут.", "Use minutes when you need a different cadence.")}
                        </p>
                      </div>
                      <Input
                        type="number"
                        min={1}
                        max={10080}
                        step={5}
                        value={schedule || scheduleConfig.interval_minutes || 60}
                        onChange={(e) => {
                          const value = Math.max(1, Number(e.target.value) || 1);
                          setSchedule(value);
                          setScheduleConfig(finalizeScheduleConfig({ ...scheduleConfig, mode: "interval", interval_minutes: value }, value));
                        }}
                        className="h-9 bg-background/60 text-sm"
                        aria-label={localize(lang, "Интервал запуска в минутах", "Run interval in minutes")}
                      />
                    </div>
                  </>
                )}
                {(["daily", "weekly", "monthly"] as AgentScheduleMode[]).includes(scheduleConfig.mode) && (
                  <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
                    <div className="space-y-2">
                      <div className="text-xs font-medium text-muted-foreground">{localize(lang, "Время запуска", "Run time")}</div>
                      <div className="flex flex-wrap gap-2">
                        {QUICK_TIMES.map((timeValue) => (
                          <button
                            key={timeValue}
                            type="button"
                            onClick={() => updateSchedule({ time: timeValue })}
                            className={`min-h-8 rounded-md border px-3 text-xs font-medium transition-colors ${
                              scheduleConfig.time === timeValue ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
                            }`}
                          >
                            {timeValue}
                          </button>
                        ))}
                      </div>
                    </div>
                    <Input
                      type="time"
                      value={scheduleConfig.time || "09:00"}
                      onChange={(e) => updateSchedule({ time: e.target.value })}
                      className="h-9 bg-background/60 text-sm sm:mt-6"
                    />
                  </div>
                )}
                {scheduleConfig.mode === "weekly" && (
                  <div className="space-y-2">
                    <div className="text-xs font-medium text-muted-foreground">{localize(lang, "Дни недели", "Weekdays")}</div>
                    <div className="flex flex-wrap gap-2">
                      {WEEKDAYS.map((day) => {
                        const active = (scheduleConfig.weekdays || []).includes(day.value);
                        return (
                          <button
                            key={day.value}
                            type="button"
                            aria-pressed={active}
                            onClick={() => toggleWeekday(day.value)}
                            className={`min-h-8 rounded-md border px-3 text-xs font-medium transition-colors ${
                              active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
                            }`}
                          >
                            {localize(lang, day.ru, day.en)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
                {scheduleConfig.mode === "monthly" && (
                  <div className="grid gap-2 sm:grid-cols-[1fr_120px] sm:items-end">
                    <div>
                      <div className="text-xs font-medium text-muted-foreground">{localize(lang, "День месяца", "Day of month")}</div>
                      <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
                        {localize(lang, "Если в месяце нет такого числа, запуск будет пропущен.", "Months without that date are skipped.")}
                      </p>
                    </div>
                    <Input
                      type="number"
                      min={1}
                      max={31}
                      value={scheduleConfig.day_of_month || 1}
                      onChange={(e) => updateSchedule({ day_of_month: Math.min(31, Math.max(1, Number(e.target.value) || 1)) })}
                      className="h-9 bg-background/60 text-sm"
                    />
                  </div>
                )}
                {scheduleConfig.mode === "once" && (
                  <div className="grid gap-2 sm:grid-cols-[1fr_240px] sm:items-end">
                    <div>
                      <div className="text-xs font-medium text-muted-foreground">{localize(lang, "Дата и время запуска", "Run date and time")}</div>
                      <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
                        {localize(lang, "Агент запустится один раз и больше не будет считаться due.", "The agent will run once and then stop being due.")}
                      </p>
                    </div>
                    <Input
                      type="datetime-local"
                      value={scheduleConfig.run_at || ""}
                      onChange={(e) => updateSchedule({ run_at: e.target.value })}
                      className="h-9 bg-background/60 text-sm"
                    />
                  </div>
                )}
              </div>

              <div className="space-y-3 rounded-lg border border-border/70 bg-secondary/20 p-3">
                <div className="flex items-center justify-between gap-3">
                  <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    <BookOpen className="h-3.5 w-3.5 text-primary" /> {localize(lang, "Скиллы агента", "Agent skills")}
                  </label>
                  <span className="text-[11px] text-muted-foreground">{selectedSkillSlugs.length}</span>
                </div>
                {availableSkills.length ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {availableSkills.map((skill) => {
                      const active = selectedSkillSlugs.includes(skill.slug);
                      return (
                        <button
                          key={skill.slug}
                          type="button"
                          aria-pressed={active}
                          onClick={() => toggleSkill(skill.slug)}
                          className={`min-h-[58px] rounded-lg border px-3 py-2 text-left transition-colors ${
                            active ? "border-primary bg-primary/10 text-foreground" : "border-border/70 bg-background/35 text-muted-foreground hover:border-primary/40 hover:text-foreground"
                          }`}
                        >
                          <span className="block truncate text-xs font-semibold">{skill.name}</span>
                          <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{skill.service || skill.category || skill.slug}</span>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="rounded-lg border border-dashed border-border/70 px-3 py-3 text-xs text-muted-foreground">
                    {localize(lang, "Доступных скиллов пока нет.", "No available skills yet.")}
                  </div>
                )}
              </div>

              <div className="space-y-3 rounded-lg border border-border/70 bg-secondary/20 p-3">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    <Upload className="h-3.5 w-3.5 text-primary" /> {localize(lang, "Материалы агента", "Agent materials")}
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <label className="inline-flex min-h-8 cursor-pointer items-center rounded-md border border-primary/40 bg-primary/10 px-2 text-xs font-medium text-primary transition-colors hover:bg-primary/15">
                      <Upload className="mr-1 h-3 w-3" /> {localize(lang, "Прикрепить файл", "Attach file")}
                      <input
                        type="file"
                        multiple
                        className="hidden"
                        accept=".txt,.md,.csv,.json,.yaml,.yml,.sh,.py,.js,.ts,.sql,.log,.ps1"
                        onChange={(e) => {
                          void onMaterialFiles(e.currentTarget.files);
                          e.currentTarget.value = "";
                        }}
                      />
                    </label>
                    <button type="button" onClick={() => addArtifact("document")} className="min-h-8 rounded-md border border-border px-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground">
                      <FileText className="mr-1 inline h-3 w-3" /> {localize(lang, "Документ", "Document")}
                    </button>
                    <button type="button" onClick={() => addArtifact("script")} className="min-h-8 rounded-md border border-border px-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground">
                      <FileCode2 className="mr-1 inline h-3 w-3" /> {localize(lang, "Скрипт", "Script")}
                    </button>
                    <button type="button" onClick={() => addArtifact("task_list")} className="min-h-8 rounded-md border border-border px-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground">
                      <CheckCircle2 className="mr-1 inline h-3 w-3" /> {localize(lang, "Список задач", "Task list")}
                    </button>
                  </div>
                </div>
                {inputArtifacts.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border/70 px-3 py-3 text-xs text-muted-foreground">
                    {localize(lang, "Прикрепите файл или создайте документ, скрипт либо список задач.", "Attach a file or create a document, script, or task list.")}
                  </div>
                ) : (
                  <div className="grid gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.35fr)]">
                    <div className="space-y-2">
                      {inputArtifacts.map((artifact, index) => {
                        const KindIcon = artifactKindIcon(artifact.kind);
                        const active = activeArtifactIndex === index;
                        return (
                          <div key={`${artifact.kind}-${index}-${artifact.name}`} className={`rounded-lg border p-3 transition-colors ${active ? "border-primary bg-primary/10" : "border-border/70 bg-background/35"}`}>
                            <div className="flex items-start gap-3">
                              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-secondary/40 text-primary">
                                <KindIcon className="h-4 w-4" />
                              </span>
                              <div className="min-w-0 flex-1">
                                <div className="truncate text-xs font-semibold text-foreground">{artifact.name || artifactKindLabel(artifact.kind, lang)}</div>
                                <div className="mt-0.5 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
                                  <span>{artifactKindLabel(artifact.kind, lang)}</span>
                                  <span>{artifactSummary(artifact, lang)}</span>
                                </div>
                              </div>
                            </div>
                            <div className="mt-3 flex items-center justify-end gap-2">
                              <Button type="button" size="xs" variant={active ? "default" : "outline"} className="gap-1" onClick={() => setActiveArtifactIndex(index)}>
                                <Eye className="h-3 w-3" /> {localize(lang, "Открыть", "Open")}
                              </Button>
                              <Button type="button" size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground" onClick={() => removeArtifact(index)} aria-label={localize(lang, "Удалить материал", "Remove material")}>
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {activeArtifact && activeArtifactIndex !== null ? (
                      <div className="space-y-3 rounded-lg border border-border/70 bg-background/35 p-3">
                        <div className="grid gap-2 sm:grid-cols-[140px_1fr]">
                          <select
                            value={activeArtifact.kind}
                            onChange={(e) => {
                              const nextKind = e.target.value as AgentInputArtifact["kind"];
                              const nextTasks = nextKind === "task_list"
                                ? (activeArtifact.tasks?.length ? activeArtifact.tasks : parseTasksFromContent(activeArtifact.content || ""))
                                : undefined;
                              updateArtifact(activeArtifactIndex, {
                                kind: nextKind,
                                tasks: nextKind === "task_list" ? (nextTasks?.length ? nextTasks : [{ title: "", details: "", done: false }]) : undefined,
                                content: nextKind === "task_list" ? activeArtifact.content : activeArtifact.content || tasksToContent(activeArtifact.tasks),
                              });
                            }}
                            className="h-9 rounded-md border border-border bg-secondary/50 px-2 text-xs text-foreground"
                          >
                            {ARTIFACT_KINDS.map((item) => <option key={item.kind} value={item.kind}>{localize(lang, item.labelRu, item.labelEn)}</option>)}
                          </select>
                          <Input value={activeArtifact.name} onChange={(e) => updateArtifact(activeArtifactIndex, { name: e.target.value })} className="h-9 bg-secondary/50 text-sm" />
                        </div>
                        <Input
                          value={activeArtifact.run_hint || ""}
                          onChange={(e) => updateArtifact(activeArtifactIndex, { run_hint: e.target.value })}
                          className="h-8 bg-secondary/50 text-xs"
                          placeholder={localize(lang, "Подсказка агенту: когда и как использовать материал", "Hint for the agent: when and how to use this material")}
                        />

                        {activeArtifact.kind === "task_list" ? (
                          <div className="space-y-2">
                            {(activeArtifact.tasks?.length ? activeArtifact.tasks : [{ title: "", details: "", done: false }]).map((task, taskIndex) => (
                              <div key={taskIndex} className="rounded-lg border border-border/60 bg-secondary/20 p-2">
                                <div className="grid gap-2 sm:grid-cols-[auto_1fr_auto] sm:items-center">
                                  <input
                                    type="checkbox"
                                    checked={Boolean(task.done)}
                                    onChange={(e) => updateArtifactTask(activeArtifactIndex, taskIndex, { done: e.target.checked })}
                                    className="rounded"
                                    aria-label={localize(lang, "Задача выполнена", "Task done")}
                                  />
                                  <Input
                                    value={task.title}
                                    onChange={(e) => updateArtifactTask(activeArtifactIndex, taskIndex, { title: e.target.value })}
                                    className="h-8 bg-background/60 text-xs"
                                    placeholder={localize(lang, "Название задачи", "Task title")}
                                  />
                                  <Button type="button" size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground" onClick={() => removeArtifactTask(activeArtifactIndex, taskIndex)} aria-label={localize(lang, "Удалить задачу", "Remove task")}>
                                    <X className="h-3.5 w-3.5" />
                                  </Button>
                                </div>
                                <Textarea
                                  value={task.details || ""}
                                  onChange={(e) => updateArtifactTask(activeArtifactIndex, taskIndex, { details: e.target.value })}
                                  rows={2}
                                  className="mt-2 bg-background/60 text-xs"
                                  placeholder={localize(lang, "Детали, сервер, ссылка, критерий готовности", "Details, server, link, ready criteria")}
                                />
                              </div>
                            ))}
                            <Button type="button" size="sm" variant="outline" className="w-full gap-1" onClick={() => addArtifactTask(activeArtifactIndex)}>
                              <Plus className="h-3.5 w-3.5" /> {localize(lang, "Добавить задачу", "Add task")}
                            </Button>
                          </div>
                        ) : (
                          <Textarea
                            value={activeArtifact.content}
                            onChange={(e) => updateArtifact(activeArtifactIndex, { content: e.target.value })}
                            rows={activeArtifact.kind === "script" ? 10 : 8}
                            className={`bg-secondary/50 text-xs ${activeArtifact.kind === "script" ? "font-mono" : ""}`}
                            placeholder={activeArtifact.kind === "script" ? localize(lang, "Содержимое скрипта", "Script content") : localize(lang, "Содержимое документа", "Document content")}
                          />
                        )}
                      </div>
                    ) : (
                      <div className="flex min-h-[180px] items-center justify-center rounded-lg border border-dashed border-border/70 px-4 py-6 text-center text-xs text-muted-foreground">
                        {localize(lang, "Выберите вложение слева, чтобы посмотреть или изменить содержимое.", "Select an attachment on the left to view or edit it.")}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="space-y-3 rounded-lg border border-border/70 bg-secondary/20 p-3">
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    checked={telegramEnabled}
                    onChange={(e) => setTelegramEnabled(e.target.checked)}
                    className="mt-1 rounded"
                  />
                  <span className="min-w-0">
                    <span className="flex items-center gap-2 text-xs font-medium text-foreground">
                      <Send className="h-3.5 w-3.5 text-primary" /> {localize(lang, "Отправлять отчет в Telegram", "Send report to Telegram")}
                    </span>
                    <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                      {localize(lang, "Используется Telegram bot token из настроек уведомлений Studio.", "Uses the Telegram bot token from Studio notification settings.")}
                    </span>
                  </span>
                </label>
                {telegramEnabled && (
                  <Input
                    value={telegramChatId}
                    onChange={(e) => setTelegramChatId(e.target.value)}
                    className="h-9 bg-background/60 text-sm"
                    placeholder={localize(lang, "Chat ID, если нужен не общий канал", "Chat ID, when different from the default channel")}
                  />
                )}
              </div>
            </div>
          )}
        </DialogBody>
        {step === "config" && (
          <DialogFooter>
            <Button size="sm" variant="outline" className="min-w-24" onClick={isEditing ? onClose : () => setStep("template")}>
              {isEditing ? localize(lang, "Отмена", "Cancel") : t("agent.back")}
            </Button>
            <Button size="sm" className="min-w-32" onClick={onSave} disabled={saving || !selectedServers.length}>
              {saving
                ? localize(lang, isEditing ? "Сохраняем..." : "Создаём...", isEditing ? "Saving..." : "Creating...")
                : isEditing
                ? localize(lang, "Сохранить", "Save changes")
                : t("agent.create")}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
