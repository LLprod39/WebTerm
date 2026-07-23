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

export const OLLAMA_RUNTIME_KEYS = [
  { value: "auto", key: "ai.ollama_auto" },
  { value: "local", key: "ai.ollama_local_only" },
  { value: "cloud", key: "ai.ollama_cloud_only" },
];

export const OLLAMA_THINKING_KEYS = [
  { value: AUTO_OLLAMA_THINKING_VALUE, key: "ai.ollama_auto" },
  { value: "off", key: "ai.thinking_off" },
  { value: "on", key: "ai.thinking_on" },
  { value: "low", key: "ai.thinking_low" },
  { value: "medium", key: "ai.thinking_medium" },
  { value: "high", key: "ai.thinking_high" },
];

export const PROVIDER_API_STATUS_KEY: Record<string, string> = {
  gemini: "gemini_set",
  grok: "grok_set",
  openai: "openai_set",
  claude: "claude_set",
  ollama: "ollama_set",
};

export const API_KEY_PROVIDERS = [
  { value: "gemini", name: "Gemini", statusKey: "gemini_set", envName: "GEMINI_API_KEY", placeholder: "AIza..." },
  { value: "grok", name: "Grok", statusKey: "grok_set", envName: "GROK_API_KEY", placeholder: "xai-..." },
  { value: "openai", name: "OpenAI", statusKey: "openai_set", envName: "OPENAI_API_KEY", placeholder: "sk-..." },
  { value: "claude", name: "Claude", statusKey: "claude_set", envName: "ANTHROPIC_API_KEY", placeholder: "sk-ant-..." },
  { value: "ollama", name: "Ollama Cloud", statusKey: "ollama_cloud_set", envName: "OLLAMA_API_KEY", placeholder: "ollama key" },
];

export const PROVIDER_METADATA: Record<
  string,
  {
    accentColor: string;
    textColor: string;
    badge: string;
    brand: string;
    slogan: string;
  }
> = {
  grok: {
    accentColor: "bg-amber-500",
    textColor: "text-amber-500",
    badge: "Быстрые ответы",
    brand: "xAI",
    slogan: "Подходит для коротких проверок, сводок и быстрых ответов.",
  },
  gemini: {
    accentColor: "bg-violet-500",
    textColor: "text-violet-500",
    badge: "Широкий контекст",
    brand: "Google",
    slogan: "Удобен для длинных логов, документов и больших контекстов.",
  },
  openai: {
    accentColor: "bg-emerald-500",
    textColor: "text-emerald-500",
    badge: "Инструменты и логика",
    brand: "OpenAI",
    slogan: "Хороший выбор для вызова инструментов, проверок и структурированных ответов.",
  },
  claude: {
    accentColor: "bg-orange-500",
    textColor: "text-orange-500",
    badge: "Анализ текста",
    brand: "Anthropic",
    slogan: "Полезен для разборов, аккуратных отчётов и сложных инструкций.",
  },
  ollama: {
    accentColor: "bg-sky-500",
    textColor: "text-sky-500",
    badge: "Локальное исполнение",
    brand: "Ollama",
    slogan: "Запускает локальные модели, когда данные не должны уходить наружу.",
  },
};

export const ROLE_FEATURES: Record<string, { label: string; tooltip: string }[]> = {
  "Чат / терминал": [
    { label: "Потоковый вывод", tooltip: "Ответ появляется по мере генерации, без ожидания полного текста." },
    { label: "Быстрый ответ", tooltip: "Лучше выбирать модель с небольшой задержкой первого токена." },
    { label: "Контекст сессии", tooltip: "Учитывает историю терминала и настройки сервера." },
  ],
  "Агенты (ReAct)": [
    { label: "Инструменты", tooltip: "Должна стабильно вызывать SSH и системные инструменты." },
    { label: "Большой контекст", tooltip: "Полезно для логов, конфигураций и длинных выводов." },
    { label: "Самопроверка", tooltip: "Модель должна корректировать план после ошибок выполнения." },
  ],
  Пайплайны: [
    { label: "JSON", tooltip: "Нужны строгие структурированные ответы." },
    { label: "Стабильность", tooltip: "Важно одинаково выполнять повторяющиеся шаги автоматизации." },
    { label: "Состояние", tooltip: "Передаёт состояние между шагами сценария." },
  ],
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
