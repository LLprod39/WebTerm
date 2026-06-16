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
  ArrowLeft, ArrowRight, Save, Tag, ListChecks,
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

const HIDDEN_AGENT_TEMPLATE_TYPES = new Set(["docker_status"]);

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

type AgentWizardStep = "template" | "basics" | "servers" | "capabilities" | "review";

const AGENT_WIZARD_STEPS: Array<{
  key: AgentWizardStep;
  labelRu: string;
  labelEn: string;
  detailRu: string;
  detailEn: string;
  icon: LucideIcon;
}> = [
  { key: "template", labelRu: "Тип", labelEn: "Type", detailRu: "Шаблон агента", detailEn: "Agent template", icon: Layers },
  { key: "basics", labelRu: "Основное", labelEn: "Basics", detailRu: "Имя, команды, права", detailEn: "Name, commands, access", icon: Tag },
  { key: "servers", labelRu: "Серверы", labelEn: "Servers", detailRu: "Окружения и расписание", detailEn: "Targets and schedule", icon: Server },
  { key: "capabilities", labelRu: "Возможности", labelEn: "Capabilities", detailRu: "Скиллы и материалы", detailEn: "Skills and materials", icon: BookOpen },
  { key: "review", labelRu: "Обзор", labelEn: "Review", detailRu: "Проверка и запуск", detailEn: "Check and launch", icon: CheckCircle2 },
];

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
  const [step, setStep] = useState<AgentWizardStep>("template");
  const [mode, setMode] = useState<"mini" | "full" | "multi">("mini");
  const [selectedType, setSelectedType] = useState("");
  const [name, setName] = useState("");
  const [commands, setCommands] = useState("");
  const [aiPrompt, setAiPrompt] = useState("");
  const [goal, setGoal] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [maxIter, setMaxIter] = useState(20);
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
  const [toolsExpanded, setToolsExpanded] = useState(false);
  const [skillsExpanded, setSkillsExpanded] = useState(false);
  const [saving, setSaving] = useState(false);

  const { data: tplData } = useQuery({ queryKey: ["agents", "templates"], queryFn: fetchAgentTemplates, enabled: open });
  const { data: bootstrapData } = useQuery({ queryKey: ["frontend", "bootstrap"], queryFn: fetchFrontendBootstrap, staleTime: 30_000 });
  const { data: availableSkills = [] } = useQuery<StudioSkill[]>({ queryKey: ["studio", "skills", "agent-picker"], queryFn: studioSkills.list, enabled: open });

  const templates = (tplData?.templates || [])
    .filter((template) => !HIDDEN_AGENT_TEMPLATE_TYPES.has(template.type))
    .filter((template) => template.mode === mode || (mode === "multi" && template.mode === "full"));
  const servers = bootstrapData?.servers || [];
  const allServerIds = servers.map((server) => server.id);
  const activeArtifact = activeArtifactIndex !== null ? inputArtifacts[activeArtifactIndex] : null;
  const currentStepIndex = Math.max(0, AGENT_WIZARD_STEPS.findIndex((item) => item.key === step));
  const commandCount = commands.split("\n").map((item) => item.trim()).filter(Boolean).length;
  const canSave = Boolean((name || selectedType).trim()) && selectedServers.length > 0;

  const resetForm = () => {
    setStep("template");
    setMode("mini");
    setSelectedType("");
    setName("");
    setCommands("");
    setAiPrompt("");
    setGoal("");
    setSystemPrompt("");
    setMaxIter(20);
    setToolsConfig(buildDefaultToolsConfig());
    setSudoPolicy("disabled");
    setStopConditionsText("");
    setSessionTimeoutSeconds(600);
    setMaxConnections(5);
    setSelectedServers([]);
    setSchedule(0);
    setScheduleConfig(defaultScheduleConfig());
    setSelectedSkillSlugs([]);
    setInputArtifacts([]);
    setActiveArtifactIndex(null);
    setTelegramEnabled(false);
    setTelegramChatId("");
    setToolsExpanded(false);
    setSkillsExpanded(false);
  };

  useEffect(() => {
    if (!open) return;
    if (!initialAgent) {
      resetForm();
      return;
    }
    setStep("basics");
    setMode(initialAgent.mode);
    setSelectedType(initialAgent.agent_type || "custom");
    setName(initialAgent.name || "");
    setCommands((initialAgent.commands || []).join("\n"));
    setAiPrompt(initialAgent.ai_prompt || "");
    setGoal(initialAgent.goal || "");
    setSystemPrompt(initialAgent.system_prompt || "");
    setMaxIter(initialAgent.max_iterations || 20);
    setToolsConfig({ ...buildDefaultToolsConfig(), ...(initialAgent.tools_config || {}) });
    setSudoPolicy(sudoAgentOption(initialAgent.sudo_policy).value);
    setStopConditionsText((initialAgent.stop_conditions || []).join("\n"));
    setSessionTimeoutSeconds(initialAgent.session_timeout_seconds || 600);
    setMaxConnections(initialAgent.max_connections || 5);
    setSelectedServers(initialAgent.server_ids || []);
    setSchedule(initialAgent.schedule_minutes || 0);
    setScheduleConfig(initialAgent.schedule_config || scheduleConfigFromMinutes(initialAgent.schedule_minutes || 0));
    setSelectedSkillSlugs(initialAgent.skill_slugs || []);
    setInputArtifacts((initialAgent.input_artifacts || []).map(normalizeArtifactDraft));
    setActiveArtifactIndex(null);
    const telegram = initialAgent.report_delivery?.telegram;
    setTelegramEnabled(Boolean(telegram?.enabled));
    setTelegramChatId(telegram?.chat_id || "");
    setToolsExpanded(false);
    setSkillsExpanded(false);
  }, [open, initialAgent]);

  const onSelectTemplate = (tpl: AgentTemplate) => {
    setSelectedType(tpl.type);
    setName(tpl.name);
    setCommands(tpl.commands.join("\n"));
    setAiPrompt(tpl.ai_prompt);
    setGoal(tpl.goal || "");
    setSystemPrompt(tpl.system_prompt || "");
    setStopConditionsText((tpl.stop_conditions || []).join("\n"));
    setStep("basics");
  };

  const onSave = async () => {
    setSaving(true);
    try {
      const normalizedSchedule = finalizeScheduleConfig(scheduleConfig, schedule);
      const payload = {
        name: name || localize(lang, "Новый агент", "Custom Agent"),
        mode,
        agent_type: selectedType || "custom",
        server_ids: selectedServers,
        commands: commands.split("\n").map((c) => c.trim()).filter(Boolean),
        ai_prompt: aiPrompt,
        schedule_minutes: deriveScheduleMinutes(normalizedSchedule),
        schedule_config: normalizedSchedule,
        goal,
        system_prompt: systemPrompt,
        max_iterations: maxIter,
        allow_multi_server: selectedServers.length > 1,
        tools_config: mode === "mini" ? {} : toolsConfig,
        sudo_policy: sudoPolicy,
        stop_conditions: stopConditionsText.split("\n").map((item) => item.trim()).filter(Boolean),
        skill_slugs: selectedSkillSlugs,
        input_artifacts: inputArtifacts.map(prepareArtifactForSave).filter((item) => item.name && (item.content || item.tasks?.length)),
        report_delivery: { telegram: { enabled: telegramEnabled, chat_id: telegramChatId.trim(), format: "brief", include_link: true } },
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
    } finally {
      setSaving(false);
    }
  };

  const goNext = () => setStep(AGENT_WIZARD_STEPS[Math.min(currentStepIndex + 1, AGENT_WIZARD_STEPS.length - 1)].key);
  const goBack = () => setStep(AGENT_WIZARD_STEPS[Math.max(currentStepIndex - 1, 0)].key);
  const toggleServer = (id: number) => setSelectedServers((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  const hasAllServersSelected = allServerIds.length > 0 && allServerIds.every((id) => selectedServers.includes(id));
  const selectAll = () => setSelectedServers(hasAllServersSelected ? [] : allServerIds);
  const setScheduleMode = (modeValue: AgentScheduleMode) => {
    const nextInterval = modeValue === "interval" ? (schedule || scheduleConfig.interval_minutes || 60) : 0;
    setSchedule(nextInterval);
    setScheduleConfig(finalizeScheduleConfig({ ...scheduleConfig, mode: modeValue, interval_minutes: nextInterval }, nextInterval));
  };
  const updateSchedule = (patch: Partial<AgentScheduleConfig>) => setScheduleConfig((current) => finalizeScheduleConfig({ ...current, ...patch }, schedule));
  const toggleWeekday = (day: number) => {
    setScheduleConfig((current) => {
      const currentDays = current.weekdays || [];
      const weekdays = currentDays.includes(day) ? currentDays.filter((item) => item !== day) : [...currentDays, day].sort();
      return finalizeScheduleConfig({ ...current, weekdays: weekdays.length ? weekdays : [day] }, schedule);
    });
  };
  const toggleSkill = (slug: string) => setSelectedSkillSlugs((current) => current.includes(slug) ? current.filter((item) => item !== slug) : [...current, slug]);
  const updateArtifact = (index: number, patch: Partial<AgentInputArtifact>) => setInputArtifacts((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  const addArtifact = (kind: AgentInputArtifact["kind"]) => {
    const labels = { document: localize(lang, "Документ", "Document"), task_list: localize(lang, "Список задач", "Task list"), script: localize(lang, "Скрипт", "Script") };
    const artifact: AgentInputArtifact = kind === "task_list"
      ? { kind, name: labels[kind], content: "", run_hint: "", tasks: [{ title: "", details: "", done: false }] }
      : { kind, name: labels[kind], content: "", run_hint: "" };
    const next = [...inputArtifacts, artifact].slice(0, 10);
    setInputArtifacts(next);
    setActiveArtifactIndex(next.length - 1);
  };
  const removeArtifact = (index: number) => {
    setInputArtifacts((current) => current.filter((_, itemIndex) => itemIndex !== index));
    setActiveArtifactIndex((current) => current === index ? null : current !== null && current > index ? current - 1 : current);
  };
  const updateArtifactTask = (artifactIndex: number, taskIndex: number, patch: Partial<AgentTaskDraft>) => {
    setInputArtifacts((current) => current.map((artifact, index) => {
      if (index !== artifactIndex) return artifact;
      const tasks = artifact.tasks?.length ? artifact.tasks : [{ title: "", details: "", done: false }];
      return { ...artifact, tasks: tasks.map((task, itemIndex) => itemIndex === taskIndex ? { ...task, ...patch } : task) };
    }));
  };
  const addArtifactTask = (artifactIndex: number) => setInputArtifacts((current) => current.map((artifact, index) => index === artifactIndex ? { ...artifact, tasks: [...(artifact.tasks || []), { title: "", details: "", done: false }] } : artifact));
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
      const kind: AgentInputArtifact["kind"] = file.name.toLowerCase().match(/\.(sh|py|js|ts|sql|ps1)$/) ? "script" : "document";
      added.push({ kind, name: file.name, source_name: file.name, size_bytes: file.size, content: content.slice(0, 12_000), run_hint: "" });
    }
    const next = [...inputArtifacts, ...added].slice(0, 10);
    setInputArtifacts(next);
    if (added.length) setActiveArtifactIndex(Math.min(inputArtifacts.length, next.length - 1));
  };

  const summaryRows = [
    { icon: Tag, label: localize(lang, "Название", "Name"), value: name || localize(lang, "Новый агент", "New agent") },
    { icon: Layers, label: localize(lang, "Тип", "Type"), value: agentModeLabel(mode, lang) },
    { icon: Server, label: localize(lang, "Серверы", "Servers"), value: selectedServers.length ? localize(lang, `${selectedServers.length} выбрано`, `${selectedServers.length} selected`) : localize(lang, "Не выбраны", "Not selected") },
    { icon: Shield, label: localize(lang, "Права запуска", "Run access"), value: localize(lang, sudoAgentOption(sudoPolicy).labelRu, sudoAgentOption(sudoPolicy).labelEn) },
  ];
  const enabledToolCount = Object.values(toolsConfig).filter(Boolean).length;
  const visibleSkills = skillsExpanded ? availableSkills : availableSkills.slice(0, 4);

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
      <DialogContent className="max-h-[calc(100vh-32px)] max-w-[min(1420px,calc(100vw-32px))] rounded-lg border-primary/10 bg-card/95 p-0 shadow-[0_24px_90px_hsl(var(--background)_/_0.72)]">
        <DialogHeader className="px-6 py-5">
          <div className="flex items-start gap-4 pr-12">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/15 text-primary shadow-[0_0_28px_hsl(var(--primary)_/_0.16)]">
              <Bot className="h-6 w-6" />
            </span>
            <div className="min-w-0">
              <DialogTitle className="text-xl">{isEditing ? localize(lang, "Редактирование агента", "Edit agent") : localize(lang, "Создание агента", "Create agent")}</DialogTitle>
              <DialogDescription>{localize(lang, "Настройте поведение, окружения, возможности и запуск.", "Configure behavior, targets, capabilities, and launch.")}</DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="border-b border-border/70 bg-secondary/10 px-6 py-4">
          <div className="grid gap-3 md:grid-cols-5">
            {AGENT_WIZARD_STEPS.map((item, index) => {
              const Icon = item.icon;
              const active = item.key === step;
              const complete = index < currentStepIndex;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setStep(item.key)}
                  className={`flex min-h-[58px] items-center gap-3 rounded-lg border px-3 text-left transition-colors ${
                    active ? "border-primary/80 bg-primary/10 text-foreground" : complete ? "border-primary/25 bg-secondary/30 text-foreground hover:border-primary/50" : "border-border/60 bg-background/20 text-muted-foreground hover:border-primary/35 hover:text-foreground"
                  }`}
                >
                  <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-sm font-semibold ${active || complete ? "border-primary bg-primary/15 text-primary" : "border-border/80 bg-secondary/30"}`}>
                    {complete ? <CheckCircle2 className="h-4 w-4" /> : active ? index + 1 : <Icon className="h-4 w-4" />}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold">{localize(lang, item.labelRu, item.labelEn)}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">{localize(lang, item.detailRu, item.detailEn)}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <DialogBody className="max-h-[calc(100vh-250px)] overflow-y-auto px-6 py-4">
          <div className={step === "template" ? "space-y-4" : "grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]"}>
            <div className="space-y-4">
              {step === "template" && (
                <>
                  <section className="rounded-lg border border-border/70 bg-secondary/15 p-4">
                    <h3 className="mb-4 text-lg font-semibold text-foreground">{localize(lang, "Тип агента", "Agent type")}</h3>
                    <div className="grid gap-3 md:grid-cols-3">
                      {[
                        { key: "mini" as const, icon: Zap, label: localize(lang, "Mini-агент", "Mini Agent"), text: localize(lang, "Команды и краткий разбор", "Commands and short analysis") },
                        { key: "full" as const, icon: Brain, label: localize(lang, "Полный агент", "Full Agent"), text: localize(lang, "Цель, инструменты и проверки", "Goal, tools, and checks") },
                        { key: "multi" as const, icon: Layers, label: "Pipeline", text: localize(lang, "Несколько агентов и серверов", "Multiple agents and servers") },
                      ].map((item) => {
                        const Icon = item.icon;
                        const active = mode === item.key;
                        return (
                          <button key={item.key} type="button" aria-pressed={active} onClick={() => setMode(item.key)} className={`min-h-[92px] rounded-lg border p-4 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/70 bg-background/30 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                            <span className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 bg-secondary/50 text-primary"><Icon className="h-4 w-4" /></span>
                            <span className="block text-sm font-semibold">{item.label}</span>
                            <span className="mt-1 block text-xs text-muted-foreground">{item.text}</span>
                          </button>
                        );
                      })}
                    </div>
                  </section>

                  <section className="rounded-lg border border-border/70 bg-secondary/15 p-4">
                    <div className="mb-4">
                      <h3 className="text-lg font-semibold text-foreground">{localize(lang, "Шаблон", "Template")}</h3>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      <button
                        type="button"
                        onClick={() => { setSelectedType("custom"); setStep("basics"); }}
                        className="min-h-[104px] rounded-lg border border-dashed border-primary/35 bg-primary/5 p-4 text-left transition-colors hover:border-primary/60 hover:bg-primary/10"
                      >
                        <div className="mb-3 flex items-center gap-3">
                          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                            <Settings2 className="h-4 w-4" />
                          </span>
                          <span className="min-w-0 truncate text-sm font-semibold text-foreground">{localize(lang, "Вручную", "Custom")}</span>
                        </div>
                        <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">
                          {localize(lang, "Создать агента без шаблона", "Create an agent without a template")}
                        </p>
                      </button>
                      {templates.map((tpl) => {
                        const TemplateIcon = AGENT_ICONS[tpl.type] || Settings2;
                        return (
                          <button key={tpl.type} type="button" onClick={() => onSelectTemplate(tpl)} className="min-h-[104px] rounded-lg border border-border/70 bg-background/30 p-4 text-left transition-colors hover:border-primary/50 hover:bg-primary/5">
                            <div className="mb-3 flex items-center gap-3">
                              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-secondary/50 text-primary"><TemplateIcon className="h-4 w-4" /></span>
                              <span className="min-w-0 truncate text-sm font-semibold text-foreground">{tpl.name}</span>
                            </div>
                            <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">{tpl.mode === "full" ? (tpl.goal || localize(lang, "Автономная OPS-задача", "Autonomous OPS task")) : localize(lang, `${tpl.command_count} команд`, `${tpl.command_count} commands`)}</p>
                          </button>
                        );
                      })}
                    </div>
                  </section>
                </>
              )}

              {step === "basics" && (
                <section className="space-y-4 rounded-lg border border-border/70 bg-secondary/15 p-4">
                  <h3 className="text-lg font-semibold text-foreground">{localize(lang, "Основные настройки", "Basics")}</h3>
                  <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
                    <label className="pt-2 text-sm font-medium text-muted-foreground">{localize(lang, "Название агента", "Agent name")} <span className="text-primary">*</span></label>
                    <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={localize(lang, "Анализ логов", "Log analysis")} className="h-10 bg-background/60" />
                  </div>
                  {mode === "mini" ? (
                    <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
                      <label className="pt-2 text-sm font-medium text-muted-foreground">{t("agent.commands_label")} <span className="text-primary">*</span></label>
                      <Textarea value={commands} onChange={(e) => setCommands(e.target.value)} rows={7} className="bg-background/60 font-mono text-xs" placeholder={"hostname\nuptime\nfree -m"} />
                    </div>
                  ) : (
                    <>
                      <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
                        <label className="pt-2 text-sm font-medium text-muted-foreground">{localize(lang, "Цель", "Goal")}</label>
                        <Textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} className="bg-background/60 text-sm" />
                      </div>
                      <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
                        <label className="pt-2 text-sm font-medium text-muted-foreground">{localize(lang, "Системные инструкции", "System instructions")}</label>
                        <Textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={3} className="bg-background/60 text-sm" />
                      </div>
                      <div className="grid gap-3 lg:grid-cols-3 lg:pl-[236px]">
                        <Input type="number" min={1} max={100} value={maxIter} onChange={(e) => setMaxIter(Number(e.target.value))} className="h-10 bg-background/60" aria-label={localize(lang, "Максимум итераций", "Max iterations")} />
                        <Input type="number" min={30} max={3600} value={sessionTimeoutSeconds} onChange={(e) => setSessionTimeoutSeconds(Number(e.target.value))} className="h-10 bg-background/60" aria-label={localize(lang, "Таймаут сессии", "Session timeout")} />
                        <Input type="number" min={1} max={10} value={maxConnections} onChange={(e) => setMaxConnections(Number(e.target.value))} className="h-10 bg-background/60" aria-label={localize(lang, "Максимум подключений", "Max connections")} />
                      </div>
                    </>
                  )}
                  <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
                    <label className="pt-2 text-sm font-medium text-muted-foreground">{localize(lang, "Инструкции к анализу", "Analysis instructions")}</label>
                    <Textarea value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} rows={4} className="bg-background/60 text-sm" />
                  </div>
                  <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
                    <label className="pt-2 text-sm font-medium text-muted-foreground">{localize(lang, "Права запуска", "Run access")}</label>
                    <div className="grid gap-3 md:grid-cols-3">
                      {SUDO_AGENT_OPTIONS.map((option) => {
                        const active = sudoPolicy === option.value;
                        return (
                          <button key={option.value} type="button" aria-pressed={active} onClick={() => setSudoPolicy(option.value)} className={`min-h-[76px] rounded-lg border p-3 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/70 bg-background/30 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                            <Shield className="mb-2 h-4 w-4 text-primary" />
                            <span className="block text-sm font-semibold">{localize(lang, option.labelRu, option.labelEn)}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </section>
              )}

              {step === "servers" && (
                <section className="space-y-4 rounded-lg border border-border/70 bg-secondary/15 p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <h3 className="text-lg font-semibold text-foreground">{localize(lang, "Выбор серверов", "Server selection")}</h3>
                    <button type="button" onClick={selectAll} className={`min-h-9 rounded-md border px-3 text-sm font-semibold transition-colors ${hasAllServersSelected ? "border-primary bg-primary/10 text-primary" : "border-border/70 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>{hasAllServersSelected ? localize(lang, "Снять выбор", "Clear") : localize(lang, "Выбрать все", "Select all")}</button>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    {servers.map((server) => {
                      const active = selectedServers.includes(server.id);
                      return (
                        <button key={server.id} type="button" aria-pressed={active} onClick={() => toggleServer(server.id)} className={`flex min-h-[64px] items-center gap-3 rounded-lg border p-3 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/70 bg-background/30 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-secondary/50 text-muted-foreground"><Server className="h-4 w-4" /></span>
                          <span className="min-w-0 flex-1 truncate text-sm font-semibold">{server.name}</span>
                          {active && <CheckCircle2 className="h-5 w-5 shrink-0 text-primary" />}
                        </button>
                      );
                    })}
                  </div>
                  <div className="space-y-4 rounded-lg border border-border/70 bg-background/25 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground"><CalendarDays className="h-4 w-4 text-primary" /> {t("agent.schedule")}</h4>
                      <span className="rounded-md border border-primary/25 bg-primary/10 px-2 py-1 text-xs font-semibold text-primary">{formatScheduleConfigLabel(scheduleConfig, schedule, lang)}</span>
                    </div>
                    <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
                      {SCHEDULE_MODES.map((option) => {
                        const active = scheduleConfig.mode === option.mode;
                        return (
                          <button key={option.mode} type="button" aria-pressed={active} onClick={() => setScheduleMode(option.mode)} className={`min-h-[76px] rounded-lg border p-3 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/70 bg-background/30 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                            <span className="block text-sm font-semibold">{localize(lang, option.labelRu, option.labelEn)}</span>
                            <span className="mt-1 block text-[11px] text-muted-foreground">{localize(lang, option.hintRu, option.hintEn)}</span>
                          </button>
                        );
                      })}
                    </div>
                    {scheduleConfig.mode === "interval" && (
                      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_150px]">
                        <div className="grid gap-2 sm:grid-cols-4">
                          {SCHEDULE_PRESETS.filter((option) => option.minutes > 0).map((option) => (
                            <button key={option.minutes} type="button" aria-pressed={schedule === option.minutes} onClick={() => { setSchedule(option.minutes); setScheduleConfig(finalizeScheduleConfig({ ...scheduleConfig, mode: "interval", interval_minutes: option.minutes }, option.minutes)); }} className={`min-h-10 rounded-md border px-3 text-sm font-semibold transition-colors ${schedule === option.minutes ? "border-primary bg-primary/10 text-primary" : "border-border/70 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                              {localize(lang, option.labelRu, option.labelEn)}
                            </button>
                          ))}
                        </div>
                        <Input type="number" min={1} max={10080} step={5} value={schedule || scheduleConfig.interval_minutes || 60} onChange={(e) => { const value = Math.max(1, Number(e.target.value) || 1); setSchedule(value); setScheduleConfig(finalizeScheduleConfig({ ...scheduleConfig, mode: "interval", interval_minutes: value }, value)); }} className="h-10 bg-background/60" aria-label={localize(lang, "Интервал запуска в минутах", "Run interval in minutes")} />
                      </div>
                    )}
                    {(["daily", "weekly", "monthly"] as AgentScheduleMode[]).includes(scheduleConfig.mode) && (
                      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
                        <div className="flex flex-wrap gap-2">
                          {QUICK_TIMES.map((timeValue) => (
                            <button key={timeValue} type="button" onClick={() => updateSchedule({ time: timeValue })} className={`min-h-9 rounded-md border px-3 text-xs font-semibold transition-colors ${scheduleConfig.time === timeValue ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>{timeValue}</button>
                          ))}
                        </div>
                        <Input type="time" value={scheduleConfig.time || "09:00"} onChange={(e) => updateSchedule({ time: e.target.value })} className="h-9 bg-background/60" />
                      </div>
                    )}
                    {scheduleConfig.mode === "weekly" && (
                      <div className="flex flex-wrap gap-2">
                        {WEEKDAYS.map((day) => {
                          const active = (scheduleConfig.weekdays || []).includes(day.value);
                          return <button key={day.value} type="button" aria-pressed={active} onClick={() => toggleWeekday(day.value)} className={`min-h-9 rounded-md border px-3 text-xs font-semibold transition-colors ${active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>{localize(lang, day.ru, day.en)}</button>;
                        })}
                      </div>
                    )}
                    {scheduleConfig.mode === "monthly" && <Input type="number" min={1} max={31} value={scheduleConfig.day_of_month || 1} onChange={(e) => updateSchedule({ day_of_month: Math.min(31, Math.max(1, Number(e.target.value) || 1)) })} className="h-9 max-w-32 bg-background/60" />}
                    {scheduleConfig.mode === "once" && <Input type="datetime-local" value={scheduleConfig.run_at || ""} onChange={(e) => updateSchedule({ run_at: e.target.value })} className="h-9 max-w-64 bg-background/60" />}
                  </div>
                </section>
              )}

              {step === "capabilities" && (
                <section className="space-y-4 rounded-lg border border-border/70 bg-secondary/15 p-4">
                  <h3 className="text-lg font-semibold text-foreground">{localize(lang, "Возможности", "Capabilities")}</h3>
                  {(mode === "full" || mode === "multi") && (
                    <div className="space-y-3 rounded-lg border border-border/70 bg-background/25 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <h4 className="text-sm font-semibold text-foreground">{localize(lang, "Доступ к инструментам", "Tool access")}</h4>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {localize(lang, `${enabledToolCount} из ${FULL_AGENT_TOOL_OPTIONS.length} включено`, `${enabledToolCount} of ${FULL_AGENT_TOOL_OPTIONS.length} enabled`)}
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <button type="button" className="min-h-8 rounded-md px-2 text-xs font-semibold text-primary transition-colors hover:bg-primary/10" onClick={() => setToolsConfig(buildDefaultToolsConfig())}>{localize(lang, "Включить все", "Enable all")}</button>
                          <button type="button" className="min-h-8 rounded-md border border-border/70 px-3 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground" onClick={() => setToolsExpanded((current) => !current)}>
                            {toolsExpanded ? localize(lang, "Свернуть", "Collapse") : localize(lang, "Развернуть", "Expand")}
                          </button>
                        </div>
                      </div>
                      {toolsExpanded && (
                        <>
                          <div className="grid gap-2 md:grid-cols-2">
                            {FULL_AGENT_TOOL_OPTIONS.map((tool) => (
                              <label key={tool.key} className="flex min-h-10 items-center gap-2 rounded-md border border-border/70 bg-background/35 px-3 text-xs text-muted-foreground">
                                <input type="checkbox" checked={Boolean(toolsConfig[tool.key])} onChange={(event) => setToolsConfig((current) => ({ ...current, [tool.key]: event.target.checked }))} />
                                {tool.label}
                              </label>
                            ))}
                          </div>
                          <Textarea value={stopConditionsText} onChange={(e) => setStopConditionsText(e.target.value)} rows={3} className="bg-background/60 text-xs" placeholder={localize(lang, "Условия остановки", "Stop conditions")} />
                        </>
                      )}
                    </div>
                  )}
                  <div className="space-y-3 rounded-lg border border-border/70 bg-background/25 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground"><BookOpen className="h-4 w-4 text-primary" /> {localize(lang, "Скиллы агента", "Agent skills")}</h4>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {localize(lang, `${selectedSkillSlugs.length} выбрано · ${availableSkills.length} доступно`, `${selectedSkillSlugs.length} selected · ${availableSkills.length} available`)}
                        </p>
                      </div>
                      {availableSkills.length > 4 && (
                        <button type="button" className="min-h-8 shrink-0 rounded-md border border-border/70 px-3 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground" onClick={() => setSkillsExpanded((current) => !current)}>
                          {skillsExpanded ? localize(lang, "Свернуть", "Collapse") : localize(lang, "Показать все", "Show all")}
                        </button>
                      )}
                    </div>
                    {availableSkills.length ? (
                      <div className="grid gap-2 md:grid-cols-2">
                        {visibleSkills.map((skill) => {
                          const active = selectedSkillSlugs.includes(skill.slug);
                          return (
                            <button key={skill.slug} type="button" aria-pressed={active} onClick={() => toggleSkill(skill.slug)} className={`min-h-[58px] rounded-lg border px-3 py-2 text-left transition-colors ${active ? "border-primary bg-primary/10 text-foreground" : "border-border/70 bg-background/35 text-muted-foreground hover:border-primary/40 hover:text-foreground"}`}>
                              <span className="block truncate text-xs font-semibold">{skill.name}</span>
                              <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{skill.service || skill.category || skill.slug}</span>
                            </button>
                          );
                        })}
                      </div>
                    ) : <div className="rounded-lg border border-dashed border-border/70 px-3 py-3 text-xs text-muted-foreground">{localize(lang, "Доступных скиллов пока нет.", "No available skills yet.")}</div>}
                  </div>
                  <div className="space-y-3 rounded-lg border border-border/70 bg-background/25 p-4">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground"><Upload className="h-4 w-4 text-primary" /> {localize(lang, "Материалы агента", "Agent materials")}</h4>
                      <div className="flex flex-wrap gap-2">
                        <label className="inline-flex min-h-8 cursor-pointer items-center rounded-md border border-primary/40 bg-primary/10 px-2 text-xs font-semibold text-primary transition-colors hover:bg-primary/15">
                          <Upload className="mr-1 h-3 w-3" /> {localize(lang, "Файл", "File")}
                          <input type="file" multiple className="hidden" accept=".txt,.md,.csv,.json,.yaml,.yml,.sh,.py,.js,.ts,.sql,.log,.ps1" onChange={(e) => { void onMaterialFiles(e.currentTarget.files); e.currentTarget.value = ""; }} />
                        </label>
                        <button type="button" onClick={() => addArtifact("document")} className="min-h-8 rounded-md border border-border px-2 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"><FileText className="mr-1 inline h-3 w-3" /> {localize(lang, "Документ", "Document")}</button>
                        <button type="button" onClick={() => addArtifact("script")} className="min-h-8 rounded-md border border-border px-2 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"><FileCode2 className="mr-1 inline h-3 w-3" /> {localize(lang, "Скрипт", "Script")}</button>
                        <button type="button" onClick={() => addArtifact("task_list")} className="min-h-8 rounded-md border border-border px-2 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"><ListChecks className="mr-1 inline h-3 w-3" /> {localize(lang, "Задачи", "Tasks")}</button>
                      </div>
                    </div>
                    {inputArtifacts.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-border/70 px-3 py-4 text-xs text-muted-foreground">{localize(lang, "Материалы не добавлены.", "No materials added.")}</div>
                    ) : (
                      <div className="grid gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.35fr)]">
                        <div className="space-y-2">
                          {inputArtifacts.map((artifact, index) => {
                            const KindIcon = artifactKindIcon(artifact.kind);
                            const active = activeArtifactIndex === index;
                            return (
                              <div key={`${artifact.kind}-${index}-${artifact.name}`} className={`rounded-lg border p-3 transition-colors ${active ? "border-primary bg-primary/10" : "border-border/70 bg-background/35"}`}>
                                <div className="flex items-start gap-3">
                                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-secondary/40 text-primary"><KindIcon className="h-4 w-4" /></span>
                                  <div className="min-w-0 flex-1">
                                    <div className="truncate text-xs font-semibold text-foreground">{artifact.name || artifactKindLabel(artifact.kind, lang)}</div>
                                    <div className="mt-0.5 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground"><span>{artifactKindLabel(artifact.kind, lang)}</span><span>{artifactSummary(artifact, lang)}</span></div>
                                  </div>
                                </div>
                                <div className="mt-3 flex items-center justify-end gap-2">
                                  <Button type="button" size="xs" variant={active ? "default" : "outline"} className="gap-1" onClick={() => setActiveArtifactIndex(index)}><Eye className="h-3 w-3" /> {localize(lang, "Открыть", "Open")}</Button>
                                  <Button type="button" size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground" onClick={() => removeArtifact(index)} aria-label={localize(lang, "Удалить материал", "Remove material")}><Trash2 className="h-3.5 w-3.5" /></Button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                        {activeArtifact && activeArtifactIndex !== null ? (
                          <div className="space-y-3 rounded-lg border border-border/70 bg-background/35 p-3">
                            <div className="grid gap-2 sm:grid-cols-[140px_1fr]">
                              <select value={activeArtifact.kind} onChange={(e) => {
                                const nextKind = e.target.value as AgentInputArtifact["kind"];
                                const nextTasks = nextKind === "task_list" ? (activeArtifact.tasks?.length ? activeArtifact.tasks : parseTasksFromContent(activeArtifact.content || "")) : undefined;
                                updateArtifact(activeArtifactIndex, { kind: nextKind, tasks: nextKind === "task_list" ? (nextTasks?.length ? nextTasks : [{ title: "", details: "", done: false }]) : undefined, content: nextKind === "task_list" ? activeArtifact.content : activeArtifact.content || tasksToContent(activeArtifact.tasks) });
                              }} className="h-9 rounded-md border border-border bg-secondary/50 px-2 text-xs text-foreground">
                                {ARTIFACT_KINDS.map((item) => <option key={item.kind} value={item.kind}>{localize(lang, item.labelRu, item.labelEn)}</option>)}
                              </select>
                              <Input value={activeArtifact.name} onChange={(e) => updateArtifact(activeArtifactIndex, { name: e.target.value })} className="h-9 bg-secondary/50 text-sm" />
                            </div>
                            {activeArtifact.kind === "task_list" ? (
                              <div className="space-y-2">
                                {(activeArtifact.tasks?.length ? activeArtifact.tasks : [{ title: "", details: "", done: false }]).map((task, taskIndex) => (
                                  <div key={taskIndex} className="rounded-lg border border-border/60 bg-secondary/20 p-2">
                                    <div className="grid gap-2 sm:grid-cols-[auto_1fr_auto] sm:items-center">
                                      <input type="checkbox" checked={Boolean(task.done)} onChange={(e) => updateArtifactTask(activeArtifactIndex, taskIndex, { done: e.target.checked })} className="rounded" aria-label={localize(lang, "Задача выполнена", "Task done")} />
                                      <Input value={task.title} onChange={(e) => updateArtifactTask(activeArtifactIndex, taskIndex, { title: e.target.value })} className="h-8 bg-background/60 text-xs" placeholder={localize(lang, "Название задачи", "Task title")} />
                                      <Button type="button" size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground" onClick={() => removeArtifactTask(activeArtifactIndex, taskIndex)} aria-label={localize(lang, "Удалить задачу", "Remove task")}><X className="h-3.5 w-3.5" /></Button>
                                    </div>
                                    <Textarea value={task.details || ""} onChange={(e) => updateArtifactTask(activeArtifactIndex, taskIndex, { details: e.target.value })} rows={2} className="mt-2 bg-background/60 text-xs" />
                                  </div>
                                ))}
                                <Button type="button" size="sm" variant="outline" className="w-full gap-1" onClick={() => addArtifactTask(activeArtifactIndex)}><Plus className="h-3.5 w-3.5" /> {localize(lang, "Добавить задачу", "Add task")}</Button>
                              </div>
                            ) : <Textarea value={activeArtifact.content} onChange={(e) => updateArtifact(activeArtifactIndex, { content: e.target.value })} rows={activeArtifact.kind === "script" ? 10 : 8} className={`bg-secondary/50 text-xs ${activeArtifact.kind === "script" ? "font-mono" : ""}`} />}
                          </div>
                        ) : <div className="flex min-h-[180px] items-center justify-center rounded-lg border border-dashed border-border/70 px-4 py-6 text-center text-xs text-muted-foreground">{localize(lang, "Выберите материал слева.", "Select a material on the left.")}</div>}
                      </div>
                    )}
                  </div>
                  <div className="rounded-lg border border-border/70 bg-background/25 p-4">
                    <label className="flex cursor-pointer items-center gap-3">
                      <input type="checkbox" checked={telegramEnabled} onChange={(e) => setTelegramEnabled(e.target.checked)} className="rounded" />
                      <span className="flex items-center gap-2 text-sm font-semibold text-foreground"><Send className="h-4 w-4 text-primary" /> {localize(lang, "Отправлять отчет в Telegram", "Send report to Telegram")}</span>
                    </label>
                    {telegramEnabled && <Input value={telegramChatId} onChange={(e) => setTelegramChatId(e.target.value)} className="mt-3 h-9 bg-background/60 text-sm" placeholder="Chat ID" />}
                  </div>
                </section>
              )}

              {step === "review" && (
                <section className="space-y-4 rounded-lg border border-border/70 bg-secondary/15 p-4">
                  <h3 className="text-lg font-semibold text-foreground">{localize(lang, "Обзор", "Review")}</h3>
                  <div className="grid gap-3 md:grid-cols-2">
                    {summaryRows.map((row) => {
                      const Icon = row.icon;
                      return (
                        <div key={row.label} className="rounded-lg border border-border/70 bg-background/30 p-4">
                          <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 bg-secondary/50 text-primary"><Icon className="h-4 w-4" /></div>
                          <div className="text-xs text-muted-foreground">{row.label}</div>
                          <div className="mt-1 text-sm font-semibold text-foreground">{row.value}</div>
                        </div>
                      );
                    })}
                  </div>
                  <div className="rounded-lg border border-border/70 bg-background/30 p-4">
                    <div className="grid gap-3 text-sm md:grid-cols-4">
                      <div><span className="block text-xs text-muted-foreground">{localize(lang, "Команды", "Commands")}</span><strong>{commandCount}</strong></div>
                      <div><span className="block text-xs text-muted-foreground">{localize(lang, "Скиллы", "Skills")}</span><strong>{selectedSkillSlugs.length}</strong></div>
                      <div><span className="block text-xs text-muted-foreground">{localize(lang, "Материалы", "Materials")}</span><strong>{inputArtifacts.length}</strong></div>
                      <div><span className="block text-xs text-muted-foreground">Telegram</span><strong>{telegramEnabled ? localize(lang, "Да", "Yes") : localize(lang, "Нет", "No")}</strong></div>
                    </div>
                  </div>
                </section>
              )}
            </div>

            {step !== "template" && (
              <aside className="space-y-4">
                <section className="rounded-lg border border-border/70 bg-secondary/20 p-4">
                  <h3 className="mb-4 text-base font-semibold text-foreground">{localize(lang, "Краткий обзор", "Quick summary")}</h3>
                  <div className="space-y-4">
                    {summaryRows.map((row) => {
                      const Icon = row.icon;
                      return (
                        <div key={row.label} className="flex gap-3">
                          <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                          <div className="min-w-0">
                            <div className="text-xs text-muted-foreground">{row.label}</div>
                            <div className="truncate text-sm text-foreground">{row.value}</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </section>
              </aside>
            )}
          </div>
        </DialogBody>

        <DialogFooter className="items-center justify-between gap-3 px-6 py-4 sm:flex-row">
          <Button size="sm" variant="outline" className="min-w-28 gap-2" onClick={currentStepIndex === 0 ? onClose : goBack}>
            <ArrowLeft className="h-4 w-4" /> {currentStepIndex === 0 ? localize(lang, "Отмена", "Cancel") : t("agent.back")}
          </Button>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" className="min-w-44 gap-2" onClick={onSave} disabled={saving || !canSave}>
              <Save className="h-4 w-4" /> {saving ? localize(lang, "Сохраняем...", "Saving...") : localize(lang, "Сохранить", "Save")}
            </Button>
            {step === "review" ? (
              <Button size="sm" className="min-w-36 gap-2" onClick={onSave} disabled={saving || !canSave}>
                {saving ? localize(lang, "Сохраняем...", "Saving...") : isEditing ? localize(lang, "Сохранить", "Save") : t("agent.create")}
              </Button>
            ) : (
              <Button size="sm" className="min-w-32 gap-2" onClick={goNext}>
                {localize(lang, "Далее", "Next")} <ArrowRight className="h-4 w-4" />
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
