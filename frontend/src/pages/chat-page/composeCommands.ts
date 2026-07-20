/** Catalog of slash commands for the Operator compose palette (Grok-style). */

export type SlashCommandKind = "send" | "insert" | "browse";

export type SlashCommandDef = {
  id: string;
  /** Shown after `/` */
  trigger: string;
  labelRu: string;
  labelEn: string;
  hintRu: string;
  hintEn: string;
  kind: SlashCommandKind;
  /** Nested browser for attach/pin without sending */
  browse?: "servers" | "users" | "agents";
  /** Build message when kind is send/insert */
  build?: (args: string) => string;
  /** Keywords for filter */
  keywords?: string[];
};

export const SLASH_COMMANDS: SlashCommandDef[] = [
  {
    id: "servers",
    trigger: "servers",
    labelRu: "Серверы",
    labelEn: "Servers",
    hintRu: "Посмотреть и прикрепить серверы к чату",
    hintEn: "Browse and pin servers to this chat",
    kind: "browse",
    browse: "servers",
    keywords: ["pin", "host", "ssh", "сервер"],
  },
  {
    id: "users",
    trigger: "users",
    labelRu: "Пользователи",
    labelEn: "Users",
    hintRu: "Посмотреть пользователей и прикрепить к контексту",
    hintEn: "Browse users and pin to context",
    kind: "browse",
    browse: "users",
    keywords: ["people", "operator", "юзер"],
  },
  {
    id: "agents",
    trigger: "agents",
    labelRu: "Агенты",
    labelEn: "Agents",
    hintRu: "Список агентов — вставить упоминание или спросить",
    hintEn: "List agents — insert mention or ask",
    kind: "browse",
    browse: "agents",
    keywords: ["bot", "агент"],
  },
  {
    id: "fleet",
    trigger: "fleet",
    labelRu: "Флот",
    labelEn: "Fleet",
    hintRu: "Статус флота, worst, прогнозы",
    hintEn: "Fleet status, worst hosts, forecasts",
    kind: "send",
    build: () => "Что с флотом? Покажи статус, worst-серверы и активные прогнозы.",
    keywords: ["status", "health"],
  },
  {
    id: "forecasts",
    trigger: "forecasts",
    labelRu: "Прогнозы",
    labelEn: "Forecasts",
    hintRu: "Активные прогнозы диска/памяти/cert",
    hintEn: "Active disk/memory/cert forecasts",
    kind: "send",
    build: () =>
      "Посмотри прогнозы по флоту (operator.server_forecasts). Если пусто — fleet_status. Ответ 1–2 строки, без длинных списков.",
  },
  {
    id: "alerts",
    trigger: "alerts",
    labelRu: "Алерты",
    labelEn: "Alerts",
    hintRu: "Последние алерты мониторинга",
    hintEn: "Recent monitoring alerts",
    kind: "send",
    build: () => "Покажи последние алерты мониторинга.",
  },
  {
    id: "briefing",
    trigger: "briefing",
    labelRu: "Брифинг",
    labelEn: "Briefing",
    hintRu: "Короткий операторский брифинг",
    hintEn: "Short operator briefing",
    kind: "send",
    build: () => "Сделай краткий операторский брифинг: алерты, прогнозы, худшие серверы.",
  },
  {
    id: "web",
    trigger: "web",
    labelRu: "Веб-поиск",
    labelEn: "Web research",
    hintRu: "Найти свежие публичные источники и дать ссылки",
    hintEn: "Find current public sources and include citations",
    kind: "send",
    build: (args) => {
      const query = args.trim();
      if (!query) return "Найди в интернете актуальные публичные источники по теме и дай ответ со ссылками.";
      return `Найди в интернете актуальные публичные источники по запросу: «${query}». Проверь источники и дай ответ со ссылками.`;
    },
    keywords: ["search", "internet", "источники", "поиск"],
  },
  {
    id: "run",
    trigger: "run",
    labelRu: "Команда",
    labelEn: "Run command",
    hintRu: "Вставить шаблон выполнения команды",
    hintEn: "Insert run-command template",
    kind: "insert",
    build: (args) => {
      const cmd = args.trim();
      if (!cmd) return "Выполни команду на привязанном сервере: `…`";
      return `Выполни команду на привязанном сервере: \`${cmd}\``;
    },
    keywords: ["cmd", "shell", "ssh"],
  },
  {
    id: "runbook",
    trigger: "runbook",
    labelRu: "Runbook",
    labelEn: "Runbook",
    hintRu: "Сохранить цепочку как runbook",
    hintEn: "Save chain as runbook",
    kind: "send",
    build: (args) => {
      const name = args.trim();
      if (!name) return "Сохрани последнюю успешную цепочку как runbook.";
      return `Сохрани успешную цепочку как runbook с названием «${name}».`;
    },
  },
  {
    id: "memory",
    trigger: "memory",
    labelRu: "Память",
    labelEn: "Memory",
    hintRu: "Память прикреплённого сервера",
    hintEn: "Memory of pinned server",
    kind: "send",
    build: () => "Покажи память прикреплённого сервера (инциденты, риски, привычки).",
  },
  {
    id: "metrics",
    trigger: "metrics",
    labelRu: "Метрики",
    labelEn: "Metrics",
    hintRu: "График CPU/памяти прикреплённого сервера",
    hintEn: "CPU/memory chart for pinned server",
    kind: "send",
    build: () => "Покажи метрики (cpu/memory/disk) прикреплённого сервера за последние часы.",
  },
];

export function filterSlashCommands(query: string, lang: "ru" | "en" = "ru"): SlashCommandDef[] {
  const q = query.trim().toLowerCase().replace(/^\//, "");
  if (!q) return SLASH_COMMANDS;
  return SLASH_COMMANDS.filter((cmd) => {
    const hay = [
      cmd.trigger,
      cmd.labelRu,
      cmd.labelEn,
      cmd.hintRu,
      cmd.hintEn,
      ...(cmd.keywords || []),
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(q) || cmd.trigger.startsWith(q);
  });
}

/** Detect `/query` or `@query` at the caret in the draft. */
export function detectComposeTrigger(
  text: string,
  caret: number,
): { type: "slash" | "mention"; query: string; start: number; end: number } | null {
  const before = text.slice(0, Math.max(0, caret));
  // Slash: from last whitespace or start
  const slashMatch = before.match(/(?:^|\s)(\/[^\s]*)$/);
  if (slashMatch) {
    const token = slashMatch[1];
    const start = before.length - token.length;
    return { type: "slash", query: token.slice(1), start, end: caret };
  }
  const atMatch = before.match(/(?:^|\s)(@[A-Za-z0-9._-]*)$/);
  if (atMatch) {
    const token = atMatch[1];
    const start = before.length - token.length;
    return { type: "mention", query: token.slice(1), start, end: caret };
  }
  return null;
}

export function replaceComposeRange(text: string, start: number, end: number, replacement: string): string {
  return text.slice(0, start) + replacement + text.slice(end);
}
