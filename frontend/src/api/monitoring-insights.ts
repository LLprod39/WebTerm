import { apiFetch } from "@/lib/api";

// ---------------------------------------------------------------------------
// Admin Insights API — extended metrics, forecasts, certificates (staff only)
// ---------------------------------------------------------------------------

export type PredictionSeverity = "info" | "warning" | "critical";

export type PredictionKind =
  | "disk_full"
  | "inode_full"
  | "memory_pressure"
  | "swap_growth"
  | "log_error_surge"
  | "cert_expiry"
  | "cert_changed";

export interface InsightPrediction {
  kind: PredictionKind;
  target: string;
  severity: PredictionSeverity;
  eta_days: number | null;
  predicted_for: string | null;
  current_value: number | null;
  threshold: number | null;
  unit: string;
  slope_per_day: number | null;
  confidence: number;
  evidence: Record<string, unknown>;
  server_id?: number;
  server_name?: string;
}

export interface InsightDiskMount {
  mount: string;
  filesystem?: string;
  percent?: number;
  used_gb?: number;
  total_gb?: number;
  inode_percent?: number;
}

export interface InsightTopProcess {
  pid: number;
  cpu_percent: number;
  memory_percent: number;
  command: string;
}

export interface InsightServer {
  id: number;
  name: string;
  host: string;
  owner: string;
  status: "healthy" | "warning" | "critical" | "unreachable" | "unknown";
  checked_at: string | null;
  sample_at: string | null;
  has_extended_metrics: boolean;
  cpu_percent: number | null;
  cpu_iowait_percent: number | null;
  cpu_steal_percent: number | null;
  cpu_count: number | null;
  load_1m: number | null;
  memory_percent: number | null;
  memory_available_mb: number | null;
  swap_percent: number | null;
  worst_disk: InsightDiskMount | null;
  disk_mounts: InsightDiskMount[];
  net_rx_bps: number | null;
  net_tx_bps: number | null;
  tcp_retrans_per_sec: number | null;
  tcp_established: number | null;
  fd_percent: number | null;
  process_count: number | null;
  zombie_count: number | null;
  top_processes: { by_cpu?: InsightTopProcess[]; by_memory?: InsightTopProcess[] };
  journal_err_10m: number | null;
  journal_warn_10m: number | null;
  reboot_required: boolean | null;
  ntp_synchronized: boolean | null;
  uptime_seconds: number | null;
  spark: { cpu: number[]; mem: number[]; disk: number[] };
  predictions: InsightPrediction[];
}

export interface InsightCertificate {
  id: number;
  server_id: number;
  server_name: string;
  port: number;
  endpoint: string;
  subject: string;
  issuer: string;
  not_after: string | null;
  days_left: number | null;
  sans: string[];
  is_active: boolean;
  changed_at: string | null;
  last_checked_at: string | null;
}

export interface InsightAlert {
  id: number;
  server_id: number;
  server_name: string;
  alert_type: string;
  severity: PredictionSeverity;
  title: string;
  message: string;
  created_at: string;
}

export interface AdminInsightsResponse {
  success: boolean;
  generated_at: string;
  cached?: boolean;
  summary: {
    servers_total: number;
    healthy: number;
    warning: number;
    critical: number;
    unreachable: number;
    unknown: number;
    active_alerts: number;
    predictions_total: number;
    predictions_critical: number;
    predictions_warning: number;
    certificates_total: number;
    certificates_expiring_30d: number;
    certificates_changed_7d: number;
  };
  servers: InsightServer[];
  predictions: InsightPrediction[];
  certificates: InsightCertificate[];
  alerts: InsightAlert[];
}

export async function fetchAdminInsights(refresh = false) {
  const qs = refresh ? "?refresh=1" : "";
  return apiFetch<AdminInsightsResponse>(`/servers/api/admin/insights/${qs}`);
}
