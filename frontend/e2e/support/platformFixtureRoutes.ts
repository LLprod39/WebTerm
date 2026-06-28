import { json } from "./apiHarness";
import { handlePluginMockRequest } from "./platformFixturePlugins";
import { makeSessionUser, ServerItem, FIXED_DATE } from "./platformFixtureTypes";
import { PlatformFixtureContext } from "./platformFixtureState";

export function handlePlatformMockRequest(req: any, ctx: PlatformFixtureContext) {
  const {
    options, defaultUser, state, groups, servers, marsWorkspace, marsSession, marsRun, marsProjects,
    serverAgents, agentWorkerStates, agentRuntimeOverview, agentRunReport, agentRunPlanTasks, agentRunEvents,
    pipelines, draftSessions, notifications, settingsConfig, accessUsers, accessGroups, accessPermissions, accessGroupPermissions,
  } = ctx;
      if (req.path === "/api/auth/session/" && req.method === "GET") {
        return json({
          authenticated: state.authenticated,
          user: state.authenticated ? defaultUser : null,
        });
      }

      if (req.path === "/api/auth/login/" && req.method === "POST") {
        state.authenticated = true;
        return json({
          success: true,
          authenticated: true,
          next_url: "/servers",
          user: makeSessionUser(options.isStaff ?? false, String(req.body?.username || defaultUser.username)),
        });
      }

      if (req.path === "/api/auth/logout/" && req.method === "POST") {
        state.authenticated = false;
        return json({ success: true });
      }

      if (req.path === "/api/auth/ws-token/" && req.method === "GET") {
        return json({ token: "mock-ws-token" });
      }

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

      if (req.path === "/api/mars/workspaces/" && req.method === "GET") {
        return json({ workspaces: [marsWorkspace] });
      }

      if (req.path === "/api/mars/projects/" && req.method === "GET") {
        return json({ projects: marsProjects });
      }

      if (req.path.match(/^\/api\/mars\/sessions\/\d+\/$/) && req.method === "GET") {
        return json({ session: marsSession, recommended_skills: [] });
      }

      if (req.path.match(/^\/api\/mars\/runs\/\d+\/$/) && req.method === "GET") {
        return json({ run: marsRun });
      }

      if (req.path.match(/^\/api\/mars\/runs\/\d+\/events\/$/) && req.method === "GET") {
        return json({
          events: [
            {
              id: 1,
              run_id: marsRun.id,
              event_type: "tests_completed",
              message: "Verification passed.",
              payload: {},
              created_at: FIXED_DATE,
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

      if (req.path === "/servers/api/agents/" && req.method === "GET") {
        return json({
          success: true,
          agents: options.agentList === "empty" ? [] : serverAgents,
          worker_states: options.agentList === "empty" ? {} : agentWorkerStates,
          runtime_overview: options.agentList === "empty" ? undefined : agentRuntimeOverview,
        });
      }

      if (req.path === "/servers/api/agents/dashboard/" && req.method === "GET") {
        return json({ success: true, active: [], recent: [] });
      }

      if (req.path === "/servers/api/agents/runs/901/report/" && req.method === "GET") {
        return json(agentRunReport);
      }

      if (req.path === "/servers/api/agents/runs/901/" && req.method === "GET") {
        return json({
          success: true,
          run: {
            id: 901,
            agent_id: 202,
            agent_name: "Patch Rollout",
            agent_type: "custom",
            agent_mode: "multi",
            server_name: "Web-01",
            status: "running",
            ai_analysis: "",
            commands_output: [],
            duration_ms: 125000,
            started_at: FIXED_DATE,
            completed_at: null,
            iterations_log: [],
            tool_calls: [],
            total_iterations: 4,
            connected_servers: [{ server_id: 1, server_name: "Web-01" }],
            final_report: "",
            pending_question: "",
            plan_tasks: agentRunPlanTasks,
            orchestrator_log: [],
          },
        });
      }

      if (req.path === "/servers/api/agents/runs/901/log/" && req.method === "GET") {
        return json({
          success: true,
          iterations_log: [],
          tool_calls: [],
          total_iterations: 4,
          status: "running",
          pending_question: "",
          plan_tasks: agentRunPlanTasks,
        });
      }

      if (req.path === "/servers/api/agents/runs/901/events/" && req.method === "GET") {
        return json({
          success: true,
          events: agentRunEvents,
        });
      }

      if (req.path === "/api/studio/pipelines/" && req.method === "GET") {
        return json(pipelines);
      }

      if (req.path.match(/^\/api\/studio\/pipelines\/\d+\/$/) && req.method === "GET") {
        const id = Number(req.path.split("/")[4]);
        return json(pipelines.find((pipeline) => pipeline.id === id) || pipelines[0]);
      }

      if ((req.path === "/api/studio/assistant/drafts/" || req.path === "/api/studio/pipeline-drafts/") && req.method === "GET") {
        return json(draftSessions);
      }

      if (
        (req.path.match(/^\/api\/studio\/assistant\/drafts\/\d+\/$/) ||
          req.path.match(/^\/api\/studio\/pipeline-drafts\/\d+\/$/)) &&
        req.method === "GET"
      ) {
        const id = Number(req.path.match(/\/(\d+)\/$/)?.[1] || 0);
        return json(draftSessions.find((draft) => draft.id === id) || draftSessions[0]);
      }

      if (req.path === "/api/studio/runs/" && req.method === "GET") {
        return json([]);
      }

      if (req.path === "/api/studio/skills/" && req.method === "GET") {
        return json([]);
      }

      if (req.path.match(/^\/api\/studio\/pipelines\/\d+\/run\/$/) && req.method === "POST") {
        return json({
          id: 7001,
          pipeline_id: Number(req.path.split("/")[4]),
          pipeline_name: "Nightly Patch",
          status: "running",
          node_states: {},
          nodes_snapshot: [],
          context: {},
          summary: "started",
          error: "",
          duration_seconds: null,
          started_at: FIXED_DATE,
          finished_at: null,
          created_at: FIXED_DATE,
          triggered_by: "admin",
          trigger_id: null,
          entry_node_id: String(req.body?.entry_node_id || ""),
          trigger_type: "manual",
          trigger_name: "Manual start",
          trigger_node_id: String(req.body?.entry_node_id || ""),
        });
      }

      if (req.path === "/api/studio/templates/" && req.method === "GET") {
        return json([]);
      }

      if (req.path === "/api/studio/notifications/" && req.method === "GET") {
        return json(notifications);
      }

      if (req.path === "/api/studio/notifications/" && req.method === "POST") {
        Object.assign(notifications, req.body || {});
        return json({ ok: true });
      }

      if (req.path === "/api/studio/notifications/test-telegram/" && req.method === "POST") {
        return json({ ok: true, message: "Telegram test sent" });
      }

      if (req.path === "/api/studio/notifications/test-email/" && req.method === "POST") {
        return json({ ok: true, message: "Email test sent" });
      }

      if (req.path === "/api/studio/mcp/" && req.method === "GET") {
        return json([
          {
            id: 501,
            name: "GitHub MCP",
            description: "Repository tools",
            transport: "stdio",
            command: "npx",
            args: ["-y", "@modelcontextprotocol/server-github"],
            env: {},
            url: "",
            is_shared: false,
            last_test_ok: true,
            last_test_at: FIXED_DATE,
            last_test_error: "",
          },
        ]);
      }

      if (req.path === "/api/studio/mcp/templates/" && req.method === "GET") {
        return json([]);
      }

      if (req.path === "/api/studio/agents/" && req.method === "GET") {
        return json([
          {
            id: 301,
            name: "Patch review",
            description: "Reviews package updates before a rollout.",
            icon: "P",
            system_prompt: "Review patch plans before execution.",
            instructions: "Check risk and report blockers.",
            model: "gpt-5.2",
            max_iterations: 8,
            allowed_tools: ["read_console", "analyze_output", "report"],
            sudo_policy: "disabled",
            skill_slugs: ["patch-review"],
            skills: [],
            mcp_servers: [{ id: 501, name: "GitHub MCP", transport: "stdio" }],
            server_scope: [{ id: 1, name: "Web-01" }],
            owner_username: "admin",
            is_owner: true,
            can_edit: true,
            is_shared: true,
            shared_user_ids: [2],
            created_at: FIXED_DATE,
            updated_at: FIXED_DATE,
          },
          {
            id: 302,
            name: "Incident responder",
            description: "Runs first-pass diagnostics during incidents.",
            icon: "I",
            system_prompt: "Diagnose incidents without destructive changes.",
            instructions: "Collect context, explain findings, and wait for approval.",
            model: "claude-4.5-sonnet",
            max_iterations: 12,
            allowed_tools: ["ssh_execute", "read_console", "report", "ask_user"],
            sudo_policy: "ask",
            skill_slugs: [],
            skills: [],
            mcp_servers: [],
            server_scope: [],
            owner_username: "ops-lead",
            is_owner: false,
            can_edit: false,
            is_shared: false,
            shared_user_ids: [],
            created_at: FIXED_DATE,
            updated_at: FIXED_DATE,
          },
        ]);
      }

      if (req.path === "/api/studio/servers/" && req.method === "GET") {
        return json([{ id: 1, name: "Web-01", host: "10.0.0.11" }]);
      }

      const pluginResponse = handlePluginMockRequest(req);
      if (pluginResponse) return pluginResponse;

      if (req.path === "/api/settings/" && req.method === "GET") {
        return json({ success: true, config: settingsConfig });
      }

      if (req.path === "/api/settings/" && req.method === "POST") {
        Object.assign(settingsConfig, req.body || {});
        return json({ success: true, message: "saved" });
      }

      if (req.path === "/api/settings/activity/" && req.method === "GET") {
        return json({
          success: true,
          events: [],
          summary: { total_events: 0, total_users: 0 },
        });
      }

      if (req.path === "/api/models/" && req.method === "GET") {
        return json({
          gemini: ["gemini-2.5-pro"],
          grok: ["grok-3-mini", "grok-3"],
          openai: ["gpt-5.2"],
          claude: ["claude-4.5-sonnet"],
          current: {
            default_provider: "grok",
            chat_gemini: "gemini-2.5-pro",
            chat_grok: "grok-3-mini",
            chat_openai: "gpt-5.2",
            chat_claude: "claude-4.5-sonnet",
          },
        });
      }

      if (req.path === "/servers/api/monitoring/config/" && req.method === "GET") {
        return json({
          thresholds: {
            cpu_warn: 70,
            cpu_crit: 90,
            mem_warn: 75,
            mem_crit: 92,
            disk_warn: 80,
            disk_crit: 95,
          },
          stats: {
            monitored_servers: servers.length,
            total_checks: 12,
            active_alerts: 0,
            last_check_at: FIXED_DATE,
          },
        });
      }

      if (req.path === "/servers/api/monitoring/config/" && req.method === "POST") {
        return json({ success: true });
      }

      if (req.path === "/api/access/users/" && req.method === "GET") {
        return json({ users: accessUsers });
      }

      if (req.path === "/api/access/groups/" && req.method === "GET") {
        return json({ groups: accessGroups });
      }

      if (req.path === "/api/access/permissions/" && req.method === "GET") {
        return json({
          permissions: accessPermissions,
          features: [
            { value: "servers", label: "Servers" },
            { value: "settings", label: "Settings" },
            { value: "orchestrator", label: "Orchestrator" },
          ],
        });
      }

      if (req.path === "/api/access/group-permissions/" && req.method === "GET") {
        return json({
          permissions: accessGroupPermissions,
          features: [
            { value: "servers", label: "Servers" },
            { value: "settings", label: "Settings" },
            { value: "orchestrator", label: "Orchestrator" },
          ],
        });
      }
}
