export type StudioSectionFeature =
  | "studio_pipelines"
  | "studio_runs"
  | "studio_agents"
  | "studio_skills"
  | "studio_mcp"
  | "studio_notifications";

export type FeatureFlag =
  | "servers"
  | "dashboard"
  | "agents"
  | "studio"
  | StudioSectionFeature
  | "telegram_notifications"
  | "telegram_assistant"
  | "kubernetes"
  | "kubernetes_admin_read"
  | "kubernetes_admin_write"
  | "kubernetes_break_glass"
  | "kubernetes_secret_read"
  | "mars"
  | "plugins"
  | "settings"
  | "chat"
  | "orchestrator"
  | "automation"
  | "ai_connections_personal"
  | "ai_connections_admin"
  | "knowledge_base"
  | "web_research";

/** EN fallback labels — keep aligned with ACCESS_FEATURE_META in accessUiText.ts */
export const ACCESS_FEATURE_OPTIONS: Array<{ value: FeatureFlag; label: string }> = [
  { value: "servers", label: "Servers" },
  { value: "dashboard", label: "Dashboard" },
  { value: "agents", label: "Agents" },
  { value: "chat", label: "Chat (assistant)" },
  { value: "automation", label: "Automation (playbooks)" },
  { value: "ai_connections_personal", label: "AI connections (personal)" },
  { value: "ai_connections_admin", label: "AI connections (workspace admin)" },
  { value: "studio", label: "Studio" },
  { value: "studio_pipelines", label: "Studio: Pipelines" },
  { value: "studio_runs", label: "Studio: Runs" },
  { value: "studio_agents", label: "Studio: Agent configs" },
  { value: "studio_skills", label: "Studio: Skills" },
  { value: "studio_mcp", label: "Studio: MCP" },
  { value: "studio_notifications", label: "Studio: Notifications" },
  { value: "telegram_notifications", label: "Telegram: Notifications" },
  { value: "telegram_assistant", label: "Telegram: AI Assistant" },
  { value: "kubernetes", label: "Kubernetes" },
  { value: "kubernetes_admin_read", label: "Kubernetes: deep inspect" },
  { value: "kubernetes_admin_write", label: "Kubernetes: mutate cluster" },
  { value: "kubernetes_break_glass", label: "Kubernetes: emergency access (exec)" },
  { value: "kubernetes_secret_read", label: "Kubernetes: read secrets" },
  { value: "mars", label: "MARS (diagnostics)" },
  { value: "settings", label: "Settings" },
  { value: "orchestrator", label: "Orchestrator (legacy)" },
  { value: "knowledge_base", label: "Knowledge Base" },
  { value: "web_research", label: "Web research (chat tool)" },
];
