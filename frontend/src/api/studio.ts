/**
 * Studio pipelines, runs, MCP, skills, triggers, and capability API.
 */
import { apiFetch } from "@/lib/api";
import type {
  StudioPipelineAssistantPayload,
  StudioPipelineAssistantResponse,
} from "@/lib/studioPipelineDraftsApi";
import type {
  AgentConfig,
  MCPServer,
  MCPServerInspection,
  MCPTemplate,
  PipelineDetail,
  PipelineListItem,
  PipelineRun,
  PipelineRunValidation,
  PipelineTrigger,
  StudioCapabilityRegistry,
  StudioNodeManifestRegistry,
  StudioSharedUser,
  StudioSkill,
  StudioSkillDetail,
  StudioSkillScaffoldPayload,
  StudioSkillScaffoldResponse,
  StudioSkillTemplate,
  StudioSkillValidationResponse,
  StudioSkillWorkspace,
  StudioSkillWorkspaceFileDetail,
  StudioSkillWorkspaceMutationResponse,
} from "@/api/studio-types";

export * from "@/api/studio-types";
// Pipelines
export const studioPipelines = {
  list: (q?: string) => apiFetch<PipelineListItem[]>(`/api/studio/pipelines/${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  get: (id: number) => apiFetch<PipelineDetail>(`/api/studio/pipelines/${id}/`),
  create: (data: Partial<PipelineDetail>) => apiFetch<PipelineDetail>("/api/studio/pipelines/", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: Partial<PipelineDetail>) => apiFetch<PipelineDetail>(`/api/studio/pipelines/${id}/`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: number) => apiFetch<{ ok: boolean }>(`/api/studio/pipelines/${id}/`, { method: "DELETE" }),
  run: (id: number, context?: Record<string, unknown>, entryNodeId?: string) =>
    apiFetch<PipelineRun>(`/api/studio/pipelines/${id}/run/`, {
      method: "POST",
      body: JSON.stringify({
        context: context || {},
        entry_node_id: entryNodeId || undefined,
      }),
    }),
  validateRun: (id: number, context?: Record<string, unknown>, entryNodeId?: string) =>
    apiFetch<PipelineRunValidation>(`/api/studio/pipelines/${id}/run/`, {
      method: "POST",
      body: JSON.stringify({
        context: context || {},
        entry_node_id: entryNodeId || undefined,
        validate_only: true,
        dry_run: true,
      }),
    }),
  clone: (id: number) => apiFetch<PipelineDetail>(`/api/studio/pipelines/${id}/clone/`, { method: "POST" }),
  runs: (id: number) => apiFetch<PipelineRun[]>(`/api/studio/pipelines/${id}/runs/`),
  assistant: (data: StudioPipelineAssistantPayload) =>
    apiFetch<StudioPipelineAssistantResponse>("/api/studio/pipelines/assistant/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// Runs
export const studioRuns = {
  list: () => apiFetch<PipelineRun[]>("/api/studio/runs/"),
  get: (id: number) => apiFetch<PipelineRun>(`/api/studio/runs/${id}/`),
  stop: (id: number) => apiFetch<{ ok: boolean }>(`/api/studio/runs/${id}/stop/`, { method: "POST" }),
};

// Agent Configs
export const studioAgents = {
  list: () => apiFetch<AgentConfig[]>("/api/studio/agents/"),
  get: (id: number) => apiFetch<AgentConfig>(`/api/studio/agents/${id}/`),
  create: (data: Partial<AgentConfig>) => apiFetch<AgentConfig>("/api/studio/agents/", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: Partial<AgentConfig>) => apiFetch<AgentConfig>(`/api/studio/agents/${id}/`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: number) => apiFetch<{ ok: boolean }>(`/api/studio/agents/${id}/`, { method: "DELETE" }),
};

export const studioSkills = {
  list: () => apiFetch<StudioSkill[]>("/api/studio/skills/"),
  get: (slug: string) => apiFetch<StudioSkillDetail>(`/api/studio/skills/${encodeURIComponent(slug)}/`),
  update: (slug: string, data: Partial<StudioSkillDetail>) =>
    apiFetch<StudioSkillDetail>(`/api/studio/skills/${encodeURIComponent(slug)}/`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  templates: () => apiFetch<StudioSkillTemplate[]>("/api/studio/skills/templates/"),
  scaffold: (data: StudioSkillScaffoldPayload) =>
    apiFetch<StudioSkillScaffoldResponse>("/api/studio/skills/scaffold/", { method: "POST", body: JSON.stringify(data) }),
  validate: (slugs?: string[], strict = false) =>
    apiFetch<StudioSkillValidationResponse>("/api/studio/skills/validate/", {
      method: "POST",
      body: JSON.stringify({ slugs: slugs || [], strict }),
    }),
  workspace: (slug: string) => apiFetch<StudioSkillWorkspace>(`/api/studio/skills/${encodeURIComponent(slug)}/workspace/`),
  readFile: (slug: string, path: string) =>
    apiFetch<StudioSkillWorkspaceFileDetail>(`/api/studio/skills/${encodeURIComponent(slug)}/workspace/file/?path=${encodeURIComponent(path)}`),
  createFile: (slug: string, data: { path: string; content: string }) =>
    apiFetch<StudioSkillWorkspaceMutationResponse>(`/api/studio/skills/${encodeURIComponent(slug)}/workspace/file/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateFile: (slug: string, data: { path: string; content: string }) =>
    apiFetch<StudioSkillWorkspaceMutationResponse>(`/api/studio/skills/${encodeURIComponent(slug)}/workspace/file/`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteFile: (slug: string, path: string) =>
    apiFetch<StudioSkillWorkspaceMutationResponse>(`/api/studio/skills/${encodeURIComponent(slug)}/workspace/file/`, {
      method: "DELETE",
      body: JSON.stringify({ path }),
    }),
};

// MCP
export const studioMCP = {
  list: () => apiFetch<MCPServer[]>("/api/studio/mcp/"),
  get: (id: number) => apiFetch<MCPServer>(`/api/studio/mcp/${id}/`),
  create: (data: Partial<MCPServer>) => apiFetch<MCPServer>("/api/studio/mcp/", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: Partial<MCPServer>) => apiFetch<MCPServer>(`/api/studio/mcp/${id}/`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: number) => apiFetch<{ ok: boolean }>(`/api/studio/mcp/${id}/`, { method: "DELETE" }),
  test: (id: number) => apiFetch<{ ok: boolean; error: string | null }>(`/api/studio/mcp/${id}/test/`, { method: "POST" }),
  templates: () => apiFetch<MCPTemplate[]>("/api/studio/mcp/templates/"),
  tools: (id: number) => apiFetch<MCPServerInspection>(`/api/studio/mcp/${id}/tools/`),
};

export const studioCapabilities = {
  get: () => apiFetch<StudioCapabilityRegistry>("/api/studio/capabilities/"),
};

export const studioNodeManifests = {
  get: () => apiFetch<StudioNodeManifestRegistry>("/api/studio/node-manifests/"),
};

export const studioShareUsers = {
  list: () => apiFetch<StudioSharedUser[]>("/api/studio/share-users/"),
};

// Triggers
export const studioTriggers = {
  list: (pipelineId?: number) => apiFetch<PipelineTrigger[]>(`/api/studio/triggers/${pipelineId ? `?pipeline_id=${pipelineId}` : ""}`),
  create: (data: Partial<PipelineTrigger>) => apiFetch<PipelineTrigger>("/api/studio/triggers/", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: Partial<PipelineTrigger>) => apiFetch<PipelineTrigger>(`/api/studio/triggers/${id}/`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: number) => apiFetch<{ ok: boolean }>(`/api/studio/triggers/${id}/`, { method: "DELETE" }),
};

// Templates
export const studioTemplates = {
  list: () => apiFetch<Array<Record<string, unknown>>>("/api/studio/templates/"),
  use: (slug: string) => apiFetch<PipelineDetail>(`/api/studio/templates/${slug}/use/`, { method: "POST" }),
};

// Servers (for dropdowns in node config)
export const studioServers = {
  list: () => apiFetch<Array<{ id: number; name: string; host: string }>>("/api/studio/servers/"),
};
