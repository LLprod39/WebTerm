import type { AdminDashboardData, MonitoringDashboard } from "@/api";
import type { WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { buildAdminUsageWidgets } from "./adminUsageWidgets";
import { buildAdminCoreWidgets } from "./adminDashboardCoreWidgets";
import { buildAdminListWidgets } from "./adminDashboardListWidgets";

/** Public facade — keeps import path stable for AdminDashboard. */
export function buildAdminDashboardWidgets(
  d: AdminDashboardData,
  lang: string,
  mon?: MonitoringDashboard,
): WidgetDefinition[] {
  return [
    ...buildAdminCoreWidgets(d, lang, mon),
    ...buildAdminUsageWidgets(d, lang),
    ...buildAdminListWidgets(d, lang),
  ];
}
