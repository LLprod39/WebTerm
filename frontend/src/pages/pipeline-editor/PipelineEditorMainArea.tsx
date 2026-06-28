import type { ComponentType, Dispatch, DragEvent, SetStateAction } from "react";
import type { Connection, EdgeChange, NodeChange, NodeMouseHandler } from "@xyflow/react";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { PipelineEdge, PipelineNode, PipelineTrigger, StudioCapabilityNode } from "@/lib/api";
import type { StudioPipelineAssistantResponse } from "@/lib/studioPipelineDraftsApi";

import { localize } from "./presentation";
import { NodePalette } from "./NodePalette";
import { PipelineEditorCanvas } from "./PipelineEditorCanvas";
import { PipelineEditorSidePanel } from "./PipelineEditorSidePanel";

export function PipelineEditorMainArea({
  activeRunId,
  assistantHistory,
  assistantInput,
  assistantOpen,
  assistantPending,
  assistantProposal,
  displayEdges,
  displayNodes,
  lang,
  nodeManifests,
  paletteOpen,
  pluginPalette,
  pluginNodeTypes,
  pipelineId,
  selectedNode,
  showMiniMap,
  trigger,
  onAddNode,
  onApplyAssistantProposal,
  onApplyAndSaveAssistantProposal,
  onAssistantInputChange,
  onAssistantSend,
  onCloseAssistant,
  onCloseNode,
  onCloseRun,
  onConnect,
  onDeleteNode,
  onDiscardAssistantProposal,
  onDragOver,
  onDrop,
  onDuplicateNode,
  onEdgesChange,
  onNodeClick,
  onNodesChange,
  onPaneClick,
  onUpdateNodeData,
  setPaletteOpen,
}: {
  activeRunId: number | null;
  assistantHistory: Array<{ role: "user" | "assistant"; content: string }>;
  assistantInput: string;
  assistantOpen: boolean;
  assistantPending: boolean;
  assistantProposal: StudioPipelineAssistantResponse | null;
  displayEdges: PipelineEdge[];
  displayNodes: PipelineNode[];
  lang: "en" | "ru";
  nodeManifests: StudioCapabilityNode[];
  paletteOpen: boolean;
  pluginPalette: Array<{ category: string; nodes: Array<{ type: string; label: string; icon: ComponentType<{ className?: string }>; iconClassName?: string; description: string }> }>;
  pluginNodeTypes: Record<string, ComponentType<any>>;
  pipelineId: number | null;
  selectedNode: PipelineNode | null;
  showMiniMap: boolean;
  trigger: PipelineTrigger | null;
  onAddNode: (type: string) => void;
  onApplyAssistantProposal: () => void;
  onApplyAndSaveAssistantProposal: () => void;
  onAssistantInputChange: (value: string) => void;
  onAssistantSend: (intent: "create" | "edit" | "validate" | "fix_run", messageOverride?: string) => void;
  onCloseAssistant: () => void;
  onCloseNode: () => void;
  onCloseRun: () => void;
  onConnect: (connection: Connection) => void;
  onDeleteNode: (nodeId: string) => void;
  onDiscardAssistantProposal: () => void;
  onDragOver: (event: DragEvent) => void;
  onDrop: (event: DragEvent) => void;
  onDuplicateNode: (nodeId: string) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onNodeClick: NodeMouseHandler;
  onNodesChange: (changes: NodeChange[]) => void;
  onPaneClick: () => void;
  onUpdateNodeData: (nodeId: string, data: Record<string, unknown>) => void;
  setPaletteOpen: Dispatch<SetStateAction<boolean>>;
}) {
  return (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      <div className="hidden h-full min-h-0 w-64 shrink-0 lg:block">
        <NodePalette onAddNode={onAddNode} lang={lang} pluginPalette={pluginPalette} />
      </div>
      <Sheet open={paletteOpen} onOpenChange={setPaletteOpen}>
        <SheetContent side="left" className="flex w-[88vw] max-w-sm flex-col overflow-hidden border-border bg-card p-0 lg:hidden">
          <SheetHeader className="border-b border-border px-4 py-4 text-left">
            <SheetTitle className="text-base">{localize(lang, "Добавить ноду", "Add node")}</SheetTitle>
            <SheetDescription>
              {localize(lang, "Выберите шаг, и он появится на холсте.", "Choose a step and it will be added to the canvas.")}
            </SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1">
            <NodePalette
              lang={lang}
              pluginPalette={pluginPalette}
              onAddNode={(type) => {
                onAddNode(type);
                setPaletteOpen(false);
              }}
            />
          </div>
        </SheetContent>
      </Sheet>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-[#111317]">
        <div className="min-h-0 flex-1">
          <PipelineEditorCanvas
            displayNodes={displayNodes}
            displayEdges={displayEdges}
            lang={lang}
            onConnect={onConnect}
            onDragOver={onDragOver}
            onDrop={onDrop}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onNodesChange={onNodesChange}
            onPaneClick={onPaneClick}
            pluginNodeTypes={pluginNodeTypes}
            showMiniMap={showMiniMap}
          />
        </div>
      </div>

      <PipelineEditorSidePanel
        activeRunId={activeRunId}
        assistantInput={assistantInput}
        assistantOpen={assistantOpen}
        assistantHistory={assistantHistory}
        assistantPending={assistantPending}
        assistantProposal={assistantProposal}
        lang={lang}
        nodeManifests={nodeManifests}
        pipelineId={pipelineId}
        selectedNode={selectedNode}
        trigger={trigger}
        onApplyAssistantProposal={onApplyAssistantProposal}
        onApplyAndSaveAssistantProposal={onApplyAndSaveAssistantProposal}
        onAssistantInputChange={onAssistantInputChange}
        onAssistantSend={onAssistantSend}
        onCloseAssistant={onCloseAssistant}
        onCloseNode={onCloseNode}
        onCloseRun={onCloseRun}
        onDeleteNode={onDeleteNode}
        onDiscardAssistantProposal={onDiscardAssistantProposal}
        onDuplicateNode={onDuplicateNode}
        onUpdateNodeData={onUpdateNodeData}
      />
    </div>
  );
}
