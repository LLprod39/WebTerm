import type { PipelineRiskSummary } from "@/components/pipeline/pipelineRiskSummary";
import type { PipelineNode, PipelineTrigger } from "@/lib/api";

import { PipelineRunDialog, type PipelineRunDialogMode } from "./PipelineRunDialog";
import type { usePipelineRunDialogState } from "./usePipelineRunDialogState";

type RunDialogController = ReturnType<typeof usePipelineRunDialogState>;

export function PipelineRunDialogHost({
  activeMonitoringTriggers,
  activeScheduleTriggers,
  activeWebhookTriggers,
  controller,
  isRunPending,
  isSavePending,
  isValidatePending,
  lang,
  manualTriggerOptions,
  mode,
  monitoringTriggerNodes,
  onRunSubmit,
  onSaveTrigger,
  onValidateRun,
  runRiskSummary,
  saveDisabled,
  scheduleTriggerNodes,
}: {
  activeMonitoringTriggers: PipelineTrigger[];
  activeScheduleTriggers: PipelineTrigger[];
  activeWebhookTriggers: PipelineTrigger[];
  controller: RunDialogController;
  isRunPending: boolean;
  isSavePending: boolean;
  isValidatePending: boolean;
  lang: "en" | "ru";
  manualTriggerOptions: Array<{ node_id: string; label: string }>;
  mode: PipelineRunDialogMode;
  monitoringTriggerNodes: PipelineNode[];
  onRunSubmit: () => void;
  onSaveTrigger: () => void;
  onValidateRun: () => void;
  runRiskSummary: PipelineRiskSummary;
  saveDisabled: boolean;
  scheduleTriggerNodes: PipelineNode[];
}) {
  return (
    <PipelineRunDialog
      open={controller.runDialogOpen}
      onOpenChange={controller.setRunDialogOpen}
      mode={mode}
      lang={lang}
      manualTriggerOptions={manualTriggerOptions}
      runEntryNodeId={controller.runEntryNodeId}
      onRunEntryNodeIdChange={controller.setRunEntryNodeId}
      runTriggerError={controller.runTriggerError}
      onRunTriggerErrorChange={controller.setRunTriggerError}
      runRiskSummary={runRiskSummary}
      runtimeContextFields={controller.runtimeContextFields}
      onApplyRuntimeContextFields={controller.handleApplyRuntimeContextFields}
      runTaskText={controller.runTaskText}
      onRunTaskTextChange={controller.setRunTaskText}
      runAdvancedOpen={controller.runAdvancedOpen}
      onRunAdvancedOpenChange={controller.setRunAdvancedOpen}
      runRequester={controller.runRequester}
      onRunRequesterChange={controller.setRunRequester}
      runTicketId={controller.runTicketId}
      onRunTicketIdChange={controller.setRunTicketId}
      runContextText={controller.runContextText}
      onRunContextTextChange={controller.setRunContextText}
      runContextError={controller.runContextError}
      onRunContextErrorChange={controller.setRunContextError}
      activeWebhookTriggers={activeWebhookTriggers}
      activeScheduleTriggers={activeScheduleTriggers}
      activeMonitoringTriggers={activeMonitoringTriggers}
      scheduleTriggerNodes={scheduleTriggerNodes}
      monitoringTriggerNodes={monitoringTriggerNodes}
      isRunPending={isRunPending}
      isValidatePending={isValidatePending}
      isSavePending={isSavePending}
      saveDisabled={saveDisabled}
      onValidateRun={onValidateRun}
      onRunSubmit={onRunSubmit}
      onSaveTrigger={onSaveTrigger}
    />
  );
}
