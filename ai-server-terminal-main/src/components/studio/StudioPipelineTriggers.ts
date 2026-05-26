import { localize } from "@/lib/i18n";
import type { PipelineDetail, PipelineTrigger } from "@/lib/api";

export type ManualTriggerOption = {
  nodeId: string;
  label: string;
};

export type TriggerInfoTarget = {
  pipeline: PipelineDetail;
  webhookTriggers: PipelineTrigger[];
  scheduleTriggers: PipelineTrigger[];
  monitoringTriggers: PipelineTrigger[];
};

export function getActiveManualTriggerOptions(pipeline: PipelineDetail | null, lang = "en"): ManualTriggerOption[] {
  if (!pipeline || !Array.isArray(pipeline.nodes)) {
    return [];
  }
  return pipeline.nodes
    .filter((node) => node.type === "trigger/manual")
    .map((node) => {
      const data = node.data && typeof node.data === "object" ? node.data : {};
      return {
        nodeId: node.id,
        label:
          typeof data.label === "string" && data.label.trim()
            ? data.label.trim()
            : localize(lang, `Ручной вход ${node.id}`, `Manual trigger ${node.id}`),
        isActive: data.is_active !== false,
      };
    })
    .filter((node) => node.isActive)
    .map(({ nodeId, label }) => ({ nodeId, label }));
}

export function getActiveWebhookTriggers(pipeline: PipelineDetail | null): PipelineTrigger[] {
  if (!pipeline || !Array.isArray(pipeline.triggers)) {
    return [];
  }
  return pipeline.triggers.filter((trigger) => trigger.trigger_type === "webhook" && trigger.is_active);
}

export function getActiveScheduleTriggers(pipeline: PipelineDetail | null): PipelineTrigger[] {
  if (!pipeline || !Array.isArray(pipeline.triggers)) {
    return [];
  }
  return pipeline.triggers.filter((trigger) => trigger.trigger_type === "schedule" && trigger.is_active);
}

export function getActiveMonitoringTriggers(pipeline: PipelineDetail | null): PipelineTrigger[] {
  if (!pipeline || !Array.isArray(pipeline.triggers)) {
    return [];
  }
  return pipeline.triggers.filter((trigger) => trigger.trigger_type === "monitoring" && trigger.is_active);
}

export function toAbsoluteWebhookUrl(webhookUrl: string): string {
  return new URL(webhookUrl, window.location.origin).toString();
}
