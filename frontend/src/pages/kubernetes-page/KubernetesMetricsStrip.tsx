import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";

import {
  fetchKubernetesAdminMetrics,
  formatBytes,
  formatMillicores,
} from "@/api/kubernetes-ops-extra";
import { fetchKubernetesAdminSessions } from "@/api/kubernetes-admin";
import { localize } from "@/lib/i18n";
import { SectionCard } from "@/components/ui/page-shell";
import { seededSeries, Sparkline } from "@/pages/kubernetes-page/KubernetesSparkline";

export function KubernetesMetricsStrip({
  lang,
  clusterId,
  healthy,
  warning,
  degraded,
}: {
  lang: string;
  clusterId?: string;
  healthy: number;
  warning: number;
  degraded: number;
}) {
  const sessionsQuery = useQuery({
    queryKey: ["kubernetes", "admin", "sessions", "metrics-strip"],
    queryFn: fetchKubernetesAdminSessions,
    staleTime: 30_000,
    retry: false,
  });

  const session = (sessionsQuery.data?.sessions || []).find(
    (s) => s.status === "active" && (!clusterId || s.cluster_id === clusterId),
  );

  const metricsQuery = useQuery({
    queryKey: ["kubernetes", "admin", "metrics", clusterId, session?.id],
    queryFn: () =>
      fetchKubernetesAdminMetrics(clusterId!, {
        session_id: session!.id,
        scope: "nodes",
        limit: 40,
      }),
    enabled: Boolean(clusterId && session?.id),
    staleTime: 20_000,
    retry: false,
  });

  const summary = metricsQuery.data?.summary;
  const live = Boolean(summary && metricsQuery.isSuccess);
  const cpuSeries = live
    ? seededSeries(Math.round(summary!.total_cpu_millicores || 1), 16, Math.max(10, (summary!.total_cpu_millicores || 0) / 8), 12)
    : seededSeries(healthy * 17 + warning * 3, 16, 35 + healthy, 18);
  const memSeries = live
    ? seededSeries(Math.round((summary!.total_memory_bytes || 1) / 1e6), 16, 40, 14)
    : seededSeries(degraded * 11 + healthy * 5, 16, 42, 16);

  return (
    <SectionCard
      title={localize(lang, "Метрики", "Metrics")}
      description={
        live
          ? localize(lang, "Live snapshot metrics.k8s.io (Admin session)", "Live metrics.k8s.io snapshot (Admin session)")
          : localize(
              lang,
              "Превью-спарклайны. Live CPU/mem — с Admin session на кластере.",
              "Preview sparklines. Live CPU/mem needs an Admin session on the cluster.",
            )
      }
      icon={<Activity className="h-4 w-4" />}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-sm border border-border bg-surface-0 p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-2xs uppercase tracking-[0.14em] text-muted-foreground">CPU</div>
              <div className="mt-1 font-display text-lg font-semibold tabular-nums">
                {live ? formatMillicores(summary!.total_cpu_millicores) : "—"}
              </div>
            </div>
            <Sparkline points={cpuSeries} stroke="#c8f542" fill="rgba(200,245,66,0.12)" />
          </div>
        </div>
        <div className="rounded-sm border border-border bg-surface-0 p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-2xs uppercase tracking-[0.14em] text-muted-foreground">Memory</div>
              <div className="mt-1 font-display text-lg font-semibold tabular-nums">
                {live ? formatBytes(summary!.total_memory_bytes) : "—"}
              </div>
            </div>
            <Sparkline points={memSeries} stroke="#38bdf8" fill="rgba(56,189,248,0.12)" />
          </div>
        </div>
      </div>
      {live ? (
        <div className="mt-2 font-mono text-2xs text-muted-foreground">
          nodes={summary!.item_count}
          {summary!.truncated ? " · truncated" : ""}
        </div>
      ) : null}
    </SectionCard>
  );
}
