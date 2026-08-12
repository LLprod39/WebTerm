import { Activity, Brain, FileText, Layers, Server, Settings2, Shield, Zap, type LucideIcon } from "lucide-react";
import { localize } from "@/lib/i18n";

export function formatDuration(ms: number): string {
  if (!ms) return "—";
  if (ms < 1000) return `${ms}ms`;
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  return `${mins}m ${secs % 60}s`;
}

export const MODE_ICONS: Record<string, typeof Layers> = { mini: Zap, full: Brain, multi: Layers };

export function agentModeLabel(mode: "all" | "mini" | "full" | "multi" | string, lang: string) {
  if (mode === "all") return localize(lang, "Все", "All");
  if (mode === "mini") return localize(lang, "Мини", "Mini");
  if (mode === "full") return localize(lang, "Полный", "Full");
  // multi = multi-agent orchestrator (not Studio graph pipelines)
  if (mode === "multi") return localize(lang, "Мульти-агент", "Multi-agent");
  return mode;
}

export const AGENT_ICONS: Record<string, LucideIcon> = {
  security_audit: Shield,
  security_patrol: Shield,
  log_analyzer: FileText,
  log_investigator: FileText,
  performance: Activity,
  disk_report: Server,
  docker_status: Layers,
  service_health: Settings2,
  deploy_watcher: Zap,
  infra_scout: Server,
  multi_health: Activity,
  custom: Settings2,
};

export const HIDDEN_AGENT_TEMPLATE_TYPES = new Set(["docker_status"]);

export const FULL_AGENT_TOOL_OPTIONS = [
  { key: "open_connection", label: "Open connection" },
  { key: "close_connection", label: "Close connection" },
  { key: "ssh_execute", label: "SSH execute" },
  { key: "read_console", label: "Read console" },
  { key: "wait_for_output", label: "Wait for output" },
  { key: "report", label: "Progress report" },
  { key: "ask_user", label: "Ask user" },
  { key: "analyze_output", label: "Analyze output" },
  { key: "list_skills", label: "List skills" },
  { key: "read_skill", label: "Read skill" },
  { key: "list_materials", label: "List materials" },
  { key: "read_material", label: "Read material" },
  { key: "run_script_material", label: "Run script material" },
  { key: "update_material_task", label: "Update material task" },
] as const;

export const READ_ONLY_AGENT_TOOL_KEYS = new Set([
  "open_connection",
  "close_connection",
  "ssh_execute",
  "read_console",
  "wait_for_output",
  "report",
  "ask_user",
  "analyze_output",
  "list_skills",
  "read_skill",
  "list_materials",
  "read_material",
]);

export type AgentSudoPolicy = "disabled" | "ask" | "approved";

export const SUDO_AGENT_OPTIONS: Array<{
  value: AgentSudoPolicy;
  labelRu: string;
  labelEn: string;
  hintRu: string;
  hintEn: string;
}> = [
  {
    value: "disabled",
    labelRu: "Без sudo",
    labelEn: "No sudo",
    hintRu: "Команды с sudo будут заблокированы.",
    hintEn: "Commands with sudo are blocked.",
  },
  {
    value: "ask",
    labelRu: "Спросить при необходимости",
    labelEn: "Ask when needed",
    hintRu: "Агент остановится и попросит разрешение, если ему понадобится sudo.",
    hintEn: "The agent stops and asks when sudo is needed.",
  },
  {
    value: "approved",
    labelRu: "Разрешить на запуск",
    labelEn: "Approve for run",
    hintRu: "Sudo разрешён для запусков этого агента; backend выполнит его как sudo -n.",
    hintEn: "Sudo is approved for this agent's runs; backend enforces sudo -n.",
  },
];

export function sudoAgentOption(value: string | undefined) {
  return SUDO_AGENT_OPTIONS.find((item) => item.value === value) || SUDO_AGENT_OPTIONS[0];
}

export function buildDefaultToolsConfig() {
  return Object.fromEntries(
    FULL_AGENT_TOOL_OPTIONS.map((tool) => [tool.key, READ_ONLY_AGENT_TOOL_KEYS.has(tool.key)]),
  );
}

export function buildAllToolsConfig() {
  return Object.fromEntries(FULL_AGENT_TOOL_OPTIONS.map((tool) => [tool.key, true]));
}

export function enforceReadOnlyToolsConfig(config: Record<string, boolean>) {
  return Object.fromEntries(
    FULL_AGENT_TOOL_OPTIONS.map((tool) => [
      tool.key,
      READ_ONLY_AGENT_TOOL_KEYS.has(tool.key) && Boolean(config[tool.key]),
    ]),
  );
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

export function formatRoleLabel(role: string): string {
  return role
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
