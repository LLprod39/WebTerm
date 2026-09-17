/**
 * AI file rollback snapshots (CommandSnapshot) — pre-edit backups before AI writes a file.
 */
import { apiFetch } from "@/lib/api";

export interface ServerFileSnapshot {
  id: number;
  file_path: string;
  command: string;
  byte_size: number;
  content_truncated: boolean;
  file_existed: boolean | null;
  content_hash: string;
  created_at: string;
  restored_at: string | null;
}

export interface ServerFileSnapshotDetail extends ServerFileSnapshot {
  server_id: number;
  user_id: number;
  content: string;
}

export async function fetchServerFileSnapshots(serverId: number, limit = 30) {
  const q = new URLSearchParams({ limit: String(limit) });
  return apiFetch<{ snapshots: ServerFileSnapshot[] }>(
    `/servers/api/${serverId}/snapshots/?${q}`,
  );
}

export async function fetchServerFileSnapshotDetail(serverId: number, snapshotId: number) {
  return apiFetch<{ snapshot: ServerFileSnapshotDetail }>(
    `/servers/api/${serverId}/snapshots/${snapshotId}/`,
  );
}

export async function restoreServerFileSnapshot(serverId: number, snapshotId: number) {
  return apiFetch<{ restore_command: string }>(
    `/servers/api/${serverId}/snapshots/${snapshotId}/restore/`,
    { method: "POST" },
  );
}
