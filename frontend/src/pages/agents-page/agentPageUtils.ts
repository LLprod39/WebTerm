import {
  Activity,
  BookOpen,
  Brain,
  CheckCircle2,
  FileCode2,
  FileText,
  Layers,
  ListChecks,
  Server,
  Settings2,
  Shield,
  Tag,
  Zap,
  type LucideIcon,
} from "lucide-react";

import type {
  AgentInputArtifact,
  AgentItem,
  AgentScheduleConfig,
  AgentScheduleMode,
} from "@/lib/api";
import { localize } from "@/lib/i18n";

export function formatDuration(ms: number): string {
  if (!ms) return "—";
  if (ms < 1000) return `${ms}ms`;
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  return `${mins}m ${secs % 60}s`;
}

export const MODE_ICONS: Record<string, typeof Layers> = { mini: Zap, full: Brain, multi: Layers };

export function agentModeLabel(mode: "all" | "mini" | "full" | "multi" | string, lang: string) {
  if (mode === "all") return localize(lang, "Все", "All");
  if (mode === "mini") return localize(lang, "Мини", "Mini");
  if (mode === "full") return localize(lang, "Полный", "Full");
  if (mode === "multi") return localize(lang, "Пайплайн", "Pipeline");
  return mode;
}

export const AGENT_ICONS: Record<string, LucideIcon> = {
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

export const HIDDEN_AGENT_TEMPLATE_TYPES = new Set(["docker_status"]);

export const FULL_AGENT_TOOL_OPTIONS = [
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

export type AgentSudoPolicy = "disabled" | "ask" | "approved";

export const SUDO_AGENT_OPTIONS: Array<{
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

export function sudoAgentOption(value: string | undefined) {
  return SUDO_AGENT_OPTIONS.find((item) => item.value === value) || SUDO_AGENT_OPTIONS[0];
}

export const SCHEDULE_PRESETS = [
  { minutes: 0, labelRu: "Вручную", labelEn: "Manual", hintRu: "Только кнопкой запуска", hintEn: "Run only from button" },
  { minutes: 15, labelRu: "15 минут", labelEn: "15 minutes", hintRu: "Частый мониторинг", hintEn: "Frequent checks" },
  { minutes: 30, labelRu: "30 минут", labelEn: "30 minutes", hintRu: "Оперативные проверки", hintEn: "Operational checks" },
  { minutes: 60, labelRu: "1 час", labelEn: "1 hour", hintRu: "Стандартный режим", hintEn: "Standard cadence" },
  { minutes: 180, labelRu: "3 часа", labelEn: "3 hours", hintRu: "Периодический обзор", hintEn: "Periodic review" },
  { minutes: 360, labelRu: "6 часов", labelEn: "6 hours", hintRu: "Несколько раз в день", hintEn: "Several times a day" },
  { minutes: 720, labelRu: "12 часов", labelEn: "12 hours", hintRu: "Утро и вечер", hintEn: "Morning and evening" },
  { minutes: 1440, labelRu: "1 день", labelEn: "1 day", hintRu: "Ежедневная проверка", hintEn: "Daily check" },
] as const;

export const SCHEDULE_MODES: Array<{ mode: AgentScheduleMode; labelRu: string; labelEn: string; hintRu: string; hintEn: string }> = [
  { mode: "manual", labelRu: "Вручную", labelEn: "Manual", hintRu: "Только кнопкой", hintEn: "Button only" },
  { mode: "interval", labelRu: "Интервал", labelEn: "Interval", hintRu: "Каждые N минут", hintEn: "Every N minutes" },
  { mode: "daily", labelRu: "Ежедневно", labelEn: "Daily", hintRu: "В выбранное время", hintEn: "At selected time" },
  { mode: "weekly", labelRu: "По дням", labelEn: "Weekly", hintRu: "Дни недели", hintEn: "Weekdays" },
  { mode: "monthly", labelRu: "Месяц", labelEn: "Monthly", hintRu: "День месяца", hintEn: "Day of month" },
  { mode: "once", labelRu: "Разово", labelEn: "Once", hintRu: "Дата и время", hintEn: "Date and time" },
];

export const WEEKDAYS = [
  { value: 0, ru: "Пн", en: "Mon" },
  { value: 1, ru: "Вт", en: "Tue" },
  { value: 2, ru: "Ср", en: "Wed" },
  { value: 3, ru: "Чт", en: "Thu" },
  { value: 4, ru: "Пт", en: "Fri" },
  { value: 5, ru: "Сб", en: "Sat" },
  { value: 6, ru: "Вс", en: "Sun" },
] as const;

export const QUICK_TIMES = ["08:00", "09:00", "10:00", "18:00"] as const;

export const ARTIFACT_KINDS: Array<{ kind: AgentInputArtifact["kind"]; labelRu: string; labelEn: string; icon: LucideIcon }> = [
  { kind: "document", labelRu: "Документ", labelEn: "Document", icon: FileText },
  { kind: "task_list", labelRu: "Список задач", labelEn: "Task list", icon: CheckCircle2 },
  { kind: "script", labelRu: "Скрипт", labelEn: "Script", icon: FileCode2 },
];

export type AgentTaskDraft = NonNullable<AgentInputArtifact["tasks"]>[number];

export function artifactKindLabel(kind: AgentInputArtifact["kind"], lang: string) {
  const match = ARTIFACT_KINDS.find((item) => item.kind === kind);
  return match ? localize(lang, match.labelRu, match.labelEn) : kind;
}

export function artifactKindIcon(kind: AgentInputArtifact["kind"]) {
  return ARTIFACT_KINDS.find((item) => item.kind === kind)?.icon || FileText;
}

export function parseTasksFromContent(content: string): AgentTaskDraft[] {
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

export function tasksToContent(tasks: AgentTaskDraft[] | undefined): string {
  return (tasks || [])
    .filter((task) => task.title.trim() || (task.details || "").trim())
    .map((task) => {
      const details = (task.details || "").trim();
      return `- [${task.done ? "x" : " "}] ${task.title.trim()}${details ? ` — ${details}` : ""}`;
    })
    .join("\n");
}

export function normalizeArtifactDraft(item: AgentInputArtifact): AgentInputArtifact {
  if (item.kind !== "task_list") return item;
  const tasks = item.tasks?.length ? item.tasks : parseTasksFromContent(item.content || "");
  return { ...item, tasks };
}

export function prepareArtifactForSave(item: AgentInputArtifact): AgentInputArtifact {
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
    return { ...item, name, run_hint, tasks, content: tasksToContent(tasks) };
  }
  return { ...item, name, run_hint, content: item.content.trim() };
}

export function artifactSummary(item: AgentInputArtifact, lang: string) {
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

export function buildDefaultToolsConfig() {
  return Object.fromEntries(FULL_AGENT_TOOL_OPTIONS.map((tool) => [tool.key, true]));
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

export function formatRoleLabel(role: string): string {
  return role
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatScheduleLabel(minutes: number, lang: string): string {
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

export function defaultScheduleConfig(): AgentScheduleConfig {
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

export function scheduleConfigFromMinutes(minutes: number): AgentScheduleConfig {
  const base = defaultScheduleConfig();
  if (!minutes) return base;
  return { ...base, mode: "interval", interval_minutes: minutes };
}

export function deriveScheduleMinutes(config: AgentScheduleConfig): number {
  if (config.mode === "manual") return 0;
  if (config.mode === "interval") return Math.max(0, Number(config.interval_minutes || 0));
  if (config.mode === "daily") return 1440;
  if (config.mode === "weekly" || config.mode === "monthly") return 10080;
  if (config.mode === "once") return 1;
  return 0;
}

export function finalizeScheduleConfig(config: AgentScheduleConfig, intervalMinutes: number): AgentScheduleConfig {
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

export function formatScheduleConfigLabel(config: AgentScheduleConfig | undefined, minutes: number, lang: string): string {
  const current = config || scheduleConfigFromMinutes(minutes);
  if (current.mode === "manual") return localize(lang, "Только ручной запуск", "Manual only");
  if (current.mode === "interval") return formatScheduleLabel(Number(current.interval_minutes || minutes || 0), lang);
  if (current.mode === "daily") return localize(lang, `Каждый день в ${current.time || "09:00"}`, `Daily at ${current.time || "09:00"}`);
  if (current.mode === "weekly") return localize(lang, `По дням недели в ${current.time || "09:00"}`, `Weekly at ${current.time || "09:00"}`);
  if (current.mode === "monthly") return localize(lang, `${current.day_of_month || 1} числа в ${current.time || "09:00"}`, `Day ${current.day_of_month || 1} at ${current.time || "09:00"}`);
  if (current.mode === "once") return localize(lang, "Разовый запуск", "One-time run");
  return formatScheduleLabel(minutes, lang);
}

export function isAgentScheduled(agent: AgentItem): boolean {
  const mode = agent.schedule_config?.mode || (agent.schedule_minutes > 0 ? "interval" : "manual");
  return mode !== "manual";
}

export type AgentWizardStep = "template" | "basics" | "servers" | "capabilities" | "review";

export const AGENT_WIZARD_STEPS: Array<{
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
