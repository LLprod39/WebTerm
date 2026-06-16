import type { AgentConfig, MCPServer, StudioSkill } from "@/lib/api";

export type Lang = "en" | "ru";
export type NodeData = Record<string, unknown>;
export type SetNodeData = (key: string, value: unknown) => void;
export type SetNodePatch = (patch: Record<string, unknown>) => void;
export type ServerOption = { id: number; name: string; host: string };

export type SkillPickerProps = {
  lang: Lang;
  skillList: StudioSkill[];
  selectedSkillSlugs: string[];
  selectedSkills: StudioSkill[];
  onSet: SetNodeData;
  onBrowseCatalog: () => void;
  label?: string;
};

export type NodeConfigSectionProps = {
  type: string;
  data: NodeData;
  lang: Lang;
  onSet: SetNodeData;
  onSetMany: SetNodePatch;
};

export type AgentResourceProps = {
  agents: AgentConfig[];
  mcpList: MCPServer[];
  servers: ServerOption[];
  skillList: StudioSkill[];
  selectedSkillSlugs: string[];
  selectedSkills: StudioSkill[];
};
