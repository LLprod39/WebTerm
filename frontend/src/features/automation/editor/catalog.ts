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
import type { NodeManifest } from "@/api/automation";

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
  if (known) {
    return {
      ...known,
      description: manifest?.purpose || known.description,
    };
  }
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
