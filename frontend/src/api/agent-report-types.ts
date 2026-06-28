import type { AgentRunDispatchRecord, AgentRunEventItem } from "@/api/agent-types";

export type AgentRunReportSeverity = "success" | "info" | "warning" | "high" | "critical" | "fatal";
export type AgentRunReportPhase =
  | "queued"
  | "starting"
  | "planning"
  | "plan_review"
  | "executing"
  | "synthesizing"
  | "delivery"
  | "waiting"
  | "ready"
  | "failed"
  | "stopped"
  | "activity"
  | (string & {});

export interface AgentRunReportState {
  phase: AgentRunReportPhase;
  report_ready: boolean;
  artifacts_ready: boolean;
  is_terminal: boolean;
  headline: string;
  description: string;
  current_step: string;
  next_expected: string;
  progress: number;
  execution_state?: AgentRunExecutionState;
}

export interface AgentRunArtifactState {
  ready: boolean;
  title: string;
  description: string;
  empty_title: string;
  empty_description: string;
  bundle_ready?: boolean;
  bundle_download_url?: string;
  artifact_count?: number;
  total_size_bytes?: number;
  total_size_label?: string;
  manifest_ready?: boolean;
  manifest_name?: string;
}

export interface AgentRunExecutionWorkerState {
  worker_kind: string;
  worker_key: string;
  status: string;
  is_stale: boolean;
  hostname: string;
  pid: number | null;
  command?: string;
  heartbeat_at: string | null;
  heartbeat_age_ms?: number | null;
  lease_expires_at: string | null;
  last_started_at: string | null;
  last_stopped_at: string | null;
  last_cycle_started_at: string | null;
  last_cycle_finished_at: string | null;
  last_summary: Record<string, unknown>;
  last_error: string;
}

export interface AgentRunExecutionState {
  status: string;
  severity: AgentRunReportSeverity;
  title: string;
  description: string;
  next_action: string;
  dispatch: AgentRunDispatchRecord | null;
  worker: AgentRunExecutionWorkerState;
  queued_age_ms: number | null;
  queued_for: string;
  heartbeat_age_ms: number | null;
  heartbeat_age: string;
  runtime_age_ms: number | null;
  runtime_age: string;
  stale_after_ms: number;
  stale_after: string;
  is_stale_candidate: boolean;
  can_cleanup: boolean;
  lease_expired: boolean;
  worker_ready: boolean;
  commands?: {
    execution_worker?: string;
    ops_supervisor?: string;
  };
}

export interface AgentRunReportKpi {
  id: string;
  label: string;
  value: string;
  hint: string;
  severity: AgentRunReportSeverity;
}

export interface AgentRunReportFinding {
  id: string;
  title: string;
  description: string;
  severity: AgentRunReportSeverity;
  source?: string;
}

export interface AgentRunReportRecommendation {
  id: string;
  priority: "P0" | "P1" | "P2" | string;
  title: string;
  description: string;
  owner: string;
  done: boolean;
}

export interface AgentRunReportBody {
  schema_version: number;
  title: string;
  subtitle: string;
  status: string;
  status_label: string;
  severity: AgentRunReportSeverity;
  summary: string;
  root_cause: string | null;
  markdown: string;
  meta: {
    server: string;
    window: string;
    analysis_duration: string;
    finished_at: string | null;
    started_at: string | null;
  };
  kpis: AgentRunReportKpi[];
  findings: AgentRunReportFinding[];
  risks: AgentRunReportFinding[];
  recommendations: AgentRunReportRecommendation[];
}

export interface AgentRunReportEvent extends AgentRunEventItem {
  severity: AgentRunReportSeverity;
  source: string;
  title: string;
  summary: string;
  phase: AgentRunReportPhase;
  category: string;
  important: boolean;
}

export interface AgentRunReportEventSummary {
  total: number;
  important: number;
  problems: number;
  debug: number;
  categories: Record<string, number>;
  severities: Record<string, number>;
  latest: AgentRunReportEvent | null;
  latest_important: AgentRunReportEvent | null;
}

export interface AgentRunReportEventGroup {
  phase: AgentRunReportPhase;
  label: string;
  count: number;
  important: number;
  problems: number;
  first_at: string | null;
  last_at: string | null;
  events: AgentRunReportEvent[];
}

export interface AgentRunReportDeliveryState {
  enabled: boolean;
  channels: string[];
  channel: string;
  target: string;
  status: string;
  severity: AgentRunReportSeverity;
  label: string;
  title: string;
  description: string;
  next_action: string;
  updated_at: string | null;
  event: AgentRunReportEvent | null;
}

export interface AgentRunReportRun {
  id: number;
  agent_id: number;
  agent_name: string;
  agent_type: string;
  agent_mode: string;
  server_name: string;
  server_id: number | null;
  status: string;
  duration_ms: number;
  started_at: string | null;
  completed_at: string | null;
  total_iterations: number;
  connected_servers: Array<{ server_id: number; server_name: string }>;
  pending_question: string;
  dispatch?: AgentRunDispatchRecord | null;
}

export interface AgentRunReportLog {
  id: string;
  index: number;
  kind: string;
  title: string;
  command: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  duration_ms: number;
  status: string;
  severity: AgentRunReportSeverity;
  timestamp: string | null;
}

export interface AgentRunReportStep {
  id: string;
  index: number;
  title: string;
  description: string;
  command: string;
  status: string;
  severity: AgentRunReportSeverity;
  status_label: string;
  duration_ms: number;
  details: string;
  error: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface AgentRunReportArtifact {
  id: string;
  artifact_id: number | null;
  name: string;
  type: string;
  description: string;
  size_bytes: number;
  original_size_bytes?: number;
  size_label: string;
  created_at: string | null;
  download_kind: "inline" | string;
  download_url: string;
  content_type: string;
  content: string;
  truncated: boolean;
  checksum_sha256?: string;
  metadata?: Record<string, unknown>;
}

export interface AgentRunReportResponse {
  success: boolean;
  schema_version: number;
  run: AgentRunReportRun;
  report: AgentRunReportBody;
  report_state: AgentRunReportState;
  artifact_state: AgentRunArtifactState;
  delivery_state?: AgentRunReportDeliveryState;
  event_summary?: AgentRunReportEventSummary;
  event_groups?: AgentRunReportEventGroup[];
  events: AgentRunReportEvent[];
  logs: AgentRunReportLog[];
  agent_steps: AgentRunReportStep[];
  artifacts: AgentRunReportArtifact[];
  generated_at: string;
}
