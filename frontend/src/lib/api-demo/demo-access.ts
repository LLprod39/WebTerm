import { ACCESS_FEATURE_OPTIONS } from "../access-features";

/** Health + access control demo fallbacks. */
export function demoAccessFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
  if (path.includes("/api/health")) return { status: "ok" } as T;
  if (path.includes("/api/access/users")) return {
    success: true,
    features: ACCESS_FEATURE_OPTIONS,
    users: [
      {
        id: 1,
        username: "demo",
        email: "demo@example.com",
        is_staff: true,
        is_active: true,
        is_superuser: false,
        access_profile: "admin_full",
        groups: [{ id: 1, name: "Operators" }],
        effective_permissions: {
          servers: true,
          dashboard: true,
          agents: true,
          studio: true,
          studio_pipelines: true,
          studio_runs: true,
          studio_agents: true,
          studio_skills: true,
          studio_mcp: true,
          studio_notifications: true,
          kubernetes: false,
          mars: false,
          settings: true,
          orchestrator: true,
          knowledge_base: true,
        },
        explicit_permissions: {},
        group_permissions: { servers: true, studio: true, studio_pipelines: true, studio_runs: true, studio_agents: true, studio_skills: true, studio_mcp: true, studio_notifications: true },
        group_permission_sources: {
          servers: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_pipelines: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_runs: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_agents: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_skills: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_mcp: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_notifications: [{ group_id: 1, group_name: "Operators", allowed: true }],
        },
        permission_sources: {
          servers: "group_explicit",
          dashboard: "staff_default",
          agents: "staff_default",
          studio: "group_explicit",
          studio_pipelines: "group_explicit",
          studio_runs: "group_explicit",
          studio_agents: "group_explicit",
          studio_skills: "group_explicit",
          studio_mcp: "group_explicit",
          studio_notifications: "group_explicit",
          kubernetes: "explicit_opt_in",
          mars: "explicit_opt_in",
          settings: "staff_default",
          orchestrator: "staff_default",
          knowledge_base: "staff_default",
        },
      },
    ],
  } as T;
  if (path.includes("/api/access/groups")) return {
    success: true,
    features: ACCESS_FEATURE_OPTIONS,
    groups: [
      {
        id: 1,
        name: "Operators",
        member_count: 1,
        members: [{ id: 1, username: "demo" }],
        explicit_permissions: { servers: true, studio: true, studio_pipelines: true, studio_runs: true, studio_agents: true, studio_skills: true, studio_mcp: true, studio_notifications: true },
      },
    ],
  } as T;
  if (path.includes("/api/access/group-permissions")) return {
    success: true,
    features: ACCESS_FEATURE_OPTIONS,
    permissions: [
      { id: 1, group_id: 1, group_name: "Operators", feature: "servers", feature_display: "Servers", allowed: true },
      { id: 2, group_id: 1, group_name: "Operators", feature: "studio", feature_display: "Studio", allowed: true },
      { id: 3, group_id: 1, group_name: "Operators", feature: "studio_pipelines", feature_display: "Studio Pipelines", allowed: true },
      { id: 4, group_id: 1, group_name: "Operators", feature: "studio_runs", feature_display: "Studio Runs", allowed: true },
      { id: 5, group_id: 1, group_name: "Operators", feature: "studio_agents", feature_display: "Studio Agents", allowed: true },
      { id: 6, group_id: 1, group_name: "Operators", feature: "studio_skills", feature_display: "Studio Skills", allowed: true },
      { id: 7, group_id: 1, group_name: "Operators", feature: "studio_mcp", feature_display: "Studio MCP", allowed: true },
      { id: 8, group_id: 1, group_name: "Operators", feature: "studio_notifications", feature_display: "Studio Notifications", allowed: true },
    ],
  } as T;
  if (path.includes("/api/access/permissions")) return {
    success: true,
    features: ACCESS_FEATURE_OPTIONS,
    permissions: [],
    group_permissions: [],
  } as T;
  return undefined;
}
