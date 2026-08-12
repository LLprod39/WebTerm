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
  | "kubernetes"
  | "mars"
  | "plugins"
  | "settings"
  | "chat"
  | "orchestrator"
  | "automation"
  | "ai_connections_personal"
  | "ai_connections_admin"
  | "knowledge_base";

export const ACCESS_FEATURE_OPTIONS: Array<{ value: FeatureFlag; label: string }> = [
  { value: "servers", label: "Servers" },
  { value: "dashboard", label: "Dashboard" },
  { value: "agents", label: "Agents" },
  { value: "studio", label: "Studio" },
  { value: "studio_pipelines", label: "Studio Pipelines" },
  { value: "studio_runs", label: "Studio Runs" },
  { value: "studio_agents", label: "Studio Agents" },
  { value: "studio_skills", label: "Studio Skills" },
  { value: "studio_mcp", label: "Studio MCP" },
  { value: "studio_notifications", label: "Studio Notifications" },
  { value: "kubernetes", label: "Kubernetes" },
  { value: "mars", label: "MARS" },
  { value: "settings", label: "Settings" },
  { value: "chat", label: "Chat" },
  { value: "orchestrator", label: "Operator orchestration" },
  { value: "automation", label: "Automation" },
  { value: "ai_connections_personal", label: "AI connections (personal)" },
  { value: "ai_connections_admin", label: "AI connections (admin)" },
  { value: "knowledge_base", label: "Knowledge Base" },
];
