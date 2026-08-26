import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileText, Layers3, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  fetchKubernetesCluster,
  fetchKubernetesClusterEvents,
  fetchKubernetesClusterNetwork,
  fetchKubernetesClusterNamespaces,
  fetchKubernetesClusterPods,
  fetchKubernetesClusterWorkloads,
  fetchKubernetesPodLogs,
  fetchKubernetesWorkloadDescribe,
  createKubernetesActionRequest,
  type KubernetesActionRequestRecord,
  type KubernetesAppRef,
  type KubernetesWorkloadDescribeResponse,
} from "@/api";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  QueryStateBlock,
  SectionCard,
  StatusBadge,
} from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import {
  AppRow,
  formatSync,
  healthIcon,
  statusLabel,
  statusTone,
} from "@/pages/kubernetes-page/kubernetesPageSections";
import { KubernetesActionRequestPanel } from "@/pages/kubernetes-page/KubernetesActionRequestPanel";
import {
  countHealth,
  KpiTile,
} from "@/pages/kubernetes-page/KubernetesCockpitPrimitives";
import { KubernetesMetricsStrip } from "@/pages/kubernetes-page/KubernetesMetricsStrip";
import { KubernetesNetworkPanel } from "@/pages/kubernetes-page/KubernetesNetworkPanel";
import { KubernetesPodLogsPanel } from "@/pages/kubernetes-page/KubernetesPodLogsPanel";
import { KubernetesPodsPanel } from "@/pages/kubernetes-page/KubernetesPodsPanel";
import {
  K8sRefreshButton,
  KubernetesPageHeader,
  KubernetesShell,
} from "@/pages/kubernetes-page/KubernetesShell";
import { KubernetesTopology } from "@/pages/kubernetes-page/KubernetesTopology";
import { useKubernetesDeepLinkAudit } from "@/pages/kubernetes-page/useKubernetesDeepLinkAudit";

export default function KubernetesClusterDetailPage() {
  const { lang } = useI18n();
  const { clusterId = "" } = useParams();
  const queryClient = useQueryClient();
  const auditDeepLink = useKubernetesDeepLinkAudit();
  const [describeId, setDescribeId] = useState("");
  const [logsPodId, setLogsPodId] = useState("");
  const [actionRequestTargetId, setActionRequestTargetId] = useState("");
  const [actionRequestResult, setActionRequestResult] = useState<KubernetesActionRequestRecord | null>(null);
  const clusterQuery = useQuery({
    queryKey: ["kubernetes", "cluster", clusterId],
    queryFn: () => fetchKubernetesCluster(clusterId),
    enabled: Boolean(clusterId),
  });
  const namespacesQuery = useQuery({
    queryKey: ["kubernetes", "cluster", clusterId, "namespaces"],
    queryFn: () => fetchKubernetesClusterNamespaces(clusterId),
    enabled: Boolean(clusterId),
  });
  const workloadsQuery = useQuery({
    queryKey: ["kubernetes", "cluster", clusterId, "workloads"],
    queryFn: () => fetchKubernetesClusterWorkloads(clusterId),
    enabled: Boolean(clusterId),
  });
  const networkQuery = useQuery({
    queryKey: ["kubernetes", "cluster", clusterId, "network"],
    queryFn: () => fetchKubernetesClusterNetwork(clusterId),
    enabled: Boolean(clusterId),
  });
  const podsQuery = useQuery({
    queryKey: ["kubernetes", "cluster", clusterId, "pods"],
    queryFn: () => fetchKubernetesClusterPods(clusterId),
    enabled: Boolean(clusterId),
  });
  const eventsQuery = useQuery({
    queryKey: ["kubernetes", "cluster", clusterId, "events"],
    queryFn: () => fetchKubernetesClusterEvents(clusterId),
    enabled: Boolean(clusterId),
  });
  const describeQuery = useQuery({
    queryKey: ["kubernetes", "workload", describeId, "describe"],
    queryFn: () => fetchKubernetesWorkloadDescribe(describeId),
    enabled: Boolean(describeId),
  });
  const podLogsQuery = useQuery({
    queryKey: ["kubernetes", "pod", logsPodId, "logs"],
    queryFn: () => fetchKubernetesPodLogs(logsPodId),
    enabled: Boolean(logsPodId),
  });
  const actionRequestMutation = useMutation({
    mutationFn: (app: KubernetesAppRef) =>
      createKubernetesActionRequest({
        action: "k8s.rollout.restart",
        reason: `Operator requested restart approval for ${app.namespace}/${app.name}`,
        target: { workload_id: app.id },
      }),
    onMutate: (app) => {
      setActionRequestTargetId(app.id);
      setActionRequestResult(null);
    },
    onSuccess: (result) => setActionRequestResult(result.request),
    onSettled: () => setActionRequestTargetId(""),
  });

  const cluster = clusterQuery.data?.cluster;
  const workloads = workloadsQuery.data?.workloads || [];
  const pods = podsQuery.data?.pods || [];
  const networkRefs = networkQuery.data?.network_refs || [];
  const namespaces = namespacesQuery.data?.namespaces || [];
  const events = eventsQuery.data?.events || [];
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["kubernetes", "cluster", clusterId] });
  };
  const loading = clusterQuery.isLoading || namespacesQuery.isLoading || workloadsQuery.isLoading || podsQuery.isLoading || networkQuery.isLoading || eventsQuery.isLoading;
  const error = clusterQuery.error || namespacesQuery.error || workloadsQuery.error || podsQuery.error || networkQuery.error || eventsQuery.error;
  const degradedNamespaces = namespaces.filter((namespace) => namespace.degraded > 0).length;
  const warningNamespaces = namespaces.filter((namespace) => namespace.warning > 0).length;
  const wlHealth = countHealth(workloads);

  return (
    <KubernetesShell>
      <KubernetesPageHeader
        kicker={localize(lang, "Кластер", "Cluster")}
        title={cluster?.name || localize(lang, "Кластер", "Cluster")}
        description={localize(
          lang,
          "Пространства имён, нагрузки, поды, сеть и события. Только просмотр.",
          "Namespaces, workloads, pods, networking, and events. Read-only.",
        )}
        meta={
          cluster ? (
            <>
              {healthIcon(cluster.health)}
              <StatusBadge label={statusLabel(lang, cluster.health)} tone={statusTone(cluster.health)} />
              <StatusBadge label={cluster.environment || "env"} tone="neutral" />
              <span className="font-mono text-2xs text-muted-foreground">
                {localize(lang, "Синхронизация:", "Synced:")} {formatSync(lang, cluster.last_sync_at)}
              </span>
            </>
          ) : null
        }
        actions={
          <>
            <Button asChild variant="outline" size="sm" className="h-10 gap-2">
              <Link to="/kubernetes">
                <ArrowLeft className="h-4 w-4" />
                {localize(lang, "К обзору", "Back to overview")}
              </Link>
            </Button>
            <K8sRefreshButton onClick={refresh} label={localize(lang, "Обновить", "Refresh")} />
          </>
        }
      />

      <QueryStateBlock
        loading={loading}
        error={error || (!clusterQuery.isLoading && clusterQuery.data && !clusterQuery.data.success ? new Error("Cluster request failed") : undefined)}
        errorText={localize(lang, "Не удалось загрузить данные кластера", "Failed to load cluster data")}
        onRetry={refresh}
      >
        {cluster ? (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <KpiTile
                label={localize(lang, "Состояние", "Health")}
                value={statusLabel(lang, cluster.health)}
                hint={formatSync(lang, cluster.last_sync_at)}
                tone={statusTone(cluster.health) === "danger" ? "danger" : statusTone(cluster.health) === "warning" ? "warning" : "success"}
              />
              <KpiTile
                label={localize(lang, "Ноды", "Nodes")}
                value={`${cluster.nodes_ready}/${cluster.nodes_total}`}
                tone={cluster.nodes_total && cluster.nodes_ready < cluster.nodes_total ? "warning" : "success"}
              />
              <KpiTile
                label={localize(lang, "Пространства", "Namespaces")}
                value={namespaces.length || cluster.namespaces}
                hint={`${warningNamespaces} warn · ${degradedNamespaces} deg`}
                tone={degradedNamespaces ? "danger" : warningNamespaces ? "warning" : "success"}
              />
              <KpiTile
                label={localize(lang, "Нагрузки", "Workloads")}
                value={workloads.length || cluster.workloads}
                tone="info"
              />
            </div>

            <KubernetesMetricsStrip
              lang={lang}
              clusterId={cluster.id}
              healthy={wlHealth.healthy}
              warning={wlHealth.warning}
              degraded={wlHealth.degraded}
            />

            <SectionCard
              title={localize(lang, "Топология", "Topology")}
              description={localize(
                lang,
                "Связи пространств имён, нагрузок и сервисов.",
                "Relationships between namespaces, workloads, and services.",
              )}
              icon={<Layers3 className="h-4 w-4" />}
            >
              <KubernetesTopology
                lang={lang}
                namespaces={namespaces}
                workloads={workloads}
                networkRefs={networkRefs}
              />
            </SectionCard>

            <div className="grid gap-5 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
              <SectionCard
                title={localize(lang, "Пространства имён", "Namespaces")}
                description={localize(lang, "Данные Rancher и Devtron.", "Data from Rancher and Devtron.")}
                icon={<ShieldCheck className="h-4 w-4" />}
              >
                {namespaces.length ? (
                  <div className="space-y-3">
                    {namespaces.map((namespace) => (
                      <div key={namespace.id} className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <h3 className="text-sm font-semibold text-foreground">{namespace.name}</h3>
                              <StatusBadge label={namespace.environment || cluster.environment || "env"} tone="neutral" />
                              {namespace.owners.map((owner) => (
                                <StatusBadge key={owner} label={owner} tone={owner === "devtron" ? "info" : "neutral"} />
                              ))}
                            </div>
                            <div className="mt-2 text-xs text-muted-foreground">
                              {localize(lang, "Команды:", "Teams:")} {namespace.teams.join(", ") || localize(lang, "не указаны", "not set")}
                            </div>
                          </div>
                          <div className="text-xs text-muted-foreground sm:text-right">
                            <div className="font-semibold text-foreground">{namespace.apps}</div>
                            <div>{localize(lang, "приложений", "apps")}</div>
                          </div>
                        </div>
                        <div className="mt-3 grid grid-cols-4 gap-2 text-xs">
                          {[
                            ["healthy", namespace.healthy],
                            ["warning", namespace.warning],
                            ["degraded", namespace.degraded],
                            ["unknown", namespace.unknown],
                          ].map(([label, value]) => (
                            <div key={label} className="rounded-md bg-secondary/30 px-3 py-2">
                              <div className="font-semibold text-foreground">{value}</div>
                              <div className="text-muted-foreground">{label}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={<ShieldCheck className="h-5 w-5" />}
                    title={localize(lang, "Нет данных о пространствах имён", "No namespace data")}
                    description={localize(lang, "Запустите синхронизацию Rancher или Devtron.", "Run a Rancher or Devtron sync.")}
                  />
                )}
              </SectionCard>

              <SectionCard
                title={localize(lang, "Нагрузки", "Workloads")}
                description={localize(lang, "Данные Rancher и Devtron.", "Data from Rancher and Devtron.")}
                icon={<Layers3 className="h-4 w-4" />}
              >
                {workloads.length ? (
                  <div className="space-y-2">
                    {workloads.map((app) => (
                      <AppRow
                        key={app.id}
                        app={app}
                        lang={lang}
                        onDescribe={(item) => setDescribeId(item.id)}
                        onRequestRestart={(item) => actionRequestMutation.mutate(item)}
                        onOpenLink={auditDeepLink}
                        describePending={describeId === app.id && describeQuery.isFetching}
                        restartPending={actionRequestTargetId === app.id && actionRequestMutation.isPending}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={<Layers3 className="h-5 w-5" />}
                    title={localize(lang, "Нагрузки не найдены", "No workloads found")}
                    description={localize(lang, "Запустите синхронизацию кластера.", "Run a cluster sync.")}
                  />
                )}
              </SectionCard>
            </div>

            <KubernetesPodsPanel
              lang={lang}
              pods={pods}
              logsPendingId={podLogsQuery.isFetching ? logsPodId : ""}
              onViewLogs={(pod) => setLogsPodId(pod.id)}
            />

            {logsPodId ? (
              <KubernetesPodLogsPanel
                lang={lang}
                logs={podLogsQuery.data}
                loading={podLogsQuery.isLoading || podLogsQuery.isFetching}
                error={podLogsQuery.error}
                onClose={() => setLogsPodId("")}
                onOpenLink={auditDeepLink}
              />
            ) : null}

            {(actionRequestResult || actionRequestMutation.error) ? (
              <KubernetesActionRequestPanel
                lang={lang}
                request={actionRequestResult}
                error={actionRequestMutation.error}
                onClose={() => {
                  setActionRequestResult(null);
                  actionRequestMutation.reset();
                }}
              />
            ) : null}

            <KubernetesNetworkPanel lang={lang} networkRefs={networkRefs} />

            {describeId ? (
              <DescribeEvidencePanel
                lang={lang}
                describe={describeQuery.data}
                loading={describeQuery.isLoading || describeQuery.isFetching}
                error={describeQuery.error}
                onClose={() => setDescribeId("")}
              />
            ) : null}

            <SectionCard
              title={localize(lang, "События кластера", "Cluster events")}
              description={localize(lang, "События Kubernetes и журнал WebTerm.", "Kubernetes events and the WebTerm audit log.")}
              icon={<ShieldCheck className="h-4 w-4" />}
            >
              {events.length ? (
                <div className="space-y-2">
                  {events.map((event) => (
                    <div key={event.id} className="grid gap-3 rounded-lg border border-border/70 bg-background/45 px-4 py-3 text-sm md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusBadge label={event.source} tone="info" />
                          <span className="font-semibold text-foreground">{event.reason}</span>
                          <StatusBadge label={event.severity} tone={event.severity === "error" ? "danger" : event.severity === "warning" ? "warning" : "neutral"} />
                          {event.namespace ? <StatusBadge label={event.namespace} tone="neutral" /> : null}
                          {event.count && event.count > 1 ? <StatusBadge label={`x${event.count}`} tone="neutral" /> : null}
                        </div>
                        <div className="mt-1 truncate text-xs text-muted-foreground">{event.message}</div>
                      </div>
                      <div className="text-xs text-muted-foreground md:text-right">
                        <div>{event.username || "system"}</div>
                        <div>{formatSync(lang, event.created_at)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={<ShieldCheck className="h-5 w-5" />}
                  title={localize(lang, "Событий пока нет", "No events yet")}
                  description={localize(lang, "События появятся после синхронизации или действий в кластере.", "Events will appear after a sync or cluster activity.")}
                />
              )}
            </SectionCard>
          </>
        ) : null}
      </QueryStateBlock>
    </KubernetesShell>
  );
}

function DescribeEvidencePanel({
  lang,
  describe,
  loading,
  error,
  onClose,
}: {
  lang: string;
  describe?: KubernetesWorkloadDescribeResponse;
  loading: boolean;
  error: unknown;
  onClose: () => void;
}) {
  return (
    <SectionCard
      title={localize(lang, "Сведения о нагрузке", "Workload details")}
      description={localize(lang, "Манифест, политика доступа и связанные события. Только просмотр.", "Manifest, access policy, and related events. Read-only.")}
      icon={<FileText className="h-4 w-4" />}
      actions={
        <Button variant="outline" size="sm" onClick={onClose}>
          {localize(lang, "Закрыть", "Close")}
        </Button>
      }
    >
      {loading ? (
        <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4 text-sm text-muted-foreground">
          {localize(lang, "Загружаю сведения", "Loading details")}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-4 text-sm text-destructive">
          {localize(lang, "Не удалось загрузить сведения", "Failed to load details")}
        </div>
      ) : describe ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <div className="space-y-3">
            <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge label={describe.target.source} tone="info" />
                <StatusBadge label={describe.target.namespace || "namespace"} tone="neutral" />
                <StatusBadge label={statusLabel(lang, describe.target.health)} tone={statusTone(describe.target.health)} />
                <StatusBadge label={describe.policy.mode} tone="success" />
              </div>
              <h3 className="mt-3 text-sm font-semibold text-foreground">{describe.target.name}</h3>
              <div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
                <div>{localize(lang, "Кластер:", "Cluster:")} {describe.target.cluster_name}</div>
                <div>{localize(lang, "Владелец:", "Owner:")} {describe.target.owner}</div>
                <div>{localize(lang, "Команда:", "Team:")} {describe.target.team || localize(lang, "не указана", "not set")}</div>
                <div>{localize(lang, "Версия:", "Version:")} {describe.target.version || localize(lang, "нет", "none")}</div>
              </div>
            </div>

            <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
              <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{localize(lang, "Политика доступа", "Access policy")}</div>
              <div className="mt-2 text-sm text-foreground">
                {describe.policy.mutates_state ? localize(lang, "Изменения разрешены", "Changes allowed") : localize(lang, "Только просмотр", "Read-only")}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {describe.policy.blocked_actions.map((action) => (
                  <StatusBadge key={action} label={action} tone="neutral" />
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
              <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{localize(lang, "Связанные события", "Related events")}</div>
              {describe.related_events.length ? (
                <div className="mt-3 space-y-2">
                  {describe.related_events.map((event) => (
                    <div key={event.id} className="rounded-md bg-secondary/30 px-3 py-2 text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge label={event.severity} tone={event.severity === "error" ? "danger" : event.severity === "warning" ? "warning" : "neutral"} />
                        <span className="font-semibold text-foreground">{event.reason}</span>
                      </div>
                      <div className="mt-1 text-muted-foreground">{event.message}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-2 text-xs text-muted-foreground">{localize(lang, "Связанных событий нет", "No related events")}</div>
              )}
            </div>
          </div>

          <pre className="max-h-[28rem] overflow-auto rounded-lg border border-border/70 bg-secondary/25 p-4 text-xs leading-5 text-foreground">
            {JSON.stringify(describe.manifest_preview, null, 2)}
          </pre>
        </div>
      ) : null}
    </SectionCard>
  );
}
