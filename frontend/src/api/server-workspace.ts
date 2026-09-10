import { api, downloadFile } from "./client";
export interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  kind: string;
  size: number;
  permissions: string;
  permissions_octal: string;
  modified_at: number;
  owner?: string;
  group?: string;
}
export interface FileList {
  path: string;
  parent_path: string | null;
  entries: FileEntry[];
}
export interface TextFile {
  path: string;
  content: string;
  size: number;
  encoding: string;
}
export interface Share {
  id: number;
  username: string;
  user_id: number;
  email: string;
  is_active: boolean;
  can_connect_terminal: boolean;
  can_execute_command: boolean;
  can_read_files: boolean;
  can_write_files: boolean;
  share_context: boolean;
  expires_at: string | null;
  created_at: string;
}
export interface ShareInput {
  user: string;
  can_connect_terminal: boolean;
  can_execute_command: boolean;
  can_read_files: boolean;
  can_write_files: boolean;
  share_context: boolean;
  expires_at: string | null;
}
export const serverWorkspaceApi = {
  files: (id: number, path: string, signal?: AbortSignal) =>
    api.get<FileList>(
      `/servers/api/${id}/files/?${new URLSearchParams({ path })}`,
      signal,
    ),
  read: (id: number, path: string) =>
    api.post<{ file: TextFile }>(`/servers/api/${id}/files/read/`, { path }),
  write: (id: number, path: string, content: string) =>
    api.post<{ file: TextFile }>(`/servers/api/${id}/files/write/`, {
      path,
      content,
    }),
  fileAction: (
    id: number,
    action: "rename" | "mkdir" | "delete" | "chmod" | "chown",
    body: Record<string, unknown>,
  ) => api.post(`/servers/api/${id}/files/${action}/`, body),
  download: (id: number, file: FileEntry) =>
    downloadFile(`/servers/api/${id}/files/download/`, file.name, {
      path: file.path,
    }),
  upload: (id: number, path: string, files: globalThis.File[]) => {
    const data = new FormData();
    data.set("path", path);
    for (const file of files) data.append("files", file);
    return api.upload(`/servers/api/${id}/files/upload/`, data);
  },
  shares: (id: number, signal?: AbortSignal) =>
    api.get<{ shares: Share[] }>(`/servers/api/${id}/shares/`, signal),
  share: (id: number, body: ShareInput) =>
    api.post(`/servers/api/${id}/share/`, body),
  revoke: (id: number, shareId: number) =>
    api.post(`/servers/api/${id}/shares/${shareId}/revoke/`),
  transfer: (id: number, target_user: string) =>
    api.post(`/servers/api/${id}/transfer-owner/`, { target_user }),
  execute: (id: number, command: string) =>
    api.post<{
      output: { stdout?: string; stderr?: string; exit_code?: number };
    }>(`/servers/api/${id}/execute/`, { command }),
};
