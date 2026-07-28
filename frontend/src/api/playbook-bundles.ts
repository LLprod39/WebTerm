import { apiFetch } from "@/lib/api";

import type { PlaybookCategory, PlaybookVisibility } from "./playbooks";

export const PLAYBOOK_BUNDLE_ACCEPT =
  ".zip,.tar,.tar.gz,application/zip,application/x-tar,application/gzip";

export interface PlaybookBundleFilePreview {
  path: string;
  size_bytes: number;
  sha256: string;
  is_text: boolean;
}

export interface PlaybookBundlePlayPreview {
  name: string;
  hosts: string;
  task_count: number;
}

export interface PlaybookBundleEntrypointPreview {
  path: string;
  play_count: number;
  task_count: number;
  plays: PlaybookBundlePlayPreview[];
}

export interface PlaybookBundleSecurityWarning {
  path: string;
  kind: string;
  key?: string;
}

export interface PlaybookBundleManifest {
  schema_version?: number;
  kind?: string;
  name?: string;
  description?: string;
  entrypoint?: string;
  tags?: string[];
  required_collections?: string[];
  required_roles?: string[];
  sanitized?: boolean;
  redaction_count?: number;
  revision?: {
    id?: number;
    number?: number;
    content_hash?: string;
    bundle_hash?: string;
  };
}

export interface PlaybookBundlePreview {
  archive_format: "zip" | "tar" | string;
  content_hash: string;
  file_count: number;
  total_size_bytes: number;
  files: PlaybookBundleFilePreview[];
  manifest: PlaybookBundleManifest;
  entrypoints: PlaybookBundleEntrypointPreview[];
  selected_entrypoint: string;
  secret_warnings: PlaybookBundleSecurityWarning[];
  safe_to_commit: boolean;
}

export interface CommitPlaybookBundleMetadata {
  entrypoint: string;
  name: string;
  description: string;
  category: PlaybookCategory;
  visibility: PlaybookVisibility;
  tags: string[];
}

export interface CommitPlaybookBundleResponse {
  success: true;
  playbook: {
    id: number;
    name: string;
    category: PlaybookCategory;
    visibility: PlaybookVisibility;
  };
  revision: {
    id: number;
    number: number;
    content_hash: string;
    bundle_hash: string;
  };
  bundle: {
    id: number;
    content_hash: string;
    file_count: number;
    size_bytes: number;
    scan_status: string;
  };
  preview: PlaybookBundlePreview;
}

export interface GitLabProjectSourceInput {
  project_url: string;
  ref: string;
  path: string;
  token: string;
}

export interface GitLabProjectSource {
  type: "gitlab";
  host: string;
  project: string;
  ref?: string;
  path?: string;
}

export interface PlaybookBundleExport {
  blob: Blob;
  filename: string;
  redactionCount: number;
}

export function isSupportedPlaybookBundleFile(file: Pick<File, "name"> | string): boolean {
  const filename = (typeof file === "string" ? file : file.name).trim().toLowerCase();
  return filename.endsWith(".zip") || filename.endsWith(".tar") || filename.endsWith(".tar.gz");
}

export async function previewPlaybookBundle(file: File, entrypoint = "") {
  const body = new FormData();
  body.append("bundle", file);
  if (entrypoint) body.append("entrypoint", entrypoint);
  return apiFetch<{ success: true; preview: PlaybookBundlePreview }>(
    "/servers/api/playbooks/import/preview/",
    { method: "POST", body },
  );
}

export async function commitPlaybookBundle(file: File, metadata: CommitPlaybookBundleMetadata) {
  const body = new FormData();
  body.append("bundle", file);
  body.append("entrypoint", metadata.entrypoint);
  body.append("name", metadata.name.trim());
  body.append("description", metadata.description.trim());
  body.append("category", metadata.category);
  body.append("visibility", metadata.visibility);
  body.append("tags", JSON.stringify(metadata.tags));
  return apiFetch<CommitPlaybookBundleResponse>("/servers/api/playbooks/import/commit/", {
    method: "POST",
    body,
  });
}

export async function previewGitLabPlaybookProject(source: GitLabProjectSourceInput) {
  return apiFetch<{ success: true; preview: PlaybookBundlePreview; source: GitLabProjectSource }>(
    "/servers/api/playbooks/import/gitlab/preview/",
    { method: "POST", body: JSON.stringify(source) },
  );
}

export async function commitGitLabPlaybookProject(
  source: GitLabProjectSourceInput,
  metadata: CommitPlaybookBundleMetadata,
  expectedContentHash: string,
) {
  return apiFetch<CommitPlaybookBundleResponse>("/servers/api/playbooks/import/gitlab/commit/", {
    method: "POST",
    body: JSON.stringify({
      ...source,
      expected_content_hash: expectedContentHash,
      ...metadata,
      name: metadata.name.trim(),
      description: metadata.description.trim(),
    }),
  });
}

export async function exportPlaybookRevisionBundle(
  playbookId: number,
  revisionId: number,
): Promise<PlaybookBundleExport> {
  const apiBase = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");
  const response = await fetch(
    `${apiBase}/servers/api/playbooks/${playbookId}/revisions/${revisionId}/export/`,
    { credentials: "include" },
  );
  if (!response.ok) {
    throw new Error(await readBundleExportError(response));
  }
  return {
    blob: await response.blob(),
    filename: exportFilename(response.headers.get("content-disposition")),
    redactionCount: Number.parseInt(response.headers.get("x-playbook-redactions") || "0", 10) || 0,
  };
}

export function downloadPlaybookBundleExport(artifact: PlaybookBundleExport): void {
  const url = URL.createObjectURL(artifact.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = artifact.filename;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function readBundleExportError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { error?: unknown };
    if (typeof payload.error === "string" && payload.error) return payload.error;
  } catch {
    // Fall through to a stable status error when the response is not JSON.
  }
  return `Export failed (HTTP ${response.status})`;
}

function exportFilename(contentDisposition: string | null): string {
  if (!contentDisposition) return "playbook-bundle.zip";
  const encoded = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const quoted = contentDisposition.match(/filename="([^"]+)"/i)?.[1];
  const plain = contentDisposition.match(/filename=([^;]+)/i)?.[1];
  let candidate = encoded || quoted || plain || "playbook-bundle.zip";
  if (encoded) {
    try {
      candidate = decodeURIComponent(encoded);
    } catch {
      candidate = encoded;
    }
  }
  return candidate.trim().replace(/^['"]|['"]$/g, "").split(/[\\/]/).pop() || "playbook-bundle.zip";
}
