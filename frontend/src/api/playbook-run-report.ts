import { apiFetch } from "@/lib/api";

import type { PlaybookRunStatus, PlaybookRunSummary } from "./playbooks";

export interface PlaybookRunReportProgress {
  state_version: number;
  phase: string;
  total_kind: "exact" | "estimated" | "unknown" | string;
  completed: number | null;
  total: number | null;
  percent: number | null;
  indeterminate: boolean;
  engine: string;
  play: string;
  task: string;
  task_number: number | null;
  hosts_seen: number;
  hosts_total: number;
  counts: Record<string, number>;
  is_terminal: boolean;
  log_start_cursor: number;
  log_end_cursor: number;
  log_truncated: boolean;
}

export interface PlaybookRunReportHost {
  server_id: number | null;
  server_name: string;
  host: string;
  status: string;
  task_counts: {
    total: number;
    ok: number;
    changed: number;
    failed: number;
    unreachable: number;
    skipped: number;
    cancelled: number;
    running: number;
    pending: number;
  };
  first_failure: { task_id: string; task_name: string; message: string } | null;
  detail_url: string;
}

export interface PlaybookRunReportFailure {
  code: string;
  message: string;
  host_id: number | null;
  host_name: string;
  task_id: string;
  task_name: string;
  retryable: boolean;
  suggested_action: string;
}

export interface PlaybookRunReport {
  schema_version: number;
  run: {
    id: number;
    playbook_id: number | null;
    playbook_name: string;
    revision_id: number | null;
    validation_id: number | null;
    binding_profile_id: number | null;
    binding_profile_name: string;
    status: PlaybookRunStatus;
    cancel_requested: boolean;
    target_count: number;
    options: Record<string, unknown>;
    created_at: string | null;
    started_at: string | null;
    finished_at: string | null;
    duration_ms: number | null;
  };
  progress: PlaybookRunReportProgress;
  summary: PlaybookRunSummary & Record<string, unknown>;
  failure: PlaybookRunReportFailure | null;
  hosts: PlaybookRunReportHost[];
  dispatch: null | {
    status: string;
    queued_at: string | null;
    claimed_at: string | null;
    completed_at: string | null;
    attempt_count: number;
    heartbeat_stale: boolean;
    mutation_safe_to_retry: boolean;
  };
  log: { start_cursor: number; end_cursor: number; truncated: boolean; url: string };
  actions: {
    can_cancel: boolean;
    can_retry_failed: boolean;
    can_export: boolean;
    retry_context_url: string;
    export_url: string;
  };
}

export interface PlaybookRunHostDetail extends PlaybookRunReportHost {
  tasks: Array<{
    task_id: string;
    name: string;
    command: string;
    description: string;
    status: string;
    exit_code: number | null;
    output: string;
  }>;
}

export interface PlaybookRunRetryContext {
  run_id: number;
  can_retry: boolean;
  blockers: Array<{ code: string; message: string }>;
  playbook_id: number | null;
  revision_id: number | null;
  validation_id: number | null;
  binding_profile_id: number | null;
  failed_server_ids: number[];
  options: Record<string, unknown>;
  required_variable_names: string[];
  managed_variable_names: string[];
  values_redacted: boolean;
  rerun_endpoint: string;
}

export interface PlaybookRunHistoryItem {
  id: number;
  playbook_id: number | null;
  playbook_name: string;
  status: PlaybookRunStatus;
  phase: string;
  state_version: number;
  total_kind: string;
  progress_percent: number | null;
  summary: PlaybookRunSummary & Record<string, unknown>;
  failure: PlaybookRunReportFailure | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface PlaybookRunHistoryResponse {
  success: true;
  items: PlaybookRunHistoryItem[];
  page: { limit: number; next_cursor: number | null; has_more: boolean };
  filters: { status: string[]; playbook_id: number | null; q: string };
}

const reportCache = new Map<number, { etag: string; report: PlaybookRunReport }>();

export async function getPlaybookRunReport(runId: number) {
  const apiBase = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");
  const cached = reportCache.get(runId);
  const response = await fetch(`${apiBase}/servers/api/playbooks/runs/${runId}/report/`, {
    credentials: "include",
    headers: cached?.etag ? { "If-None-Match": cached.etag } : undefined,
  });
  if (response.status === 304 && cached) return { success: true as const, report: cached.report };
  if (!response.ok) throw new Error(await reportError(response));
  const payload = await response.json() as { success: true; report: PlaybookRunReport };
  const etag = response.headers.get("etag") || "";
  if (etag) reportCache.set(runId, { etag, report: payload.report });
  return payload;
}

export async function getPlaybookRunReportHost(runId: number, serverId: number) {
  return apiFetch<{ success: true; host: PlaybookRunHostDetail }>(
    `/servers/api/playbooks/runs/${runId}/hosts/${serverId}/`,
  );
}

export async function getPlaybookRunReportLog(runId: number, after = 0, limitChars = 120_000) {
  const query = new URLSearchParams({ after: String(after), limit_chars: String(limitChars) });
  return apiFetch<{
    success: true;
    text: string;
    cursor: number;
    next_cursor: number;
    start_cursor: number;
    end_cursor: number;
    has_more: boolean;
    truncated: boolean;
    reset_required: boolean;
  }>(`/servers/api/playbooks/runs/${runId}/log/?${query}`);
}

export async function getPlaybookRunRetryContext(runId: number) {
  return apiFetch<{ success: true; retry_context: PlaybookRunRetryContext }>(
    `/servers/api/playbooks/runs/${runId}/retry-context/`,
  );
}

export async function listPlaybookRunHistory(filters: {
  cursor?: number;
  limit?: number;
  status?: string[];
  playbookId?: number;
  q?: string;
} = {}) {
  const query = new URLSearchParams();
  if (filters.cursor) query.set("cursor", String(filters.cursor));
  query.set("limit", String(filters.limit || 25));
  if (filters.status?.length) query.set("status", filters.status.join(","));
  if (filters.playbookId) query.set("playbook_id", String(filters.playbookId));
  if (filters.q?.trim()) query.set("q", filters.q.trim());
  return apiFetch<PlaybookRunHistoryResponse>(`/servers/api/playbooks/runs/history/?${query}`);
}

export async function downloadPlaybookRunReport(runId: number) {
  const apiBase = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");
  const response = await fetch(`${apiBase}/servers/api/playbooks/runs/${runId}/export/`, { credentials: "include" });
  if (!response.ok) throw new Error(`Report export failed (HTTP ${response.status})`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `ansible-run-${runId}-report.zip`;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function reportError(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { error?: unknown };
    if (typeof payload.error === "string" && payload.error) return payload.error;
  } catch {
    // A stable HTTP fallback is more useful than a JSON parsing error.
  }
  return `Run report failed (HTTP ${response.status})`;
}
