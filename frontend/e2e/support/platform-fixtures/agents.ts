import { json } from "../apiHarness";
import { FIXED_DATE } from "../platformFixtureTypes";
import type { PlatformFixtureContext } from "../platformFixtureState";

/** Server agents list/dashboard/runs fixtures. */
export function handleAgentsFixture(req: any, ctx: PlatformFixtureContext) {
  const {
    options, serverAgents, agentWorkerStates, agentRuntimeOverview,
    agentRunReport, agentRunPlanTasks, agentRunEvents,
  } = ctx;
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
  return undefined;
}
