import type { AgentItem, AgentScheduleConfig, AgentScheduleMode } from "@/lib/api";
import { localize } from "@/lib/i18n";

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

export function isScheduleConfigValid(config: AgentScheduleConfig, intervalMinutes: number): boolean {
  if (config.mode === "manual") return true;
  if (config.mode === "interval") return Number(intervalMinutes || config.interval_minutes || 0) > 0;
  if (config.mode === "daily") return Boolean(config.time);
  if (config.mode === "weekly") return Boolean(config.time) && Boolean(config.weekdays?.length);
  if (config.mode === "monthly") return Boolean(config.time) && Number(config.day_of_month || 0) >= 1 && Number(config.day_of_month || 0) <= 31;
  if (config.mode === "once") return Boolean(config.run_at);
  return false;
}
