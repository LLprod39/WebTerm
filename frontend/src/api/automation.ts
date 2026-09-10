import { api } from "./client";

export type Json =
  null | boolean | number | string | Json[] | { [key: string]: Json };
export type Values = Record<string, Json>;
export interface Capability {
  can_view: boolean;
  can_edit: boolean;
  can_validate: boolean;
  can_publish: boolean;
  can_run: boolean;
  can_export: boolean;
  can_share: boolean;
  can_delete: boolean;
  is_owner: boolean;
}
export interface Task {
  id: string;
  command: string;
  description: string;
  continue_on_error: boolean;
}
export interface Playbook {
  id: number;
  name: string;
  description: string;
  kind: string;
  category: string;
  tags: string[];
  task_count: number;
  last_run_status: string;
  last_run_at: string | null;
  updated_at: string;
  owner_id: number;
  published_revision_id: number | null;
  published_revision_number: number | null;
  has_unpublished_draft: boolean;
  capabilities: Capability;
  source_yaml?: string;
  tasks?: Task[];
  source?: Record<string, string>;
}
export interface PlaybookDraft {
  id: number;
  version: number;
  base_revision_id: number;
  source_yaml: string;
  tasks: Task[];
  content_format: string;
  content_hash: string;
  bundle_hash: string;
  asset_bundle_id: number | null;
  entrypoint: string;
  updated_at: string;
}
export interface Revision {
  id: number;
  revision_number: number;
  parent_id: number | null;
  content_hash: string;
  bundle_hash: string;
  message: string;
  author_username: string;
  created_at: string;
  content_format: string;
  source_yaml?: string;
  tasks?: Task[];
}
export interface Binding {
  id: number;
  name: string;
  version: number;
  is_default: boolean;
  selector_mappings: Values;
  variable_values: Values;
  secret_variables: string[];
  options: Values;
  updated_at: string;
}
export interface Issue {
  code?: string;
  message?: string;
  severity?: string;
  field?: string;
  node_id?: string;
  node_ids?: string[];
  next_action?: string;
  [key: string]: unknown;
}
export interface Validation {
  id?: number;
  status?: string;
  ok?: boolean;
  errors?: string[];
  issues?: Issue[];
  stages?: Record<string, unknown>;
  compatibility?: unknown;
}
export interface RunSummary {
  id: number;
  playbook_id: number | null;
  playbook_name: string;
  status: string;
  phase?: string;
  progress_percent?: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  summary: Record<string, unknown>;
  error_message?: string;
}
export interface HostResult {
  server_id: number;
  server_name: string;
  status: string;
  host?: string;
  task_counts?: Record<string, number>;
  tasks?: {
    task_id: string;
    name: string;
    status: string;
    output: string;
    exit_code: number | null;
  }[];
}
export interface RunReport {
  schema_version: number;
  run: RunSummary & {
    revision_id: number | null;
    target_count: number;
    duration_ms: number | null;
    binding_profile_name: string;
    cancel_requested: boolean;
    options: Values;
  };
  progress: {
    phase: string;
    percent: number | null;
    total_kind: string;
    state_version: number;
  };
  summary: Record<string, unknown>;
  failure: { code: string; message: string; suggested_action?: string } | null;
  hosts: HostResult[];
  actions: {
    can_cancel: boolean;
    can_retry_failed: boolean;
    can_export: boolean;
    export_url: string;
  };
  log: { truncated: boolean };
}
export interface LogDelta {
  text: string;
  cursor: number;
  next_cursor: number;
  has_more: boolean;
  truncated: boolean;
  reset_required: boolean;
  state_version: number;
}
export interface ServerOption {
  id: number;
  name: string;
  host?: string;
  group_name?: string;
}
export interface Schema {
  type?: string;
  title?: string;
  description?: string;
  enum?: Json[];
  default?: Json;
  minimum?: number;
  maximum?: number;
  properties?: Record<string, Schema>;
  required?: string[];
  items?: Schema;
}
export interface NodeManifest {
  type: string;
  category: string;
  purpose: string;
  source_handles: string[];
  risk_level: string;
  idempotency: string;
  mutates_state: boolean;
  supports_dry_run: boolean;
  requires_approval_by_default: boolean;
  input_schema: Schema;
  output_schema: Schema;
  tags: string[];
}
export interface PipelineNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: Values;
}
export interface PipelineEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
}
export interface Trigger {
  id: number;
  pipeline_id: number;
  node_id: string;
  name: string;
  trigger_type: string;
  is_active: boolean;
  cron_expression: string;
  last_triggered_at: string | null;
  webhook_header_url: string;
  webhook_token: string;
  has_signing_secret: boolean;
  webhook_payload_map: Values;
  monitoring_filters: Values;
}
export interface Pipeline {
  id: number;
  name: string;
  description: string;
  tags: string[];
  node_count: number;
  graph_version: number;
  updated_at: string;
  last_run: { id: number; status: string; started_at: string | null } | null;
  nodes?: PipelineNode[];
  edges?: PipelineEdge[];
  triggers?: Trigger[];
}
export interface NodeState {
  status: string;
  output?: string;
  error?: string;
  started_at?: string;
  finished_at?: string;
  [key: string]: unknown;
}
export interface PipelineRun {
  id: number;
  pipeline_id: number;
  pipeline_name: string;
  status: string;
  node_states: Record<string, NodeState>;
  nodes_snapshot: PipelineNode[];
  edges_snapshot?: PipelineEdge[];
  summary: string;
  error: string;
  duration_seconds: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  entry_node_id: string;
  trigger_type: string;
  can_resume: boolean;
  resume_confirmation_required: unknown[];
}
export interface PipelinePreflight {
  ok: boolean;
  validation: { ok: boolean; errors: string[]; issues: Issue[] };
  risk: { level: string; [key: string]: unknown };
  dry_run: { executed: false; message: string };
  entry_node_id: string;
}
export interface Template {
  slug: string;
  name: string;
  description: string;
  category: string;
  tags?: string[];
  node_count?: number;
}
export interface DraftSession {
  id: number;
  title: string;
  user_goal: string;
  status: string;
  intent: string;
  source_pipeline_id: number | null;
  applied_pipeline_id: number | null;
  updated_at: string;
  latest_revision: {
    id: number;
    user_message: string;
    preview_nodes: PipelineNode[];
    preview_edges: PipelineEdge[];
    response: {
      reply: string;
      validation: Validation;
      risk: { level: string };
      questions: unknown[];
      warnings: unknown[];
      requirements: unknown[];
      patch_summary: string;
      [key: string]: unknown;
    };
  } | null;
}
export interface Skill {
  slug: string;
  name: string;
  description: string;
  category: string;
  service: string;
  safety_level: string;
  tags: string[];
  can_edit: boolean;
  can_share: boolean;
  is_owner: boolean;
  is_shared: boolean;
  owner_username: string;
  content?: string;
  metadata?: Values;
  guardrail_summary?: string[];
  recommended_tools?: string[];
  runtime_policy?: Values;
}
export interface SkillFile {
  path: string;
  name?: string;
  kind?: string;
  size_bytes?: number;
  language?: string;
  editable?: boolean;
  content?: string;
}
export interface SkillWorkspace {
  slug: string;
  files: SkillFile[];
  can_edit: boolean;
  validation?: { errors: string[]; warnings: string[] };
}
export const playbookBase = "/servers/api/playbooks/";
export const studioBase = "/api/studio/";
export const automationApi = {
  playbooks: (signal?: AbortSignal) =>
    api.get<{ playbooks: Playbook[] }>(playbookBase, signal),
  playbook: (id: number, signal?: AbortSignal) =>
    api.get<{ playbook: Playbook }>(`${playbookBase}${id}/`, signal),
  createPlaybook: (body: unknown) =>
    api.post<{ playbook: Playbook }>(`${playbookBase}create/`, body),
  updatePlaybook: (id: number, body: unknown) =>
    api.post<{ playbook: Playbook }>(`${playbookBase}${id}/update/`, body),
  draft: (id: number, signal?: AbortSignal) =>
    api.get<{ draft: PlaybookDraft }>(`${playbookBase}${id}/draft/`, signal),
  saveDraft: (id: number, body: unknown) =>
    api.put<{ draft: PlaybookDraft }>(`${playbookBase}${id}/draft/`, body),
  revisions: (id: number, signal?: AbortSignal) =>
    api.get<{ revisions: Revision[]; published_revision_id: number | null }>(
      `${playbookBase}${id}/revisions/`,
      signal,
    ),
  createRevision: (id: number, body: unknown) =>
    api.post<{ revision: Revision }>(`${playbookBase}${id}/revisions/`, body),
  publish: (id: number, revision: number) =>
    api.post(`${playbookBase}${id}/revisions/${revision}/publish/`),
  validateRevision: (id: number, revision: number, body: unknown) =>
    api.post<{ validation: Validation }>(
      `${playbookBase}${id}/revisions/${revision}/validate/`,
      body,
    ),
  runPlaybook: (id: number, body: unknown) =>
    api.post<{ run: RunSummary }>(`${playbookBase}${id}/run/`, body),
  bindings: (id: number, signal?: AbortSignal) =>
    api.get<{ bindings: Binding[] }>(`${playbookBase}${id}/bindings/`, signal),
  runs: (signal?: AbortSignal) =>
    api.get<{ runs: RunSummary[] }>(`${playbookBase}runs/`, signal),
  report: (id: number, signal?: AbortSignal) =>
    api.get<{ report: RunReport }>(`${playbookBase}runs/${id}/report/`, signal),
  log: (id: number, after: number, signal?: AbortSignal) =>
    api.get<LogDelta>(
      `${playbookBase}runs/${id}/log/?after=${after}&limit_chars=32000`,
      signal,
    ),
  pipelines: (signal?: AbortSignal) =>
    api.get<Pipeline[]>(`${studioBase}pipelines/`, signal),
  pipeline: (id: number, signal?: AbortSignal) =>
    api.get<Pipeline>(`${studioBase}pipelines/${id}/`, signal),
  createPipeline: (body: unknown) =>
    api.post<Pipeline>(`${studioBase}pipelines/`, body),
  savePipeline: (id: number, body: unknown) =>
    api.put<Pipeline>(`${studioBase}pipelines/${id}/`, body),
  preflight: (id: number, body: unknown) =>
    api.post<PipelinePreflight>(`${studioBase}pipelines/${id}/run/`, {
      ...(body as object),
      validate_only: true,
    }),
  runPipeline: (id: number, body: unknown) =>
    api.post<PipelineRun>(`${studioBase}pipelines/${id}/run/`, body),
  manifests: (signal?: AbortSignal) =>
    api.get<{ nodes: NodeManifest[] }>(`${studioBase}node-manifests/`, signal),
  pipelineRuns: (signal?: AbortSignal) =>
    api.get<PipelineRun[]>(`${studioBase}runs/`, signal),
  pipelineRun: (id: number, signal?: AbortSignal) =>
    api.get<PipelineRun>(`${studioBase}runs/${id}/`, signal),
  triggers: (signal?: AbortSignal) =>
    api.get<Trigger[]>(`${studioBase}triggers/`, signal),
  templates: (signal?: AbortSignal) =>
    api.get<Template[]>(`${studioBase}templates/`, signal),
  drafts: (signal?: AbortSignal) =>
    api.get<DraftSession[]>(`${studioBase}assistant/drafts/`, signal),
  sessionDraft: (id: number, signal?: AbortSignal) =>
    api.get<DraftSession>(`${studioBase}assistant/drafts/${id}/`, signal),
  createSessionDraft: (body: unknown) =>
    api.post<DraftSession>(`${studioBase}assistant/drafts/`, body),
  skills: (signal?: AbortSignal) =>
    api.get<Skill[]>(`${studioBase}skills/`, signal),
  skill: (slug: string, signal?: AbortSignal) =>
    api.get<Skill>(`${studioBase}skills/${encodeURIComponent(slug)}/`, signal),
  skillWorkspace: (slug: string, signal?: AbortSignal) =>
    api.get<SkillWorkspace>(
      `${studioBase}skills/${encodeURIComponent(slug)}/workspace/`,
      signal,
    ),
  servers: (signal?: AbortSignal) =>
    api.get<{ servers: ServerOption[] }>(
      "/servers/api/frontend/bootstrap/",
      signal,
    ),
  studioServers: (signal?: AbortSignal) =>
    api.get<ServerOption[]>(`${studioBase}servers/`, signal),
};
