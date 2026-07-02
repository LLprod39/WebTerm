import { Boxes, ScrollText } from "lucide-react";

import type { KubernetesPodRef } from "@/api";
import { Button } from "@/components/ui/button";
import { EmptyState, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";
import { formatSync, statusLabel, statusTone } from "@/pages/kubernetes-page/kubernetesPageSections";

export function KubernetesPodsPanel({
  lang,
  pods,
  logsPendingId,
  onViewLogs,
}: {
  lang: string;
  pods: KubernetesPodRef[];
  logsPendingId?: string;
  onViewLogs?: (pod: KubernetesPodRef) => void;
}) {
  const unhealthy = pods.filter((pod) => pod.health === "degraded").length;
  const warning = pods.filter((pod) => pod.health === "warning").length;
  return (
    <SectionCard
      title={localize(lang, "Pods", "Pods")}
      description={localize(lang, "Native Rancher pod inventory, read-only.", "Native Rancher pod inventory, read-only.")}
      icon={<Boxes className="h-4 w-4" />}
    >
      {pods.length ? (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="rounded-md bg-secondary/30 px-3 py-2">
              <div className="font-semibold text-foreground">{pods.length}</div>
              <div className="text-muted-foreground">pods</div>
            </div>
            <div className="rounded-md bg-secondary/30 px-3 py-2">
              <div className="font-semibold text-foreground">{warning}</div>
              <div className="text-muted-foreground">warning</div>
            </div>
            <div className="rounded-md bg-secondary/30 px-3 py-2">
              <div className="font-semibold text-foreground">{unhealthy}</div>
              <div className="text-muted-foreground">degraded</div>
            </div>
          </div>
          <div className="space-y-2">
            {pods.map((pod) => (
              <div key={pod.id} className="rounded-lg border border-border/70 bg-background/45 px-4 py-3 text-sm">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-foreground">{pod.name}</span>
                      <StatusBadge label={pod.phase || "phase"} tone="neutral" />
                      <StatusBadge label={statusLabel(lang, pod.health)} tone={statusTone(pod.health)} />
                      {pod.restart_count ? <StatusBadge label={`${pod.restart_count} restarts`} tone="warning" /> : null}
                    </div>
                    <div className="mt-1 truncate text-xs text-muted-foreground">
                      {pod.namespace} / {pod.node_name || localize(lang, "node unknown", "node unknown")}
                    </div>
                    <div className="mt-2 grid gap-x-4 gap-y-1 text-xs text-muted-foreground md:grid-cols-2">
                      <div>{localize(lang, "Containers:", "Containers:")} {pod.ready_containers}/{pod.total_containers}</div>
                      <div>{localize(lang, "Owner:", "Owner:")} {[pod.owner_kind, pod.owner_name].filter(Boolean).join("/") || localize(lang, "нет", "none")}</div>
                      <div>{localize(lang, "Pod IP:", "Pod IP:")} {pod.pod_ip || localize(lang, "нет", "none")}</div>
                      <div className="truncate">{localize(lang, "Image:", "Image:")} {pod.images[0] || localize(lang, "нет", "none")}</div>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-row items-center gap-2 sm:flex-col sm:items-end">
                    <div className="text-xs text-muted-foreground sm:text-right">{formatSync(lang, pod.last_sync_at)}</div>
                    {onViewLogs ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-8 gap-1.5 text-xs"
                        disabled={logsPendingId === pod.id}
                        aria-label={`Logs ${pod.name}`}
                        onClick={() => onViewLogs(pod)}
                      >
                        <ScrollText className="h-3.5 w-3.5" />
                        Logs
                      </Button>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <EmptyState
          icon={<Boxes className="h-5 w-5" />}
          title={localize(lang, "Pods не синхронизированы", "Pods are not synced")}
          description={localize(lang, "Появятся после Rancher pod sync.", "They will appear after Rancher pod sync.")}
        />
      )}
    </SectionCard>
  );
}
