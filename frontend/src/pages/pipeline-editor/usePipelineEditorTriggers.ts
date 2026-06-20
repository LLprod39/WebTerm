import { useMemo } from "react";

import { buildPipelineRiskSummary } from "@/components/pipeline/pipelineRiskSummary";
import type { PipelineEdge, PipelineNode, PipelineTrigger } from "@/lib/api";

import type { PipelineRunDialogMode } from "./PipelineRunDialog";
import {
  getActiveManualTriggerOptions,
  getActiveStoredTriggers,
  getActiveTriggerNodes,
} from "./pipelineGraphUtils";

export function usePipelineEditorTriggers({
  edges,
  lang,
  nodes,
  triggers,
}: {
  edges: PipelineEdge[];
  lang: "en" | "ru";
  nodes: PipelineNode[];
  triggers?: PipelineTrigger[] | null;
}) {
  const manualTriggerOptions = useMemo(() => getActiveManualTriggerOptions(nodes, lang), [lang, nodes]);
  const webhookTriggerNodes = useMemo(() => getActiveTriggerNodes(nodes, "trigger/webhook"), [nodes]);
  const scheduleTriggerNodes = useMemo(() => getActiveTriggerNodes(nodes, "trigger/schedule"), [nodes]);
  const monitoringTriggerNodes = useMemo(() => getActiveTriggerNodes(nodes, "trigger/monitoring"), [nodes]);
  const activeWebhookTriggers = useMemo(() => getActiveStoredTriggers(triggers, "webhook"), [triggers]);
  const activeScheduleTriggers = useMemo(() => getActiveStoredTriggers(triggers, "schedule"), [triggers]);
  const activeMonitoringTriggers = useMemo(() => getActiveStoredTriggers(triggers, "monitoring"), [triggers]);
  const runRiskSummary = useMemo(() => buildPipelineRiskSummary(nodes, edges), [edges, nodes]);
  const runDialogMode: PipelineRunDialogMode = manualTriggerOptions.length
    ? "manual"
    : webhookTriggerNodes.length
      ? "webhook"
      : scheduleTriggerNodes.length
        ? "schedule"
        : monitoringTriggerNodes.length
          ? "monitoring"
          : "manual";

  return {
    activeMonitoringTriggers,
    activeScheduleTriggers,
    activeWebhookTriggers,
    manualTriggerOptions,
    monitoringTriggerNodes,
    runDialogMode,
    runRiskSummary,
    scheduleTriggerNodes,
    webhookTriggerNodes,
  };
}
