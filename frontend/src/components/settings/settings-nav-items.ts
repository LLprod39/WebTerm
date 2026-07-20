import type { LucideIcon } from "lucide-react";

import { SettingsIcons } from "@/lib/app-icons";

export interface SettingsNavItem {
  id: string;
  label: string;
  description: string;
  icon: LucideIcon;
  path: string;
  adminOnly?: boolean;
  /** Short setup tip for readiness / hub cards */
  setupHint?: string;
}

export interface SettingsNavGroup {
  id: string;
  label: string;
  description?: string;
  items: SettingsNavItem[];
}

/**
 * Settings IA for “deploy then configure in UI”:
 * 1. Launch — readiness + AI + limits + notifications
 * 2. Access — people and SSO
 * 3. Platform — memory, audit, k8s, plugins
 *
 * Icons come from SettingsIcons (curated, one glyph per concept).
 */
export const settingsNavGroups: SettingsNavGroup[] = [
  {
    id: "launch",
    label: "Запуск платформы",
    description: "После деплоя настройте здесь — без правки env",
    items: [
      {
        id: "readiness",
        label: "Готовность",
        description: "Чеклист: что ещё не настроено",
        icon: SettingsIcons.readiness,
        path: "/settings/readiness",
        adminOnly: true,
        setupHint: "С чего начать после развёртывания",
      },
      {
        id: "ai",
        label: "AI и модели",
        description: "Провайдеры, ключи, роли моделей",
        icon: SettingsIcons.ai,
        path: "/settings/ai",
        adminOnly: true,
        setupHint: "Подключите LLM — чат, агенты, оркестратор",
      },
      {
        id: "limits",
        label: "Лимиты и бюджеты",
        description: "Runs, SSH, токены, MCP-таймауты",
        icon: SettingsIcons.limits,
        path: "/settings/limits",
        adminOnly: true,
        setupHint: "Защита от перегрузки платформы",
      },
      {
        id: "notifications",
        label: "Оповещения",
        description: "Telegram, email, публичный URL",
        icon: SettingsIcons.notifications,
        path: "/settings/notifications",
        adminOnly: true,
        setupHint: "Куда слать алерты и отчёты агентов",
      },
    ],
  },
  {
    id: "access",
    label: "Доступ",
    description: "Кто входит и что может делать",
    items: [
      {
        id: "access",
        label: "Обзор доступов",
        description: "Сводка рисков и быстрые ссылки",
        icon: SettingsIcons.access,
        path: "/settings/access",
        setupHint: "Карта пользователей, групп и прав",
      },
      {
        id: "users",
        label: "Пользователи",
        description: "Аккаунты, роли, активность",
        icon: SettingsIcons.users,
        path: "/settings/users",
        setupHint: "Создание и блокировка пользователей",
      },
      {
        id: "groups",
        label: "Группы",
        description: "Команды и общие права",
        icon: SettingsIcons.groups,
        path: "/settings/groups",
        setupHint: "Права пачками через группы",
      },
      {
        id: "permissions",
        label: "Разрешения",
        description: "Точечные feature-права",
        icon: SettingsIcons.permissions,
        path: "/settings/permissions",
        setupHint: "Кто видит агентов, студию, k8s…",
      },
      {
        id: "sso",
        label: "SSO и домен",
        description: "LDAP, заголовок домена, auto-create",
        icon: SettingsIcons.sso,
        path: "/settings/sso",
        adminOnly: true,
        setupHint: "Корпоративный вход без ручных учёток",
      },
    ],
  },
  {
    id: "platform",
    label: "Платформа",
    description: "Эксплуатация и расширения",
    items: [
      {
        id: "memory",
        label: "Автозаметки",
        description: "Память AI по серверам",
        icon: SettingsIcons.memory,
        path: "/settings/memory",
        adminOnly: true,
        setupHint: "Долгосрочный контекст на хостах",
      },
      {
        id: "audit",
        label: "Аудит и журнал",
        description: "Что логировать и история действий",
        icon: SettingsIcons.audit,
        path: "/settings/audit",
        adminOnly: true,
        setupHint: "Контроль изменений и расследования",
      },
      {
        id: "kubernetes",
        label: "Kubernetes",
        description: "Rancher, Devtron, sync",
        icon: SettingsIcons.kubernetes,
        path: "/settings/kubernetes",
        adminOnly: true,
        setupHint: "Подключение k8s-кластеров",
      },
      {
        id: "plugins",
        label: "Плагины",
        description: "Marketplace и локальные пакеты",
        icon: SettingsIcons.plugins,
        path: "/settings/plugins",
        adminOnly: true,
        setupHint: "Расширения без пересборки образа",
      },
    ],
  },
];

export const allSettingsNavItems = settingsNavGroups.flatMap((group) => group.items);

export function findSettingsNavItem(pathname: string): SettingsNavItem | undefined {
  const exact = allSettingsNavItems.find((item) => item.path === pathname);
  if (exact) return exact;
  return allSettingsNavItems.find((item) => pathname.startsWith(`${item.path}/`));
}
