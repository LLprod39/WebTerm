import { localize } from "@/lib/i18n";

export function formatRelativeTime(value: string, lang = "en"): string {
  const diffMs = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(diffMs / 60_000));
  if (minutes < 60) return localize(lang, `${minutes} мин назад`, `${minutes}m ago`);
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return localize(lang, `${hours} ч назад`, `${hours}h ago`);
  const days = Math.floor(hours / 24);
  return localize(lang, `${days} д назад`, `${days}d ago`);
}

export function formatActivityLabel(label: string, lang: string): string {
  if (lang !== "ru") {
    return label;
  }
  const labels: Record<string, string> = {
    Active: "Активен",
    "Legacy graph": "Старый граф",
    "Manual ready": "Готов вручную",
    "No active trigger": "Нет триггера",
    Pending: "В очереди",
    Running: "Выполняется",
  };
  return labels[label] ?? label;
}

export function formatActivityDetail(detail: string, lang: string): string {
  if (lang !== "ru") {
    return detail;
  }
  const triggerTime = (value: string) =>
    value
      .replace(/(\d+)m ago/g, "$1 мин назад")
      .replace(/(\d+)h ago/g, "$1 ч назад")
      .replace(/(\d+)d ago/g, "$1 д назад");
  const replacements: Array<[RegExp, string | ((...groups: string[]) => string)]> = [
    [/^Run #(\d+) is executing now\.$/, (id) => `Запуск #${id} выполняется сейчас.`],
    [/^Run #(\d+) is queued and starting soon\.$/, (id) => `Запуск #${id} в очереди и скоро стартует.`],
    [/^This pipeline must be resaved as V2 before it can run again\.$/, "Нужно пересохранить пайплайн как V2 перед следующим запуском."],
    [/^Add a manual, webhook, schedule, or monitoring trigger to arm this pipeline\.$/, "Добавьте manual, webhook, расписание или monitoring-триггер, чтобы активировать пайплайн."],
    [/^Ready for one manual entry point\.$/, "Готов один ручной вход."],
    [/^Ready for (\d+) manual entry points\.$/, (count) => `Готово ручных входов: ${count}.`],
    [/^Waiting for webhook POST\.(?: Last trigger (.+)\.)?$/, (time) => `Ждет webhook POST.${time ? ` Последний триггер: ${triggerTime(time)}.` : ""}`],
    [/^Waiting for the schedule trigger\.(?: Last trigger (.+)\.)?$/, (time) => `Ждет запуск по расписанию.${time ? ` Последний триггер: ${triggerTime(time)}.` : ""}`],
    [/^Waiting for a monitoring alert\.(?: Last trigger (.+)\.)?$/, (time) => `Ждет monitoring alert.${time ? ` Последний триггер: ${triggerTime(time)}.` : ""}`],
    [/^Multiple trigger types are active: (.+)\.(?: Last trigger (.+)\.)?$/, (types, time) => `Активно несколько типов триггеров: ${types}.${time ? ` Последний триггер: ${triggerTime(time)}.` : ""}`],
  ];
  for (const [pattern, replacement] of replacements) {
    const match = detail.match(pattern);
    if (!match) {
      continue;
    }
    if (typeof replacement === "string") {
      return replacement;
    }
    return replacement(...match.slice(1));
  }
  return detail;
}
