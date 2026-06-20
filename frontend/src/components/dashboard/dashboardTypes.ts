import type { ReactNode } from "react";

import type { DashboardWidgetConfig } from "@/lib/api";

export type DashboardType = "admin" | "user";

export interface WidgetDefinition {
  id: string;
  title: string;
  icon?: ReactNode;
  defaultSize: { w: number; h: number };
  render: (config: DashboardWidgetConfig) => ReactNode;
}

export type VisibleDashboardWidget = {
  config: DashboardWidgetConfig;
  def: WidgetDefinition;
};
