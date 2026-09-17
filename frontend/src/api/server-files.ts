import { apiFetch, buildBinaryRequestHeaders } from "@/lib/api";
import { isDemoMode } from "@/lib/demo";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface SftpEntry {
  name: string;
  path: string;
  kind: "file" | "dir" | "symlink";
  is_dir: boolean;
  is_symlink: boolean;
  size: number;
  permissions: string;
  permissions_octal?: string;
  modified_at: number;
}

export interface SftpListResponse {
  success: boolean;
  path: string;
  home_path: string;
  parent_path: string | null;
  entries: SftpEntry[];
}

export interface SftpMutationResponse {
  success: boolean;
  path: string;
  entry?: SftpEntry;
  entries?: SftpEntry[];
  deleted_path?: string;
  error?: string;
}

export interface SftpTextFile {
  path: string;
  filename: string;
  size: number;
  encoding: string;
  content: string;
}

export interface SftpTextFileResponse {
  success: boolean;
  file: SftpTextFile;
}

export interface SftpTransferProgress {
  loaded: number;
  total?: number;
}

export interface SftpDownloadResult {
  blob: Blob;
  filename: string;
  size: number;
}

function makeApiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function parseErrorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.error === "string" && data.error) return data.error;
    if (typeof data?.message === "string" && data.message) return data.message;
  } catch {
    // noop
  }
  return `HTTP ${res.status}`;
}

function parseContentDispositionFilename(headerValue: string | null): string | null {
  const raw = (headerValue || "").trim();
  if (!raw) return null;

  const utf8Match = raw.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }

  const quotedMatch = raw.match(/filename="([^"]+)"/i);
  if (quotedMatch?.[1]) return quotedMatch[1];

  const bareMatch = raw.match(/filename=([^;]+)/i);
  return bareMatch?.[1]?.trim() || null;
}

function extractPathBasename(path: string): string {
  const normalized = String(path || "").replace(/\/+$/, "");
  const parts = normalized.split("/");
  return parts[parts.length - 1] || "download";
}

export function saveBlobAsFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function listServerFiles(serverId: number, path = ".") {
  const query = new URLSearchParams({ path }).toString();
  return apiFetch<SftpListResponse>(`/servers/api/${serverId}/files/?${query}`);
}

export async function renameServerFile(serverId: number, path: string, newName: string) {
  return apiFetch<SftpMutationResponse>(`/servers/api/${serverId}/files/rename/`, {
    method: "POST",
    body: JSON.stringify({ path, new_name: newName }),
  });
}

export async function deleteServerFile(serverId: number, path: string, recursive = false) {
  return apiFetch<SftpMutationResponse>(`/servers/api/${serverId}/files/delete/`, {
    method: "POST",
    body: JSON.stringify({ path, recursive }),
  });
}

export async function createServerFolder(serverId: number, path: string, name: string) {
  return apiFetch<SftpMutationResponse>(`/servers/api/${serverId}/files/mkdir/`, {
    method: "POST",
    body: JSON.stringify({ path, name }),
  });
}

export type ServerTextFileOptions = {
  elevate?: boolean;
  sudoPassword?: string;
};

export class ServerFileApiError extends Error {
  code: string;
  status: number;

  constructor(message: string, opts?: { code?: string; status?: number }) {
    super(message);
    this.name = "ServerFileApiError";
    this.code = opts?.code || "error";
    this.status = opts?.status || 500;
  }
}

function isPermissionRelated(code: string, message: string): boolean {
  if (code === "permission_denied" || code === "sudo_required" || code === "sudo_failed") return true;
  return /недостаточно прав|permission denied|sudo|пароль/i.test(message);
}

function permissionErrorCode(message: string): string {
  if (/пароль sudo|password is required|sudo_required|требуется пароль/i.test(message)) {
    return "sudo_required";
  }
  if (/неверный пароль|incorrect password|sudo_failed/i.test(message)) {
    return "sudo_failed";
  }
  return "permission_denied";
}

export async function readServerTextFile(
  serverId: number,
  path: string,
  options: ServerTextFileOptions = {},
) {
  if (options.elevate) {
    // POST keeps sudo password out of query string / access logs.
    try {
      return await apiFetch<SftpTextFileResponse>(`/servers/api/${serverId}/files/read/`, {
        method: "POST",
        body: JSON.stringify({
          path,
          elevate: true,
          ...(options.sudoPassword ? { sudo_password: options.sudoPassword } : {}),
        }),
      });
    } catch (err) {
      if (err instanceof Error && isPermissionRelated("", err.message)) {
        throw new ServerFileApiError(err.message, {
          code: permissionErrorCode(err.message),
          status: 403,
        });
      }
      throw err;
    }
  }
  const params = new URLSearchParams({ path }).toString();
  try {
    return await apiFetch<SftpTextFileResponse>(`/servers/api/${serverId}/files/read/?${params}`);
  } catch (err) {
    if (err instanceof Error && isPermissionRelated("", err.message)) {
      throw new ServerFileApiError(err.message, {
        code: permissionErrorCode(err.message),
        status: 403,
      });
    }
    throw err;
  }
}

export async function writeServerTextFile(
  serverId: number,
  path: string,
  content: string,
  options: ServerTextFileOptions = {},
) {
  try {
    return await apiFetch<SftpTextFileResponse>(`/servers/api/${serverId}/files/write/`, {
      method: "POST",
      body: JSON.stringify({
        path,
        content,
        ...(options.elevate ? { elevate: true } : {}),
        ...(options.sudoPassword ? { sudo_password: options.sudoPassword } : {}),
      }),
    });
  } catch (err) {
    if (err instanceof Error && isPermissionRelated("", err.message)) {
      throw new ServerFileApiError(err.message, {
        code: permissionErrorCode(err.message),
        status: 403,
      });
    }
    throw err;
  }
}

export function isElevatableFileError(err: unknown): err is ServerFileApiError {
  if (err instanceof ServerFileApiError) {
    return err.code === "permission_denied" || err.code === "sudo_required" || err.code === "sudo_failed";
  }
  if (err instanceof Error) {
    return isPermissionRelated("", err.message);
  }
  return false;
}

export async function chmodServerFile(serverId: number, path: string, mode: string) {
  return apiFetch<SftpMutationResponse>(`/servers/api/${serverId}/files/chmod/`, {
    method: "POST",
    body: JSON.stringify({ path, mode }),
  });
}

export async function chownServerFile(serverId: number, path: string, owner: string, recursive = false) {
  return apiFetch<SftpMutationResponse>(`/servers/api/${serverId}/files/chown/`, {
    method: "POST",
    body: JSON.stringify({ path, owner, recursive }),
  });
}

export async function uploadServerFiles(
  serverId: number,
  options: {
    path: string;
    files: File[];
    overwrite?: boolean;
    signal?: AbortSignal;
    onProgress?: (progress: SftpTransferProgress) => void;
  },
) {
  if (isDemoMode()) {
    options.onProgress?.({ loaded: 1, total: 1 });
    return {
      success: true,
      path: options.path,
      entries: options.files.map((file) => ({
        name: file.name,
        path: `${options.path.replace(/\/$/, "")}/${file.name}`,
        kind: "file" as const,
        is_dir: false,
        is_symlink: false,
        size: file.size,
        permissions: "-rw-r--r--",
        modified_at: Math.floor(Date.now() / 1000),
      })),
    } satisfies SftpMutationResponse;
  }

  const headers = await buildBinaryRequestHeaders("POST");
  const form = new FormData();
  form.append("path", options.path || ".");
  if (options.overwrite) form.append("overwrite", "true");
  for (const file of options.files) {
    form.append("files", file);
  }

  return new Promise<SftpMutationResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abortHandler = () => xhr.abort();

    xhr.open("POST", makeApiUrl(`/servers/api/${serverId}/files/upload/`));
    xhr.withCredentials = true;
    Object.entries(headers).forEach(([key, value]) => xhr.setRequestHeader(key, value));

    xhr.upload.onprogress = (event) => {
      options.onProgress?.({
        loaded: event.loaded,
        total: event.lengthComputable ? event.total : undefined,
      });
    };

    xhr.onload = () => {
      try {
        const data = xhr.responseText ? JSON.parse(xhr.responseText) : {};
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data as SftpMutationResponse);
          return;
        }
        reject(new Error(String(data?.error || `HTTP ${xhr.status}`)));
      } catch {
        reject(new Error(`HTTP ${xhr.status}`));
      }
    };

    xhr.onerror = () => reject(new Error("Upload failed"));
    xhr.onabort = () => reject(new DOMException("Upload aborted", "AbortError"));

    if (options.signal) {
      if (options.signal.aborted) {
        xhr.abort();
        return;
      }
      options.signal.addEventListener("abort", abortHandler, { once: true });
    }

    xhr.onloadend = () => {
      if (options.signal) {
        options.signal.removeEventListener("abort", abortHandler);
      }
    };

    xhr.send(form);
  });
}

export async function downloadServerFile(
  serverId: number,
  options: {
    path: string;
    signal?: AbortSignal;
    onProgress?: (progress: SftpTransferProgress) => void;
  },
) {
  if (isDemoMode()) {
    const blob = new Blob([`Demo download for ${options.path}\n`], { type: "text/plain;charset=utf-8" });
    options.onProgress?.({ loaded: blob.size, total: blob.size });
    return {
      blob,
      filename: extractPathBasename(options.path),
      size: blob.size,
    } satisfies SftpDownloadResult;
  }

  const headers = await buildBinaryRequestHeaders("POST");
  const response = await fetch(makeApiUrl(`/servers/api/${serverId}/files/download/`), {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: JSON.stringify({ path: options.path }),
    signal: options.signal,
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  const filename =
    parseContentDispositionFilename(response.headers.get("Content-Disposition")) || extractPathBasename(options.path);
  const totalHeader = Number(response.headers.get("Content-Length") || 0);
  const total = Number.isFinite(totalHeader) && totalHeader > 0 ? totalHeader : undefined;

  if (!response.body) {
    const blob = await response.blob();
    options.onProgress?.({ loaded: blob.size, total: blob.size });
    return { blob, filename, size: blob.size } satisfies SftpDownloadResult;
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let loaded = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) {
      chunks.push(value);
      loaded += value.byteLength;
      options.onProgress?.({ loaded, total });
    }
  }

  const blob = new Blob(chunks as BlobPart[], { type: response.headers.get("Content-Type") || "application/octet-stream" });
  return { blob, filename, size: loaded } satisfies SftpDownloadResult;
}
