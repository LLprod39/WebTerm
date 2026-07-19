/**
 * Warm React.lazy() page chunks after login so sidebar navigation
 * does not hit a full Suspense flash on first visit.
 *
 * Paths must match the same modules used by App.tsx lazy() imports
 * so Vite/webpack share the cached module graph.
 */

type PrefetchFn = () => Promise<unknown>;

/** Core shell pages (main sidebar). */
const CORE_PREFETCH: PrefetchFn[] = [
  () => import("@/pages/DashboardRouter"),
  () => import("@/pages/Servers"),
  () => import("@/pages/AgentsPage"),
  () => import("@/pages/StudioPage"),
  () => import("@/pages/settings/SettingsAIPage"),
  () => import("@/components/settings/SettingsLayout"),
];

/** Secondary pages — lower priority. */
const SECONDARY_PREFETCH: PrefetchFn[] = [
  () => import("@/pages/TerminalPage"),
  () => import("@/pages/AgentRunPage"),
  () => import("@/pages/StudioDraftsPage"),
  () => import("@/pages/PipelineEditorPage"),
  () => import("@/pages/PipelineRunsPage"),
  () => import("@/pages/StudioSkillsPage"),
  () => import("@/pages/MCPHubPage"),
  () => import("@/pages/NotificationsSettingsPage"),
  () => import("@/pages/AgentConfigPage"),
  () => import("@/pages/KubernetesPage"),
  () => import("@/pages/MarsPage"),
  () => import("@/pages/settings/SettingsReadinessPage"),
  () => import("@/pages/settings/SettingsAccessPage"),
  () => import("@/pages/SettingsUsersPage"),
  () => import("@/pages/SettingsGroupsPage"),
  () => import("@/pages/SettingsPermissionsPage"),
  () => import("@/pages/settings/SettingsLimitsPage"),
  () => import("@/pages/settings/SettingsMemoryPage"),
  () => import("@/pages/settings/SettingsAuditPage"),
  () => import("@/pages/settings/SettingsSSOPage"),
  () => import("@/pages/settings/SettingsKubernetesPage"),
  () => import("@/pages/plugin-marketplace/InstalledPluginsPage"),
];

/** Map nav path prefixes → prefetch for hover. */
const PATH_PREFETCH: Array<{ prefix: string; load: PrefetchFn }> = [
  { prefix: "/dashboard", load: () => import("@/pages/DashboardRouter") },
  { prefix: "/servers", load: () => import("@/pages/Servers") },
  { prefix: "/agents", load: () => import("@/pages/AgentsPage") },
  { prefix: "/chat", load: () => import("@/pages/ChatPage") },
  { prefix: "/studio", load: () => import("@/pages/StudioPage") },
  { prefix: "/kubernetes", load: () => import("@/pages/KubernetesPage") },
  { prefix: "/mars", load: () => import("@/pages/MarsPage") },
  { prefix: "/settings", load: () => import("@/components/settings/SettingsLayout") },
];

const warmed = new Set<string>();

function runPrefetch(fn: PrefetchFn, key: string) {
  if (warmed.has(key)) return;
  warmed.add(key);
  void fn().catch(() => {
    warmed.delete(key);
  });
}

function scheduleIdle(fn: () => void, timeoutMs = 2000) {
  const ric = (window as Window & {
    requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
  }).requestIdleCallback;
  if (typeof ric === "function") {
    ric(fn, { timeout: timeoutMs });
    return;
  }
  window.setTimeout(fn, 200);
}

/** Prefetch primary routes shortly after shell is interactive. */
export function prefetchCoreRoutes() {
  if (typeof window === "undefined") return;
  scheduleIdle(() => {
    CORE_PREFETCH.forEach((fn, i) => runPrefetch(fn, `core:${i}`));
    // Secondary after a beat so first paint stays free.
    window.setTimeout(() => {
      SECONDARY_PREFETCH.forEach((fn, i) => runPrefetch(fn, `sec:${i}`));
    }, 1200);
  });
}

/** Prefetch the chunk for a nav URL (call on pointer enter). */
export function prefetchRouteForPath(path: string) {
  if (typeof window === "undefined" || !path) return;
  const hit = PATH_PREFETCH.find((entry) => path === entry.prefix || path.startsWith(`${entry.prefix}/`));
  if (!hit) return;
  runPrefetch(hit.load, `path:${hit.prefix}`);
}
