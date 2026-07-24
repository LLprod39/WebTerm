import { json } from "../apiHarness";
import { FIXED_DATE } from "../platformFixtureTypes";
import type { PlatformFixtureContext } from "../platformFixtureState";

/** Studio pipelines/drafts/runs/skills/notifications/mcp/agents fixtures. */
export function handleStudioFixture(req: any, ctx: PlatformFixtureContext) {
  const { pipelines, draftSessions, notifications } = ctx;
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
  return undefined;
}
