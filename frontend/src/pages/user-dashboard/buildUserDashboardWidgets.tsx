import type { WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { buildPluginDashboardWidgets } from "@/plugins/dashboardWidgets";
import { buildUserAttentionItems } from "./userDashboardAttention";
import { buildUserMiscWidgets } from "./userDashboardMiscWidgets";
import { buildUserRunWidgets } from "./userDashboardRunWidgets";
import { buildUserServerWidgets } from "./userDashboardServerWidgets";
import type { UserDashboardData } from "./useUserDashboardData";

/** Compose builtin user-dashboard widgets + plugin surfaces. */
export function buildUserDashboardWidgets(data: UserDashboardData): WidgetDefinition[] {
  const {
    boot,
    runs,
    mon,
    monLoading,
    monFetching,
    liveConnected,
    liveMetrics,
    pluginSurfaces,
    lang,
  } = data;

  if (!boot && !runs && !mon) return [];

  const attentionItems = buildUserAttentionItems(runs, mon, lang);

  const builtins: WidgetDefinition[] = [
    ...buildUserRunWidgets({ boot, runs, mon, lang, attentionItems }),
    ...buildUserServerWidgets({ boot, mon, monLoading, monFetching, liveConnected, liveMetrics, lang }),
    ...buildUserMiscWidgets({ boot, lang }),
  ];

  return [...builtins, ...buildPluginDashboardWidgets(pluginSurfaces?.surfaces?.dashboard_widgets ?? [])];
}
