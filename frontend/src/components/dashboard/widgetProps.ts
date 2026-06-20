import type { DashboardWidgetConfig } from "@/lib/api";

export function getWidgetStringProp(config: DashboardWidgetConfig, key: string, fallback: string): string {
  const value = config.props?.[key];
  return typeof value === "string" ? value : fallback;
}

export function getWidgetNumberProp(config: DashboardWidgetConfig, key: string, fallback: number): number {
  const value = config.props?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}
