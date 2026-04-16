/**
 * src/api/agents.ts — Server Agents API.
 *
 * Migration target for functions from src/lib/api.ts related to:
 *   - Agent CRUD (fetchAgents, createAgent, updateAgent, deleteAgent)
 *   - Agent runs (startAgentRun, stopAgentRun, fetchAgentRuns)
 *   - Run events (fetchRunEvents, fetchRunLog, replyToRun)
 *   - Plan approval (approvePlan, updateTask, refineTask)
 *   - Schedule overview and dispatch
 *
 * Status: re-exported from src/api/index.ts (pending migration)
 */
