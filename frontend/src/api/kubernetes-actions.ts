import { apiFetch } from "@/lib/api";

export type KubernetesActionName =
  | "k8s.rollout.restart"
  | "fleet.rollout.pause"
  | "fleet.rollout.resume"
  | "gitops.create_merge_request"
  | "devtron.open_rollback"
  | string;

export type KubernetesActionRequestStatus =
  | "pending_approval"
  | "approved_external"
  | "verified_external"
  | "verification_failed"
  | "execution_blocked"
  | "rejected"
  | string;

export interface KubernetesActionRequestPayload {
  action: KubernetesActionName;
  reason: string;
  target: Record<string, unknown>;
  approval_ref?: string;
}

export interface KubernetesExternalApprovalPayload {
  approval_ref: string;
  summary?: string;
}

export interface KubernetesExternalVerificationPayload {
  outcome: "succeeded" | "failed" | string;
  summary: string;
  external_ref?: string;
  checks?: string[];
  evidence?: Record<string, unknown>;
}

export interface KubernetesActionRequestRecord {
  id: string;
  database_id: number;
  action: KubernetesActionName;
  status: KubernetesActionRequestStatus;
  risk_tier: "low" | "medium" | "high" | string;
  cluster: string;
  target: Record<string, unknown>;
  preview: Record<string, unknown>;
  execution_policy: {
    approval_required?: boolean;
    dry_run_required?: boolean;
    verification_required?: boolean;
    native_execution_enabled?: boolean;
    native_execution_mode?: string;
    allowed_execution_modes?: string[];
    lifecycle?: string[];
    blocked_reason?: string;
    [key: string]: unknown;
  };
  report: Record<string, unknown>;
  reason: string;
  approval_ref: string;
  requested_by: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface KubernetesActionRequestResponse {
  success: boolean;
  request: KubernetesActionRequestRecord;
}

export interface KubernetesActionRequestListQuery {
  all?: boolean;
  status?: KubernetesActionRequestStatus;
  action?: KubernetesActionName;
  cluster_id?: string;
  risk_tier?: string;
  limit?: number;
}

export interface KubernetesActionRequestListResponse {
  success: boolean;
  requests: KubernetesActionRequestRecord[];
  count: number;
  limit: number;
}

export interface KubernetesActionTimelineEvent {
  action: string;
  username: string;
  created_at: string;
  payload: Record<string, unknown>;
}

export interface KubernetesActionReportResponse {
  success: boolean;
  request_id: string;
  status: KubernetesActionRequestStatus;
  request: KubernetesActionRequestRecord;
  report: Record<string, unknown>;
  execution_policy: KubernetesActionRequestRecord["execution_policy"];
  timeline: KubernetesActionTimelineEvent[];
  summary?: Record<string, unknown>;
}

export async function createKubernetesActionRequest(payload: KubernetesActionRequestPayload) {
  return apiFetch<KubernetesActionRequestResponse>("/api/kubernetes/actions/request-approval/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchKubernetesActionRequests(query: KubernetesActionRequestListQuery = {}) {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, typeof value === "boolean" ? String(value) : String(value));
    }
  });
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<KubernetesActionRequestListResponse>(`/api/kubernetes/actions/${suffix}`);
}

export async function fetchKubernetesActionStatus(requestId: string) {
  return apiFetch<KubernetesActionRequestResponse>(`/api/kubernetes/actions/${requestId}/status/`);
}

export async function fetchKubernetesActionReport(requestId: string) {
  return apiFetch<KubernetesActionReportResponse>(`/api/kubernetes/actions/${requestId}/report/`);
}

export async function approveExternalKubernetesAction(requestId: string, payload: KubernetesExternalApprovalPayload) {
  return apiFetch<KubernetesActionRequestResponse>(`/api/kubernetes/actions/${requestId}/approve-external/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function verifyExternalKubernetesAction(requestId: string, payload: KubernetesExternalVerificationPayload) {
  return apiFetch<KubernetesActionRequestResponse>(`/api/kubernetes/actions/${requestId}/verify-external/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
