import {
  Blocks,
  Bot,
  Box,
  Braces,
  CalendarClock,
  ClipboardList,
  FileCode2,
  GitBranch,
  MessagesSquare,
  NotebookPen,
  Plug,
  ScanLine,
  Server,
  Settings2,
  ShieldCheck,
  Sparkles,
  Users,
  UsersRound,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import type { SessionUser } from "@/api/auth";

export const SERVER_HOME = "/infrastructure/servers";

export interface NavigationItem {
  path: string;
  label: string;
  icon: LucideIcon;
  feature?: string;
  anyFeature?: string[];
  allFeatures?: string[];
  staff?: boolean;
  canAccess?: (user: SessionUser) => boolean;
  advanced?: boolean;
  hiddenInSection?: boolean;
  parentPath?: string;
  matchPaths?: string[];
}
export interface NavigationGroup {
  id: string;
  label: string;
  icon: LucideIcon;
  items: NavigationItem[];
}

export function canSeeNavigation(
  item: NavigationItem,
  user: SessionUser | null,
) {
  return (
    !!user &&
    (!item.feature || !!user.features[item.feature]) &&
    (!item.staff || user.is_staff) &&
    (!item.anyFeature ||
      item.anyFeature.some((feature) => user.features[feature])) &&
    (!item.allFeatures ||
      item.allFeatures.every((feature) => user.features[feature])) &&
    (!item.canAccess || !!item.canAccess(user))
  );
}

export function matchesNavigation(item: NavigationItem, pathname: string) {
  return [item.path, ...(item.matchPaths ?? [])].some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
}

export const navigation: NavigationGroup[] = [
  {
    id: "servers",
    label: "Серверы",
    icon: Server,
    items: [
      {
        path: SERVER_HOME,
        label: "Серверы",
        icon: Server,
        feature: "servers",
        matchPaths: ["/infrastructure/terminal"],
      },
      {
        path: "/intelligence/memory",
        label: "Память серверов",
        icon: Box,
        feature: "servers",
        hiddenInSection: true,
      },
    ],
  },
  {
    id: "chat",
    label: "AI-чат",
    icon: MessagesSquare,
    items: [
      {
        path: "/intelligence/chat",
        label: "AI-чат",
        icon: MessagesSquare,
        feature: "chat",
      },
    ],
  },
  {
    id: "automation",
    label: "Автоматизация",
    icon: Workflow,
    items: [
      {
        path: "/automation/playbooks",
        label: "Playbooks",
        icon: FileCode2,
        feature: "automation",
      },
      {
        path: "/automation/pipelines",
        label: "Pipelines",
        icon: GitBranch,
        feature: "studio_pipelines",
      },
      {
        path: "/automation/runs",
        label: "История запусков",
        icon: Workflow,
        anyFeature: ["automation", "studio_runs"],
      },
      {
        path: "/automation/drafts",
        label: "Черновики",
        icon: NotebookPen,
        feature: "studio_pipelines",
        advanced: true,
      },
      {
        path: "/automation/schedules",
        label: "Расписания",
        icon: CalendarClock,
        feature: "studio_pipelines",
        advanced: true,
      },
      {
        path: "/intelligence/profiles",
        label: "Профили AI-узлов",
        icon: Bot,
        feature: "studio_agents",
        advanced: true,
      },
    ],
  },
  {
    id: "agents",
    label: "Агенты",
    icon: Bot,
    items: [
      {
        path: "/intelligence/agents",
        label: "Агенты",
        icon: Bot,
        feature: "agents",
        matchPaths: ["/intelligence/runs"],
      },
      {
        path: "/intelligence/skills",
        label: "Навыки",
        icon: Braces,
        feature: "studio_skills",
        advanced: true,
      },
      {
        path: "/intelligence/mars",
        label: "MARS",
        icon: Sparkles,
        feature: "mars",
        advanced: true,
      },
    ],
  },
  {
    id: "settings",
    label: "Настройки",
    icon: Settings2,
    items: [
      {
        path: "/settings/ai",
        label: "AI и подключения",
        icon: Sparkles,
        feature: "settings",
        canAccess: (user) => user.can_manage_ai_routing,
      },
      {
        path: "/settings/access",
        label: "Доступ",
        icon: Users,
        feature: "settings",
        staff: true,
        matchPaths: [
          "/governance/users",
          "/governance/groups",
          "/governance/permissions",
        ],
      },
      {
        path: "/settings/integrations",
        label: "Интеграции",
        icon: Plug,
        canAccess: (user) =>
          !!user.features.studio_mcp ||
          !!(user.is_staff && user.features.settings && user.features.plugins),
        matchPaths: ["/intelligence/mcp", "/governance/plugins"],
      },
      {
        path: "/governance/users",
        label: "Пользователи",
        icon: Users,
        feature: "settings",
        staff: true,
        parentPath: "/settings/access",
      },
      {
        path: "/governance/groups",
        label: "Группы",
        icon: UsersRound,
        feature: "settings",
        staff: true,
        parentPath: "/settings/access",
      },
      {
        path: "/governance/permissions",
        label: "Матрица разрешений",
        icon: ShieldCheck,
        feature: "settings",
        staff: true,
        parentPath: "/settings/access",
        advanced: true,
      },
      {
        path: "/intelligence/mcp",
        label: "MCP-инструменты",
        icon: Plug,
        feature: "studio_mcp",
        parentPath: "/settings/integrations",
      },
      {
        path: "/governance/plugins",
        label: "Плагины",
        icon: Blocks,
        allFeatures: ["settings", "plugins"],
        staff: true,
        parentPath: "/settings/integrations",
      },
      {
        path: "/governance/audit",
        label: "Аудит",
        icon: ClipboardList,
        feature: "settings",
        staff: true,
        advanced: true,
      },
      {
        path: "/settings/general",
        label: "Журналирование и хранение",
        icon: Settings2,
        feature: "settings",
        staff: true,
        advanced: true,
      },
      {
        path: "/settings/identity",
        label: "Корпоративный вход",
        icon: ShieldCheck,
        feature: "settings",
        staff: true,
        advanced: true,
      },
      {
        path: "/settings/limits",
        label: "Лимиты выполнения",
        icon: ScanLine,
        feature: "settings",
        staff: true,
        advanced: true,
      },
      {
        path: "/settings/readiness",
        label: "Диагностика системы",
        icon: ScanLine,
        feature: "settings",
        staff: true,
        advanced: true,
      },
    ],
  },
];

export function visibleNavigation(user: SessionUser | null): NavigationGroup[] {
  return navigation
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => canSeeNavigation(item, user)),
    }))
    .filter((group) => group.items.length > 0);
}

export function sectionLanding(group: NavigationGroup) {
  return (
    group.items.find(
      (item) => !item.parentPath && !item.advanced && !item.hiddenInSection,
    ) ??
    group.items.find((item) => !item.parentPath && !item.hiddenInSection) ??
    group.items[0]
  );
}
