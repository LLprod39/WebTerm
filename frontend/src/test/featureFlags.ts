import type { FeatureFlag } from "@/lib/api";

const FEATURE_FLAGS: FeatureFlag[] = [
  "servers",
  "dashboard",
  "agents",
  "studio",
  "studio_pipelines",
  "studio_runs",
  "studio_agents",
  "studio_skills",
  "studio_mcp",
  "studio_notifications",
  "kubernetes",
  "mars",
  "plugins",
  "settings",
  "chat",
  "orchestrator",
  "automation",
  "ai_connections_personal",
  "ai_connections_admin",
  "knowledge_base",
];

export function featureMap(overrides: Partial<Record<FeatureFlag, boolean>> = {}) {
  const defaults = Object.fromEntries(FEATURE_FLAGS.map((feature) => [feature, false])) as Record<FeatureFlag, boolean>;
  return { ...defaults, ...overrides };
}
