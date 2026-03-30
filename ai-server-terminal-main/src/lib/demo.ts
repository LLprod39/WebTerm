/**
 * Demo / offline mode: provides mock data when the Django backend is unavailable.
 * Activated automatically when the first auth session request fails.
 */

import type {
  AuthSessionResponse,
  FrontendBootstrapResponse,
  SettingsConfigResponse,
  ModelsResponse,
  ActivityLogsResponse,
} from "./api";

let _demoMode = false;
const _demoModeFlag = String(import.meta.env.VITE_ENABLE_DEMO_MODE || "").toLowerCase();
const _isLocalHost =
  typeof window !== "undefined" &&
  ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname.toLowerCase());
const _isLovablePreview =
  typeof window !== "undefined" && window.location.hostname.includes("lovable.app");
const _demoModeAllowed =
  _demoModeFlag === "true" || (_demoModeFlag !== "false" && (import.meta.env.DEV || _isLocalHost || _isLovablePreview));

export function isDemoMode(): boolean {
  return _demoMode;
}

export function canUseDemoMode(): boolean {
  return _demoModeAllowed;
}

export function enableDemoMode(): boolean {
  if (!_demoModeAllowed) {
    return false;
  }
  _demoMode = true;
  console.info("[WebTermAI] Demo mode enabled — backend unavailable, using mock data");
  return true;
}

export const DEMO_SESSION: AuthSessionResponse = {
  authenticated: true,
  user: {
    id: 1,
    username: "demo",
    email: "demo@webtermanal.local",
    is_staff: true,
    features: {
      servers: true,
      dashboard: true,
      agents: true,
      studio: true,
      settings: true,
      orchestrator: true,
    },
  },
};

export const DEMO_BOOTSTRAP: FrontendBootstrapResponse = {
  success: true,
  servers: [
    {
      id: 1,
      name: "web-prod-01",
      host: "192.168.1.10",
      port: 22,
      username: "admin",
      server_type: "ssh",
      rdp: false,
      status: "online",
      group_id: 1,
      group_name: "Production",
      is_shared: false,
      can_edit: true,
      share_context_enabled: false,
      shared_by_username: "",
      terminal_path: "/servers/1/terminal/",
      minimal_terminal_path: "/servers/1/terminal/minimal/",
      last_connected: new Date().toISOString(),
    },
    {
      id: 2,
      name: "db-prod-01",
      host: "192.168.1.11",
      port: 22,
      username: "dba",
      server_type: "ssh",
      rdp: false,
      status: "online",
      group_id: 1,
      group_name: "Production",
      is_shared: false,
      can_edit: true,
      share_context_enabled: false,
      shared_by_username: "",
      terminal_path: "/servers/2/terminal/",
      minimal_terminal_path: "/servers/2/terminal/minimal/",
      last_connected: null,
    },
    {
      id: 3,
      name: "win-rdp-01",
      host: "192.168.1.20",
      port: 3389,
      username: "Administrator",
      server_type: "rdp",
      rdp: true,
      status: "offline",
      group_id: 2,
      group_name: "Staging",
      is_shared: false,
      can_edit: true,
      share_context_enabled: false,
      shared_by_username: "",
      terminal_path: "/servers/3/terminal/",
      minimal_terminal_path: "/servers/3/terminal/minimal/",
      last_connected: null,
    },
  ],
  groups: [
    { id: null, name: "All Servers", server_count: 3 },
    { id: 1, name: "Production", server_count: 2 },
    { id: 2, name: "Staging", server_count: 1 },
  ],
  stats: { owned: 3, shared: 0, total: 3 },
  recent_activity: [
    {
      id: 1,
      action: "server_connect",
      status: "success",
      description: "Connected to web-prod-01",
      entity_name: "web-prod-01",
      created_at: new Date().toISOString(),
    },
    {
      id: 2,
      action: "server_create",
      status: "info",
      description: "Server db-prod-01 added",
      entity_name: "db-prod-01",
      created_at: new Date(Date.now() - 3600_000).toISOString(),
    },
  ],
};

export const DEMO_SETTINGS: SettingsConfigResponse = {
  success: true,
  config: {
    default_provider: "gemini",
    internal_llm_provider: "gemini",
    gemini_enabled: true,
    grok_enabled: false,
    openai_enabled: false,
    claude_enabled: false,
    ollama_enabled: false,
    ollama_cloud_enabled: false,
    chat_llm_provider: "gemini",
    chat_llm_model: "gemini-2.0-flash",
    agent_llm_provider: "gemini",
    agent_llm_model: "gemini-2.0-flash",
    orchestrator_llm_provider: "gemini",
    orchestrator_llm_model: "gemini-2.0-flash",
    chat_model_gemini: "gemini-2.0-flash",
    chat_model_grok: "",
    chat_model_openai: "",
    chat_model_claude: "",
    chat_model_ollama: "",
    ollama_base_url: "http://127.0.0.1:11434",
    ollama_runtime_mode: "auto",
    ollama_cloud_base_url: "https://ollama.com",
    ollama_think_mode: "",
    log_terminal_commands: true,
    log_ai_assistant: true,
    log_agent_runs: true,
    log_pipeline_runs: true,
    log_auth_events: true,
    log_server_changes: true,
    log_settings_changes: true,
    log_file_operations: false,
    log_mcp_calls: true,
    log_http_requests: true,
    retention_days: 90,
    export_format: "json",
  },
};

export const DEMO_MODELS: ModelsResponse = {
  gemini: ["gemini-2.0-flash", "gemini-1.5-pro"],
  grok: [],
  openai: [],
  claude: [],
  ollama: [],
  ollama_local: [],
  ollama_cloud: [],
  current: {
    default_provider: "gemini",
    chat_gemini: "gemini-2.0-flash",
    chat_grok: "",
    chat_openai: "",
    chat_claude: "",
    chat_ollama: "",
    ollama_runtime_mode: "auto",
    ollama_think_mode: "",
  },
};

export const DEMO_ACTIVITY_LOGS: ActivityLogsResponse = {
  success: true,
  events: [],
  summary: { total_events: 0, total_users: 1 },
};

/** Generic fallback for any demo API call that returns {success: true} */
export function demoSuccess<T extends Record<string, unknown>>(extra?: T) {
  return { success: true, ...extra } as T & { success: boolean };
}
