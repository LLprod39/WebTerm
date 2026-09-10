import type { LucideIcon } from "lucide-react";
import {
  Bell,
  Bot,
  Boxes,
  Clock,
  Container,
  Copy,
  Cpu,
  FileSearch,
  FileText,
  FolderOpen,
  GitBranch,
  GitMerge,
  Globe,
  HardDrive,
  Mail,
  MessageCircle,
  Package,
  Play,
  ShieldCheck,
  Terminal,
  Timer,
  Trash2,
  Webhook,
  Wrench,
  Zap,
} from "lucide-react";
import type { NodeManifest, Values } from "@/api/automation";

export type NodeGroup =
  | "trigger"
  | "agent"
  | "logic"
  | "ops"
  | "output"
  | "default";

export interface CatalogEntry {
  type: string;
  title: string;
  description: string;
  icon: LucideIcon;
  group: NodeGroup;
}

const ENTRIES: CatalogEntry[] = [
  {
    type: "trigger/manual",
    title: "Ручной запуск",
    description: "Оператор запускает процесс из интерфейса",
    icon: Play,
    group: "trigger",
  },
  {
    type: "trigger/webhook",
    title: "Webhook",
    description: "Старт по HTTP POST запросу",
    icon: Webhook,
    group: "trigger",
  },
  {
    type: "trigger/schedule",
    title: "Расписание",
    description: "Запуск по cron-расписанию",
    icon: Clock,
    group: "trigger",
  },
  {
    type: "trigger/monitoring",
    title: "Мониторинг",
    description: "Старт по событию мониторинга серверов",
    icon: Bell,
    group: "trigger",
  },
  {
    type: "agent/react",
    title: "Ops-агент",
    description: "Агент рассуждает и вызывает инструменты",
    icon: Bot,
    group: "agent",
  },
  {
    type: "agent/multi",
    title: "Мульти-агент",
    description: "Расследование на нескольких серверах или агентах",
    icon: Boxes,
    group: "agent",
  },
  {
    type: "agent/ssh_cmd",
    title: "SSH-команда",
    description: "Прямое выполнение команды по SSH",
    icon: Terminal,
    group: "agent",
  },
  {
    type: "agent/llm_query",
    title: "Запрос к LLM",
    description: "Прямой запрос к языковой модели",
    icon: Zap,
    group: "agent",
  },
  {
    type: "agent/mcp_call",
    title: "Вызов MCP",
    description: "Закреплённый вызов инструмента MCP",
    icon: Wrench,
    group: "agent",
  },
  {
    type: "logic/condition",
    title: "Условие",
    description: "Ветвление по значению: true / false",
    icon: GitBranch,
    group: "logic",
  },
  {
    type: "logic/parallel",
    title: "Параллельно",
    description: "Запуск нескольких веток одновременно",
    icon: Copy,
    group: "logic",
  },
  {
    type: "logic/merge",
    title: "Слияние",
    description: "Объединение параллельных веток",
    icon: GitMerge,
    group: "logic",
  },
  {
    type: "logic/wait",
    title: "Ожидание",
    description: "Пауза перед следующим шагом",
    icon: Timer,
    group: "logic",
  },
  {
    type: "logic/human_approval",
    title: "Согласование",
    description: "Ожидание решения оператора",
    icon: ShieldCheck,
    group: "logic",
  },
  {
    type: "logic/telegram_input",
    title: "Ввод Telegram",
    description: "Ожидание ответа в Telegram",
    icon: MessageCircle,
    group: "logic",
  },
  {
    type: "ops/server_snapshot",
    title: "Снимок сервера",
    description: "Структурированный снимок Linux-сервера",
    icon: HardDrive,
    group: "ops",
  },
  {
    type: "ops/log_query",
    title: "Запрос логов",
    description: "Сбор логов Linux, сервисов или Docker",
    icon: FileSearch,
    group: "ops",
  },
  {
    type: "ops/file_action",
    title: "Файловое действие",
    description: "Чтение, запись или управление файлами",
    icon: FolderOpen,
    group: "ops",
  },
  {
    type: "ops/package_action",
    title: "Пакеты",
    description: "Установка или обновление пакетов",
    icon: Package,
    group: "ops",
  },
  {
    type: "ops/service_action",
    title: "Сервис",
    description: "Управление systemd-сервисом",
    icon: Cpu,
    group: "ops",
  },
  {
    type: "ops/docker_action",
    title: "Docker",
    description: "Действие с контейнером Docker",
    icon: Container,
    group: "ops",
  },
  {
    type: "ops/process_action",
    title: "Процесс",
    description: "Управление процессом на сервере",
    icon: Terminal,
    group: "ops",
  },
  {
    type: "ops/disk_cleanup",
    title: "Очистка диска",
    description: "Освобождение места на диске",
    icon: Trash2,
    group: "ops",
  },
  {
    type: "ops/backup_restore_check",
    title: "Проверка бэкапа",
    description: "Проверка доступности резервной копии",
    icon: HardDrive,
    group: "ops",
  },
  {
    type: "ops/http_check",
    title: "HTTP-проверка",
    description: "Проверка доступности HTTP-эндпоинта",
    icon: Globe,
    group: "ops",
  },
  {
    type: "ops/alert_update",
    title: "Обновление алерта",
    description: "Обновление статуса оповещения",
    icon: Bell,
    group: "ops",
  },
  {
    type: "output/telegram",
    title: "Telegram",
    description: "Отправка сообщения в Telegram",
    icon: MessageCircle,
    group: "output",
  },
  {
    type: "output/email",
    title: "Email",
    description: "Отправка электронного письма",
    icon: Mail,
    group: "output",
  },
  {
    type: "output/webhook",
    title: "Исходящий webhook",
    description: "HTTP-уведомление во внешнюю систему",
    icon: Webhook,
    group: "output",
  },
  {
    type: "output/report",
    title: "Отчёт",
    description: "Формирование текстового отчёта",
    icon: FileText,
    group: "output",
  },
  {
    type: "output/slack",
    title: "Slack",
    description: "Отправка сообщения в Slack",
    icon: MessageCircle,
    group: "output",
  },
];

const BY_TYPE = new Map(ENTRIES.map((entry) => [entry.type, entry]));

export const CATALOG_TYPES = ENTRIES.map((entry) => entry.type);

export const GROUP_LABELS: Record<NodeGroup, string> = {
  trigger: "Триггеры",
  agent: "Агенты",
  logic: "Логика",
  ops: "Операции",
  output: "Вывод",
  default: "Прочее",
};

export function resolveCatalog(
  type: string,
  manifest?: NodeManifest,
): CatalogEntry {
  const known = BY_TYPE.get(type);
  if (known) return known;
  const group = (type.split("/")[0] as NodeGroup) || "default";
  const fallbackGroup: NodeGroup = GROUP_LABELS[group] ? group : "default";
  return {
    type,
    title:
      type.split("/").at(-1)?.replaceAll("_", " ") ??
      type,
    description: manifest?.purpose || type,
    icon: Zap,
    group: fallbackGroup,
  };
}

export function catalogTitle(type: string, manifest?: NodeManifest) {
  return resolveCatalog(type, manifest).title;
}

/** English placeholder labels the backend seeds; the UI shows the RU title instead. */
const SEEDED_LABELS = new Set(["Manual Start"]);

export function displayLabel(type: string, data: Values): string {
  const label = typeof data.label === "string" ? data.label.trim() : "";
  if (!label || SEEDED_LABELS.has(label)) return catalogTitle(type);
  return label;
}

const HANDLE_LABELS: Record<string, string> = {
  out: "далее",
  success: "успех",
  error: "ошибка",
  true: "да",
  false: "нет",
  done: "готово",
  approved: "одобрено",
  rejected: "отклонено",
  timeout: "таймаут",
  received: "получено",
};

export function handleLabel(handle: string) {
  return HANDLE_LABELS[handle] ?? handle;
}

/**
 * Suggested next steps by the type of the node they follow. Order matters:
 * the first entries are shown first in the picker.
 */
const NEXT_BY_TYPE: Record<string, string[]> = {
  "trigger/manual": [
    "ops/server_snapshot",
    "agent/ssh_cmd",
    "ops/http_check",
    "agent/react",
  ],
  "trigger/schedule": [
    "ops/server_snapshot",
    "ops/http_check",
    "ops/backup_restore_check",
    "ops/disk_cleanup",
  ],
  "trigger/monitoring": [
    "ops/server_snapshot",
    "ops/log_query",
    "agent/react",
    "output/telegram",
  ],
  "trigger/webhook": ["agent/ssh_cmd", "agent/react", "logic/condition"],
  "logic/condition": ["output/telegram", "agent/ssh_cmd", "output/report"],
  "logic/parallel": ["ops/server_snapshot", "ops/http_check", "logic/merge"],
  "logic/merge": ["output/report", "output/telegram", "logic/condition"],
  "logic/human_approval": ["agent/ssh_cmd", "ops/service_action", "output/telegram"],
  "logic/telegram_input": ["logic/condition", "agent/llm_query"],
};

const NEXT_BY_GROUP: Record<NodeGroup, string[]> = {
  trigger: ["ops/server_snapshot", "agent/ssh_cmd", "logic/condition"],
  agent: ["logic/condition", "output/telegram", "output/report"],
  logic: ["output/telegram", "output/report"],
  ops: ["logic/condition", "output/telegram", "logic/human_approval"],
  output: ["output/report", "logic/wait"],
  default: ["logic/condition", "output/telegram"],
};

const POPULAR = [
  "agent/ssh_cmd",
  "ops/server_snapshot",
  "logic/condition",
  "output/telegram",
];

/** Types worth showing first when adding a step after `sourceType`. */
export function suggestNext(sourceType?: string): string[] {
  if (!sourceType) return POPULAR;
  const exact = NEXT_BY_TYPE[sourceType];
  if (exact) return exact;
  return NEXT_BY_GROUP[resolveCatalog(sourceType).group] ?? POPULAR;
}

function short(value: unknown, max = 48): string {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

const ACTION_LABELS: Record<string, string> = {
  read: "чтение",
  write: "запись",
  list_updates: "список обновлений",
  install: "установка",
  update: "обновление",
  remove: "удаление",
  inspect: "осмотр",
  journal_vacuum: "очистка журнала",
  tmp_cleanup: "очистка tmp",
  verify_latest: "проверка последнего",
  start: "запуск",
  stop: "остановка",
  restart: "перезапуск",
  reload: "перечитать конфиг",
  terminate: "завершить",
  kill_force: "убить",
  resolve: "закрыть",
};

const CHECK_LABELS: Record<string, string> = {
  contains: "содержит",
  not_contains: "не содержит",
  status_ok: "успешно",
  status_failed: "с ошибкой",
  always_true: "всегда",
};

/**
 * One-line human summary of node configuration shown on the canvas card.
 * Returns an empty string when nothing meaningful is configured yet.
 */
export function summarizeNode(type: string, data: Values): string {
  const d = data;
  const action = typeof d.action === "string" ? ACTION_LABELS[d.action] ?? d.action : "";
  switch (type) {
    case "trigger/schedule":
      return short(d.cron_expression) || "расписание не задано";
    case "trigger/webhook":
      return "HTTP POST";
    case "trigger/monitoring":
      return "по алерту мониторинга";
    case "trigger/manual":
      return "";
    case "agent/ssh_cmd":
      return short(d.command, 56);
    case "agent/react":
    case "agent/multi":
      return short(d.goal, 56);
    case "agent/llm_query":
      return short(d.prompt, 56);
    case "agent/mcp_call":
      return short(d.tool_name);
    case "logic/condition": {
      const check =
        typeof d.check_type === "string" ? CHECK_LABELS[d.check_type] ?? d.check_type : "";
      const value = short(d.check_value, 28);
      return [check, value && `«${value}»`].filter(Boolean).join(" ");
    }
    case "logic/wait":
      return d.duration_minutes ? `${d.duration_minutes} мин` : "";
    case "logic/human_approval":
      return d.approver_username
        ? `ждёт ${d.approver_username}`
        : short(d.message, 48);
    case "logic/telegram_input":
      return short(d.message, 48);
    case "ops/service_action":
      return [short(d.service, 28), action].filter(Boolean).join(" · ");
    case "ops/docker_action":
      return [short(d.container, 28), action].filter(Boolean).join(" · ");
    case "ops/process_action":
      return [d.pid ? `PID ${d.pid}` : "", action].filter(Boolean).join(" · ");
    case "ops/file_action":
      return [action, short(d.path, 40)].filter(Boolean).join(" · ");
    case "ops/package_action": {
      const pkgs = Array.isArray(d.packages) ? d.packages.map(String) : [];
      return [action, pkgs.length ? short(pkgs.join(", "), 32) : ""]
        .filter(Boolean)
        .join(" · ");
    }
    case "ops/disk_cleanup":
    case "ops/backup_restore_check":
    case "ops/alert_update":
      return action;
    case "ops/http_check":
      return [d.method, short(d.url, 44)].filter(Boolean).join(" ");
    case "ops/log_query":
      return [
        typeof d.source === "string" ? d.source : "",
        short(d.service || d.container, 24),
      ]
        .filter(Boolean)
        .join(" · ");
    case "output/telegram":
      return short(d.message, 56);
    case "output/email":
      return short(d.to_email || d.subject, 48);
    case "output/webhook":
      return [d.method, short(d.url, 44)].filter(Boolean).join(" ");
    case "output/report":
      return short(d.subject, 48);
    default:
      return "";
  }
}
