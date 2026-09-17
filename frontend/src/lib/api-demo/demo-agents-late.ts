/** Agents templates/runs/watchers, alerts, and directory listing demo fallbacks. */
export function demoAgentsLateFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
  if (path.includes("/servers/api/agents/templates")) return { success: true, templates: [] } as T;
  if (path.includes("/servers/api/agents/runs/") && path.includes("/events/")) {
    return { success: true, events: [], total: 0 } as T;
  }
  if (path.includes("/servers/api/agents/runs")) return { success: true, runs: [] } as T;
  if (path.includes("/servers/api/watchers/drafts/") && path.includes("/launch/")) {
    return {
      success: true,
      draft: {
        id: 1,
        server_id: 1,
        server_name: "demo-linux",
        severity: "warning",
        recommended_role: "infra_scout",
        objective: "Investigate service drift on demo-linux",
        reasons: ["Demo mode watcher draft"],
        memory_excerpt: ["Nginx was restarted during the last deploy"],
        status: "acknowledged",
        acknowledged_at: new Date().toISOString(),
        acknowledged_by: "demo",
        resolved_at: null,
        first_seen_at: new Date().toISOString(),
        last_seen_at: new Date().toISOString(),
        metadata: { launch_count: 1 },
      },
      agent_id: 1,
      run_id: 1,
      status: "pending",
    } as T;
  }
  if (path.includes("/servers/api/agents")) return { success: true, agents: [] } as T;
  if (path.includes("/servers/api/alerts")) return { success: true, alerts: [] } as T;
  if (path.includes("/servers/api/") && path.includes("/files/")) return {
    success: true,
    path: "/home/demo",
    home_path: "/home/demo",
    parent_path: "/home",
    entries: [
      {
        name: "deploy.log",
        path: "/home/demo/deploy.log",
        kind: "file",
        is_dir: false,
        is_symlink: false,
        size: 18432,
        permissions: "-rw-r--r--",
        permissions_octal: "0644",
        modified_at: Math.floor(Date.now() / 1000) - 3600,
      },
      {
        name: "releases",
        path: "/home/demo/releases",
        kind: "dir",
        is_dir: true,
        is_symlink: false,
        size: 0,
        permissions: "drwxr-xr-x",
        permissions_octal: "0755",
        modified_at: Math.floor(Date.now() / 1000) - 86400,
      },
    ],
  } as T;
  return undefined;
}
