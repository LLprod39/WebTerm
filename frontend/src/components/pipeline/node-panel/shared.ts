import type { AgentConfig, MCPServer, StudioSkill } from "@/lib/api";

export type NodePanelLang = "en" | "ru";

export type SudoPolicy = "inherit" | "disabled" | "ask" | "approved";

export const SUDO_POLICY_OPTIONS: Array<{
  value: SudoPolicy;
  labelRu: string;
  labelEn: string;
  hintRu: string;
  hintEn: string;
}> = [
  {
    value: "inherit",
    labelRu: "Как в профиле",
    labelEn: "Inherit",
    hintRu: "Использовать настройку сохранённого агента. Без профиля = sudo запрещён.",
    hintEn: "Use the saved agent setting. Without a saved profile, sudo is disabled.",
  },
  {
    value: "disabled",
    labelRu: "Без sudo",
    labelEn: "No sudo",
    hintRu: "Команды с sudo будут заблокированы.",
    hintEn: "Commands with sudo are blocked.",
  },
  {
    value: "ask",
    labelRu: "Спросить",
    labelEn: "Ask",
    hintRu: "Агент остановится и попросит разрешение, если ему понадобится sudo.",
    hintEn: "The agent stops and asks when it needs sudo.",
  },
  {
    value: "approved",
    labelRu: "Разрешить",
    labelEn: "Approved",
    hintRu: "Sudo разрешён на этот запуск; система выполнит его как sudo -n.",
    hintEn: "Sudo is approved for this run; backend enforces sudo -n.",
  },
];

export function sudoPolicyLabel(value: string | undefined, lang: NodePanelLang) {
  const option = SUDO_POLICY_OPTIONS.find((item) => item.value === value);
  if (!option) return t(lang, "Без sudo", "No sudo");
  return t(lang, option.labelRu, option.labelEn);
}

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
