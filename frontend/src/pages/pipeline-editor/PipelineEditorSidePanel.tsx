import type { PipelineNode, PipelineTrigger } from "@/lib/api";
import type { StudioPipelineAssistantResponse } from "@/lib/studioPipelineDraftsApi";
import { cn } from "@/lib/utils";

import { NodeConfigPanel } from "./NodeConfigPanel";
import { PipelineAssistantPanel } from "./PipelineAssistantPanel";
import { RunMonitorPanel } from "./RunMonitorPanel";

export function PipelineEditorSidePanel({
  activeRunId,
  assistantInput,
  assistantOpen,
  assistantHistory,
  assistantPending,
  assistantProposal,
  lang,
  pipelineId,
  selectedNode,
  trigger,
  onApplyAssistantProposal,
  onApplyAndSaveAssistantProposal,
  onAssistantInputChange,
  onAssistantSend,
  onCloseAssistant,
  onCloseNode,
  onCloseRun,
  onDeleteNode,
  onDiscardAssistantProposal,
  onDuplicateNode,
  onUpdateNodeData,
}: {
  activeRunId: number | null;
  assistantInput: string;
  assistantOpen: boolean;
  assistantHistory: Array<{ role: "user" | "assistant"; content: string }>;
  assistantPending: boolean;
  assistantProposal: StudioPipelineAssistantResponse | null;
  lang: "en" | "ru";
  pipelineId: number | null;
  selectedNode: PipelineNode | null;
  trigger: PipelineTrigger | null;
  onApplyAssistantProposal: () => void;
  onApplyAndSaveAssistantProposal: () => void;
  onAssistantInputChange: (value: string) => void;
  onAssistantSend: (intent: "create" | "edit" | "validate" | "fix_run", messageOverride?: string) => void;
  onCloseAssistant: () => void;
  onCloseNode: () => void;
  onCloseRun: () => void;
  onDeleteNode: (nodeId: string) => void;
  onDiscardAssistantProposal: () => void;
  onDuplicateNode: (nodeId: string) => void;
  onUpdateNodeData: (nodeId: string, data: Record<string, unknown>) => void;
}) {
  if (!activeRunId && !assistantOpen && !selectedNode) return null;

  return (
    <div className={cn(
      "fixed inset-x-3 bottom-3 top-32 z-30 flex flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl lg:static lg:inset-auto lg:h-full lg:min-h-0 lg:shrink-0 lg:rounded-none lg:border-y-0 lg:border-r-0 lg:shadow-none",
      assistantOpen && !activeRunId ? "lg:w-96" : "lg:w-80",
    )}>
      {activeRunId ? (
        <RunMonitorPanel
          runId={activeRunId}
          onClose={onCloseRun}
        />
      ) : assistantOpen ? (
        <PipelineAssistantPanel
          lang={lang}
          selectedNode={selectedNode}
          input={assistantInput}
          history={assistantHistory}
          proposal={assistantProposal}
          isPending={assistantPending}
          onInputChange={onAssistantInputChange}
          onSend={onAssistantSend}
          onApply={onApplyAssistantProposal}
          onApplyAndSave={onApplyAndSaveAssistantProposal}
          onDiscard={onDiscardAssistantProposal}
          onClose={onCloseAssistant}
        />
      ) : selectedNode ? (
        <NodeConfigPanel
          key={selectedNode.id}
          node={selectedNode}
          pipelineId={pipelineId}
          trigger={trigger}
          lang={lang}
          onUpdate={onUpdateNodeData}
          onClose={onCloseNode}
          onDelete={onDeleteNode}
          onDuplicate={onDuplicateNode}
        />
      ) : null}
    </div>
  );
}
