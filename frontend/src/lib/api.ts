import {
  isDemoMode,
  enableDemoMode,
} from "./demo";
import { demoFallback } from "./api-demo-fallback";
export * from "./access-features";
export * from "@/api/auth";
export * from "@/api/agents";
export * from "@/api/linux-ui";
export * from "@/api/mars";
export * from "@/api/monitoring";
export * from "@/api/servers";
export * from "@/api/server-files";
export * from "@/api/server-memory";
export * from "@/api/settings";
export * from "@/api/studio";
export * from "@/api/studio-notifications";

const API_BASE = import.meta.env.VITE_API_BASE || "";
const BACKEND_ORIGIN = (
  import.meta.env.VITE_BACKEND_ORIGIN ||
  (import.meta.env.DEV && window.location.port === "8080" ? "http://127.0.0.1:9000" : "")
).replace(/\/$/, "");
const DEFAULT_REQUEST_TIMEOUT_MS = parsePositiveInt(import.meta.env.VITE_API_TIMEOUT_MS, 30_000);
const CSRF_REQUEST_TIMEOUT_MS = parsePositiveInt(import.meta.env.VITE_CSRF_TIMEOUT_MS, 8_000);
let csrfTokenCache: string | null = null;
let csrfTokenRequest: Promise<string | null> | null = null;

type ApiFetchOptions = RequestInit & {
  timeoutMs?: number;
};

function parsePositiveInt(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

async function fetchWithTimeout(input: RequestInfo | URL, init: RequestInit = {}, timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const parentSignal = init.signal;
  const abortFromParent = () => controller.abort();

  if (parentSignal?.aborted) {
    controller.abort();
  } else if (parentSignal) {
    parentSignal.addEventListener("abort", abortFromParent, { once: true });
  }

  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
    parentSignal?.removeEventListener("abort", abortFromParent);
  }
}

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? match[2] : null;
}

function isMutationRequest(method?: string): boolean {
  const normalized = (method || "GET").toUpperCase();
  return !["GET", "HEAD", "OPTIONS", "TRACE"].includes(normalized);
}

function isMarsApiPath(path: string): boolean {
  return path.startsWith("/api/mars/");
}

function isDemoBlackholeApiBase(value: string): boolean {
  return /^https?:\/\/(127\.0\.0\.1|localhost):1\/?$/.test(value);
}

function apiBaseForPath(path: string): string {
  return isMarsApiPath(path) && isDemoBlackholeApiBase(API_BASE) ? "" : API_BASE;
}

async function ensureCsrfToken(forceBackend = false): Promise<string | null> {
  const cookieToken = getCookie("csrftoken");
  if (cookieToken) {
    csrfTokenCache = cookieToken;
    return cookieToken;
  }

  if (csrfTokenCache) {
    return csrfTokenCache;
  }

  if (isDemoMode() && !forceBackend) return null;

  if (!csrfTokenRequest) {
    csrfTokenRequest = fetchWithTimeout(
      `${forceBackend && isDemoBlackholeApiBase(API_BASE) ? "" : API_BASE}/api/auth/csrf/`,
      {
        credentials: "include",
      },
      CSRF_REQUEST_TIMEOUT_MS,
    )
      .then(async (response) => {
        if (!response.ok) {
          return null;
        }
        const ct = response.headers.get("content-type") || "";
        if (ct.includes("text/html")) return null;

        const data = (await response.json().catch(() => null)) as { csrfToken?: unknown } | null;
        const token =
          typeof data?.csrfToken === "string" && data.csrfToken
            ? data.csrfToken
            : getCookie("csrftoken");
        csrfTokenCache = token || null;
        return csrfTokenCache;
      })
      .catch(() => null)
      .finally(() => {
        csrfTokenRequest = null;
      });
  }

  return csrfTokenRequest;
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

function fallbackToDemoOrThrow<T>(path: string, options: RequestInit, errorMessage: string): T {
  if (isMarsApiPath(path)) {
    throw new Error(`${errorMessage}. MARS requires the Django backend and local worker; demo mode cannot generate interviews.`);
  }
  if (enableDemoMode()) {
    return demoFallback<T>(path, options);
  }
  throw new Error(`${errorMessage}. Start Django or set VITE_ENABLE_DEMO_MODE=true to use demo data.`);
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const forceBackend = isMarsApiPath(path);
  // In demo mode, return mock data for known paths
  if (isDemoMode() && !forceBackend) {
    return demoFallback<T>(path, options);
  }

  let response: Response;
  const { timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS, ...requestOptions } = options;
  try {
    const csrfToken = isMutationRequest(requestOptions.method) ? await ensureCsrfToken(forceBackend) : getCookie("csrftoken");
    response = await fetchWithTimeout(`${apiBaseForPath(path)}${path}`, {
      credentials: "include",
      ...requestOptions,
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
        ...((requestOptions.headers as Record<string, string>) || {}),
      },
    }, timeoutMs);
  } catch (error) {
    // Network error — backend unreachable
    return fallbackToDemoOrThrow<T>(path, requestOptions, isAbortError(error) ? "Backend request timed out" : "Backend unavailable");
  }

  // If server returned HTML instead of JSON (Vite SPA fallback), switch to demo
  const ct = response.headers.get("content-type") || "";
  if (ct.includes("text/html")) {
    return fallbackToDemoOrThrow<T>(path, options, "Backend returned HTML instead of JSON");
  }

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return response.json();
}

function normalizeWsOrigin(rawValue: string): string {
  const raw = (rawValue || "").trim().replace(/\/$/, "");
  if (!raw) return "";
  if (raw.startsWith("ws://") || raw.startsWith("wss://")) return raw;
  if (raw.startsWith("http://")) return `ws://${raw.slice("http://".length)}`;
  if (raw.startsWith("https://")) return `wss://${raw.slice("https://".length)}`;
  const proto = window.location.protocol === "https:" ? "wss://" : "ws://";
  return `${proto}${raw}`;
}

function buildWsBase(): string {
  const explicitWs = normalizeWsOrigin(import.meta.env.VITE_DJANGO_WS_URL || "");
  if (explicitWs) {
    return explicitWs;
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = import.meta.env.VITE_WS_HOST || window.location.host;
  return `${proto}//${host}`;
}

export function getWsUrl(serverId: number | string, wsToken?: string): string {
  const base = `${buildWsBase()}/ws/servers/${serverId}/terminal/`;
  if (wsToken) {
    return `${base}?ws_token=${encodeURIComponent(wsToken)}`;
  }
  return base;
}

export function getStudioPipelineRunWsUrl(runId: number | string): string {
  return `${buildWsBase()}/ws/studio/pipeline-runs/${runId}/live/`;
}

export function getMarsRunWsUrl(runId: number | string): string {
  return `${buildWsBase()}/ws/mars/runs/${runId}/live/`;
}

export function backendPath(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (BACKEND_ORIGIN) return `${BACKEND_ORIGIN}${normalized}`;
  return normalized;
}

export function getRdpPath(serverId: number | string): string {
  return backendPath(`/servers/${serverId}/terminal/`);
}

export async function buildBinaryRequestHeaders(method = "POST"): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};
  if (isMutationRequest(method)) {
    const csrfToken = await ensureCsrfToken();
    if (csrfToken) headers["X-CSRFToken"] = csrfToken;
  }
  return headers;
}

export type WatcherDraftSeverity = "info" | "warning" | "critical";
export type WatcherDraftStatus = "open" | "acknowledged" | "resolved" | "suppressed";

export interface WatcherDraftItem {
  id: number;
  server_id: number;
  server_name: string;
  severity: WatcherDraftSeverity;
  recommended_role: string;
  objective: string;
  reasons: string[];
  memory_excerpt: string[];
  status: WatcherDraftStatus;
  acknowledged_at: string | null;
  acknowledged_by: string;
  resolved_at: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  metadata: Record<string, unknown>;
}

export interface WatcherDraftSummary {
  open: number;
  acknowledged: number;
  resolved: number;
  suppressed: number;
  total: number;
}

export interface WatcherScanSummary {
  scanned_servers: number;
  critical: number;
  warning: number;
  drafts: number;
}

export interface WatcherPersistedStats {
  created: number;
  updated: number;
  reopened: number;
  resolved: number;
}

export interface WatcherScanDraft {
  server_id: number;
  server_name: string;
  severity: WatcherDraftSeverity;
  recommended_role: string;
  objective: string;
  reasons: string[];
  memory_excerpt: string[];
}

export interface WatcherDraftsResponse {
  success: boolean;
  summary: WatcherDraftSummary;
  drafts: WatcherDraftItem[];
}

export interface WatcherScanResponse {
  success: boolean;
  generated_at: string;
  summary: WatcherScanSummary;
  scanned_server_ids: number[];
  requested_server_ids: number[];
  persisted_scan: boolean;
  persisted?: WatcherPersistedStats;
  drafts: WatcherScanDraft[];
}

export async function fetchWatcherDrafts(options?: {
  statuses?: WatcherDraftStatus[];
  serverId?: number;
  limit?: number;
}) {
  const params = new URLSearchParams();
  for (const status of options?.statuses || []) {
    params.append("status", status);
  }
  if (options?.serverId) {
    params.set("server_id", String(options.serverId));
  }
  if (options?.limit) {
    params.set("limit", String(options.limit));
  }
  const query = params.toString();
  return apiFetch<WatcherDraftsResponse>(`/servers/api/watchers/drafts/${query ? `?${query}` : ""}`);
}

export async function scanWatcherDrafts(payload?: {
  persist?: boolean;
  server_ids?: number[];
  limit?: number;
}) {
  return apiFetch<WatcherScanResponse>("/servers/api/watchers/scan/", {
    method: "POST",
    body: JSON.stringify(payload || { persist: true }),
  });
}

export async function acknowledgeWatcherDraft(draftId: number) {
  return apiFetch<{ success: boolean; draft: WatcherDraftItem }>(`/servers/api/watchers/drafts/${draftId}/ack/`, {
    method: "POST",
  });
}

export async function launchWatcherDraft(draftId: number) {
  return apiFetch<{
    success: boolean;
    draft: WatcherDraftItem;
    agent_id: number;
    run_id: number;
    status: string;
  }>(`/servers/api/watchers/drafts/${draftId}/launch/`, {
    method: "POST",
  });
}
