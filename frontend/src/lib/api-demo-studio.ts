export function demoStudioFallback<T>(path: string): T | undefined {
  if (path.includes("/api/studio/share-users")) return [{ id: 1, username: "demo", email: "demo@example.com" }] as T;
  if (path.includes("/api/studio/assistant/drafts")) return [] as T;
  if (path.includes("/api/studio/node-manifests")) return { version: 1, count: 0, nodes: [] } as T;
  if (path.includes("/api/studio/capabilities")) return {
    strategy: {
      mode: "minimal_universal_nodes",
      service_specific_work: "mcp_plus_skills",
      default_execution_node: "agent/mcp_call",
      approval_node: "logic/human_approval",
      verification_nodes: ["ops/http_check", "output/report", "agent/mcp_call"],
    },
    nodes: [],
    capability_packs: [],
    resources: { mcp_servers: [], skills: [], server_count: 0 },
    task_families: [],
  } as T;
  if (path.includes("/api/studio/templates")) return [] as T;
  if (path.includes("/api/studio/pipelines")) return [] as T;
  if (path.includes("/api/studio/runs")) return [] as T;
  if (path.includes("/api/studio/agents")) return [] as T;
  if (path.includes("/api/studio/mcp/templates")) return [] as T;
  if (path.includes("/api/studio/mcp")) return [] as T;
  if (path.includes("/api/studio/triggers")) return [] as T;
  if (path.includes("/api/studio/notifications")) return { success: true } as T;
  if (path.includes("/api/studio/servers")) return [] as T;
  if (path.includes("/api/studio/skills")) return [] as T;
  return undefined;
}
