import { localize } from "./presentation";

export const CRON_PRESETS = [
  {
    id: "every_5_min",
    labelRu: "Каждые 5 минут",
    labelEn: "Every 5 minutes",
    descriptionRu: "Для частых health-check и быстрых проверок.",
    descriptionEn: "For frequent health checks and fast polling.",
    value: "*/5 * * * *",
  },
  {
    id: "hourly",
    labelRu: "Каждый час",
    labelEn: "Hourly",
    descriptionRu: "Запуск в начале каждого часа.",
    descriptionEn: "Runs at the top of every hour.",
    value: "0 * * * *",
  },
  {
    id: "daily",
    labelRu: "Каждый день",
    labelEn: "Daily",
    descriptionRu: "Один раз в день в выбранное время.",
    descriptionEn: "Runs once per day at the selected time.",
    value: "0 4 * * *",
  },
] as const;

function parseCronExpression(value: unknown): string[] | null {
  const parts = String(value || "").trim().split(/\s+/).filter(Boolean);
  return parts.length === 5 ? parts : null;
}

function padCronNumber(value: string) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? String(numeric).padStart(2, "0") : value;
}

export function getDailyTimeFromCron(value: unknown) {
  const parts = parseCronExpression(value);
  if (!parts || parts[2] !== "*" || parts[3] !== "*" || parts[4] !== "*") return "04:00";
  const [minute, hour] = parts;
  if (!/^\d+$/.test(minute) || !/^\d+$/.test(hour)) return "04:00";
  return `${padCronNumber(hour)}:${padCronNumber(minute)}`;
}

export function getMinuteIntervalFromCron(value: unknown) {
  const parts = parseCronExpression(value);
  if (!parts || parts[1] !== "*" || parts[2] !== "*" || parts[3] !== "*" || parts[4] !== "*") return 5;
  const match = parts[0].match(/^\*\/(\d+)$/);
  if (!match) return 5;
  return Math.max(1, Math.min(59, Number(match[1]) || 5));
}

export function dailyTimeToCron(value: string) {
  const [hour = "4", minute = "0"] = value.split(":");
  return `${Number(minute) || 0} ${Number(hour) || 0} * * *`;
}

export function describeCronExpression(value: unknown, lang: "en" | "ru") {
  const parts = parseCronExpression(value);
  if (!parts) {
    return localize(lang, "Расписание не настроено или cron заполнен неверно.", "Schedule is not set or the cron expression is invalid.");
  }
  const [minute, hour, day, month, weekday] = parts;
  if (/^\*\/\d+$/.test(minute) && hour === "*" && day === "*" && month === "*" && weekday === "*") {
    const interval = minute.replace("*/", "");
    return localize(lang, `Запуск каждые ${interval} мин.`, `Runs every ${interval} min.`);
  }
  if (minute === "0" && hour === "*" && day === "*" && month === "*" && weekday === "*") {
    return localize(lang, "Запуск каждый час в :00.", "Runs every hour at :00.");
  }
  if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && day === "*" && month === "*" && weekday === "*") {
    return localize(lang, `Запуск каждый день в ${padCronNumber(hour)}:${padCronNumber(minute)}.`, `Runs every day at ${padCronNumber(hour)}:${padCronNumber(minute)}.`);
  }
  if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && day === "*" && month === "*" && weekday === "1-5") {
    return localize(lang, `Запуск по будням в ${padCronNumber(hour)}:${padCronNumber(minute)}.`, `Runs on weekdays at ${padCronNumber(hour)}:${padCronNumber(minute)}.`);
  }
  return localize(lang, "Пользовательское cron-расписание.", "Custom cron schedule.");
}

export function getCronPresetId(value: unknown) {
  const cron = String(value || "").trim();
  return CRON_PRESETS.find((preset) => preset.value === cron)?.id || "custom";
}
