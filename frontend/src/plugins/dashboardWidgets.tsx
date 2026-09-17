import { Puzzle } from "lucide-react";

import type { WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { PluginDashboardWidgetHost, type PluginDashboardWidgetDescriptor } from "./DashboardWidgetHost";
import type { FrontendBundleRuntime } from "./pluginDynamicBundleFrame";

function pluginDashboardWidgetId(widget: PluginDashboardWidgetDescriptor) {
  return `plugin:${widget.plugin_id}:${widget.id}`;
}

function normalizeWidget(raw: Record<string, unknown>): PluginDashboardWidgetDescriptor | null {
  const pluginId = String(raw.plugin_id || "").trim();
  const id = String(raw.id || "").trim();
  if (!pluginId || !id) return null;
  return {
    plugin_id: pluginId,
    id,
    title: String(raw.title || id),
    description: String(raw.description || ""),
    page_id: String(raw.page_id || ""),
    path: String(raw.path || ""),
    renderer: String(raw.renderer || ""),
    frontend_bundle_runtime: raw.frontend_bundle_runtime && typeof raw.frontend_bundle_runtime === "object"
      ? raw.frontend_bundle_runtime as FrontendBundleRuntime
      : undefined,
  };
}

export function buildPluginDashboardWidgets(rawWidgets: Array<Record<string, unknown>>): WidgetDefinition[] {
  return rawWidgets
    .map(normalizeWidget)
    .filter((widget): widget is PluginDashboardWidgetDescriptor => Boolean(widget))
    .map((widget) => ({
      id: pluginDashboardWidgetId(widget),
      title: widget.title || widget.id,
      icon: <Puzzle className="h-4 w-4" />,
      defaultSize: { w: 4, h: 1 },
      render: (config) => <PluginDashboardWidgetHost config={config} widget={widget} />,
    }));
}
