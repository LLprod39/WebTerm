import { json } from "./apiHarness";
import { AgentItem, AgentMode, FIXED_DATE, fullFeatures, normalizeAgent, runtimeOverview, workerState } from "./agentsMockShared";
import { applyDeliveryStatus } from "./agentDeliveryMocks";
import { buildRunDetail, buildRunLog, buildRunReport } from "./agentRunReportMocks";

export function makeAgentsHandler(
  initialAgents: AgentItem[] = [],
  options: {
    workerStates?: Record<string, unknown>;
    runtimeOverview?: Record<string, unknown>;
    completedRunIds?: number[];
    deliveryStatusByRunId?: Record<number, "sent" | "failed" | "skipped" | "pending">;
    waitingRunQuestions?: Record<number, string>;
    reportMutators?: Record<number, (report: ReturnType<typeof buildRunReport>) => void>;
  } = {},
) {
  const agents = initialAgents.map(normalizeAgent);
  const completedRunIds = new Set(options.completedRunIds || []);
  const deliveryStatusByRunId: Record<number, "sent" | "failed" | "skipped" | "pending"> = { ...(options.deliveryStatusByRunId || {}) };
  const workerStates = options.workerStates || {
    scheduled_agents: workerState(),
  };
  const runtime = options.runtimeOverview || runtimeOverview({
    summary: {
      configured_agents: agents.length,
      active_runs: agents.filter((agent) => agent.active_run_id).length,
      pending_runs: 0,
      running_runs: agents.filter((agent) => agent.active_run_id).length,
      waiting_runs: 0,
      queued_dispatches: 0,
      claimed_dispatches: 0,
      scheduled_agents: agents.filter((agent) => agent.schedule_minutes > 0).length,
      scheduled_due_now: agents.filter((agent) => agent.schedule_minutes > 0).length,
      issues: 0,
    },
    workers: workerStates,
  });
  let nextAgentId = 300;
  let nextRunId = 700;
  const runDetails = new Map<number, ReturnType<typeof buildRunDetail>>();
  const runLogs = new Map<number, ReturnType<typeof buildRunLog>>();

  for (const agent of agents) {
    if (agent.active_run_id) {
      const detail = buildRunDetail(agent.active_run_id, agent.id, agent.name);
      const pendingQuestion = options.waitingRunQuestions?.[agent.active_run_id];
      if (pendingQuestion) {
        detail.run.status = "waiting";
        detail.run.pending_question = pendingQuestion;
      }
      runDetails.set(agent.active_run_id, detail);
      runLogs.set(agent.active_run_id, buildRunLog(detail.run.status));
    }
    if (agent.last_run_id && completedRunIds.has(agent.last_run_id)) {
      const detail = buildRunDetail(agent.last_run_id, agent.id, agent.name);
      detail.run.status = "completed";
      detail.run.completed_at = FIXED_DATE;
      detail.run.final_report = "# Final\n\n## Что произошло\n- Агент завершил проверку.\n";
      runDetails.set(agent.last_run_id, detail);
      runLogs.set(agent.last_run_id, buildRunLog("completed"));
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

    if (req.path === "/api/settings/readiness/" && req.method === "GET") {
      return json({ success: true, status: "ready", checks: [] });
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

    if (req.path === "/api/studio/skills/" && req.method === "GET") {
      return json([]);
    }

    if (req.path === "/servers/api/agents/" && req.method === "GET") {
      return json({ success: true, agents, worker_states: workerStates, runtime_overview: runtime });
    }

    if (req.path === "/servers/api/agents/runtime/cleanup-stale/" && req.method === "POST") {
      const runtimeRecord = runtime as Record<string, any>;
      const items = runtimeRecord.items || {};
      const staleRuns = Array.isArray(items.stale_candidates) ? items.stale_candidates : [];
      const staleRunIds = new Set(staleRuns.map((item: any) => Number(item.run_id)));
      const cleaned = staleRunIds.size;
      for (const agent of agents) {
        if (agent.active_run_id && staleRunIds.has(agent.active_run_id)) {
          agent.active_run_id = null;
          agent.last_run_id = agent.last_run_id || Array.from(staleRunIds)[0] || null;
        }
      }
      for (const runId of staleRunIds) {
        const runDetail = runDetails.get(runId);
        if (runDetail) {
          runDetail.run.status = "failed";
          runDetail.run.completed_at = FIXED_DATE;
        }
        const runLog = runLogs.get(runId);
        if (runLog) {
          runLog.status = "failed";
        }
      }
      runtimeRecord.summary = {
        ...(runtimeRecord.summary || {}),
        active_runs: Math.max(0, Number(runtimeRecord.summary?.active_runs || 0) - cleaned),
        pending_runs: 0,
        queued_dispatches: 0,
      };
      runtimeRecord.items = {
        ...items,
        active_runs: (items.active_runs || []).filter((item: any) => !staleRunIds.has(Number(item.run_id))),
        queued_dispatches: (items.queued_dispatches || []).filter((item: any) => !staleRunIds.has(Number(item.run_id))),
        scheduled_due: (items.scheduled_due || []).map((item: any) =>
          staleRunIds.has(Number(item.active_run_id))
            ? { ...item, active_run_id: null, active_run_status: "" }
            : item,
        ),
        stale_candidates: [],
      };
      return json({
        success: true,
        cleanup: {
          stale_seconds: 60,
          scanned: cleaned,
          cleaned,
          canceled_dispatches: cleaned,
          runs: staleRuns.map((item: any) => ({
            run_id: item.run_id,
            agent_id: item.agent_id,
            agent_name: item.agent_name,
            status: "failed",
            age_seconds: item.age_seconds,
            canceled_dispatches: 1,
          })),
          generated_at: FIXED_DATE,
        },
        runtime_overview: runtime,
      });
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
        schedule_config: { mode: "manual" },
        max_iterations: Number(req.body?.max_iterations || 20),
        goal: String(req.body?.goal || ""),
        is_enabled: true,
        sudo_policy: "ask",
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

      const miniDetail = buildRunDetail(runId, target.id, target.name);
      miniDetail.run.status = "completed";
      miniDetail.run.completed_at = FIXED_DATE;
      miniDetail.run.duration_ms = 1_250;
      miniDetail.run.ai_analysis = "# Summary\nMini audit succeeded";
      miniDetail.run.final_report = "# Summary\nMini audit succeeded\n\n## Full evidence\n- Full-only evidence line";
      miniDetail.run.commands_output = [
        {
          cmd: "hostname",
          stdout: "web-01",
          stderr: "",
          exit_code: 0,
          duration_ms: 40,
        },
      ];
      runDetails.set(runId, miniDetail);
      runLogs.set(runId, buildRunLog("completed"));

      return json({
        success: true,
        run_id: runId,
        runs: [
          {
            run_id: runId,
            server_name: "Web-01",
            status: "completed",
            ai_analysis: miniDetail.run.ai_analysis,
            duration_ms: miniDetail.run.duration_ms,
            commands_output: miniDetail.run.commands_output,
            total_iterations: 1,
            final_report: miniDetail.run.final_report,
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

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/report\/$/) && req.method === "GET") {
      const runId = Number(req.path.split("/")[5]);
      const detail = runDetails.get(runId);
      if (!detail) return json({ success: false }, 404);
      const report = buildRunReport(detail);
      applyDeliveryStatus(report, deliveryStatusByRunId[runId]);
      options.reportMutators?.[runId]?.(report);
      return json(report);
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/report\/deliver\/$/) && req.method === "POST") {
      const runId = Number(req.path.split("/")[5]);
      const detail = runDetails.get(runId);
      if (!detail) return json({ success: false }, 404);
      if (detail.run.status !== "completed") return json({ success: false, error: "Report is not ready" }, 409);
      deliveryStatusByRunId[runId] = "sent";
      const report = buildRunReport(detail);
      applyDeliveryStatus(report, "sent");
      return json(report);
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/reply\/$/) && req.method === "POST") {
      const runId = Number(req.path.split("/")[5]);
      const detail = runDetails.get(runId);
      if (!detail || detail.run.status !== "waiting") return json({ success: false, error: "Run not found or not waiting" }, 404);
      const answer = String((req.body as { answer?: unknown } | null)?.answer || "").trim();
      if (!answer) return json({ success: false, error: "Answer required" }, 400);
      detail.run.status = "running";
      detail.run.pending_question = "";
      (detail.run as typeof detail.run & { user_reply?: string }).user_reply = answer;
      const runLog = runLogs.get(runId);
      if (runLog) {
        runLog.status = "running";
        runLog.pending_question = "";
      }
      return json({ success: true });
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/artifacts\/download-all\/$/) && req.method === "GET") {
      const runId = Number(req.path.split("/")[5]);
      return json("fake zip bundle", runDetails.has(runId) ? 200 : 404);
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/artifacts\/\d+\/download\/$/) && req.method === "GET") {
      const runId = Number(req.path.split("/")[5]);
      return json("# Final\n", runDetails.has(runId) ? 200 : 404);
    }

    if (req.path.match(/^\/servers\/api\/agents\/runs\/\d+\/log\/$/) && req.method === "GET") {
      const runId = Number(req.path.split("/")[5]);
      const log = runLogs.get(runId);
      return log ? json(log) : json({ success: false }, 404);
    }
  };
}
