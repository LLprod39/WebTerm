import { expect, test } from "@playwright/test";
import { installApiHarness, json } from "./support/apiHarness";

const fullFeatures = {
  servers: true,
  dashboard: true,
  agents: true,
  studio: true,
  settings: true,
  orchestrator: true,
};

const FIXED_DATE = "2026-03-01T08:00:00.000Z";

type AgentMode = "mini" | "full" | "multi";

type AgentItem = {
  id: number;
  name: string;
  mode: AgentMode;
  agent_type: string;
  agent_type_display: string;
  server_count: number;
  last_run_at: string | null;
  schedule_minutes: number;
  max_iterations: number;
  goal: string;
  active_run_id: number | null;
  last_run_id: number | null;
};

function buildRunDetail(runId: number, agentId: number, agentName: string) {
  return {
    success: true,
    run: {
      id: runId,
      agent_id: agentId,
      agent_name: agentName,
      agent_type: "custom",
      agent_mode: "full",
      server_name: "Web-01",
      status: "running",
      ai_analysis: "",
      commands_output: [],
      duration_ms: 5_000,
      started_at: FIXED_DATE,
      completed_at: null,
      iterations_log: [],
      tool_calls: [],
      total_iterations: 3,
      connected_servers: [{ server_id: 1, server_name: "Web-01" }],
      final_report: "",
      pending_question: "",
      plan_tasks: [],
      orchestrator_log: [],
    },
  };
}

function buildRunLog(status = "running") {
  return {
    success: true,
    iterations_log: [],
    tool_calls: [],
    total_iterations: 3,
    status,
    pending_question: "",
    plan_tasks: [],
  };
}

function makeAgentsHandler(initialAgents: AgentItem[] = []) {
  const agents = [...initialAgents];
  let nextAgentId = 300;
  let nextRunId = 700;
  const runDetails = new Map<number, ReturnType<typeof buildRunDetail>>();
  const runLogs = new Map<number, ReturnType<typeof buildRunLog>>();

  for (const agent of agents) {
    if (agent.active_run_id) {
      runDetails.set(agent.active_run_id, buildRunDetail(agent.active_run_id, agent.id, agent.name));
      runLogs.set(agent.active_run_id, buildRunLog());
    }
  }

  return async (req: any) => {
    if (req.path === "/api/auth/session/" && req.method === "GET") {
      return json({
        authenticated: true,
        user: {
          id: 1,
          username: "admin",
          email: "admin@example.com",
          is_staff: true,
          features: fullFeatures,
        },
      });
    }

    if (req.path === "/servers/api/frontend/bootstrap/" && req.method === "GET") {
      return json({
        success: true,
        servers: [
          {
            id: 1,
            name: "Web-01",
            host: "10.0.0.11",
            port: 22,
            username: "root",
            server_type: "ssh",
            rdp: false,
            status: "online",
            group_id: 11,
            group_name: "Core",
            is_shared: false,
            can_edit: true,
            share_context_enabled: true,
            shared_by_username: "",
            terminal_path: "/servers/1/terminal",
            minimal_terminal_path: "/servers/1/terminal/minimal",
            last_connected: null,
          },
        ],
        groups: [{ id: 11, name: "Core", server_count: 1 }],
        stats: { owned: 1, shared: 0, total: 1 },
        recent_activity: [],
      });
    }

    if (req.path === "/servers/api/agents/templates/" && req.method === "GET") {
      return json({ success: true, templates: [] });
    }

    if (req.path === "/servers/api/agents/dashboard/" && req.method === "GET") {
      return json({ success: true, active: [], recent: [] });
    }

    if (req.path === "/servers/api/agents/" && req.method === "GET") {
      return json({ success: true, agents });
    }

    if (req.path === "/servers/api/agents/create/" && req.method === "POST") {
      const created: AgentItem = {
        id: nextAgentId++,
        name: String(req.body?.name || "Custom Agent"),
        mode: (req.body?.mode || "mini") as AgentMode,
        agent_type: String(req.body?.agent_type || "custom"),
        agent_type_display: "Custom",
        server_count: Array.isArray(req.body?.server_ids) ? req.body.server_ids.length : 0,
        last_run_at: null,
        schedule_minutes: Number(req.body?.schedule_minutes || 0),
        max_iterations: Number(req.body?.max_iterations || 20),
        goal: String(req.body?.goal || ""),
        active_run_id: null,
        last_run_id: null,
      };
      agents.push(created);
      return json({ success: true, id: created.id });
    }

    if (req.path.match(/^\/servers\/api\/agents\/\d+\/run\/$/) && req.method === "POST") {
      const agentId = Number(req.path.split("/")[4]);
      const target = agents.find((agent) => agent.id === agentId);
      if (!target) {
        return json({ success: false, runs: [] }, 404);
      }

      const runId = nextRunId++;
      target.last_run_id = runId;
      target.last_run_at = FIXED_DATE;

      if (target.mode === "full" || target.mode === "multi") {
        target.active_run_id = runId;
        runDetails.set(runId, buildRunDetail(runId, target.id, target.name));
        runLogs.set(runId, buildRunLog());
        return json({ success: true, runs: [], run_id: runId });
      }

      return json({
        success: true,
        run_id: runId,
        runs: [
          {
            run_id: runId,
            server_name: "Web-01",
            status: "completed",
            ai_analysis: "# Summary\nMini audit succeeded",
            duration_ms: 1_250,
            commands_output: [
              {
                cmd: "hostname",
                stdout: "web-01",
                stderr: "",
                exit_code: 0,
                duration_ms: 40,
              },
            ],
            total_iterations: 1,
            final_report: "# Summary\nMini audit succeeded",
          },
        ],
      });
    }

    if (req.path.match(/^\/servers\/api\/agents\/\d+\/stop\/$/) && req.method === "POST") {
      const agentId = Number(req.path.split("/")[4]);
      const target = agents.find((agent) => agent.id === agentId);
      if (target?.active_run_id) {
        const runId = target.active_run_id;
        target.active_run_id = null;
        const runDetail = runDetails.get(runId);
        if (runDetail) {
          runDetail.run.status = "stopped";
          runDetail.run.completed_at = FIXED_DATE;
        }
        const runLog = runLogs.get(runId);
        if (runLog) {
          runLog.status = "stopped";
        }
      }
      return json({ success: true });
    }

    if (req.path.match(/^\/servers\/api\/agents\/\d+\/delete\/$/) && req.method === "POST") {
      const agentId = Number(req.path.split("/")[4]);
      const index = agents.findIndex((agent) => agent.id === agentId);
      if (index >= 0) {
        agents.splice(index, 1);
      }
      return json({ success: true });
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/$/) && req.method === "GET") {
      const runId = Number(req.path.split("/")[5]);
      const detail = runDetails.get(runId);
      return detail ? json(detail) : json({ success: false }, 404);
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/log\/$/) && req.method === "GET") {
      const runId = Number(req.path.split("/")[5]);
      const log = runLogs.get(runId);
      return log ? json(log) : json({ success: false }, 404);
    }
  };
}

test("creates and runs a mini agent from the agents page", async ({ page }) => {
  const harness = await installApiHarness(page, makeAgentsHandler());

  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Agents" })).toBeVisible();
  await page.getByRole("button", { name: "Create your first agent" }).click();

  const createDialog = page.getByRole("dialog");
  await createDialog.getByRole("button", { name: /Build from scratch/i }).click();

  const configDialog = page.getByRole("dialog");
  await expect(configDialog.getByText("Configure Mini Agent")).toBeVisible();
  await configDialog.getByPlaceholder("My Agent").fill("Disk Audit");
  await configDialog.locator("textarea").nth(0).fill("hostname\nuptime");
  await configDialog.locator("textarea").nth(1).fill("Summarize the result");
  await configDialog.getByRole("button", { name: "Web-01" }).click();
  await configDialog.getByRole("button", { name: "Create Agent" }).click();

  await expect(page.getByText("Disk Audit")).toBeVisible();
  expect(harness.getCalls("/servers/api/agents/create/", "POST").length).toBe(1);

  await page.getByRole("button", { name: /^Run$/ }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/300/run/", "POST").length).toBe(1);
  await expect(page.getByText("Mini audit succeeded")).toBeVisible();
});

test("opens a live agent run and sends stop from the run page", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler([
      {
        id: 202,
        name: "Patch Rollout",
        mode: "full",
        agent_type: "custom",
        agent_type_display: "Custom",
        server_count: 1,
        last_run_at: FIXED_DATE,
        schedule_minutes: 0,
        max_iterations: 20,
        goal: "Roll out production patch safely",
        active_run_id: 901,
        last_run_id: 901,
      },
    ]),
  );

  await page.goto("/agents");
  await expect(page.getByText("Patch Rollout")).toBeVisible();
  await page.getByRole("link", { name: "Watch" }).click();

  await expect(page).toHaveURL(/\/agents\/run\/901$/);
  await expect(page.locator("h1", { hasText: "Patch Rollout" })).toBeVisible();

  await page.getByRole("button", { name: /Stop/i }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/202/stop/", "POST").length).toBe(1);
});
