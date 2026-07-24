import type { Dispatch, SetStateAction } from "react";
import type { LucideIcon } from "lucide-react";
import type {
  AgentInputArtifact,
  AgentScheduleConfig,
  AgentScheduleMode,
  AgentTemplate,
  FrontendServer,
  StudioSkill,
} from "@/lib/api";
import type { AgentSudoPolicy, AgentTaskDraft, AgentWizardCheck, AgentWizardStep } from "./agentPageUtils";

export type SummaryRow = { icon: LucideIcon; label: string; value: string };
export type AgentMode = "mini" | "full" | "multi";
export type StateSetter<T> = Dispatch<SetStateAction<T>>;

export type AgentWizardStepContentProps = {
  step: AgentWizardStep;
  lang: string;
  t: (key: string) => string;
  mode: AgentMode;
  setMode: StateSetter<AgentMode>;
  templates: AgentTemplate[];
  onSelectTemplate: (template: AgentTemplate) => void;
  selectedType: string;
  setSelectedType: StateSetter<string>;
  setStep: StateSetter<AgentWizardStep>;
  name: string;
  setName: StateSetter<string>;
  commands: string;
  setCommands: StateSetter<string>;
  aiPrompt: string;
  setAiPrompt: StateSetter<string>;
  goal: string;
  setGoal: StateSetter<string>;
  systemPrompt: string;
  setSystemPrompt: StateSetter<string>;
  maxIter: number;
  setMaxIter: StateSetter<number>;
  sessionTimeoutSeconds: number;
  setSessionTimeoutSeconds: StateSetter<number>;
  maxConnections: number;
  setMaxConnections: StateSetter<number>;
  sudoPolicy: AgentSudoPolicy;
  setSudoPolicy: StateSetter<AgentSudoPolicy>;
  servers: FrontendServer[];
  totalServerCount: number;
  serverSearch: string;
  setServerSearch: StateSetter<string>;
  selectedServers: number[];
  toggleServer: (id: number) => void;
  selectAll: () => void;
  hasAllServersSelected: boolean;
  schedule: number;
  setSchedule: StateSetter<number>;
  scheduleConfig: AgentScheduleConfig;
  setScheduleConfig: StateSetter<AgentScheduleConfig>;
  setScheduleMode: (mode: AgentScheduleMode) => void;
  updateSchedule: (patch: Partial<AgentScheduleConfig>) => void;
  toggleWeekday: (day: number) => void;
  enabledToolCount: number;
  toolsConfig: Record<string, boolean>;
  setToolsConfig: StateSetter<Record<string, boolean>>;
  toolsExpanded: boolean;
  setToolsExpanded: StateSetter<boolean>;
  stopConditionsText: string;
  setStopConditionsText: StateSetter<string>;
  selectedSkillSlugs: string[];
  availableSkills: StudioSkill[];
  visibleSkills: StudioSkill[];
  toggleSkill: (slug: string) => void;
  skillsExpanded: boolean;
  setSkillsExpanded: StateSetter<boolean>;
  inputArtifacts: AgentInputArtifact[];
  activeArtifact: AgentInputArtifact | null;
  activeArtifactIndex: number | null;
  setActiveArtifactIndex: StateSetter<number | null>;
  addArtifact: (kind: AgentInputArtifact["kind"]) => void;
  removeArtifact: (index: number) => void;
  updateArtifact: (index: number, patch: Partial<AgentInputArtifact>) => void;
  updateArtifactTask: (artifactIndex: number, taskIndex: number, patch: Partial<AgentTaskDraft>) => void;
  addArtifactTask: (artifactIndex: number) => void;
  removeArtifactTask: (artifactIndex: number, taskIndex: number) => void;
  onMaterialFiles: (files: FileList | null) => void | Promise<void>;
  telegramEnabled: boolean;
  setTelegramEnabled: StateSetter<boolean>;
  telegramChatId: string;
  setTelegramChatId: StateSetter<string>;
  sudoRiskAcknowledged: boolean;
  setSudoRiskAcknowledged: StateSetter<boolean>;
  summaryRows: SummaryRow[];
  commandCount: number;
  readiness: number;
  readinessChecks: AgentWizardCheck[];
  runAfterSave?: boolean;
  setRunAfterSave?: StateSetter<boolean>;
  isEditing?: boolean;
};
