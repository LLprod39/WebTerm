import type { AgentConfig, MCPServer, StudioSkill } from "@/lib/api";

export type NodePanelLang = "en" | "ru";

export type StudioServerOption = {
  id: number;
  name: string;
  host: string;
};

export type AgentProviderCardOption = {
  value: string;
  label: string;
  modelLabel: string;
  hint: string;
};

export function t(lang: NodePanelLang, ru: string, en: string) {
  return lang === "ru" ? ru : en;
}

export function clampNumber(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export function getSelectedAgentConfig(
  agents: AgentConfig[],
  agentConfigId: unknown,
) {
  return agents.find((agent) => String(agent.id) === String(agentConfigId || "")) || null;
}

export function getSelectedSkills(skillList: StudioSkill[], selectedSkillSlugs: string[]) {
  return skillList.filter((skill) => selectedSkillSlugs.includes(skill.slug));
}

export function getSelectedMcpServers(mcpList: MCPServer[], selectedIds: number[]) {
  return selectedIds
    .map((id) => mcpList.find((item) => item.id === id) || null)
    .filter((item): item is MCPServer => Boolean(item));
}

export function getSelectedServers(servers: StudioServerOption[], selectedIds: number[]) {
  return selectedIds
    .map((id) => servers.find((item) => item.id === id) || null)
    .filter((item): item is StudioServerOption => Boolean(item));
}
