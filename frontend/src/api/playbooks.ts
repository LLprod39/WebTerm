import { apiFetch } from "@/lib/api";

export type PlaybookKind = "runbook" | "ansible";
export type PlaybookCategory = "deploy" | "patch" | "diagnose" | "security" | "maintenance" | "custom";
export type PlaybookVisibility = "private" | "shared";
export type PlaybookRunStatus = "pending" | "running" | "completed" | "failed" | "partial" | "cancelled";
export type TaskResultStatus = "pending" | "running" | "success" | "error" | "skipped";

export interface PlaybookTask {
  id: string;
  command: string;
  description: string;
  continue_on_error: boolean;
}

export interface PlaybookFidelity {
  runnable?: number;
  total?: number;
  score?: number;
  unsupported_modules?: string[];
  hosts_hint?: string;
}

export interface PlaybookSummary {
  id: number;
  name: string;
  description: string;
  kind: PlaybookKind;
  category: PlaybookCategory;
  visibility: PlaybookVisibility;
  tags: string[];
  fidelity: PlaybookFidelity;
  task_count: number;
  is_template_clone: boolean;
  template_slug: string;
  last_run_at: string | null;
  last_run_status: string;
  created_at: string | null;
  updated_at: string | null;
  owner_id: number;
}

export interface PlaybookDetail extends PlaybookSummary {
  tasks: PlaybookTask[];
  source_yaml: string;
}

export interface PlaybookTaskResult {
  task_id: string;
  command: string;
  description?: string;
  status: TaskResultStatus;
  output: string;
  exit_code?: number | null;
}

export interface PlaybookHostResult {
  server_id: number;
  server_name: string;
  host?: string;
  status: string;
  task_results: PlaybookTaskResult[];
}

export interface PlaybookRunSummary {
  hosts_total?: number;
  hosts_ok?: number;
  hosts_failed?: number;
  hosts_partial?: number;
  tasks_ok?: number;
  tasks_failed?: number;
  tasks_skipped?: number;
  engine?: string;
  ansible_method?: string;
}

export interface PlaybookRunProgress {
  engine?: string;
  play?: string;
  plays?: number;
  /** Current task name (both engines) */
  task?: string;
  /** Ansible: TASK headers seen so far */
  task_number?: number;
  /** Estimated total task steps (per engine semantics) */
  tasks_total?: number | null;
  /** Shell: completed host×task steps */
  tasks_done?: number;
  hosts_seen?: number;
  hosts_total?: number;
  counts?: {
    ok?: number;
    changed?: number;
    failed?: number;
    skipped?: number;
    unreachable?: number;
  };
  recap_seen?: boolean;
  finished?: boolean;
}

export interface PlaybookRun {
  id: number;
  playbook_id: number | null;
  status: PlaybookRunStatus;
  playbook_name: string;
  target_server_ids: number[];
  target_group_ids: number[];
  options: {
    concurrency?: number;
    dry_run?: boolean;
    online_only?: boolean;
    rerun_of?: number;
    engine?: string;
    become?: boolean;
  };
  summary: PlaybookRunSummary;
  progress?: PlaybookRunProgress;
  live_log?: string;
  inventory_preview: string;
  error_message: string;
  cancel_requested: boolean;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
  host_results?: PlaybookHostResult[];
  playbook_snapshot?: {
    id?: number;
    name?: string;
    description?: string;
    kind?: string;
    category?: string;
    tasks?: PlaybookTask[];
  };
}

export interface PlaybookTemplate {
  slug: string;
  name: string;
  description: string;
  kind: PlaybookKind;
  category: PlaybookCategory;
  tags: string[];
  task_count: number;
  tasks_preview: Array<{ description: string; command: string }>;
}

export async function listPlaybooks(params?: { category?: string; kind?: string; q?: string }) {
  const sp = new URLSearchParams();
  if (params?.category) sp.set("category", params.category);
  if (params?.kind) sp.set("kind", params.kind);
  if (params?.q) sp.set("q", params.q);
  const q = sp.toString();
  return apiFetch<{ success: boolean; playbooks: PlaybookSummary[]; count: number }>(
    `/servers/api/playbooks/${q ? `?${q}` : ""}`,
  );
}

export async function getPlaybook(id: number) {
  return apiFetch<{ success: boolean; playbook: PlaybookDetail }>(`/servers/api/playbooks/${id}/`);
}

export async function createPlaybook(payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; playbook: PlaybookDetail; error?: string }>("/servers/api/playbooks/create/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updatePlaybook(id: number, payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; playbook: PlaybookDetail; error?: string }>(`/servers/api/playbooks/${id}/update/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deletePlaybook(id: number) {
  return apiFetch<{ success: boolean }>(`/servers/api/playbooks/${id}/delete/`, { method: "POST", body: "{}" });
}

export async function duplicatePlaybook(id: number) {
  return apiFetch<{ success: boolean; playbook: PlaybookDetail }>(`/servers/api/playbooks/${id}/duplicate/`, {
    method: "POST",
    body: "{}",
  });
}

export async function importPlaybook(payload: { content: string; filename?: string; save?: boolean }) {
  return apiFetch<{
    success: boolean;
    playbook?: PlaybookDetail;
    parsed?: Record<string, unknown>;
    error?: string;
  }>("/servers/api/playbooks/import/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listPlaybookTemplates() {
  return apiFetch<{ success: boolean; templates: PlaybookTemplate[] }>("/servers/api/playbooks/templates/");
}

export interface AnsibleStatus {
  available: boolean;
  method: "native" | "wsl" | "docker" | "none" | string;
  binary: string;
  version: string;
  message: string;
  image?: string;
  image_ready?: boolean;
}

export async function fetchAnsibleStatus() {
  return apiFetch<{ success: boolean; ansible: AnsibleStatus }>("/servers/api/playbooks/ansible/status/");
}

export interface GuidedField {
  key: string;
  label: string;
  placeholder?: string;
  required?: boolean;
  type?: "text" | "textarea" | "select" | "checkbox";
  options?: string[];
  default?: string | boolean;
}

export interface GuidedRecipe {
  slug: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  fields: GuidedField[];
}

export async function listGuidedRecipes() {
  return apiFetch<{ success: boolean; recipes: GuidedRecipe[] }>("/servers/api/playbooks/guided/");
}

export async function generateGuidedPlaybook(payload: {
  slug: string;
  params?: Record<string, string | boolean | number>;
  save?: boolean;
}) {
  return apiFetch<{ success: boolean; playbook: PlaybookDetail; preview?: boolean; error?: string }>(
    "/servers/api/playbooks/guided/generate/",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function installPlaybookTemplate(slug: string) {
  return apiFetch<{ success: boolean; playbook: PlaybookDetail }>(`/servers/api/playbooks/templates/${slug}/install/`, {
    method: "POST",
    body: "{}",
  });
}

export async function previewPlaybookInventory(payload: { server_ids?: number[]; group_ids?: number[] }) {
  return apiFetch<{
    success: boolean;
    inventory: string;
    hosts: Array<{
      id: number;
      name: string;
      host: string;
      port: number;
      username: string;
      group_id: number | null;
      detected_os: string;
    }>;
    count: number;
  }>("/servers/api/playbooks/inventory/preview/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function runPlaybook(
  id: number,
  payload: {
    server_ids?: number[];
    group_ids?: number[];
    concurrency?: number;
    dry_run?: boolean;
    online_only?: boolean;
    master_password?: string;
    engine?: "auto" | "ansible" | "shell";
    become?: boolean;
    tags?: string;
    limit?: string;
    extra_vars?: Record<string, unknown>;
  },
) {
  return apiFetch<{ success: boolean; run: PlaybookRun; error?: string }>(`/servers/api/playbooks/${id}/run/`, {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 60_000,
  });
}

export async function listPlaybookRuns() {
  return apiFetch<{ success: boolean; runs: PlaybookRun[] }>("/servers/api/playbooks/runs/");
}

export async function getPlaybookRun(runId: number) {
  return apiFetch<{ success: boolean; run: PlaybookRun }>(`/servers/api/playbooks/runs/${runId}/`);
}

export async function cancelPlaybookRun(runId: number) {
  return apiFetch<{ success: boolean; run: PlaybookRun }>(`/servers/api/playbooks/runs/${runId}/cancel/`, {
    method: "POST",
    body: "{}",
  });
}

export async function rerunFailedPlaybookHosts(runId: number, masterPassword = "") {
  return apiFetch<{ success: boolean; run: PlaybookRun; error?: string }>(
    `/servers/api/playbooks/runs/${runId}/rerun-failed/`,
    {
      method: "POST",
      body: JSON.stringify(masterPassword ? { master_password: masterPassword } : {}),
    },
  );
}
