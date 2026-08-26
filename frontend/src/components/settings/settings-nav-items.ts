import type { LucideIcon } from "lucide-react";

import { SettingsIcons } from "@/lib/app-icons";
import type { AuthUser } from "@/lib/api";
import { canManageAiRouting, hasAnyFeatureAccess, hasFeatureAccess } from "@/lib/featureAccess";

export interface SettingsNavItem {
  id: string;
  label: string;
  labelEn?: string;
  description: string;
  descriptionEn?: string;
  icon: LucideIcon;
  path: string;
  adminOnly?: boolean;
  aiRoutingOnly?: boolean;
  feature?: string | string[];
  /** Short setup tip for readiness / hub cards */
  setupHint?: string;
}

export interface SettingsNavGroup {
  id: string;
  label: string;
  labelEn?: string;
  description?: string;
  descriptionEn?: string;
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
    description: "Основные настройки",
    descriptionEn: "Core settings",
    items: [
      {
        id: "appearance",
        label: "Оформление",
        labelEn: "Appearance",
        description: "Темы интерфейса",
        descriptionEn: "Interface themes",
        icon: SettingsIcons.appearance,
        path: "/settings/appearance",
        setupHint: "Тема сохраняется для вашего аккаунта",
      },
      {
        id: "readiness",
        label: "Готовность",
        description: "Проверка основных настроек",
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
        aiRoutingOnly: true,
        setupHint: "Подключение моделей для чата и агентов",
      },
      {
        id: "ai-connections",
        label: "CLI-подписки",
        labelEn: "CLI subscriptions",
        description: "Codex CLI, Grok CLI и маршрутизация",
        descriptionEn: "Codex CLI, Grok CLI, and routing",
        icon: SettingsIcons.ai,
        path: "/settings/ai-connections",
        aiRoutingOnly: true,
        feature: ["ai_connections_personal", "ai_connections_admin"],
        setupHint: "Личные подключения и общие пулы",
      },
      {
        id: "limits",
        label: "Лимиты и бюджеты",
        description: "Запуски, SSH, токены и тайм-ауты MCP",
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
        setupHint: "Каналы для предупреждений и отчётов",
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
        description: "Доступ к функциям платформы",
        icon: SettingsIcons.permissions,
        path: "/settings/permissions",
        setupHint: "Доступ к агентам, Студии и Kubernetes",
      },
      {
        id: "sso",
        label: "SSO и домен",
        description: "LDAP, домен и создание аккаунтов",
        icon: SettingsIcons.sso,
        path: "/settings/sso",
        adminOnly: true,
        setupHint: "Корпоративный вход и создание аккаунтов",
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
        feature: "kubernetes",
        setupHint: "Подключение k8s-кластеров",
      },
      {
        id: "plugins",
        label: "Плагины",
        description: "Каталог и локальные пакеты",
        icon: SettingsIcons.plugins,
        path: "/settings/plugins",
        adminOnly: true,
        setupHint: "Расширения без пересборки образа",
      },
    ],
  },
];

export const allSettingsNavItems = settingsNavGroups.flatMap((group) => group.items);

export function visibleSettingsNavGroups(
  user: AuthUser | null | undefined,
  pluginsEnabled: boolean,
): SettingsNavGroup[] {
  const isAdmin = Boolean(user?.is_staff);
  return settingsNavGroups
    .map((group) => ({
      ...group,
      items: group.items.filter(
        (item) => {
          if (item.adminOnly && !isAdmin && !item.aiRoutingOnly) return false;
          if (item.aiRoutingOnly && !canManageAiRouting(user)) return false;
          if (item.id === "plugins" && !pluginsEnabled) return false;
          const feature = item.feature ?? "settings";
          return Array.isArray(feature)
            ? hasAnyFeatureAccess(user, feature)
            : hasFeatureAccess(user, feature);
        },
      ),
    }))
    .filter((group) => group.items.length > 0);
}

export function canViewSettingsNavItem(
  user: AuthUser | null | undefined,
  item: SettingsNavItem | undefined,
): boolean {
  if (!item) return true;
  if (item.adminOnly && !user?.is_staff && !item.aiRoutingOnly) return false;
  if (item.aiRoutingOnly && !canManageAiRouting(user)) return false;
  const feature = item.feature ?? "settings";
  return Array.isArray(feature)
    ? hasAnyFeatureAccess(user, feature)
    : hasFeatureAccess(user, feature);
}

export function findSettingsNavItem(pathname: string): SettingsNavItem | undefined {
  const exact = allSettingsNavItems.find((item) => item.path === pathname);
  if (exact) return exact;
  return allSettingsNavItems.find((item) => pathname.startsWith(`${item.path}/`));
}
