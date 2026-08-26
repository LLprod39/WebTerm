import type { AgentRunReportSeverity } from "@/api/agent-report-types";

export type AgentRunReportV2Severity = AgentRunReportSeverity;
export type AgentRunEvidenceView = "activity" | "events" | "outputs" | "artifacts" | "document";
export type AgentRunPageDirection = "older" | "newer";

export interface AgentRunReportV2Run {
  id: number;
  agent_id: number;
  agent_name: string;
  agent_type: string;
  agent_mode: string;
  server_id: number | null;
  server_name: string;
}

export interface AgentRunReportV2Lifecycle {
  status: string;
  label: string;
  is_active: boolean;
  is_terminal: boolean;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number;
  can_cleanup?: boolean;
}

export interface AgentRunReportV2Outcome {
  status: string;
  label: string;
  reason: string;
  exit_reason: string;
  source: string;
  reason_source?: string;
  severity: AgentRunReportV2Severity;
  details: unknown;
}

export interface AgentRunReportV2Coverage {
  checked: number | null;
  total: number | null;
  unit: string;
  ratio: number | null;
}

export interface AgentRunReportV2EvidenceState {
  status: string;
  label: string;
  summary: string;
  coverage: AgentRunReportV2Coverage;
}

export interface AgentRunReportV2Generation {
  status: string;
  label: string;
  ready: boolean;
  error: string;
  generated_at: string | null;
}

export interface AgentRunReportV2Delivery {
  enabled: boolean;
  configured: boolean;
  channel: string;
  status: string;
  label: string;
  description: string;
  target: string;
  severity: AgentRunReportV2Severity;
  can_retry: boolean;
  blocked_reason: string;
  setup_url: string;
  next_action: string;
  updated_at: string | null;
  attempt_id?: string | number | null;
  attempt_count: number;
  last_attempt_at: string | null;
}

export interface AgentRunReportV2EvidenceRef {
  kind: "event" | "activity" | "document" | "artifact";
  ref: string;
  label: string;
  href: string;
}

export interface AgentRunReportV2Indicator {
  id: string;
  role: "primary" | "supporting";
  label: string;
  value: string;
  value_kind: "status" | "duration" | "ratio" | "count";
  unit: string;
  numerator: number | null;
  denominator: number | null;
  tone: Exclude<AgentRunReportV2Severity, "fatal">;
  priority: number;
  evidence_refs: AgentRunReportV2EvidenceRef[];
}

export interface AgentRunReportV2EvidenceLinks {
  events: string;
  activity: string;
  artifacts: string;
  audit_export: string;
}

export interface AgentRunReportV2Finding {
  id: string;
  kind: "finding" | "risk";
  title: string;
  description: string;
  severity: AgentRunReportV2Severity;
  confidence: "reported" | "derived";
  scope: string;
  evidence_refs: AgentRunReportV2EvidenceRef[];
}

export interface AgentRunReportV2Action {
  id: string;
  title: string;
  description: string;
  priority: string;
  status: "pending" | "done";
  owner: string;
  safety: "read_only" | "review_required";
  evidence_refs: AgentRunReportV2EvidenceRef[];
  cta: {
    type: "open_evidence" | "navigate" | "retry_delivery";
    label: string;
    ref: string;
    href: string;
    enabled: boolean;
  };
}

export interface AgentRunReportV2Phase {
  id: string;
  label: string;
  status: "completed" | "active" | "problem" | "active_problem" | "pending";
  count: number;
  important: number;
  problems: number;
  started_at: string | null;
  completed_at: string | null;
  summary?: string;
  goal?: string;
  action?: string;
  observation?: string;
  conclusion?: string;
}

export interface AgentRunReportV2Counts {
  events_total: number;
  important_events: number;
  execution_problem_events: number;
  delivery_problem_events: number;
  findings: number;
  risks: number;
  actions: number;
  activities_total: number;
  activities_succeeded: number;
  activities_failed: number;
  activities_unknown: number;
  operations_total?: number;
  operations_succeeded?: number;
  operations_failed?: number;
  operations_unknown?: number;
  commands?: number;
  steps?: number;
  tool_calls?: number;
  iterations?: number;
  artifacts: number;
}

export interface AgentRunReportV2Document {
  available: boolean;
  title: string;
  content_type: string;
  size_bytes: number;
  size_label: string;
  checksum_sha256: string;
  preview: string;
  preview_truncated: boolean;
  detail_url: string;
  download_url: string;
}

export interface AgentRunEventHighWatermark {
  sequence_no: number;
  total: number;
  updated_at: string | null;
}

export interface AgentRunReportV2Response {
  success: boolean;
  schema_version: number;
  run: AgentRunReportV2Run;
  lifecycle: AgentRunReportV2Lifecycle;
  outcome: AgentRunReportV2Outcome;
  evidence_state: AgentRunReportV2EvidenceState;
  report_generation: AgentRunReportV2Generation;
  delivery: AgentRunReportV2Delivery;
  indicators: AgentRunReportV2Indicator[];
  /** Transitional response alias; the view-model normalizes it. */
  dynamic_indicators?: AgentRunReportV2Indicator[];
  findings: AgentRunReportV2Finding[];
  actions: AgentRunReportV2Action[];
  phases: AgentRunReportV2Phase[];
  counts: AgentRunReportV2Counts;
  report_revision: string;
  event_high_watermark: AgentRunEventHighWatermark;
  /** Transitional response aliases; the view-model normalizes them. */
  revision?: string | number;
  event_watermark?: string | number | null;
  document: AgentRunReportV2Document;
  evidence_links: AgentRunReportV2EvidenceLinks;
  updated_at: string;
  generated_at?: string;
}

export interface AgentRunCursorPage {
  limit: number;
  direction: AgentRunPageDirection;
  next_cursor: string | number | null;
  prev_cursor: string | number | null;
  has_more: boolean;
}

export interface AgentRunReportEventV2 {
  id: string | number;
  sequence_no: number;
  event_type: string;
  title: string;
  summary: string;
  message: string;
  severity: AgentRunReportV2Severity;
  phase: string;
  category: string;
  source: string;
  important: boolean;
  task_id: number | null;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface AgentRunReportEventsV2Response {
  success: boolean;
  items: AgentRunReportEventV2[];
  page: AgentRunCursorPage;
  total: number;
  filters: Record<string, unknown>;
  event_watermark: string | number | null;
  integrity: Record<string, unknown>;
}

export interface AgentRunActivityV2Item {
  id: string | number;
  ordinal: number;
  kind: "command" | "step" | "iteration" | "tool";
  status: string;
  success: boolean | null;
  title: string;
  summary: string;
  tool: string;
  server: string;
  command: string;
  exit_code: number | null;
  duration_ms: number;
  started_at: string | null;
  completed_at: string | null;
  error: string;
  evidence_refs: AgentRunReportV2EvidenceRef[];
}

export interface AgentRunActivityV2Response {
  success: boolean;
  items: AgentRunActivityV2Item[];
  page: AgentRunCursorPage;
  total: number;
  counts: Record<string, number>;
}

export interface AgentRunArtifactV2Item {
  id: number;
  key: string;
  name: string;
  type: string;
  description: string;
  content_type: string;
  size_bytes: number;
  size_label: string;
  checksum_sha256: string;
  truncated: boolean;
  created_at: string | null;
  updated_at: string | null;
  download_url: string;
}

export interface AgentRunArtifactsV2Response {
  success: boolean;
  items: AgentRunArtifactV2Item[];
  total: number;
  download_all_url: string;
}

export interface AgentRunReportEventFilters {
  cursor?: string | number | null;
  direction?: AgentRunPageDirection;
  limit?: number;
  severity?: string[];
  phase?: string[];
  category?: string[];
  important?: boolean;
  q?: string;
}

export interface AgentRunActivityFilters {
  cursor?: string | number | null;
  direction?: AgentRunPageDirection;
  limit?: number;
  kind?: string[];
  status?: string[];
}

export interface AgentRunReportDeliveryAttemptResponse {
  success: boolean;
  accepted?: boolean;
  attempt_id?: string | number | null;
  code?: string;
  delivery: AgentRunReportV2Delivery;
}

export interface AgentRunCleanupStaleResponse {
  success: boolean;
  run_id: number;
  cleaned: boolean;
  canceled_dispatches?: number;
  code?: string;
}
