import { api } from "./client";

export type DashboardType = "admin" | "user";
export type DashboardSectionId = "servers" | "activity" | "alerts";
export type DashboardColumn = "main" | "side";
export interface OverviewLayout {
  columns: Record<DashboardColumn, DashboardSectionId[]>;
  hidden: DashboardSectionId[];
}
export const dashboardSectionLabels: Record<DashboardSectionId, string> = {
  servers: "Состояние серверов",
  activity: "Последние операции",
  alerts: "Требуют внимания",
};
export const defaultOverviewLayout = (): OverviewLayout => ({
  columns: { main: ["servers", "activity"], side: ["alerts"] },
  hidden: [],
});
function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
function isSection(value: unknown): value is DashboardSectionId {
  return (
    typeof value === "string" &&
    Object.prototype.hasOwnProperty.call(dashboardSectionLabels, value)
  );
}
// The backend stores unvalidated JSON. Normalize only our versioned namespace.
export function readOverviewLayout(raw: unknown): OverviewLayout {
  const next = object(object(raw)?.frontend_next);
  const overview = object(next?.overview);
  const columns = object(overview?.columns);
  if (next?.version !== 1 || !overview || !columns)
    return defaultOverviewLayout();
  const result: OverviewLayout = {
    columns: { main: [], side: [] },
    hidden: [],
  };
  const seen = new Set<DashboardSectionId>();
  for (const column of ["main", "side"] as const) {
    const entries = columns[column];
    if (Array.isArray(entries)) {
      for (const entry of entries) {
        if (isSection(entry) && !seen.has(entry)) {
          result.columns[column].push(entry);
          seen.add(entry);
        }
      }
    }
  }
  const defaults = defaultOverviewLayout();
  for (const column of ["main", "side"] as const) {
    for (const entry of defaults.columns[column]) {
      if (!seen.has(entry)) result.columns[column].push(entry);
    }
  }
  result.hidden = Array.isArray(overview.hidden)
    ? [...new Set(overview.hidden.filter(isSection))]
    : [];
  return result;
}
export function mergeOverviewLayout(raw: unknown, layout: OverviewLayout) {
  const root = object(raw) ?? (raw == null ? {} : { legacy_layout: raw });
  const next = object(root.frontend_next) ?? {};
  return {
    ...root,
    frontend_next: { ...next, version: 1, overview: layout },
  };
}
export const dashboardLayoutApi = {
  get: (type: DashboardType, signal?: AbortSignal) =>
    api.get<{ layout: unknown }>(
      `/api/dashboard-custom/layout/${type}/`,
      signal,
    ),
  save: (type: DashboardType, layout: unknown) =>
    api.post<{ created: boolean }>(`/api/dashboard-custom/layout/${type}/`, {
      layout,
    }),
};
