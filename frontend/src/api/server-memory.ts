import { apiFetch, type StudioSkillDetail } from "@/lib/api";

export interface ServerMemorySnapshotHistoryRecord {
  id: number;
  title: string;
  version: number;
  is_active: boolean;
  source_kind?: string;
  source_ref?: string;
  updated_at: string | null;
  archived_at: string | null;
  rewrite_reason?: string | null;
  action_summary: string | null;
  created_by_username?: string | null;
  content_preview?: string | null;
}

export interface ServerMemorySnapshotRecord {
  id: number;
  memory_key: string;
  title: string;
  content: string;
  source_kind: string;
  source_ref?: string;
  version: number;
  is_active: boolean;
  version_group_id: string;
  superseded_by_id: number | null;
  importance_score: number;
  stability_score: number;
  confidence: number;
  last_verified_at: string | null;
  updated_at: string | null;
  archived_at: string | null;
  rewrite_reason?: string | null;
  prior_snapshot_id?: number | null;
  prior_version?: number | null;
  action_summary: string | null;
  created_by_username?: string | null;
  metadata: Record<string, unknown>;
  history: ServerMemorySnapshotHistoryRecord[];
}

export interface ServerMemoryEpisodeRecord {
  id: number;
  episode_kind: string;
  title: string;
  summary: string;
  event_count: number;
  importance_score: number;
  confidence: number;
  is_active: boolean;
  first_event_at: string | null;
  last_event_at: string | null;
  updated_at: string | null;
  metadata: Record<string, unknown>;
  kind?: string;
}

export interface ServerMemoryRevalidationRecord {
  id: number;
  memory_key: string;
  title: string;
  reason: string;
  status: string;
  confidence: number;
  payload: Record<string, unknown>;
  updated_at: string | null;
  resolved_at: string | null;
}

export interface BackgroundWorkerStateRecord {
  worker_kind: string;
  worker_key: string;
  status: string;
  is_stale: boolean;
  hostname: string;
  pid: number | null;
  command?: string;
  heartbeat_at: string | null;
  lease_expires_at: string | null;
  last_started_at: string | null;
  last_stopped_at: string | null;
  last_cycle_started_at: string | null;
  last_cycle_finished_at: string | null;
  last_summary: Record<string, unknown>;
  last_error: string;
}

export interface ServerMemoryOverviewResponse {
  success: boolean;
  server_id: number;
  policy: {
    dream_mode: "heuristic" | "nightly_llm" | "hybrid";
    nightly_model_alias: string;
    nearline_event_threshold: number;
    sleep_start_hour: number;
    sleep_end_hour: number;
    raw_event_retention_days: number;
    episode_retention_days: number;
    human_habits_capture_enabled: boolean;
    is_enabled: boolean;
    ai_memory_enabled: boolean;
    operational_memory_enabled: boolean;
  };
  daemon_state: BackgroundWorkerStateRecord;
  worker_states?: Record<string, BackgroundWorkerStateRecord>;
  canonical: ServerMemorySnapshotRecord[];
  manual: ServerMemorySnapshotRecord[];
  patterns: ServerMemorySnapshotRecord[];
  automation_candidates: ServerMemorySnapshotRecord[];
  skill_drafts: ServerMemorySnapshotRecord[];
  revalidation: ServerMemoryRevalidationRecord[];
  episodes: ServerMemoryEpisodeRecord[];
  archive: Array<(ServerMemorySnapshotRecord | ServerMemoryEpisodeRecord) & { kind: string }>;
  stats: {
    canonical: number;
    manual: number;
    patterns: number;
    automation_candidates: number;
    skill_drafts: number;
    revalidation_open: number;
    episodes: number;
    archive: number;
  };
}

export interface ServerMemorySnapshotActionResponse {
  success: boolean;
  snapshot: ServerMemorySnapshotRecord;
  overview: ServerMemoryOverviewResponse;
}

export interface ServerMemoryPromoteNoteResponse extends ServerMemorySnapshotActionResponse {
  knowledge_id: number;
  knowledge_title: string;
}

export interface ServerMemoryPromoteSkillResponse extends ServerMemorySnapshotActionResponse {
  knowledge_id?: number;
  skill: StudioSkillDetail;
  validation: {
    slug: string;
    path: string;
    errors: string[];
    warnings: string[];
    is_valid: boolean;
  };
}

export async function listServerKnowledge(serverId: number) {
  return apiFetch<{
    success: boolean;
    items: Array<{
      id: number;
      title: string;
      content: string;
      category: string;
      category_label: string;
      source: string;
      source_label: string;
      confidence: number;
      is_active: boolean;
      updated_at: string | null;
    }>;
    categories: Array<{ value: string; label: string }>;
  }>(`/servers/api/${serverId}/knowledge/`);
}

export async function createServerKnowledge(
  serverId: number,
  payload: { title: string; content: string; category?: string; is_active?: boolean },
) {
  return apiFetch<{ success: boolean; id?: number; error?: string }>(`/servers/api/${serverId}/knowledge/create/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateServerKnowledge(
  serverId: number,
  knowledgeId: number,
  payload: { title?: string; content?: string; category?: string; is_active?: boolean },
) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/${serverId}/knowledge/${knowledgeId}/update/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteServerKnowledge(serverId: number, knowledgeId: number) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/${serverId}/knowledge/${knowledgeId}/delete/`, {
    method: "POST",
  });
}

export interface MemorySnapshotItem {
  id: number;
  title: string;
  content: string;
  memory_key: string;
  kind: "canonical" | "pattern" | "automation" | "skill_draft" | "manual_note" | "ai_note";
  version: number;
  confidence: number;
  freshness: number;
  updated_at: string | null;
  created_at: string | null;
  rewrite_reason: string;
}

export async function listServerMemorySnapshots(serverId: number) {
  return apiFetch<{ success: boolean; items: MemorySnapshotItem[] }>(
    `/servers/api/${serverId}/memory/snapshots/`,
  );
}

export async function updateServerMemorySnapshot(
  serverId: number,
  snapshotId: number,
  payload: { title?: string; content?: string },
) {
  return apiFetch<{ success: boolean; id: number; title: string; content: string; updated_at: string | null }>(
    `/servers/api/${serverId}/memory/snapshots/${snapshotId}/update/`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteServerMemorySnapshot(serverId: number, snapshotId: number) {
  return apiFetch<{ success: boolean; deleted?: Record<string, unknown>; purged_all_ai_memory?: boolean; error?: string }>(
    `/servers/api/${serverId}/memory/snapshots/${snapshotId}/delete/`,
    {
      method: "POST",
    },
  );
}

export async function bulkDeleteServerMemorySnapshots(
  serverId: number,
  payload: { snapshot_ids: number[] },
) {
  return apiFetch<{ success: boolean; deleted_count: number; snapshot_ids: number[]; purged_all_ai_memory?: boolean; error?: string }>(
    `/servers/api/${serverId}/memory/snapshots/bulk-delete/`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function purgeServerAiMemory(serverId: number) {
  return apiFetch<{
    success: boolean;
    deleted: {
      snapshots: number;
      revalidations: number;
      episodes: number;
      events: number;
      knowledge: number;
    };
    overview?: ServerMemoryOverviewResponse;
    error?: string;
  }>(`/servers/api/${serverId}/memory/purge/`, {
    method: "POST",
  });
}

export async function fetchServerMemoryOverview(serverId: number) {
  return apiFetch<ServerMemoryOverviewResponse>(`/servers/api/${serverId}/memory/overview/`);
}

export async function runServerMemoryDreams(
  serverId: number,
  payload: { job_kind?: "nearline" | "nightly" | "weekly" | "hybrid" } = {},
) {
  return apiFetch<{
    success: boolean;
    job_kind: string;
    result: Record<string, unknown>;
    overview: ServerMemoryOverviewResponse;
  }>(`/servers/api/${serverId}/memory/run-dreams/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateServerMemoryPolicy(
  serverId: number,
  payload: {
    dream_mode?: "heuristic" | "nightly_llm" | "hybrid";
    nightly_model_alias?: string;
    nearline_event_threshold?: number;
    sleep_start_hour?: number;
    sleep_end_hour?: number;
    raw_event_retention_days?: number;
    episode_retention_days?: number;
    human_habits_capture_enabled?: boolean;
    is_enabled?: boolean;
  },
) {
  return apiFetch<{
    success: boolean;
    overview: ServerMemoryOverviewResponse;
  }>(`/servers/api/${serverId}/memory/policy/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function archiveServerMemorySnapshot(serverId: number, snapshotId: number) {
  return apiFetch<ServerMemorySnapshotActionResponse>(`/servers/api/${serverId}/memory/snapshots/${snapshotId}/archive/`, {
    method: "POST",
  });
}

export async function promoteServerMemorySnapshotToNote(serverId: number, snapshotId: number) {
  return apiFetch<ServerMemoryPromoteNoteResponse>(`/servers/api/${serverId}/memory/snapshots/${snapshotId}/promote-note/`, {
    method: "POST",
  });
}

export async function promoteServerMemorySnapshotToSkill(serverId: number, snapshotId: number) {
  return apiFetch<ServerMemoryPromoteSkillResponse>(`/servers/api/${serverId}/memory/snapshots/${snapshotId}/promote-skill/`, {
    method: "POST",
  });
}

export async function getGlobalServerContext() {
  return apiFetch<{
    rules: string;
    forbidden_commands: string[];
    required_checks: string[];
    environment_vars: Record<string, string>;
  }>("/servers/api/global-context/");
}

export async function saveGlobalServerContext(payload: {
  rules?: string;
  forbidden_commands?: string[] | string;
  required_checks?: string[] | string;
  environment_vars?: Record<string, string>;
}) {
  return apiFetch<{ success: boolean; error?: string }>("/servers/api/global-context/save/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getGroupServerContext(groupId: number) {
  return apiFetch<{
    id: number;
    name: string;
    rules: string;
    forbidden_commands: string[];
    environment_vars: Record<string, string>;
  }>(`/servers/api/groups/${groupId}/context/`);
}

export async function saveGroupServerContext(
  groupId: number,
  payload: { rules?: string; forbidden_commands?: string[] | string; environment_vars?: Record<string, string> },
) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/groups/${groupId}/context/save/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
