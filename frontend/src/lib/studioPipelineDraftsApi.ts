import { apiFetch, type PipelineDetail, type PipelineEdge, type PipelineNode } from "@/lib/api";

export interface StudioPipelineAssistantPayload {
  pipeline_id?: number | null;
  pipeline_name: string;
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  selected_node?: PipelineNode | null;
  user_message: string;
  intent?: "create" | "edit" | "validate" | "fix_run";
  compiler_mode?: "deterministic" | "local" | "pilot" | "pilot_template";
  last_validation_errors?: string[];
  last_run_summary?: Record<string, unknown>;
  draft_mode?: boolean;
  history?: Array<{
    role: "user" | "assistant";
    content: string;
  }>;
}

export interface StudioPipelineDraftResourceItem {
  id?: number | string;
  slug?: string;
  name?: string;
  reason?: string;
  tools?: string[];
  [key: string]: unknown;
}

export interface StudioPipelineDraftResourcePlan {
  servers?: StudioPipelineDraftResourceItem[];
  agents?: StudioPipelineDraftResourceItem[];
  mcp_servers?: StudioPipelineDraftResourceItem[];
  skills?: StudioPipelineDraftResourceItem[];
  missing?: string[];
  notes?: string[];
  available?: Record<string, StudioPipelineDraftResourceItem[]>;
}

export interface StudioPipelineTemplateRecommendation {
  slug: string;
  name: string;
  description?: string;
  category?: string;
  tags?: string[];
  match_score?: number;
  matched_terms?: string[];
  node_types?: string[];
  skeleton?: {
    nodes?: Array<{
      id: string;
      type: string;
      label?: string;
      [key: string]: unknown;
    }>;
    edges?: Array<{
      source: string;
      target: string;
      source_handle?: string;
      label?: string | null;
    }>;
  };
}

export interface StudioPipelineGraphPatchNode {
  ref: string;
  type: string;
  data: Record<string, unknown>;
  label?: string;
  x_offset?: number;
  y_offset?: number;
}

export interface StudioPipelineGraphPatchEdge {
  source: string;
  target: string;
  label?: string;
  source_handle?: string;
  target_handle?: string;
}

export interface StudioPipelineGraphPatch {
  anchor_node_id: string | null;
  nodes: StudioPipelineGraphPatchNode[];
  edges: StudioPipelineGraphPatchEdge[];
  update_nodes?: Array<{
    node_id: string;
    data: Record<string, unknown>;
  }>;
  remove_node_ids?: string[];
  remove_edge_ids?: string[];
}

export interface StudioPipelineAssistantResponse {
  reply: string;
  requirements?: string[];
  assumptions?: string[];
  questions?: string[];
  resource_plan?: StudioPipelineDraftResourcePlan;
  target_node_id: string | null;
  node_patch: Record<string, unknown>;
  graph_patch: StudioPipelineGraphPatch;
  node_explanations?: Record<string, string>;
  confidence?: number | null;
  warnings: string[];
  patch_summary?: string;
  validation?: {
    ok: boolean;
    errors: string[];
    warnings: string[];
  };
  risk?: {
    level: "safe" | "dangerous" | string;
    items: Array<{
      node_id: string;
      node_label?: string;
      stage?: string;
      command?: string;
      level?: string;
      categories?: string[];
      matched_patterns?: string[];
      reasons?: string[];
    }>;
  };
  suggested_next_actions?: string[];
  selected_template?: {
    slug?: string;
    name?: string;
    source?: string;
  } | null;
  template_recommendations?: StudioPipelineTemplateRecommendation[];
  dry_run?: {
    ok: boolean;
    executed: boolean;
    mode: string;
    checks: string[];
    message: string;
  };
}

export interface StudioPipelineDraftRevision {
  id: number;
  session_id: number;
  user_message: string;
  created_at: string;
  preview_nodes: PipelineNode[];
  preview_edges: PipelineEdge[];
  response: StudioPipelineAssistantResponse;
}

export interface StudioPipelineDraftSession {
  id: number;
  status: "drafting" | "needs_input" | "ready" | "invalid" | "blocked" | "applied" | "discarded" | string;
  intent: "create" | "edit" | "validate" | "fix_run" | string;
  title: string;
  user_goal: string;
  source_pipeline_id: number | null;
  applied_pipeline_id: number | null;
  selected_node_id: string;
  created_at: string;
  updated_at: string;
  applied_at: string | null;
  latest_revision: StudioPipelineDraftRevision | null;
}

export const studioPipelineDrafts = {
  list: () => apiFetch<StudioPipelineDraftSession[]>("/api/studio/assistant/drafts/"),
  create: (data: StudioPipelineAssistantPayload) =>
    apiFetch<StudioPipelineDraftSession>("/api/studio/assistant/drafts/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  get: (id: number) => apiFetch<StudioPipelineDraftSession>(`/api/studio/assistant/drafts/${id}/`),
  discard: (id: number) =>
    apiFetch<StudioPipelineDraftSession>(`/api/studio/assistant/drafts/${id}/`, {
      method: "DELETE",
    }),
  revise: (id: number, data: Partial<StudioPipelineAssistantPayload>) =>
    apiFetch<StudioPipelineDraftSession>(`/api/studio/assistant/drafts/${id}/revise/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  validate: (id: number) =>
    apiFetch<{
      draft: StudioPipelineDraftSession;
      validation: NonNullable<StudioPipelineAssistantResponse["validation"]>;
      risk: NonNullable<StudioPipelineAssistantResponse["risk"]>;
      dry_run: NonNullable<StudioPipelineAssistantResponse["dry_run"]>;
    }>(`/api/studio/assistant/drafts/${id}/validate/`, {
      method: "POST",
    }),
  useTemplate: (id: number, templateSlug: string) =>
    apiFetch<StudioPipelineDraftSession>(`/api/studio/assistant/drafts/${id}/use-template/`, {
      method: "POST",
      body: JSON.stringify({ template_slug: templateSlug }),
    }),
  apply: (
    id: number,
    data: {
      create_new?: boolean;
      name?: string;
      description?: string;
      icon?: string;
      tags?: string[];
    } = {},
  ) =>
    apiFetch<{ draft: StudioPipelineDraftSession; pipeline: PipelineDetail }>(`/api/studio/assistant/drafts/${id}/apply/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
