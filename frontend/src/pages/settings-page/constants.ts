import type { ElementType } from "react";
import {
  Activity,
  Bot,
  Cpu,
  Database,
  FileText,
  Globe,
  Key,
  MessageSquare,
  Shield,
  Terminal,
  Workflow,
} from "lucide-react";
import type { SettingsConfig } from "@/lib/api";

export const LLM_PROVIDERS = [
  { value: "grok", label: "Grok (xAI)" },
  { value: "gemini", label: "Gemini (Google)" },
  { value: "openai", label: "OpenAI" },
  { value: "claude", label: "Claude (Anthropic)" },
  { value: "ollama", label: "Ollama" },
];

export const AUTO_REASONING_VALUE = "__auto__";
export const AUTO_OLLAMA_THINKING_VALUE = "__auto__";
export const LLM_PROVIDER_VALUES = LLM_PROVIDERS.map((provider) => provider.value);

export const OLLAMA_RUNTIME_OPTIONS = [
  { value: "auto", label: "Авто" },
  { value: "local", label: "Только локально" },
  { value: "cloud", label: "Только облако" },
];

export const OLLAMA_THINKING_OPTIONS = [
  { value: AUTO_OLLAMA_THINKING_VALUE, label: "Авто" },
  { value: "off", label: "Выкл" },
  { value: "on", label: "Вкл" },
  { value: "low", label: "Низкий" },
  { value: "medium", label: "Средний" },
  { value: "high", label: "Высокий" },
];

export const PROVIDER_API_STATUS_KEY: Record<string, string> = {
  gemini: "gemini_set",
  grok: "grok_set",
  openai: "openai_set",
  claude: "claude_set",
  ollama: "ollama_set",
};

export const CATEGORY_ICONS: Record<string, ElementType> = {
  terminal: Terminal,
  ai: Bot,
  agent: Bot,
  pipeline: Workflow,
  auth: Shield,
  server: Database,
  settings: Key,
};

export const DATE_PRESETS = [
  { label: "Сегодня", days: 0 },
  { label: "Вчера", days: 1 },
  { label: "7 дней", days: 7 },
  { label: "14 дней", days: 14 },
  { label: "30 дней", days: 30 },
];

export const DEFAULT_LOGGING_CONFIG = {
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
};

export const LOGGING_KEYS = Object.keys(DEFAULT_LOGGING_CONFIG);

export const LOGGING_ITEMS = [
  { key: "log_terminal_commands", label: "Команды терминала", desc: "Записывать все SSH-команды пользователей", icon: Terminal },
  { key: "log_ai_assistant", label: "AI", desc: "Записывать запросы и ответы AI", icon: MessageSquare },
  { key: "log_agent_runs", label: "Запуски агентов", desc: "Логировать все действия и итерации агентов", icon: Bot },
  { key: "log_pipeline_runs", label: "Pipeline запуски", desc: "Логировать выполнение pipeline и результаты", icon: Workflow },
  { key: "log_auth_events", label: "Авторизация", desc: "Входы, выходы, неудачные попытки", icon: Shield },
  { key: "log_server_changes", label: "Изменения серверов", desc: "Создание, обновление, удаление серверов", icon: Database },
  { key: "log_settings_changes", label: "Изменения настроек", desc: "Любые изменения в конфигурации платформы", icon: Key },
  { key: "log_mcp_calls", label: "MCP вызовы", desc: "Все вызовы к MCP серверам и инструментам", icon: Cpu },
  { key: "log_file_operations", label: "Файловые операции", desc: "Загрузки, скачивания и изменения файлов", icon: FileText },
  { key: "log_http_requests", label: "HTTP/API запросы", desc: "Логировать каждый web/API запрос пользователя", icon: Globe },
];

export type SettingsTabValue = "ai" | "access" | "memory" | "logging" | "activity";

export function relativeTime(value: string): string {
  const d = new Date(value);
  const diff = Math.max(1, Math.floor((Date.now() - d.getTime()) / 60000));
  if (diff < 60) return `${diff}m ago`;
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`;
  return `${Math.floor(diff / 1440)}d ago`;
}

export function getProviderLabel(value: string): string {
  return LLM_PROVIDERS.find((provider) => provider.value === value)?.label || value;
}

export function getProviderEnabled(config: SettingsConfig, provider: string): boolean {
  if (provider === "gemini") return config.gemini_enabled;
  if (provider === "openai") return config.openai_enabled;
  if (provider === "claude") return config.claude_enabled;
  if (provider === "ollama") return config.ollama_enabled;
  return config.grok_enabled;
}

export function getSavedModelForProvider(config: SettingsConfig, provider: string): string {
  if (provider === "gemini") return config.chat_model_gemini || "";
  if (provider === "openai") return config.chat_model_openai || "";
  if (provider === "claude") return config.chat_model_claude || "";
  if (provider === "ollama") return config.chat_model_ollama || "";
  return config.chat_model_grok || "";
}
