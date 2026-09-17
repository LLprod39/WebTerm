import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Boxes, Cable, RefreshCw, Settings } from "lucide-react";
import { Link } from "react-router-dom";

import { fetchAuthSession } from "@/api";
import { Button } from "@/components/ui/button";
import { ContentPanel } from "@/components/system/ContentPanel";
import { PageShell, QueryStateBlock, SoftHeader, StatStrip, StatStripItem } from "@/components/ui/page-shell";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { localize, useI18n } from "@/lib/i18n";
import { CockpitToolbar } from "@/pages/kubernetes-cockpit/CockpitToolbar";
import { CockpitWorkbench } from "@/pages/kubernetes-cockpit/CockpitWorkbench";
import { AddClusterPanel } from "@/pages/kubernetes-cockpit/AddClusterPanel";
import { EventsPanel } from "@/pages/kubernetes-cockpit/EventsPanel";
import { explainLogsMock } from "@/pages/kubernetes-cockpit/explainLogsMock";
import { PodListPanel } from "@/pages/kubernetes-cockpit/PodListPanel";
import type { CockpitMainTab, ExplainLogsResult } from "@/pages/kubernetes-cockpit/types";
import { isPodReady } from "@/pages/kubernetes-cockpit/types";
import { useCockpitQueries } from "@/pages/kubernetes-cockpit/useCockpitQueries";
import { useCockpitUrlState } from "@/pages/kubernetes-cockpit/useCockpitUrlState";

const mainTabClass =
  "h-10 gap-2 rounded-none border-b-2 border-transparent bg-transparent px-1 text-sm shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:shadow-none";

export default function KubernetesCockpitPage() {
  const { lang } = useI18n();
  const url = useCockpitUrlState();
  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = Boolean(authData?.user?.is_staff);
  const {
    clustersQuery,
    namespacesQuery,
    podsQuery,
    eventsQuery,
    logsQuery,
    clusters,
    namespaces,
    pods,
    events,
    selectedPod,
    refresh,
  } = useCockpitQueries(url.clusterId, url.namespace, url.podId);

  const [explain, setExplain] = useState<ExplainLogsResult | null>(null);
  const [podSearch, setPodSearch] = useState("");

  useEffect(() => {
    if (url.clusterId || clustersQuery.isLoading || !clusters.length) return;
    const preferred =
      clusters.find((cluster) => cluster.health === "healthy" || !cluster.is_stale) || clusters[0];
    if (preferred?.id) url.setCluster(preferred.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- hydrate once clusters arrive
  }, [clusters, clustersQuery.isLoading, url.clusterId]);

  useEffect(() => {
    if (!url.clusterId || url.namespace || namespacesQuery.isLoading || !namespaces.length) return;
    const first = namespaces[0]?.name;
    if (first) url.setNamespace(first);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [namespaces, namespacesQuery.isLoading, url.clusterId, url.namespace]);

  useEffect(() => {
    if (!url.podId || podsQuery.isLoading) return;
    if (!pods.some((pod) => pod.id === url.podId)) {
      url.setPod("");
      setExplain(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pods, podsQuery.isLoading, url.podId]);

  useEffect(() => {
    setExplain(null);
  }, [url.podId, url.namespace, url.clusterId]);

  useEffect(() => {
    if (!clustersQuery.isLoading && clusters.length === 0 && url.tab !== "connect") {
      url.setTab("connect");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clusters.length, clustersQuery.isLoading]);

  const bootError =
    clustersQuery.error ||
    (!clustersQuery.isLoading && clustersQuery.data && !clustersQuery.data.success
      ? new Error("Kubernetes clusters failed")
      : undefined);

  const filteredPods = useMemo(() => {
    const q = podSearch.trim().toLowerCase();
    if (!q) return pods;
    return pods.filter(
      (pod) =>
        pod.name.toLowerCase().includes(q) ||
        pod.phase.toLowerCase().includes(q) ||
        pod.node_name?.toLowerCase().includes(q),
    );
  }, [pods, podSearch]);

  const readyPods = useMemo(() => pods.filter(isPodReady).length, [pods]);
  const warningEvents = useMemo(
    () =>
      events.filter((event) => {
        const sev = (event.severity || "").toLowerCase();
        return sev === "warning" || sev === "error";
      }).length,
    [events],
  );

  const handleExplain = () => {
    if (!selectedPod) return;
    setExplain(
      explainLogsMock(
        {
          podName: selectedPod.name,
          namespace: selectedPod.namespace,
          phase: selectedPod.phase,
          restartCount: selectedPod.restart_count,
          lines: logsQuery.data?.lines ?? [],
        },
        lang,
      ),
    );
  };

  return (
    <PageShell width="full" className="max-w-[1500px] space-y-3 pb-8">
      <SoftHeader
        compact
        title="Kubernetes"
        count={pods.length > 0 ? pods.length : undefined}
        subtitle={localize(
          lang,
          "Кластер → namespace → pod → логи, events и exec.",
          "Cluster → namespace → pod → logs, events, and exec.",
        )}
        actions={
          <>
            <Button
              type="button"
              variant="outline"
              className="h-9 gap-2 rounded-sm px-3.5"
              onClick={() => url.setTab("connect")}
            >
              <Cable className="h-4 w-4" aria-hidden />
              {localize(lang, "Добавить кластер", "Add cluster")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-9 w-9"
              onClick={refresh}
              aria-label={localize(lang, "Обновить", "Refresh")}
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
            {isAdmin ? (
              <Button asChild variant="outline" className="h-9 gap-2 rounded-sm px-3.5">
                <Link to="/settings/kubernetes">
                  <Settings className="h-4 w-4" aria-hidden />
                  {localize(lang, "Настройки", "Settings")}
                </Link>
              </Button>
            ) : null}
          </>
        }
      />

      <QueryStateBlock
        loading={clustersQuery.isLoading}
        error={bootError}
        errorText={localize(lang, "Не удалось загрузить кластеры Kubernetes", "Failed to load Kubernetes clusters")}
        onRetry={refresh}
      >
        {clusters.length > 0 ? (
          <StatStrip>
            <StatStripItem
              label={localize(lang, "Ready", "Ready")}
              value={pods.length ? `${readyPods}/${pods.length}` : "—"}
              hint={localize(lang, "поды в namespace", "pods in namespace")}
              tone={pods.length && readyPods === pods.length ? "success" : "default"}
            />
            <StatStripItem
              label={localize(lang, "Не Ready", "Not Ready")}
              value={pods.length ? String(Math.max(pods.length - readyPods, 0)) : "—"}
              hint={localize(lang, "требуют внимания", "need attention")}
              tone={pods.length && readyPods < pods.length ? "danger" : "default"}
            />
            <StatStripItem
              label={localize(lang, "Warnings", "Warnings")}
              value={String(warningEvents)}
              hint={localize(lang, "события Warning/Error", "Warning/Error events")}
              tone={warningEvents > 0 ? "warning" : "default"}
            />
            <StatStripItem
              label="Namespace"
              value={url.namespace || "—"}
              hint={localize(lang, "текущий", "current")}
            />
          </StatStrip>
        ) : null}

        <Tabs value={url.tab} onValueChange={(value) => url.setTab(value as CockpitMainTab)} className="space-y-3">
          <div className="flex flex-col gap-2 border-b border-border px-1 lg:flex-row lg:items-center lg:justify-between">
            <TabsList className="h-10 w-full justify-start gap-5 rounded-none bg-transparent p-0 lg:w-auto">
              <TabsTrigger value="pods" className={mainTabClass}>
                <Boxes className="h-4 w-4" aria-hidden />
                {localize(lang, "Pods", "Pods")}
              </TabsTrigger>
              <TabsTrigger value="events" className={mainTabClass}>
                <Activity className="h-4 w-4" aria-hidden />
                {localize(lang, "Events", "Events")}
              </TabsTrigger>
              <TabsTrigger value="connect" className={mainTabClass}>
                <Cable className="h-4 w-4" aria-hidden />
                {localize(lang, "Подключение", "Connect")}
              </TabsTrigger>
            </TabsList>

            {url.tab === "pods" && clusters.length > 0 ? (
              <CockpitToolbar
                lang={lang}
                clusters={clusters}
                namespaces={namespaces}
                clusterId={url.clusterId}
                namespace={url.namespace}
                search={podSearch}
                clustersLoading={clustersQuery.isLoading}
                namespacesLoading={namespacesQuery.isLoading}
                podsShown={filteredPods.length}
                podsTotal={pods.length}
                onClusterChange={(clusterId) => {
                  setExplain(null);
                  setPodSearch("");
                  url.setCluster(clusterId);
                }}
                onNamespaceChange={(namespace) => {
                  setExplain(null);
                  setPodSearch("");
                  url.setNamespace(namespace);
                }}
                onSearchChange={setPodSearch}
              />
            ) : null}
          </div>

          <TabsContent value="pods" className="mt-0 space-y-3">
            {!clusters.length ? (
              <AddClusterPanel lang={lang} onConnected={refresh} />
            ) : selectedPod ? (
              <CockpitWorkbench
                lang={lang}
                pod={selectedPod}
                events={events}
                eventsLoading={eventsQuery.isLoading}
                namespace={url.namespace}
                logs={logsQuery.data}
                logsLoading={logsQuery.isFetching}
                logsError={logsQuery.error}
                explain={explain}
                onBack={() => {
                  setExplain(null);
                  url.setPod("");
                }}
                onRefreshLogs={() => void logsQuery.refetch()}
                onExplain={handleExplain}
              />
            ) : (
              <PodListPanel
                lang={lang}
                pods={filteredPods}
                selectedPodId={url.podId}
                loading={podsQuery.isLoading}
                namespace={url.namespace}
                onSelect={(podId) => {
                  setExplain(null);
                  url.setPod(podId);
                }}
              />
            )}
          </TabsContent>

          <TabsContent value="events" className="mt-0 space-y-3">
            {clusters.length > 0 ? (
              <div className="flex justify-end">
                <CockpitToolbar
                  lang={lang}
                  clusters={clusters}
                  namespaces={namespaces}
                  clusterId={url.clusterId}
                  namespace={url.namespace}
                  search=""
                  showSearch={false}
                  clustersLoading={clustersQuery.isLoading}
                  namespacesLoading={namespacesQuery.isLoading}
                  podsShown={0}
                  podsTotal={0}
                  onClusterChange={url.setCluster}
                  onNamespaceChange={url.setNamespace}
                  onSearchChange={() => undefined}
                />
              </div>
            ) : null}
            <ContentPanel className="overflow-hidden">
              <EventsPanel lang={lang} events={events} loading={eventsQuery.isLoading} namespace={url.namespace} />
            </ContentPanel>
          </TabsContent>

          <TabsContent value="connect" className="mt-0">
            <AddClusterPanel lang={lang} onConnected={refresh} />
          </TabsContent>
        </Tabs>
      </QueryStateBlock>
    </PageShell>
  );
}
