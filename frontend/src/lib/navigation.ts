import type { LucideIcon } from "lucide-react";

import type { AuthUser } from "@/lib/api";
import { NavIcons } from "@/lib/app-icons";
import { canAccessStudio, hasFeatureAccess } from "@/lib/featureAccess";

export type NavSectionId =
  | "dashboard"
  | "infrastructure"
  | "automation"
  | "extensions"
  | "administration";

export interface PrimaryNavigationItem {
  id: string;
  titleKey: string;
  path: string;
  icon: LucideIcon;
  feature: string;
  section: NavSectionId;
  staffOnly?: boolean;
  requiresKubernetesReadiness?: boolean;
  keywords?: string;
  hotkey?: string;
}

/**
 * One source of truth for every global navigation surface. Routes still own
 * their server-side guard; this registry prevents the sidebar, palette and
 * hotkeys from advertising or prefetching capabilities a user does not have.
 */
export const PRIMARY_NAVIGATION: readonly PrimaryNavigationItem[] = [
  { id: "dashboard", titleKey: "nav.dashboard", path: "/dashboard", icon: NavIcons.dashboard, feature: "dashboard", section: "dashboard", keywords: "home main", hotkey: "d" },
  { id: "servers", titleKey: "nav.servers", path: "/servers", icon: NavIcons.servers, feature: "servers", section: "infrastructure", keywords: "ssh fleet hosts", hotkey: "s" },
  { id: "kubernetes", titleKey: "nav.kubernetes", path: "/kubernetes", icon: NavIcons.kubernetes, feature: "kubernetes", section: "infrastructure", requiresKubernetesReadiness: true, keywords: "cluster pods", hotkey: "k" },
  { id: "agents", titleKey: "nav.agents", path: "/agents", icon: NavIcons.agents, feature: "agents", section: "automation", keywords: "runs automation", hotkey: "a" },
  { id: "playbooks", titleKey: "nav.playbooks", path: "/automation", icon: NavIcons.playbooks, feature: "automation", section: "automation", keywords: "playbooks yaml automation runbook" },
  { id: "chat", titleKey: "nav.chat", path: "/chat", icon: NavIcons.chat, feature: "chat", section: "automation", keywords: "ai assistant", hotkey: "c" },
  { id: "studio", titleKey: "nav.studio", path: "/studio", icon: NavIcons.studio, feature: "studio", section: "automation", keywords: "pipeline", hotkey: "t" },
  { id: "mars", titleKey: "nav.mars", path: "/mars", icon: NavIcons.mars, feature: "mars", section: "automation" },
  { id: "plugins", titleKey: "nav.plugins", path: "/settings/plugins", icon: NavIcons.plugins, feature: "plugins", section: "extensions", staffOnly: true },
  { id: "insights", titleKey: "nav.insights", path: "/monitoring/insights", icon: NavIcons.insights, feature: "dashboard", section: "administration", staffOnly: true, keywords: "forecast alerts", hotkey: "m" },
  { id: "settings", titleKey: "nav.settings", path: "/settings", icon: NavIcons.settings, feature: "settings", section: "administration", keywords: "config" },
] as const;

export function canAccessPrimaryNavigationItem(
  user: AuthUser | null | undefined,
  item: PrimaryNavigationItem,
  options: { kubernetesReady?: boolean } = {},
): boolean {
  if (!user) return false;
  if (item.staffOnly && !user.is_staff) return false;
  if (item.requiresKubernetesReadiness && !user.is_staff && options.kubernetesReady === false) return false;
  if (item.feature === "studio") return canAccessStudio(user);
  return hasFeatureAccess(user, item.feature);
}

export function allowedPrimaryNavigation(
  user: AuthUser | null | undefined,
  options: { kubernetesReady?: boolean } = {},
): PrimaryNavigationItem[] {
  return PRIMARY_NAVIGATION.filter((item) => canAccessPrimaryNavigationItem(user, item, options));
}

export function firstAllowedPrimaryPath(user: AuthUser | null | undefined): string | null {
  return allowedPrimaryNavigation(user)[0]?.path ?? null;
}

export function firstAllowedApplicationPath(user: AuthUser | null | undefined): string | null {
  const primary = firstAllowedPrimaryPath(user);
  if (primary) return primary;
  if (hasFeatureAccess(user, "ai_connections_personal") || hasFeatureAccess(user, "ai_connections_admin")) {
    return "/settings/ai-connections";
  }
  return null;
}

export function canOpenAssistant(user: AuthUser | null | undefined): boolean {
  return hasFeatureAccess(user, "chat");
}

export function canNavigateToPrimaryPath(user: AuthUser | null | undefined, path: string): boolean {
  const item = PRIMARY_NAVIGATION
    .filter((candidate) => path === candidate.path || path.startsWith(`${candidate.path}/`))
    .sort((left, right) => right.path.length - left.path.length)[0];
  return item ? canAccessPrimaryNavigationItem(user, item) : false;
}
