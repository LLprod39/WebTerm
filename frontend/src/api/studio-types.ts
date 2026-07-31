/**
 * Studio API DTOs and public TypeScript contracts.
 */
// =============================================================================
// Studio API
// =============================================================================

export interface PipelineLastRun {
  id: number;
  status: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface PipelineTriggerSummary {
  active_total: number;
  active_manual: number;
  active_webhook: number;
  active_schedule: number;
  active_monitoring?: number;
  last_triggered_at: string | null;
}

export interface PipelineListItem {
  id: number;
  name: string;
  description: string;
  icon: string;
  tags: string[];
  is_shared: boolean;
  is_template: boolean;
  graph_version: number;
  node_count: number;
  created_at: string;
  updated_at: string;
  trigger_summary?: PipelineTriggerSummary;
  last_run: PipelineLastRun | null;
  owner?: StudioSharedUser | null;
  owner_username?: string;
  is_owner?: boolean;
  can_edit?: boolean;
  access_mode?: StudioAccessMode;
}

export interface PipelineNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: Record<string, unknown>;
}

export interface PipelineEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  label?: string;
}

export interface PipelineDetail extends PipelineListItem {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  triggers?: PipelineTrigger[];
}

export interface NodeState {
  status: string;
  output?: string;
  error?: string;
  agent_run_id?: number;
  started_at?: string;
  finished_at?: string;
  passed?: boolean;
  routing_ports?: string[];
  decision?: string;
}

export interface PipelineRun {
  id: number;
  pipeline_id: number;
  pipeline_name: string;
  status: string;
  node_states: Record<string, NodeState>;
  nodes_snapshot: PipelineNode[];
  context: Record<string, unknown>;
  summary: string;
  error: string;
  duration_seconds: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  triggered_by: string | null;
  trigger_id: number | null;
  entry_node_id: string;
  trigger_type: string;
  trigger_name: string;
  trigger_node_id: string;
  can_resume: boolean;
  resume_confirmation_required: Array<{
    id: string;
    type: string;
    label: string;
    idempotency: "non_idempotent";
  }>;
}

export interface PipelineRunValidation {
  ok: boolean;
  validation: {
    ok: boolean;
    errors: string[];
    warnings?: string[];
  };
  risk?: {
    level: "safe" | "dangerous" | string;
    items: Array<{
      node_id?: string;
      node_label?: string;
      stage?: string;
      command?: string;
      level?: string;
      categories?: string[];
      matched_patterns?: string[];
      reasons?: string[];
    }>;
  };
  dry_run?: {
    ok: boolean;
    executed: boolean;
    mode: string;
    checks: string[];
    message: string;
  };
  entry_node_id?: string;
  trigger_type?: string;
  would_create_run?: boolean;
}

export type StudioAccessMode = "owner" | "shared" | "admin";

export interface StudioSharedUser {
  id: number;
  username: string;
  email?: string;
}

export interface StudioAccessMetadata {
  owner?: StudioSharedUser | null;
  owner_username?: string;
  is_owner?: boolean;
  can_edit?: boolean;
  can_share?: boolean;
  is_shared?: boolean;
  shared_user_ids?: number[];
  shared_users?: StudioSharedUser[];
  access_mode?: StudioAccessMode;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AgentConfig extends StudioAccessMetadata {
  id: number;
  name: string;
  description: string;
  icon: string;
  system_prompt: string;
  instructions: string;
  model: string;
  max_iterations: number;
  allowed_tools: string[];
  sudo_policy: "disabled" | "ask" | "approved";
  skill_slugs: string[];
  skills: StudioSkill[];
  skill_errors?: string[];
  mcp_servers: Array<{ id: number; name: string; transport: string }>;
  server_scope: Array<{ id: number; name: string }>;
}

export interface StudioSkill extends StudioAccessMetadata {
  slug: string;
  name: string;
  description: string;
  tags: string[];
  service: string;
  category: string;
  safety_level: string;
  ui_hint: string;
  guardrail_summary: string[];
  recommended_tools: string[];
  runtime_enforced: boolean;
  path: string;
}

export interface StudioSkillDetail extends StudioSkill {
  runtime_policy: Record<string, unknown>;
  metadata: Record<string, unknown>;
  content: string;
}

export interface StudioSkillTemplate {
  slug: string;
  name: string;
  description: string;
  summary: string;
  defaults: {
    name?: string;
    description?: string;
    service?: string;
    category?: string;
    safety_level?: string;
    ui_hint?: string;
    tags?: string[];
    guardrail_summary?: string[];
    recommended_tools?: string[];
    runtime_policy?: Record<string, unknown>;
  };
}

export interface StudioSkillValidationResult {
  slug: string;
  path: string;
  errors: string[];
  warnings: string[];
  is_valid: boolean;
}

export interface StudioSkillValidationResponse {
  results: StudioSkillValidationResult[];
  summary: {
    skills: number;
    errors: number;
    warnings: number;
    is_valid: boolean;
    strict: boolean;
  };
}

export interface StudioSkillScaffoldPayload {
  template_slug?: string;
  name: string;
  description: string;
  slug?: string;
  service?: string;
  category?: string;
  safety_level?: string;
  ui_hint?: string;
  tags?: string[];
  guardrail_summary?: string[];
  recommended_tools?: string[];
  runtime_policy?: Record<string, unknown>;
  with_scripts?: boolean;
  with_references?: boolean;
  with_assets?: boolean;
  force?: boolean;
  is_shared?: boolean;
  shared_user_ids?: number[];
}

export interface StudioSkillScaffoldResponse {
  ok: boolean;
  skill: StudioSkillDetail;
  validation: StudioSkillValidationResult;
}

export interface StudioSkillWorkspaceFile {
  path: string;
  name: string;
  kind: "skill" | "reference" | "script" | "asset" | "file";
  language: string;
  size: number;
  editable: boolean;
}

export interface StudioSkillWorkspaceFileDetail extends StudioSkillWorkspaceFile {
  content: string;
}

export interface StudioSkillWorkspace {
  skill: StudioSkillDetail;
  files: StudioSkillWorkspaceFile[];
  validation: StudioSkillValidationResult;
}

export interface StudioSkillWorkspaceMutationResponse {
  ok: boolean;
  file?: StudioSkillWorkspaceFileDetail;
  validation: StudioSkillValidationResult;
}

export interface MCPServer extends StudioAccessMetadata {
  id: number;
  name: string;
  description: string;
  transport: "stdio" | "sse";
  command: string;
  args: string[];
  env: Record<string, string>;
  secret_env_keys?: string[];
  url: string;
  headers?: Record<string, string>;
  is_shared: boolean;
  last_test_ok: boolean | null;
  last_test_at: string | null;
  last_test_error: string;
}

export interface MCPServerTool {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
}

export interface MCPTemplate {
  slug: string;
  name: string;
  description: string;
  transport: "stdio" | "sse";
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  icon?: string;
}

export interface MCPServerInspection {
  server: {
    name: string;
    transport: string;
    protocol_version: string;
    server_info: Record<string, unknown>;
    capabilities: Record<string, unknown>;
  };
  tools: MCPServerTool[];
}

export type JsonSchema = Record<string, unknown>;

export interface StudioCapabilityNode {
  type: string;
  category: string;
  purpose: string;
  source_handles: string[];
  risk_level: string;
  idempotency: "idempotent" | "non_idempotent";
  mutates_state: boolean;
  supports_dry_run: boolean;
  requires_approval_by_default: boolean;
  recommended_verification: string[];
  tags: string[];
  input_schema: JsonSchema;
  output_schema: JsonSchema;
  metadata?: Record<string, unknown>;
}

export interface StudioNodeManifestRegistry {
  version: number;
  count: number;
  nodes: StudioCapabilityNode[];
}

export interface StudioCapabilityTaskFamily {
  slug: string;
  name: string;
  description: string;
  readiness: "ready" | "partial" | "missing";
  missing: string[];
  preferred_nodes: string[];
  required_capabilities: string[];
  matching_mcp_servers: Array<{ id: number; name: string; transport: string; last_test_ok: boolean | null }>;
  matching_skills: Array<{ slug: string; name: string; service: string; safety_level: string }>;
  pilot_prompt: string;
  capability_packs?: Array<{
    slug: string;
    name: string;
    service: string;
    mcp_server_name: string;
    tool_names: string[];
    skill_slugs: string[];
  }>;
}

export interface StudioCapabilityPackTool {
  pack_slug: string;
  pack_name: string;
  task_family: string;
  service: string;
  mcp_server_name: string;
  tool_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  permission_mode: string;
  risk_level: string;
  operation_kind: string;
  mutates_state: boolean;
  requires_approval: boolean;
  skill_slugs: string[];
  policy_tags: string[];
}

export interface StudioCapabilityPack {
  slug: string;
  name: string;
  task_family: string;
  service: string;
  mcp_server_name: string;
  skill_slugs: string[];
  tools: StudioCapabilityPackTool[];
}

export interface StudioCapabilityRegistry {
  strategy: {
    mode: string;
    service_specific_work: string;
    default_execution_node: string;
    approval_node: string;
    verification_nodes: string[];
  };
  nodes: StudioCapabilityNode[];
  capability_packs: StudioCapabilityPack[];
  resources: {
    mcp_servers: Array<{ id: number; name: string; description: string; transport: string; last_test_ok: boolean | null }>;
    skills: Array<{ slug: string; name: string; description: string; service: string; category: string; safety_level: string }>;
    server_count: number | null;
  };
  task_families: StudioCapabilityTaskFamily[];
}

export interface PipelineTrigger {
  id: number;
  pipeline_id: number;
  node_id: string;
  name: string;
  trigger_type: "manual" | "webhook" | "schedule" | "monitoring";
  is_active: boolean;
  webhook_token: string;
  webhook_url: string;
  cron_expression: string;
  webhook_payload_map: Record<string, unknown>;
  monitoring_filters?: Record<string, unknown>;
  last_triggered_at: string | null;
}
