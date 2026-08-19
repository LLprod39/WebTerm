import { useState, type ReactNode } from "react";
import { CheckCircle2, Info, Trash2 } from "lucide-react";

import type { AgentConfig, MCPServer, PipelineNode, StudioSkill } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

import { NodePanelHeader } from "./NodePanelHeader";
import { NodePanelTabContent, NodePanelTabs, type NodePanelTabValue } from "./NodePanelTabs";
import { NodeSettingsTab } from "./NodeSettingsTab";
import { PoliciesTab } from "./PoliciesTab";
import { PromptsTab } from "./PromptsTab";
import type { AgentProviderCardOption, NodePanelLang, StudioServerOption } from "./shared";
import { t } from "./shared";

type AgentNodePanelProps = {
  lang: NodePanelLang;
  node: PipelineNode;
  data: Record<string, unknown>;
  title: string;
  breadcrumb: string;
  guidanceSummary: string;
  guidanceChecklist: string[];
  icon: ReactNode;
  agents: AgentConfig[];
  selectedAgent: AgentConfig | null;
  provider: string;
  providerOptions: AgentProviderCardOption[];
  modelList: string[];
  loadingModelsFor: string | null;
  canSelectModels?: boolean;
  mcpList: MCPServer[];
  servers: StudioServerOption[];
  skillList: StudioSkill[];
  selectedSkillSlugs: string[];
  selectedSkills: StudioSkill[];
  onSet: (key: string, value: unknown) => void;
  onSetMany: (patch: Record<string, unknown>) => void;
  onProviderChange: (provider: string) => void;
  onClose: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onBrowseCatalog: () => void;
};

export function AgentNodePanel({
  lang,
  node,
  data,
  title,
  breadcrumb,
  guidanceSummary,
  guidanceChecklist,
  icon,
  agents,
  selectedAgent,
  provider,
  providerOptions,
  modelList,
  loadingModelsFor,
  canSelectModels = false,
  mcpList,
  servers,
  skillList,
  selectedSkillSlugs,
  selectedSkills,
  onSet,
  onSetMany,
  onProviderChange,
  onClose,
  onDuplicate,
  onDelete,
  onBrowseCatalog,
}: AgentNodePanelProps) {
  const [activeTab, setActiveTab] = useState<NodePanelTabValue>("settings");

  return (
    <div className="flex h-full min-h-0 flex-col bg-card">
      <NodePanelHeader
        lang={lang}
        icon={icon}
        title={title}
        breadcrumb={breadcrumb}
        nodeId={node.id}
        onDuplicate={onDuplicate}
        onClose={onClose}
      />

      <div className="border-b border-border/70 bg-muted/10 px-4 py-3">
        <div className="flex items-start gap-2">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <p className="text-xs leading-relaxed text-muted-foreground">{guidanceSummary}</p>
        </div>
        {guidanceChecklist.length ? (
          <div className="mt-2 grid gap-1">
            {guidanceChecklist.slice(0, 3).map((item) => (
              <div key={item} className="flex items-start gap-2 text-xs leading-5 text-muted-foreground">
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <NodePanelTabs lang={lang} value={activeTab} onValueChange={setActiveTab}>
        <NodePanelTabContent value="settings" className="mt-0 min-h-0 flex-1">
          <div className="h-full overflow-y-auto px-4 py-4">
            <NodeSettingsTab
              lang={lang}
              data={data}
              agents={agents}
              selectedAgent={selectedAgent}
              provider={provider}
              providerOptions={providerOptions}
              modelList={modelList}
              loadingModelsFor={loadingModelsFor}
              canSelectModels={canSelectModels}
              mcpList={mcpList}
              servers={servers}
              selectedSkills={selectedSkills}
              onSet={onSet}
              onSetMany={onSetMany}
              onProviderChange={onProviderChange}
              onOpenPoliciesTab={() => setActiveTab("policies")}
            />
          </div>
        </NodePanelTabContent>

        <NodePanelTabContent value="prompts" className="mt-0 min-h-0 flex-1">
          <div className="h-full overflow-y-auto px-4 py-4">
            <PromptsTab
              lang={lang}
              goal={(data.goal as string) || ""}
              systemPrompt={(data.system_prompt as string) || ""}
              selectedAgent={selectedAgent}
              onGoalChange={(value) => onSet("goal", value)}
              onSystemPromptChange={(value) => onSet("system_prompt", value)}
            />
          </div>
        </NodePanelTabContent>

        <NodePanelTabContent value="policies" className="mt-0 min-h-0 flex-1">
          <div className="h-full overflow-y-auto px-4 py-4">
            <PoliciesTab
              lang={lang}
              skillList={skillList}
              selectedAgent={selectedAgent}
              selectedSkillSlugs={selectedSkillSlugs}
              onBrowseCatalog={onBrowseCatalog}
              onToggleSkill={(skillSlug) => {
                const nextValue = selectedSkillSlugs.includes(skillSlug)
                  ? selectedSkillSlugs.filter((item) => item !== skillSlug)
                  : [...selectedSkillSlugs, skillSlug];
                onSet("skill_slugs", nextValue);
              }}
            />
          </div>
        </NodePanelTabContent>
      </NodePanelTabs>

      <Separator />
      <div className="px-4 py-3">
        <Button
          type="button"
          variant="outline"
          className="w-full justify-start gap-2 rounded-lg border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive"
          onClick={onDelete}
        >
          <Trash2 className="h-4 w-4" />
          {t(lang, "Удалить ноду", "Delete node")}
        </Button>
      </div>
    </div>
  );
}
