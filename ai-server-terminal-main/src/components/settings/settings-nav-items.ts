import {
  Bot,
  Users,
  Shield,
  FolderOpen,
  ScrollText,
  Activity,
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
        id: "ai",
        label: "AI конфигурация",
        description: "Провайдеры, модели, маршрутизация",
        icon: Bot,
        path: "/settings/ai",
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
    ],
  },
  {
    id: "system",
    label: "Система",
    items: [
      {
        id: "memory",
        label: "AI Memory",
        description: "Dreams, snapshots, patterns",
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
    ],
  },
];

export const allSettingsNavItems = settingsNavGroups.flatMap((group) => group.items);
