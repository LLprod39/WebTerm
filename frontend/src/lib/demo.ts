/**
 * Demo / offline mode: provides mock data when the Django backend is unavailable.
 * Enabled only when VITE_ENABLE_DEMO_MODE=true.
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
const _demoModeAllowed = _demoModeFlag === "true";

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
  console.info("[WebTermAI] Demo mode enabled by VITE_ENABLE_DEMO_MODE=true");
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
      studio_pipelines: true,
      studio_runs: true,
      studio_agents: true,
      studio_skills: true,
      studio_mcp: true,
      studio_notifications: true,
      kubernetes: false,
      mars: false,
      settings: true,
      orchestrator: true,
      knowledge_base: true,
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
  ],
  groups: [
    { id: null, name: "All Servers", description: "", color: "#64748b", server_count: 2, role: "", can_edit: false },
    {
      id: 1,
      name: "Production",
      description: "Prod hosts",
      color: "#3b82f6",
      server_count: 2,
      role: "owner",
      can_edit: true,
    },
    {
      id: 2,
      name: "Staging",
      description: "Staging hosts",
      color: "#22c55e",
      server_count: 0,
      role: "owner",
      can_edit: true,
    },
  ],
  stats: { owned: 2, shared: 0, total: 2 },
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
    fair_enabled: false,
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
    chat_model_fair: "qwen3:14b",
    chat_model_claude: "",
    chat_model_ollama: "",
    agent_model_fair: "fair-spark",
    fair_base_url: "https://fair-hyperion.dev.k8s.erg.kz/api/hyperion/openai/v1",
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
    agent_active_runs_per_user_limit: 5,
    agent_active_runs_global_limit: 25,
    agent_run_stale_seconds: 21600,
    pipeline_active_runs_per_user_limit: 8,
    pipeline_active_runs_global_limit: 40,
    pipeline_run_stale_seconds: 21600,
    ssh_terminal_sessions_per_user_limit: 12,
    ssh_terminal_sessions_global_limit: 120,
    ssh_terminal_session_stale_seconds: 180,
    llm_daily_token_limit_per_user: 250000,
    mcp_stdio_initialize_timeout_seconds: 20,
    mcp_stdio_request_timeout_seconds: 30,
    mcp_stdio_tool_call_timeout_seconds: 120,
    mcp_process_terminate_timeout_seconds: 2,
    mcp_http_connect_timeout_seconds: 10,
    mcp_http_request_timeout_seconds: 30,
    mcp_http_tool_call_timeout_seconds: 120,
    mcp_http_retry_attempts: 2,
  },
  ldap_status: {
    enabled: false,
    status: "disabled",
    severity: "ready",
    backend_loaded: false,
    server_configured: false,
    search_base_configured: false,
    bind_dn_configured: false,
    bind_password_configured: false,
    start_tls: false,
    ignore_cert: false,
    ca_cert_configured: false,
    missing: [],
    config_source: "env_startup",
  },
};

export const DEMO_MODELS: ModelsResponse = {
  gemini: ["gemini-2.0-flash", "gemini-1.5-pro"],
  grok: [],
  openai: [],
  fair: ["qwen3:14b", "fair-spark"],
  claude: [],
  ollama: [],
  ollama_local: [],
  ollama_cloud: [],
  current: {
    default_provider: "gemini",
    chat_gemini: "gemini-2.0-flash",
    chat_grok: "",
    chat_openai: "",
    chat_fair: "qwen3:14b",
    chat_claude: "",
    chat_ollama: "",
    agent_model_fair: "fair-spark",
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
