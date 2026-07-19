/**
 * Agent run status helpers. The backend reports "completed"/"failed"
 * (AgentRun model), while older API surfaces used "succeeded"/"success" —
 * treat all spellings uniformly everywhere the dashboard reasons about runs.
 */

export function isRunSuccess(status: string): boolean {
  return status === "completed" || status === "succeeded" || status === "success";
}

export function isRunFailure(status: string): boolean {
  return status === "failed" || status === "error" || status === "timeout";
}

export function isRunFinished(status: string): boolean {
  return isRunSuccess(status) || isRunFailure(status);
}
