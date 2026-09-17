import { apiFetch } from "@/lib/api";

import type { PlaybookCompatibilityReport, PlaybookInventoryBindings, PlaybookRun } from "./playbooks";

export type PlaybookValidationStatus = "ready" | "blocked" | "stale" | "running" | string;

export interface PlaybookValidationIssue {
  code: string;
  severity: "error" | "warning" | "info" | string;
  stage?: string;
  message: string;
  remediation?: string;
  path?: string;
  line?: number | null;
  column?: number | null;
  retryable?: boolean;
  details?: Record<string, unknown>;
}

export interface PlaybookValidationStage {
  status?: string;
  passed?: boolean | null;
  message?: string;
  missing?: string[];
  count?: number;
  execution?: { status?: string; ready?: boolean };
  [key: string]: unknown;
}

export interface PlaybookRunValidation {
  id: number;
  revision_id: number;
  analyzer_version?: string;
  runtime_fingerprint?: Record<string, unknown>;
  runtime_fingerprint_hash?: string;
  target_signature?: string;
  binding_profile_id?: number | null;
  binding_version?: number | null;
  status: PlaybookValidationStatus;
  stages: Record<string, PlaybookValidationStage>;
  issues: PlaybookValidationIssue[];
  compatibility?: PlaybookCompatibilityReport;
  stale_reason?: string;
  started_at?: string;
  finished_at?: string | null;
}

export interface ValidatePlaybookRevisionPayload {
  binding_profile_id?: number;
  server_ids: number[];
  group_ids: number[];
  inventory_bindings: PlaybookInventoryBindings;
  variable_names: string[];
}

export interface PlaybookRunRequest {
  revision_id: number;
  validation_id: number;
  binding_profile_id?: number;
  server_ids: number[];
  group_ids: number[];
  inventory_bindings: PlaybookInventoryBindings;
  extra_vars: Record<string, unknown>;
  concurrency: number;
  dry_run: boolean;
  become: boolean;
  tags: string;
  skip_tags: string;
  limit: string;
  engine: "ansible";
  rerun_of?: number;
}

export async function validatePlaybookRevision(
  playbookId: number,
  revisionId: number,
  payload: ValidatePlaybookRevisionPayload,
) {
  return apiFetch<{ success: true; validation: PlaybookRunValidation }>(
    `/servers/api/playbooks/${playbookId}/revisions/${revisionId}/validate/`,
    { method: "POST", body: JSON.stringify(payload), timeoutMs: 60_000 },
  );
}

export async function runValidatedPlaybook(playbookId: number, payload: PlaybookRunRequest) {
  return apiFetch<{ success: true; run: PlaybookRun }>(`/servers/api/playbooks/${playbookId}/run/`, {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 60_000,
  });
}
