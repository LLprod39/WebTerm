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

export type LoggingConfig = typeof DEFAULT_LOGGING_CONFIG;
export type LoggingConfigKey = keyof LoggingConfig;

export const LOGGING_KEYS = Object.keys(DEFAULT_LOGGING_CONFIG) as LoggingConfigKey[];

export const LOGGING_ITEM_KEYS: Array<{
  key: LoggingConfigKey;
  labelKey: string;
  descKey: string;
  icon: ElementType;
}> = [
  { key: "log_terminal_commands", labelKey: "audit.terminal_label", descKey: "audit.terminal_desc", icon: Terminal },
  { key: "log_ai_assistant", labelKey: "audit.ai_label", descKey: "audit.ai_desc", icon: MessageSquare },
  { key: "log_agent_runs", labelKey: "audit.agents_label", descKey: "audit.agents_desc", icon: Bot },
  { key: "log_pipeline_runs", labelKey: "audit.pipelines_label", descKey: "audit.pipelines_desc", icon: Workflow },
  { key: "log_auth_events", labelKey: "audit.auth_label", descKey: "audit.auth_desc", icon: Shield },
  { key: "log_server_changes", labelKey: "audit.servers_label", descKey: "audit.servers_desc", icon: Database },
  { key: "log_settings_changes", labelKey: "audit.settings_label", descKey: "audit.settings_desc", icon: Key },
  { key: "log_mcp_calls", labelKey: "audit.mcp_label", descKey: "audit.mcp_desc", icon: Cpu },
  { key: "log_file_operations", labelKey: "audit.files_label", descKey: "audit.files_desc", icon: FileText },
  { key: "log_http_requests", labelKey: "audit.http_label", descKey: "audit.http_desc", icon: Globe },
];

export const CATEGORY_ICONS: Record<string, ElementType> = {
  terminal: Terminal,
  ai: Bot,
  agent: Bot,
  pipeline: Workflow,
  auth: Shield,
  server: Database,
  settings: Key,
};

export const DATE_PRESET_KEYS = [
  { labelKey: "adash.preset_today", days: 0 },
  { labelKey: "audit.yesterday", days: 1 },
  { labelKey: "adash.preset_7d", days: 7 },
  { labelKey: "adash.preset_14d", days: 14 },
  { labelKey: "adash.preset_30d", days: 30 },
];

export function relativeTime(value: string): string {
  const d = new Date(value);
  const diff = Math.max(1, Math.floor((Date.now() - d.getTime()) / 60000));
  if (diff < 60) return `${diff}m ago`;
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`;
  return `${Math.floor(diff / 1440)}d ago`;
}
