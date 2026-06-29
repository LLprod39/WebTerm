import {
  Bot,
  Users,
  Shield,
  FolderOpen,
  ScrollText,
  Activity,
  Bell,
  Gauge,
  Globe,
  Puzzle,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";

export interface SettingsNavItem {
  id: string;
  label: string;
  description: string;
  icon: LucideIcon;
  path: string;
  adminOnly?: boolean;
  badge?: string;
}

export interface SettingsNavGroup {
  id: string;
  label: string;
  items: SettingsNavItem[];
}

export const settingsNavGroups: SettingsNavGroup[] = [
  {
    id: "core",
    label: "Core",
    items: [
      {
        id: "readiness",
        label: "Готовность",
        description: "Проверка первого запуска",
        icon: Gauge,
        path: "/settings/readiness",
        adminOnly: true,
      },
      {
        id: "ai",
        label: "Модели",
        description: "Провайдеры, роли, маршруты",
        icon: Bot,
        path: "/settings/ai",
      },
      {
        id: "limits",
        label: "Лимиты",
        description: "Runs, sessions, budgets",
        icon: SlidersHorizontal,
        path: "/settings/limits",
        adminOnly: true,
      },
    ],
  },
  {
    id: "access",
    label: "Доступ",
    items: [
      {
        id: "access",
        label: "Обзор доступов",
        description: "Пользователи, группы, разрешения",
        icon: Shield,
        path: "/settings/access",
      },
      {
        id: "users",
        label: "Пользователи",
        description: "Управление аккаунтами",
        icon: Users,
        path: "/settings/users",
      },
      {
        id: "groups",
        label: "Группы",
        description: "Команды и роли",
        icon: FolderOpen,
        path: "/settings/groups",
      },
      {
        id: "permissions",
        label: "Разрешения",
        description: "Точечные правила доступа",
        icon: Shield,
        path: "/settings/permissions",
      },
      {
        id: "sso",
        label: "SSO / Домен",
        description: "Доменная авторизация и LDAP",
        icon: Globe,
        path: "/settings/sso",
        adminOnly: true,
      },
    ],
  },
  {
    id: "system",
    label: "Система",
    items: [
      {
        id: "memory",
        label: "Автозаметки",
        description: "Долгосрочные записи серверов",
        icon: ScrollText,
        path: "/settings/memory",
        adminOnly: true,
      },
      {
        id: "audit",
        label: "Аудит и журнал",
        description: "Логирование и история действий",
        icon: Activity,
        path: "/settings/audit",
        adminOnly: true,
      },
      {
        id: "notifications",
        label: "Оповещения",
        description: "Telegram, Email и публичный URL",
        icon: Bell,
        path: "/settings/notifications",
        adminOnly: true,
      },
      {
        id: "plugins",
        label: "Плагины",
        description: "Локальные расширения и разрешения",
        icon: Puzzle,
        path: "/settings/plugins",
        adminOnly: true,
      },
    ],
  },
];

export const allSettingsNavItems = settingsNavGroups.flatMap((group) => group.items);
