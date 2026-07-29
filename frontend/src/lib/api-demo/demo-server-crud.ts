import { DEMO_BOOTSTRAP } from "../demo";

/** Context, master-password, server CRUD, knowledge, memory, shares demo fallbacks. */
export function demoServerCrudFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
  if (path.includes("/servers/api/global-context")) {
    return { rules: "", forbidden_commands: [], required_checks: [], environment_vars: {} } as T;
  }
  if (path.includes("/group-context") || path.includes("/groups/") && path.includes("/context")) {
    return { rules: "", forbidden_commands: [], environment_vars: {} } as T;
  }
  if (path.includes("/servers/api/master-password")) return { has_master_password: false, success: true } as T;

  // Server detail / CRUD used by create-edit dialogs
  if (path.includes("/servers/api/") && path.includes("/get/")) {
    const match = path.match(/\/servers\/api\/(\d+)\/get\//);
    const id = match ? Number(match[1]) : 1;
    const seed = DEMO_BOOTSTRAP.servers.find((server) => server.id === id) || DEMO_BOOTSTRAP.servers[0];
    return {
      id: seed?.id ?? id,
      name: seed?.name ?? `server-${id}`,
      host: seed?.host ?? "127.0.0.1",
      port: seed?.port ?? 22,
      username: seed?.username ?? "demo",
      server_type: "ssh",
      auth_method: "key",
      key_path: "",
      tags: "demo,ssh",
      notes: "Demo server (static UI demo — no live SSH).",
      group_id: seed?.group_id ?? 1,
      is_active: true,
      ai_read_only: true,
      sudo_auth_mode: "none",
      has_saved_sudo_password: false,
      corporate_context: "",
      network_config: {},
      has_saved_password: false,
      can_view_password: false,
      can_edit: true,
      is_shared_server: false,
      share_context_enabled: false,
      shared_by_username: "",
    } as T;
  }
  if (path.includes("/servers/api/create") || path.includes("/servers/api/") && path.endsWith("/create/")) {
    return { success: true, server_id: 99, message: "created (demo)" } as T;
  }
  if (path.includes("/update/")) return { success: true, message: "updated (demo)" } as T;
  if (path.includes("/delete/") || path.includes("/test/")) return { success: true, message: "ok (demo)" } as T;
  if (path.includes("/execute/")) {
    return {
      success: true,
      output: { stdout: "demo-execute: backend offline\n", stderr: "", exit_code: 0 },
    } as T;
  }
  if (path.includes("/reveal-password/")) {
    return { success: true, password: "••••••••" } as T;
  }

  // Knowledge + memory (must always include items arrays — UI calls .filter on them)
  if (path.includes("/knowledge")) {
    return { success: true, items: [], categories: [] } as T;
  }
  if (path.includes("/memory/snapshots") || path.includes("/memory/overview") || path.includes("/memory/")) {
    return { success: true, items: [], snapshots: [], episodes: [], revalidations: [], summary: {} } as T;
  }
  if (path.includes("/shares") || path.includes("/share/")) {
    return { success: true, shares: [] } as T;
  }
  return undefined;
}
