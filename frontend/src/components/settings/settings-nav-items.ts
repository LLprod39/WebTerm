import {
  Bot,
  Users,
  Shield,
  FolderOpen,
  ScrollText,
  Activity,
  Bell,
  Boxes,
  Gauge,
  Globe,
  Puzzle,
  SlidersHorizontal,
  LayoutDashboard,
  type LucideIcon,
} from "lucide-react";

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
        icon: Gauge,
        path: "/settings/readiness",
        adminOnly: true,
        setupHint: "С чего начать после развёртывания",
      },
      {
        id: "ai",
        label: "AI и модели",
        description: "Провайдеры, ключи, роли моделей",
        icon: Bot,
        path: "/settings/ai",
        setupHint: "Подключите LLM — чат, агенты, оркестратор",
      },
      {
        id: "limits",
        label: "Лимиты и бюджеты",
        description: "Runs, SSH, токены, MCP-таймауты",
        icon: SlidersHorizontal,
        path: "/settings/limits",
        adminOnly: true,
        setupHint: "Защита от перегрузки платформы",
      },
      {
        id: "notifications",
        label: "Оповещения",
        description: "Telegram, email, публичный URL",
        icon: Bell,
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
        icon: LayoutDashboard,
        path: "/settings/access",
        setupHint: "Карта пользователей, групп и прав",
      },
      {
        id: "users",
        label: "Пользователи",
        description: "Аккаунты, роли, активность",
        icon: Users,
        path: "/settings/users",
        setupHint: "Создание и блокировка пользователей",
      },
      {
        id: "groups",
        label: "Группы",
        description: "Команды и общие права",
        icon: FolderOpen,
        path: "/settings/groups",
        setupHint: "Права пачками через группы",
      },
      {
        id: "permissions",
        label: "Разрешения",
        description: "Точечные feature-права",
        icon: Shield,
        path: "/settings/permissions",
        setupHint: "Кто видит агентов, студию, k8s…",
      },
      {
        id: "sso",
        label: "SSO и домен",
        description: "LDAP, заголовок домена, auto-create",
        icon: Globe,
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
        icon: ScrollText,
        path: "/settings/memory",
        adminOnly: true,
        setupHint: "Долгосрочный контекст на хостах",
      },
      {
        id: "audit",
        label: "Аудит и журнал",
        description: "Что логировать и история действий",
        icon: Activity,
        path: "/settings/audit",
        adminOnly: true,
        setupHint: "Контроль изменений и расследования",
      },
      {
        id: "kubernetes",
        label: "Kubernetes",
        description: "Rancher, Devtron, sync",
        icon: Boxes,
        path: "/settings/kubernetes",
        adminOnly: true,
        setupHint: "Подключение k8s-кластеров",
      },
      {
        id: "plugins",
        label: "Плагины",
        description: "Marketplace и локальные пакеты",
        icon: Puzzle,
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
