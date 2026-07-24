/** Agents dashboard + schedules demo fallbacks (before playbooks). */
export function demoAgentsEarlyFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
  // Agents
  if (path.includes("/servers/api/agents/dashboard")) {
    const now = Date.now();
    const minutesAgo = (m: number) => new Date(now - m * 60_000).toISOString();
    const baseRun = {
      agent_mode: "full", agent_type: "deploy_watcher", pending_question: "",
      connected_servers: [], ai_analysis: "", final_report: "", commands_output: [],
    };
    const finished = (
      id: number, agentName: string, serverId: number, serverName: string,
      status: string, startedMinAgo: number, durationSec: number, iterations: number,
    ) => ({
      ...baseRun,
      id, agent_id: 1, agent_name: agentName, server_id: serverId, server_name: serverName,
      status, total_iterations: iterations, duration_ms: durationSec * 1000,
      started_at: minutesAgo(startedMinAgo), completed_at: minutesAgo(startedMinAgo - Math.ceil(durationSec / 60)),
    });
    return {
      success: true,
      active: [
        {
          ...baseRun,
          id: 120, agent_id: 1, agent_name: "Deploy Watcher", server_id: 1, server_name: "web-prod-01",
          status: "running", total_iterations: 3, duration_ms: 0,
          started_at: minutesAgo(4), completed_at: null,
        },
      ],
      recent: [
        finished(119, "Health Check", 2, "db-prod-01", "completed", 42, 38, 5),
        finished(118, "Deploy Watcher", 1, "web-prod-01", "completed", 95, 61, 7),
        finished(117, "Log Auditor", 2, "db-prod-01", "failed", 150, 24, 3),
        finished(116, "Health Check", 1, "web-prod-01", "completed", 210, 33, 5),
        finished(115, "Deploy Watcher", 1, "web-prod-01", "completed", 300, 58, 6),
        finished(114, "Backup Verifier", 2, "db-prod-01", "completed", 420, 112, 9),
        finished(113, "Health Check", 3, "staging-01", "failed", 510, 19, 2),
        finished(112, "Deploy Watcher", 1, "web-prod-01", "completed", 640, 66, 7),
        finished(111, "Log Auditor", 2, "db-prod-01", "completed", 760, 29, 4),
        finished(110, "Health Check", 1, "web-prod-01", "completed", 900, 31, 5),
      ],
    } as T;
  }
  if (path.includes("/servers/api/agents/schedules/dispatch/")) {
    return {
      success: true,
      summary: {
        scanned: 1,
        due: 1,
        launched_agents: 1,
        runs_created: 1,
        background_runs: 1,
        mini_runs: 0,
        skipped: 0,
        skip_reasons: {
          not_due: 0,
          no_servers: 0,
          active_run: 0,
          limit: 0,
          launch_rejected: 0,
          error: 0,
        },
        errors: [],
      },
      generated_at: new Date().toISOString(),
    } as T;
  }
  if (path.includes("/servers/api/agents/schedules/")) {
    return {
      success: true,
      summary: {
        total_scheduled: 1,
        enabled: 1,
        paused: 0,
        due_now: 1,
        active_runs: 0,
      },
      generated_at: new Date().toISOString(),
      scheduled_agents: [
        {
          id: 1,
          name: "Demo Deploy Watcher",
          mode: "full",
          mode_display: "Full Agent (ReAct)",
          agent_type: "deploy_watcher",
          agent_type_display: "Deploy Watcher",
          server_count: 1,
          server_names: ["demo-linux"],
          schedule_minutes: 15,
          is_enabled: true,
          commands: [],
          ai_prompt: "Track deploy drift",
          goal: "Check services after deploy and verify health.",
          system_prompt: "",
          max_iterations: 8,
          allow_multi_server: false,
          last_run_at: new Date(Date.now() - 60 * 60_000).toISOString(),
          last_run_status: "completed",
          last_run_id: 1,
          active_run_id: null,
          schedule_state: "due",
          due_now: true,
          next_due_at: new Date(Date.now() - 30 * 60_000).toISOString(),
          next_due_in_seconds: 0,
        },
      ],
    } as T;
  }
  return undefined;
}
