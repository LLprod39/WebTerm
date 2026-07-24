import { json } from "../apiHarness";
import { ServerItem, FIXED_DATE } from "../platformFixtureTypes";
import type { PlatformFixtureContext } from "../platformFixtureState";

/** Bootstrap, files listing, server create, monitoring dashboard fixtures. */
export function handleServersBootstrapFixture(req: any, ctx: PlatformFixtureContext) {
  const { groups, servers } = ctx;
      if (req.path === "/servers/api/frontend/bootstrap/" && req.method === "GET") {
        return json({
          success: true,
          servers,
          groups: groups.map((group) => ({
            ...group,
            server_count: servers.filter((server) => server.group_id === group.id).length,
          })),
          stats: { owned: servers.length, shared: 0, total: servers.length },
          recent_activity: [],
        });
      }

      if (req.path === "/servers/api/1/files/" && req.method === "GET") {
        return json({
          success: true,
          path: "/var/www/webterm",
          home_path: "/home/deploy",
          parent_path: "/var/www",
          entries: [
            {
              path: "/var/www/webterm/.env",
              name: ".env",
              kind: "file",
              is_dir: false,
              is_symlink: false,
              size: 512,
              permissions: "0600",
              modified_at: 1772326800,
            },
            {
              path: "/var/www/webterm/releases",
              name: "releases",
              kind: "dir",
              is_dir: true,
              is_symlink: false,
              size: 0,
              permissions: "0755",
              modified_at: 1772326800,
            },
            {
              path: "/var/www/webterm/nginx.conf",
              name: "nginx.conf",
              kind: "file",
              is_dir: false,
              is_symlink: false,
              size: 2048,
              permissions: "0644",
              modified_at: 1772326800,
            },
          ],
        });
      }
      if (req.path === "/servers/api/create/" && req.method === "POST") {
        const id = ctx.nextServerId++;
        const created: ServerItem = {
          id,
          name: String(req.body?.name || `Server-${id}`),
          host: String(req.body?.host || `10.0.0.${id}`),
          port: Number(req.body?.port || 22),
          username: String(req.body?.username || "root"),
          server_type: "ssh",
          status: "unknown",
          group_id: 11,
          group_name: "Core",
          is_shared: false,
          can_edit: true,
          share_context_enabled: false,
          shared_by_username: "",
          terminal_path: `/servers/${id}/terminal`,
          minimal_terminal_path: `/servers/${id}/terminal/minimal`,
          last_connected: null,
        };
        servers.push(created);
        return json({ success: true, server_id: id });
      }

      if (req.path === "/servers/api/monitoring/dashboard/" && req.method === "GET") {
        return json({
          summary: {
            total_servers: servers.length,
            healthy: servers.length,
            warning: 0,
            critical: 0,
            unreachable: 0,
          },
          servers: servers.map((server) => ({
            server_id: server.id,
            server_name: server.name,
            host: server.host,
            status: "healthy",
            cpu_percent: 35,
            memory_percent: 42,
            disk_percent: 51,
            load_1m: 0.2,
            uptime_seconds: 10_000,
            response_time_ms: 100,
            checked_at: FIXED_DATE,
          })),
          alerts: [],
        });
      }
  return undefined;
}
