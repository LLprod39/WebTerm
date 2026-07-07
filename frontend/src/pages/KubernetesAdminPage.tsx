import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Database, ListTree, RefreshCcw, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import {
  createKubernetesAdminSession,
  fetchKubernetesAdminDiscovery,
  fetchKubernetesAdminPodLogs,
  fetchKubernetesAdminResourceDetail,
  fetchKubernetesAdminResourceWatch,
  fetchKubernetesAdminResourceYaml,
  fetchKubernetesAdminResources,
  fetchKubernetesAdminSessions,
  fetchKubernetesClusters,
  fetchKubernetesReadiness,
} from "@/api";
import { Button } from "@/components/ui/button";
import { EmptyState, PageHero, PageShell, QueryStateBlock, StatusBadge } from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import { ResourceCatalogPanel } from "@/pages/kubernetes-page/KubernetesAdminResourceCatalog";
import { ResourceInspector } from "@/pages/kubernetes-page/KubernetesAdminResourceInspector";
import { ResourceTablePanel } from "@/pages/kubernetes-page/KubernetesAdminResourceTable";
import { AdminWorkspaceToolbar } from "@/pages/kubernetes-page/KubernetesAdminWorkspaceToolbar";
import {
  DEFAULT_NAMESPACE,
  activeSessionForCluster,
  buildResourceQuery,
  filterCatalogItems,
  filterResourceRows,
  sameTarget,
  targetFromItem,
  type InspectorTab,
  type ResourceTarget,
} from "@/pages/kubernetes-page/kubernetesAdminResourceModel";

export default function KubernetesAdminPage() {
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const [clusterId, setClusterId] = useState("");
  const [activeSessionId, setActiveSessionId] = useState("");
  const [namespace, setNamespace] = useState(DEFAULT_NAMESPACE);
  const [resourceSearch, setResourceSearch] = useState("");
  const [nameFilter, setNameFilter] = useState("");
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [selectedResourceId, setSelectedResourceId] = useState("");
  const [selectedTarget, setSelectedTarget] = useState<ResourceTarget | null>(null);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("summary");

  const readinessQuery = useQuery({
    queryKey: ["kubernetes", "readiness", "admin-page"],
    queryFn: fetchKubernetesReadiness,
    staleTime: 30_000,
  });
  const clustersQuery = useQuery({
    queryKey: ["kubernetes", "clusters"],
    queryFn: fetchKubernetesClusters,
    staleTime: 30_000,
  });
  const sessionsQuery = useQuery({
    queryKey: ["kubernetes", "admin", "sessions"],
    queryFn: fetchKubernetesAdminSessions,
    staleTime: 15_000,
  });

  const clusterRows = clustersQuery.data?.clusters;
  const clusters = useMemo(() => clusterRows ?? [], [clusterRows]);
  const selectedCluster = clusters.find((cluster) => cluster.id === clusterId) || clusters[0];
  const activeSession = useMemo(
    () => activeSessionForCluster(sessionsQuery.data?.sessions || [], selectedCluster, activeSessionId),
    [activeSessionId, selectedCluster, sessionsQuery.data?.sessions],
  );
  const sessionId = activeSession?.id || activeSessionId;
  const canAdminRead = Boolean(readinessQuery.data?.access_policy?.can_admin_read);
  const canUseExplorer = Boolean(canAdminRead && selectedCluster);

  useEffect(() => {
    if (!clusterId && clusters[0]?.id) setClusterId(clusters[0].id);
  }, [clusterId, clusters]);

  const discoveryQuery = useQuery({
    queryKey: ["kubernetes", "admin", "discovery", selectedCluster?.id, sessionId],
    queryFn: () => fetchKubernetesAdminDiscovery(selectedCluster!.id, sessionId),
    enabled: Boolean(canUseExplorer && selectedCluster && sessionId),
    staleTime: 60_000,
  });

  const catalog = discoveryQuery.data?.resource_catalog;
  const discoveredItems = catalog?.items;
  const discoveredGroups = catalog?.groups;
  const catalogItems = useMemo(() => discoveredItems ?? [], [discoveredItems]);
  const catalogGroups = useMemo(() => discoveredGroups ?? [], [discoveredGroups]);
  const visibleCatalogItems = useMemo(
    () => filterCatalogItems(catalogItems, selectedGroupId, resourceSearch),
    [catalogItems, resourceSearch, selectedGroupId],
  );
  const selectedResource =
    catalogItems.find((item) => item.id === selectedResourceId) ||
    visibleCatalogItems[0] ||
    catalogItems[0] ||
    null;
  const namespaceForQuery = selectedResource?.namespaced ? namespace.trim() || DEFAULT_NAMESPACE : "";

  useEffect(() => {
    setSelectedTarget(null);
    setInspectorTab("summary");
  }, [namespaceForQuery, selectedResource?.id]);

  const createSessionMutation = useMutation({
    mutationFn: () =>
      createKubernetesAdminSession({
        mode: "read",
        cluster_id: selectedCluster?.id,
        namespace: namespace.trim() || DEFAULT_NAMESPACE,
        ttl_minutes: 60,
        allowed_kinds: ["*"],
        allowed_namespaces: ["*"],
      }),
    onSuccess: async (payload) => {
      setActiveSessionId(payload.session.id);
      await queryClient.invalidateQueries({ queryKey: ["kubernetes", "admin", "sessions"] });
      await queryClient.invalidateQueries({ queryKey: ["kubernetes", "admin", "discovery"] });
    },
  });

  const resourcesQuery = useQuery({
    queryKey: [
      "kubernetes",
      "admin",
      "resources",
      selectedCluster?.id,
      sessionId,
      selectedResource?.id,
      namespaceForQuery,
    ],
    queryFn: () =>
      fetchKubernetesAdminResources(
        selectedCluster!.id,
        buildResourceQuery(sessionId, selectedResource!, namespaceForQuery),
      ),
    enabled: Boolean(canUseExplorer && selectedCluster && sessionId && selectedResource),
    staleTime: 15_000,
  });

  const resourceRows = useMemo(
    () => filterResourceRows(resourcesQuery.data?.items || [], nameFilter),
    [nameFilter, resourcesQuery.data?.items],
  );

  const selectedRow = selectedTarget
    ? resourceRows.find((item) => sameTarget(targetFromItem(item, namespaceForQuery), selectedTarget)) || null
    : null;

  const detailQuery = useQuery({
    queryKey: [
      "kubernetes",
      "admin",
      "resource-detail",
      selectedCluster?.id,
      sessionId,
      selectedResource?.id,
      selectedTarget?.namespace,
      selectedTarget?.name,
    ],
    queryFn: () =>
      fetchKubernetesAdminResourceDetail(
        selectedCluster!.id,
        buildResourceQuery(sessionId, selectedResource!, selectedTarget?.namespace || namespaceForQuery, selectedTarget?.name, {
          include_events: true,
          event_limit: 20,
        }),
      ),
    enabled: Boolean(canUseExplorer && selectedCluster && sessionId && selectedResource && selectedTarget?.name),
    staleTime: 10_000,
  });

  const yamlQuery = useQuery({
    queryKey: [
      "kubernetes",
      "admin",
      "resource-yaml",
      selectedCluster?.id,
      sessionId,
      selectedResource?.id,
      selectedTarget?.namespace,
      selectedTarget?.name,
    ],
    queryFn: () =>
      fetchKubernetesAdminResourceYaml(
        selectedCluster!.id,
        buildResourceQuery(sessionId, selectedResource!, selectedTarget?.namespace || namespaceForQuery, selectedTarget?.name),
      ),
    enabled: Boolean(inspectorTab === "yaml" && canUseExplorer && selectedCluster && sessionId && selectedResource && selectedTarget?.name),
    staleTime: 10_000,
  });

  const logsQuery = useQuery({
    queryKey: [
      "kubernetes",
      "admin",
      "resource-logs",
      selectedCluster?.id,
      sessionId,
      selectedTarget?.namespace,
      selectedTarget?.name,
    ],
    queryFn: () =>
      fetchKubernetesAdminPodLogs(selectedCluster!.id, {
        session_id: sessionId,
        namespace: selectedTarget?.namespace || namespaceForQuery || DEFAULT_NAMESPACE,
        pod: selectedTarget!.name,
        tail: 120,
      }),
    enabled: Boolean(
      inspectorTab === "logs" &&
        canUseExplorer &&
        selectedCluster &&
        sessionId &&
        selectedResource?.kind === "Pod" &&
        selectedTarget?.name,
    ),
    staleTime: 10_000,
  });

  const watchQuery = useQuery({
    queryKey: [
      "kubernetes",
      "admin",
      "resource-watch",
      selectedCluster?.id,
      sessionId,
      selectedResource?.id,
      selectedTarget?.namespace,
      selectedTarget?.name,
    ],
    queryFn: () =>
      fetchKubernetesAdminResourceWatch(
        selectedCluster!.id,
        buildResourceQuery(sessionId, selectedResource!, selectedTarget?.namespace || namespaceForQuery, selectedTarget?.name, {
          limit: 20,
          timeout_seconds: 10,
        }),
      ),
    enabled: Boolean(
      inspectorTab === "watch" &&
        canUseExplorer &&
        selectedCluster &&
        sessionId &&
        selectedResource &&
        selectedResource.safe_read_actions.includes("watch") &&
        selectedTarget?.name,
    ),
    staleTime: 10_000,
  });

  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: ["kubernetes", "readiness"] });
    void queryClient.invalidateQueries({ queryKey: ["kubernetes", "clusters"] });
    void queryClient.invalidateQueries({ queryKey: ["kubernetes", "admin"] });
  };
  const loading = readinessQuery.isLoading || clustersQuery.isLoading || sessionsQuery.isLoading;
  const error = readinessQuery.error || clustersQuery.error || sessionsQuery.error;

  return (
    <PageShell width="full" className="space-y-5">
      <PageHero
        kicker={localize(lang, "Kubernetes Admin Mode", "Kubernetes Admin Mode")}
        title={localize(lang, "Live resource workspace", "Live resource workspace")}
        description={localize(
          lang,
          "Freelens-like просмотр ресурсов через WebTerm: catalog, таблица, YAML, events, logs snapshot и watch preview. Read-only по умолчанию.",
          "Freelens-like resource browsing through WebTerm: catalog, table, YAML, events, logs snapshot, and watch preview. Read-only by default.",
        )}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge
              label={canAdminRead ? localize(lang, "Admin read", "Admin read") : localize(lang, "Нет admin read", "No admin read")}
              tone={canAdminRead ? "success" : "warning"}
            />
            <StatusBadge
              label={sessionId ? localize(lang, "Read session active", "Read session active") : localize(lang, "Нужна session", "Session required")}
              tone={sessionId ? "success" : "warning"}
            />
            <Button asChild variant="outline" size="sm">
              <Link to="/kubernetes">
                <ArrowLeft className="h-4 w-4" />
                {localize(lang, "Ops", "Ops")}
              </Link>
            </Button>
            <Button variant="outline" size="sm" onClick={refreshAll}>
              <RefreshCcw className="h-4 w-4" />
              {localize(lang, "Обновить", "Refresh")}
            </Button>
          </div>
        }
      />

      <QueryStateBlock
        loading={loading}
        error={error}
        errorText={localize(lang, "Не удалось загрузить Kubernetes Admin Mode", "Failed to load Kubernetes Admin Mode")}
        onRetry={refreshAll}
      >
        {!canAdminRead ? (
          <EmptyState
            icon={<ShieldCheck className="h-5 w-5" />}
            title={localize(lang, "Admin Mode read не включён", "Admin Mode read is not enabled")}
            description={localize(
              lang,
              "Обычный Kubernetes доступ остаётся read-only cockpit. Для live explorer нужен отдельный флаг kubernetes_admin_read.",
              "Regular Kubernetes access remains a read-only cockpit. The live explorer requires the separate kubernetes_admin_read flag.",
            )}
          />
        ) : !clusters.length ? (
          <EmptyState
            icon={<Database className="h-5 w-5" />}
            title={localize(lang, "Кластеры не найдены", "No clusters found")}
            description={localize(lang, "Сначала нужен Rancher/provider sync.", "Rancher/provider sync is required first.")}
          />
        ) : (
          <div className="space-y-4">
            <AdminWorkspaceToolbar
              lang={lang}
              clusters={clusters}
              selectedCluster={selectedCluster}
              clusterId={selectedCluster?.id || ""}
              onClusterChange={(value) => {
                setClusterId(value);
                setActiveSessionId("");
                setSelectedResourceId("");
                setSelectedTarget(null);
              }}
              activeSession={activeSession}
              sessionId={sessionId}
              createPending={createSessionMutation.isPending}
              createError={createSessionMutation.error}
              onCreateSession={() => createSessionMutation.mutate()}
              canCreate={canUseExplorer}
              catalog={discoveryQuery.data}
            />

            {!sessionId ? (
              <EmptyState
                icon={<ShieldCheck className="h-5 w-5" />}
                title={localize(lang, "Создайте read session", "Create a read session")}
                description={localize(
                  lang,
                  "После session WebTerm загрузит discovery catalog и откроет read-only resource workspace.",
                  "After a session, WebTerm will load the discovery catalog and open the read-only resource workspace.",
                )}
              />
            ) : (
              <QueryStateBlock
                loading={discoveryQuery.isLoading}
                error={discoveryQuery.error}
                errorText={localize(lang, "Не удалось загрузить resource catalog", "Failed to load resource catalog")}
                onRetry={() => void discoveryQuery.refetch()}
              >
                {!catalog ? (
                  <EmptyState
                    icon={<ListTree className="h-5 w-5" />}
                    title={localize(lang, "Resource catalog недоступен", "Resource catalog unavailable")}
                    description={localize(
                      lang,
                      "Frontend не будет угадывать Kubernetes API paths. Нужен backend resource_catalog contract.",
                      "The frontend will not guess Kubernetes API paths. The backend resource_catalog contract is required.",
                    )}
                  />
                ) : (
                  <div className="grid min-h-[680px] gap-4 xl:grid-cols-[300px_minmax(0,1fr)_420px]">
                    <ResourceCatalogPanel
                      lang={lang}
                      groups={catalogGroups}
                      items={catalogItems}
                      visibleItems={visibleCatalogItems}
                      selectedGroupId={selectedGroupId}
                      selectedResource={selectedResource}
                      search={resourceSearch}
                      onSearchChange={setResourceSearch}
                      onSelectGroup={(groupId) => {
                        setSelectedGroupId(groupId);
                        setSelectedResourceId("");
                        setSelectedTarget(null);
                        setNameFilter("");
                      }}
                      onSelectResource={(item) => {
                        setSelectedResourceId(item.id);
                        setSelectedTarget(null);
                        setInspectorTab("summary");
                        setNameFilter("");
                      }}
                    />

                    <ResourceTablePanel
                      lang={lang}
                      selectedResource={selectedResource}
                      namespace={namespace}
                      namespaceForQuery={namespaceForQuery}
                      onNamespaceChange={setNamespace}
                      nameFilter={nameFilter}
                      onNameFilterChange={setNameFilter}
                      rows={resourceRows}
                      response={resourcesQuery.data}
                      loading={resourcesQuery.isLoading || resourcesQuery.isFetching}
                      error={resourcesQuery.error}
                      onRetry={() => void resourcesQuery.refetch()}
                      selectedTarget={selectedTarget}
                      onSelectTarget={(target) => {
                        setSelectedTarget(target);
                        setInspectorTab("summary");
                      }}
                    />

                    <ResourceInspector
                      lang={lang}
                      selectedResource={selectedResource}
                      selectedTarget={selectedTarget}
                      selectedRow={selectedRow}
                      tab={inspectorTab}
                      onTabChange={setInspectorTab}
                      detail={detailQuery.data}
                      detailLoading={detailQuery.isLoading || detailQuery.isFetching}
                      detailError={detailQuery.error}
                      yaml={yamlQuery.data}
                      yamlLoading={yamlQuery.isLoading || yamlQuery.isFetching}
                      yamlError={yamlQuery.error}
                      logs={logsQuery.data}
                      logsLoading={logsQuery.isLoading || logsQuery.isFetching}
                      logsError={logsQuery.error}
                      watch={watchQuery.data}
                      watchLoading={watchQuery.isLoading || watchQuery.isFetching}
                      watchError={watchQuery.error}
                    />
                  </div>
                )}
              </QueryStateBlock>
            )}
          </div>
        )}
      </QueryStateBlock>
    </PageShell>
  );
}
