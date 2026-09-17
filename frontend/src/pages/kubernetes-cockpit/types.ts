import type { KubernetesClusterEvent, KubernetesPodRef } from "@/api";

export const LOG_TAIL = 200;

export type ExplainConfidence = "low" | "medium" | "high";

export interface ExplainLogsInput {
  podName: string;
  namespace: string;
  phase: string;
  restartCount: number;
  lines: string[];
}

export interface ExplainLogsResult {
  summary: string;
  likelyCause: string;
  signals: string[];
  suggestedChecks: string[];
  confidence: ExplainConfidence;
  disclaimer: string;
}

export type CockpitMainTab = "pods" | "events" | "connect";

export interface CockpitUrlState {
  clusterId: string;
  namespace: string;
  podId: string;
  tab: CockpitMainTab;
}

export function isPodReady(pod: KubernetesPodRef): boolean {
  if (pod.total_containers > 0) {
    return pod.ready_containers >= pod.total_containers && !isPodUnhealthyPhase(pod.phase);
  }
  return !isPodUnhealthyPhase(pod.phase) && pod.health !== "degraded" && pod.health !== "warning";
}

export function isPodUnhealthyPhase(phase: string): boolean {
  const p = (phase || "").toLowerCase();
  return (
    p.includes("crash") ||
    p.includes("fail") ||
    p.includes("error") ||
    p === "pending" ||
    p === "unknown" ||
    p.includes("backoff") ||
    p.includes("imagepull")
  );
}

export function filterPodsByNamespace(pods: KubernetesPodRef[], namespace: string): KubernetesPodRef[] {
  if (!namespace) return [];
  return pods.filter((pod) => pod.namespace === namespace);
}

export function filterEventsByNamespace(events: KubernetesClusterEvent[], namespace: string): KubernetesClusterEvent[] {
  if (!namespace) return [];
  return events.filter((event) => !event.namespace || event.namespace === namespace);
}

export function podPhaseTone(phase: string, health?: string): "success" | "warning" | "danger" | "neutral" | "info" {
  const p = (phase || "").toLowerCase();
  if (p.includes("crash") || p.includes("fail") || p.includes("error") || p.includes("backoff") || health === "degraded") {
    return "danger";
  }
  if (p === "pending" || p.includes("imagepull") || health === "warning") {
    return "warning";
  }
  if (p === "running" || p === "succeeded" || p === "completed") {
    return "success";
  }
  return "neutral";
}
