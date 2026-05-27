import type { PipelineLastRun, PipelineTrigger, PipelineTriggerSummary } from "@/lib/api";

export type PipelineActivityTone = "primary" | "success" | "info" | "warning" | "muted";
export type PipelineActivityIcon = "running" | "pending" | "manual" | "webhook" | "schedule" | "monitoring" | "warning";

export interface PipelineActivityState {
  label: string;
  detail: string;
  tone: PipelineActivityTone;
  icon: PipelineActivityIcon;
}

type PipelineActivityInput = {
  lastRun?: PipelineLastRun | null;
  triggerSummary?: PipelineTriggerSummary | null;
  triggers?: PipelineTrigger[] | null;
  graphVersion?: number | null;
};

function formatRelativeTime(value: string): string {
  const diffMs = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(diffMs / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function summarizeStoredTriggers(triggers: PipelineTrigger[]): PipelineTriggerSummary {
  const activeTriggers = triggers.filter((trigger) => trigger.is_active);
  let lastTriggeredAt: string | null = null;
  for (const trigger of activeTriggers) {
    if (!trigger.last_triggered_at) {
      continue;
    }
    if (!lastTriggeredAt || new Date(trigger.last_triggered_at).getTime() > new Date(lastTriggeredAt).getTime()) {
      lastTriggeredAt = trigger.last_triggered_at;
    }
  }
  return {
    active_total: activeTriggers.length,
    active_manual: activeTriggers.filter((trigger) => trigger.trigger_type === "manual").length,
    active_webhook: activeTriggers.filter((trigger) => trigger.trigger_type === "webhook").length,
    active_schedule: activeTriggers.filter((trigger) => trigger.trigger_type === "schedule").length,
    active_monitoring: activeTriggers.filter((trigger) => trigger.trigger_type === "monitoring").length,
    last_triggered_at: lastTriggeredAt,
  };
}

function describeMixedTriggerSummary(summary: PipelineTriggerSummary): string {
  const parts: string[] = [];
  if (summary.active_manual) {
    parts.push(`${summary.active_manual} manual`);
  }
  if (summary.active_webhook) {
    parts.push(`${summary.active_webhook} webhook`);
  }
  if (summary.active_schedule) {
    parts.push(`${summary.active_schedule} schedule`);
  }
  if (summary.active_monitoring) {
    parts.push(`${summary.active_monitoring} monitoring`);
  }
  return parts.join(", ");
}

function appendLastTriggered(detail: string, lastTriggeredAt: string | null | undefined): string {
  if (!lastTriggeredAt) {
    return detail;
  }
  return `${detail} Last trigger ${formatRelativeTime(lastTriggeredAt)}.`;
}

export function getPipelineActivityState({
  lastRun,
  triggerSummary,
  triggers,
  graphVersion,
}: PipelineActivityInput): PipelineActivityState {
  if (lastRun?.status === "running") {
    return {
      label: "Running",
      detail: `Run #${lastRun.id} is executing now.`,
      tone: "primary",
      icon: "running",
    };
  }
  if (lastRun?.status === "pending") {
    return {
      label: "Pending",
      detail: `Run #${lastRun.id} is queued and starting soon.`,
      tone: "primary",
      icon: "pending",
    };
  }
  if ((graphVersion || 0) > 0 && (graphVersion || 0) < 2) {
    return {
      label: "Legacy graph",
      detail: "This pipeline must be resaved as V2 before it can run again.",
      tone: "warning",
      icon: "warning",
    };
  }

  const summary =
    triggerSummary ||
    (Array.isArray(triggers) ? summarizeStoredTriggers(triggers) : null);

  if (!summary || summary.active_total === 0) {
    return {
      label: "No active trigger",
      detail: "Add a manual, webhook, schedule, or monitoring trigger to arm this pipeline.",
      tone: "warning",
      icon: "warning",
    };
  }

  const manualOnly = summary.active_manual > 0 && summary.active_webhook === 0 && summary.active_schedule === 0 && (summary.active_monitoring || 0) === 0;
  if (manualOnly) {
    return {
      label: "Manual ready",
      detail:
        summary.active_manual === 1
          ? "Ready for one manual entry point."
          : `Ready for ${summary.active_manual} manual entry points.`,
      tone: "success",
      icon: "manual",
    };
  }

  const webhookOnly = summary.active_webhook > 0 && summary.active_manual === 0 && summary.active_schedule === 0 && (summary.active_monitoring || 0) === 0;
  if (webhookOnly) {
    return {
      label: "Active",
      detail: appendLastTriggered("Waiting for webhook POST.", summary.last_triggered_at),
      tone: "info",
      icon: "webhook",
    };
  }

  const scheduleOnly = summary.active_schedule > 0 && summary.active_manual === 0 && summary.active_webhook === 0 && (summary.active_monitoring || 0) === 0;
  if (scheduleOnly) {
    return {
      label: "Active",
      detail: appendLastTriggered("Waiting for the schedule trigger.", summary.last_triggered_at),
      tone: "info",
      icon: "schedule",
    };
  }

  const monitoringOnly = (summary.active_monitoring || 0) > 0 && summary.active_manual === 0 && summary.active_webhook === 0 && summary.active_schedule === 0;
  if (monitoringOnly) {
    return {
      label: "Active",
      detail: appendLastTriggered("Waiting for a monitoring alert.", summary.last_triggered_at),
      tone: "info",
      icon: "monitoring",
    };
  }

  return {
    label: "Active",
    detail: appendLastTriggered(`Multiple trigger types are active: ${describeMixedTriggerSummary(summary)}.`, summary.last_triggered_at),
    tone: "info",
    icon: "webhook",
  };
}
