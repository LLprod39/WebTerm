import { apiFetch } from "@/lib/api";
import type { PlaybookInventoryBindings, PlaybookTask } from "./playbooks";

export type PlaybookContentFormat = "ansible_yaml" | "runbook_json";

export interface PlaybookCapabilities {
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

export interface PlaybookDraft {
  id: number;
  base_revision_id: number | null;
  content_format: PlaybookContentFormat;
  source_yaml: string;
  tasks: PlaybookTask[];
  content_hash: string;
  bundle_hash: string;
  version: number;
  last_editor_id: number | null;
  updated_at: string;
}

export interface PlaybookRevision {
  id: number;
  revision_number: number;
  parent_id: number | null;
  content_format: PlaybookContentFormat;
  content_hash: string;
  bundle_hash: string;
  origin_type: string;
  message: string;
  author_id: number | null;
  author_username: string;
  created_at: string;
  source_yaml?: string;
  tasks?: PlaybookTask[];
  /** Compatibility is calculated from this immutable revision, never from the mutable playbook. */
  compatibility?: import("./playbooks").PlaybookCompatibilityReport;
}

export interface PlaybookBindingOptions {
  concurrency?: number;
  become?: boolean;
  dry_run?: boolean;
  tags?: string;
  skip_tags?: string;
  limit?: string;
}

export interface PlaybookBindingProfile {
  id: number;
  name: string;
  is_default: boolean;
  selector_mappings: PlaybookInventoryBindings;
  variable_values: Record<string, unknown>;
  /** Names only. Secret values are deliberately never returned by the API. */
  secret_variables: string[];
  options: PlaybookBindingOptions;
  version: number;
  content_hash: string;
  updated_at: string;
}

export type PlaybookShareRole = "viewer" | "editor" | "operator" | "manager";
export type PlaybookSharePrincipalType = "user" | "group" | "workspace";

export interface PlaybookShareCapabilities {
  can_view: boolean;
  can_edit: boolean;
  can_validate: boolean;
  can_publish: boolean;
  can_run: boolean;
  can_export: boolean;
  can_manage_shares: boolean;
}

export interface PlaybookShare {
  id: number;
  role: PlaybookShareRole;
  principal: {
    type: PlaybookSharePrincipalType;
    id: number | null;
    label: string;
  };
  capabilities: PlaybookShareCapabilities;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface SavePlaybookBindingPayload {
  name: string;
  selector_mappings: PlaybookInventoryBindings;
  variable_values?: Record<string, unknown>;
  secret_references?: Record<string, string>;
  /** Write-only replacements. Callers must never hydrate this from a response. */
  secret_values?: Record<string, string>;
  /** Names explicitly removed from the encrypted store on update. */
  remove_secret_names?: string[];
  options?: PlaybookBindingOptions;
  is_default?: boolean;
}

export interface PlaybookDraftFileSummary {
  path: string;
  size_bytes: number;
  sha256: string;
  is_text: boolean;
  editable: boolean;
}

export interface PlaybookDraftFileTree {
  entrypoint: string;
  bundle_hash: string;
  draft_version: number | null;
  files: PlaybookDraftFileSummary[];
}

export interface PlaybookDraftFile {
  path: string;
  content: string;
  sha256: string;
  size_bytes: number;
  is_text: boolean;
}

export interface PlaybookShareCandidate {
  id: number;
  label: string;
  secondary?: string;
  type: "user" | "group";
}

export async function getPlaybookDraft(playbookId: number) {
  return apiFetch<{ success: true; draft: PlaybookDraft }>(`/servers/api/playbooks/${playbookId}/draft/`);
}

export async function updatePlaybookDraft(
  playbookId: number,
  payload: {
    expected_version: number;
    content_format?: PlaybookContentFormat;
    source_yaml?: string;
    tasks?: PlaybookTask[];
  },
) {
  return apiFetch<{ success: true; draft: PlaybookDraft }>(`/servers/api/playbooks/${playbookId}/draft/`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function listPlaybookRevisions(playbookId: number) {
  return apiFetch<{
    success: true;
    published_revision_id: number | null;
    revisions: PlaybookRevision[];
  }>(`/servers/api/playbooks/${playbookId}/revisions/`);
}

export async function createPlaybookRevision(
  playbookId: number,
  payload: { expected_version?: number; message?: string },
) {
  return apiFetch<{ success: true; revision: PlaybookRevision }>(`/servers/api/playbooks/${playbookId}/revisions/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getPlaybookRevision(playbookId: number, revisionId: number) {
  return apiFetch<{ success: true; revision: PlaybookRevision }>(
    `/servers/api/playbooks/${playbookId}/revisions/${revisionId}/`,
  );
}

export async function publishPlaybookRevision(playbookId: number, revisionId: number) {
  return apiFetch<{ success: true; published_revision_id: number; revision: PlaybookRevision }>(
    `/servers/api/playbooks/${playbookId}/revisions/${revisionId}/publish/`,
    { method: "POST", body: "{}" },
  );
}

export async function rollbackPlaybookRevision(
  playbookId: number,
  revisionId: number,
  payload: { message?: string } = {},
) {
  return apiFetch<{ success: true; revision: PlaybookRevision }>(
    `/servers/api/playbooks/${playbookId}/revisions/${revisionId}/rollback/`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function listPlaybookBindings(playbookId: number) {
  return apiFetch<{ success: true; bindings: PlaybookBindingProfile[] }>(
    `/servers/api/playbooks/${playbookId}/bindings/`,
  );
}

export async function createPlaybookBinding(playbookId: number, payload: SavePlaybookBindingPayload) {
  return apiFetch<{ success: true; binding: PlaybookBindingProfile }>(
    `/servers/api/playbooks/${playbookId}/bindings/`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function updatePlaybookBinding(
  playbookId: number,
  bindingId: number,
  payload: Partial<SavePlaybookBindingPayload> & { expected_version: number },
) {
  return apiFetch<{ success: true; binding: PlaybookBindingProfile }>(
    `/servers/api/playbooks/${playbookId}/bindings/${bindingId}/`,
    { method: "PATCH", body: JSON.stringify(payload) },
  );
}

export async function deletePlaybookBinding(playbookId: number, bindingId: number) {
  return apiFetch<{ success: true }>(`/servers/api/playbooks/${playbookId}/bindings/${bindingId}/`, {
    method: "DELETE",
    body: "{}",
  });
}

export async function listPlaybookShares(playbookId: number) {
  return apiFetch<{ success: true; shares: PlaybookShare[] }>(`/servers/api/playbooks/${playbookId}/shares/`);
}

export async function createPlaybookShare(
  playbookId: number,
  payload: {
    principal_type: PlaybookSharePrincipalType;
    principal_id?: number;
    role: PlaybookShareRole;
    expires_at?: string | null;
    capabilities?: Partial<PlaybookShareCapabilities>;
  },
) {
  return apiFetch<{ success: true; share: PlaybookShare }>(`/servers/api/playbooks/${playbookId}/shares/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deletePlaybookShare(playbookId: number, shareId: number) {
  return apiFetch<{ success: true; share: PlaybookShare }>(
    `/servers/api/playbooks/${playbookId}/shares/${shareId}/`,
    { method: "DELETE", body: "{}" },
  );
}

export async function getPlaybookDraftFiles(playbookId: number) {
  return apiFetch<{ success: true; tree: PlaybookDraftFileTree }>(
    `/servers/api/playbooks/${playbookId}/draft/files/`,
  );
}

export type PlaybookProjectFileView = "current" | "base" | "published";

export async function getPlaybookDraftFile(
  playbookId: number,
  path: string,
  view?: PlaybookProjectFileView,
) {
  const query = new URLSearchParams({ path });
  if (view) query.set("view", view);
  return apiFetch<{
    success: true;
    file: PlaybookDraftFile;
    draft_version: number;
    bundle_hash: string;
  }>(`/servers/api/playbooks/${playbookId}/draft/file/?${query}`);
}

export async function updatePlaybookDraftFile(
  playbookId: number,
  payload: { path: string; content: string; expected_draft_version: number; expected_bundle_hash: string },
) {
  const query = new URLSearchParams({ path: payload.path });
  return apiFetch<{
    success: true;
    file: PlaybookDraftFile;
    draft: PlaybookDraft;
    tree: PlaybookDraftFileTree;
  }>(`/servers/api/playbooks/${playbookId}/draft/file/?${query}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function searchPlaybookShareCandidates(
  playbookId: number,
  query: string,
  limit = 12,
) {
  const params = new URLSearchParams({ q: query.trim(), limit: String(limit) });
  const response = await apiFetch<{
    success: true;
    candidates: {
      users: Array<{ id: number; username: string; email?: string }>;
      groups: Array<{ id: number; name: string }>;
    };
  }>(`/servers/api/playbooks/${playbookId}/shares/candidates/?${params}`);
  return {
    ...response,
    items: [
      ...response.candidates.users.map((user): PlaybookShareCandidate => ({
        id: user.id,
        type: "user",
        label: user.username,
        secondary: user.email,
      })),
      ...response.candidates.groups.map((group): PlaybookShareCandidate => ({
        id: group.id,
        type: "group",
        label: group.name,
      })),
    ],
  };
}
