import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, ArrowLeft, Braces, Database, FileCode2, ListTree, RefreshCcw, ScrollText, Search, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import {
  createKubernetesAdminSession,
  fetchKubernetesAdminCrds,
  fetchKubernetesAdminDiscovery,
  fetchKubernetesAdminPodLogs,
  fetchKubernetesAdminResourceYaml,
  fetchKubernetesAdminResources,
  fetchKubernetesAdminResourceWatch,
  fetchKubernetesAdminSessions,
  fetchKubernetesClusters,
  fetchKubernetesReadiness,
  type KubernetesAdminResourceDiscoveryResponse,
  type KubernetesAdminPodLogsResponse,
  type KubernetesAdminResourceListResponse,
  type KubernetesAdminResourceWatchResponse,
  type KubernetesAdminResourceYamlResponse,
  type KubernetesAdminSession,
  type KubernetesCluster,
} from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  EmptyState,
  PageHero,
  PageShell,
  QueryStateBlock,
  SectionCard,
  StatusBadge,
} from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import { AdminLogsSnapshotPanel } from "@/pages/kubernetes-page/KubernetesAdminLogsPanel";
import { WatchPreviewPanel } from "@/pages/kubernetes-page/KubernetesAdminWatchPanel";
import { OwnershipPanel, OwnershipSummaryPanel, ownerLabel, ownerTone } from "@/pages/kubernetes-page/KubernetesAdminOwnershipPanel";

const COMMON_KINDS = [
  { label: "Deployment", apiVersion: "apps/v1", kind: "Deployment", namespaced: true },
  { label: "Pod", apiVersion: "v1", kind: "Pod", namespaced: true },
  { label: "Service", apiVersion: "v1", kind: "Service", namespaced: true },
  { label: "ConfigMap", apiVersion: "v1", kind: "ConfigMap", namespaced: true },
  { label: "Secret", apiVersion: "v1", kind: "Secret", namespaced: true },
  { label: "Ingress", apiVersion: "networking.k8s.io/v1", kind: "Ingress", namespaced: true },
  { label: "Namespace", apiVersion: "v1", kind: "Namespace", namespaced: false },
];

type AdminResult =
  | { type: "list"; payload: KubernetesAdminResourceListResponse }
  | { type: "yaml"; payload: KubernetesAdminResourceYamlResponse }
  | { type: "logs"; payload: KubernetesAdminPodLogsResponse }
  | { type: "watch"; payload: KubernetesAdminResourceWatchResponse }
  | { type: "discovery"; payload: KubernetesAdminResourceDiscoveryResponse }
  | { type: "crds"; payload: KubernetesAdminResourceListResponse };

export default function KubernetesAdminPage() {
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const [clusterId, setClusterId] = useState("");
  const [namespace, setNamespace] = useState("default");
  const [name, setName] = useState("");
  const [kindKey, setKindKey] = useState("apps/v1|Deployment");
  const [activeSessionId, setActiveSessionId] = useState("");
  const [result, setResult] = useState<AdminResult | null>(null);
  const [operationError, setOperationError] = useState<Error | null>(null);

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

  const clusters = clustersQuery.data?.clusters || [];
  const selectedCluster = clusters.find((cluster) => cluster.id === clusterId) || clusters[0];
  const selectedKind = useMemo(() => {
    const [apiVersion, kind] = kindKey.split("|");
    return COMMON_KINDS.find((item) => item.apiVersion === apiVersion && item.kind === kind) || COMMON_KINDS[0];
  }, [kindKey]);
  const activeSession = useMemo(
    () => activeSessionForCluster(sessionsQuery.data?.sessions || [], selectedCluster, activeSessionId),
    [activeSessionId, selectedCluster, sessionsQuery.data?.sessions],
  );
  const canAdminRead = Boolean(readinessQuery.data?.access_policy?.can_admin_read);
  const canUseExplorer = Boolean(canAdminRead && selectedCluster);
  const displayedSessionId = activeSession?.id || activeSessionId;
  const hasUsableSession = Boolean(displayedSessionId);

  useEffect(() => {
    if (!clusterId && clusters[0]?.id) {
      setClusterId(clusters[0].id);
    }
  }, [clusterId, clusters]);

  useEffect(() => {
    if (!activeSessionId && activeSession?.id) {
      setActiveSessionId(activeSession.id);
    }
  }, [activeSession?.id, activeSessionId]);

  const createSessionMutation = useMutation({
    mutationFn: () =>
      createKubernetesAdminSession({
        mode: "read",
        cluster_id: selectedCluster?.id,
        namespace: selectedKind.namespaced ? namespace || "default" : "",
        ttl_minutes: 60,
        allowed_kinds: ["*"],
        allowed_namespaces: ["*"],
      }),
    onSuccess: (payload) => {
      setActiveSessionId(payload.session.id);
      setOperationError(null);
      void queryClient.invalidateQueries({ queryKey: ["kubernetes", "admin", "sessions"] });
    },
    onError: (error) => setOperationError(error instanceof Error ? error : new Error("Session request failed")),
  });

  const runOperation = useMutation({
    mutationFn: async (operation: "discovery" | "list" | "yaml" | "logs" | "watch" | "crds") => {
      const sessionId = activeSessionId || activeSession?.id;
      if (!selectedCluster || !sessionId) {
        throw new Error(localize(lang, "Нужна активная read session", "Active read session is required"));
      }
      if (operation === "discovery") {
        return { type: "discovery" as const, payload: await fetchKubernetesAdminDiscovery(selectedCluster.id, sessionId) };
      }
      if (operation === "crds") {
        return { type: "crds" as const, payload: await fetchKubernetesAdminCrds(selectedCluster.id, sessionId) };
      }
      const query = {
        session_id: sessionId,
        api_version: selectedKind.apiVersion,
        kind: selectedKind.kind,
        namespace: selectedKind.namespaced ? namespace : "",
        name: name.trim(),
      };
      if (operation === "yaml") {
        if (!query.name) throw new Error(localize(lang, "Для YAML нужно имя ресурса", "Resource name is required for YAML"));
        return { type: "yaml" as const, payload: await fetchKubernetesAdminResourceYaml(selectedCluster.id, query) };
      }
      if (operation === "logs") {
        if (selectedKind.kind !== "Pod") throw new Error(localize(lang, "Logs доступны только для Pod", "Logs are available for Pod only"));
        if (!query.name) throw new Error(localize(lang, "Для logs нужно имя pod", "Pod name is required for logs"));
        return {
          type: "logs" as const,
          payload: await fetchKubernetesAdminPodLogs(selectedCluster.id, {
            session_id: sessionId,
            namespace: query.namespace || "default",
            pod: query.name,
            tail: 120,
          }),
        };
      }
      if (operation === "watch") {
        return { type: "watch" as const, payload: await fetchKubernetesAdminResourceWatch(selectedCluster.id, { ...query, limit: 20, timeout_seconds: 10 }) };
      }
      return { type: "list" as const, payload: await fetchKubernetesAdminResources(selectedCluster.id, query) };
    },
    onSuccess: (payload) => {
      setResult(payload);
      setOperationError(null);
    },
    onError: (error) => setOperationError(error instanceof Error ? error : new Error("Admin resource request failed")),
  });

  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: ["kubernetes", "readiness"] });
    void queryClient.invalidateQueries({ queryKey: ["kubernetes", "clusters"] });
    void queryClient.invalidateQueries({ queryKey: ["kubernetes", "admin", "sessions"] });
  };
  const loading = readinessQuery.isLoading || clustersQuery.isLoading || sessionsQuery.isLoading;
  const error = readinessQuery.error || clustersQuery.error || sessionsQuery.error;

  return (
    <PageShell width="full" className="space-y-5">
      <PageHero
        kicker={localize(lang, "Kubernetes Admin Mode", "Kubernetes Admin Mode")}
        title={localize(lang, "Resource explorer", "Resource explorer")}
        description={localize(
          lang,
          "Грубый read-only explorer поверх Rancher/Kubernetes API. Нужна active Admin Mode session; apply/delete/exec не доступны.",
          "Rough read-only explorer over the Rancher/Kubernetes API. Active Admin Mode session is required; apply/delete/exec are not available.",
        )}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge
              label={canAdminRead ? localize(lang, "Admin read", "Admin read") : localize(lang, "Нет admin read", "No admin read")}
              tone={canAdminRead ? "success" : "warning"}
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
          <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
            <SectionCard
              title={localize(lang, "Read session", "Read session")}
              description={localize(lang, "Создать или использовать active Admin Mode session.", "Create or use an active Admin Mode session.")}
              icon={<ShieldCheck className="h-4 w-4" />}
            >
              <div className="space-y-4">
                <FieldLabel label={localize(lang, "Cluster", "Cluster")}>
                  <Select value={selectedCluster?.id || ""} onValueChange={setClusterId}>
                    <SelectTrigger aria-label="Admin cluster">
                      <SelectValue placeholder="Cluster" />
                    </SelectTrigger>
                    <SelectContent>
                      {clusters.map((cluster) => (
                        <SelectItem key={cluster.id} value={cluster.id}>
                          {cluster.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FieldLabel>

                <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge
                      label={activeSession?.status || (activeSessionId ? "active" : localize(lang, "Нет session", "No session"))}
                      tone={hasUsableSession ? "success" : "warning"}
                    />
                    {activeSession ? <StatusBadge label={activeSession.mode} tone="info" /> : null}
                  </div>
                  <div className="mt-2 break-all font-mono text-xs text-muted-foreground">
                    {displayedSessionId || localize(lang, "Active read session ещё не создана.", "Active read session has not been created yet.")}
                  </div>
                  {activeSession?.expires_at ? (
                    <div className="mt-2 text-xs text-muted-foreground">
                      {localize(lang, "Истекает:", "Expires:")} {new Date(activeSession.expires_at).toLocaleString()}
                    </div>
                  ) : null}
                </div>

                <Button
                  type="button"
                  className="w-full"
                  disabled={!canUseExplorer || createSessionMutation.isPending}
                  onClick={() => createSessionMutation.mutate()}
                >
                  <ShieldCheck className="h-4 w-4" />
                  {createSessionMutation.isPending
                    ? localize(lang, "Создаю session", "Creating session")
                    : localize(lang, "Создать read session", "Create read session")}
                </Button>

                <div className="space-y-3 pt-2">
                  <FieldLabel label="Kind">
                    <Select
                      value={kindKey}
                      onValueChange={(value) => {
                        setKindKey(value);
                        setName("");
                      }}
                    >
                      <SelectTrigger aria-label="Resource kind">
                        <SelectValue placeholder="Kind" />
                      </SelectTrigger>
                      <SelectContent>
                        {COMMON_KINDS.map((item) => (
                          <SelectItem key={`${item.apiVersion}|${item.kind}`} value={`${item.apiVersion}|${item.kind}`}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FieldLabel>
                  <FieldLabel label={localize(lang, "Namespace", "Namespace")}>
                    <Input
                      value={selectedKind.namespaced ? namespace : ""}
                      disabled={!selectedKind.namespaced}
                      onChange={(event) => setNamespace(event.target.value)}
                      placeholder={selectedKind.namespaced ? "default" : localize(lang, "cluster-scoped", "cluster-scoped")}
                      aria-label="Resource namespace"
                    />
                  </FieldLabel>
                  <FieldLabel label={localize(lang, "Name для YAML/logs", "Name for YAML/logs")}>
                    <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="payments-api" aria-label="Resource name" />
                  </FieldLabel>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <Button variant="outline" type="button" disabled={!hasUsableSession || runOperation.isPending} onClick={() => runOperation.mutate("discovery")}>
                    <Search className="h-4 w-4" />
                    Discovery
                  </Button>
                  <Button variant="outline" type="button" disabled={!hasUsableSession || runOperation.isPending} onClick={() => runOperation.mutate("crds")}>
                    <ListTree className="h-4 w-4" />
                    CRDs
                  </Button>
                  <Button variant="outline" type="button" disabled={!hasUsableSession || runOperation.isPending} onClick={() => runOperation.mutate("list")}>
                    <Database className="h-4 w-4" />
                    List
                  </Button>
                  <Button variant="outline" type="button" disabled={!hasUsableSession || runOperation.isPending || !name.trim()} onClick={() => runOperation.mutate("yaml")}>
                    <FileCode2 className="h-4 w-4" />
                    YAML
                  </Button>
                  <Button variant="outline" type="button" disabled={!hasUsableSession || runOperation.isPending || selectedKind.kind !== "Pod" || !name.trim()} onClick={() => runOperation.mutate("logs")}>
                    <ScrollText className="h-4 w-4" />
                    Logs
                  </Button>
                  <Button variant="outline" type="button" disabled={!hasUsableSession || runOperation.isPending} onClick={() => runOperation.mutate("watch")}>
                    <Activity className="h-4 w-4" />
                    Watch
                  </Button>
                </div>

                {operationError ? (
                  <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-3 text-xs text-destructive">
                    {operationError.message}
                  </div>
                ) : null}
              </div>
            </SectionCard>

            <AdminResultPanel lang={lang} result={result} loading={runOperation.isPending} />
          </div>
        )}
      </QueryStateBlock>
    </PageShell>
  );
}

function AdminResultPanel({ lang, result, loading }: { lang: string; result: AdminResult | null; loading: boolean }) {
  if (loading) {
    return (
      <SectionCard title={localize(lang, "Result", "Result")} icon={<Braces className="h-4 w-4" />}>
        <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-8 text-sm text-muted-foreground">
          {localize(lang, "Загружаю live read-only данные", "Loading live read-only data")}
        </div>
      </SectionCard>
    );
  }

  if (!result) {
    return (
      <SectionCard title={localize(lang, "Result", "Result")} icon={<Braces className="h-4 w-4" />}>
        <EmptyState
          icon={<Braces className="h-5 w-5" />}
          title={localize(lang, "Запусти read-only операцию", "Run a read-only operation")}
          description={localize(lang, "Discovery, List, YAML, Watch и CRDs появятся здесь.", "Discovery, List, YAML, Watch, and CRDs will appear here.")}
        />
      </SectionCard>
    );
  }

  const payload = result.payload;
  const target = "target" in payload ? payload.target : null;
  const items = "items" in payload && Array.isArray(payload.items) ? payload.items : [];
  const ownership = "ownership" in payload ? payload.ownership : undefined;
  const ownershipSummary = "ownership_summary" in payload ? payload.ownership_summary : undefined;

  return (
    <SectionCard
      title={operationTitle(lang, result.type)}
      description={target ? `${target.api_version} ${target.kind} ${target.namespace || "cluster"}` : payload.operation}
      icon={<Braces className="h-4 w-4" />}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge label={payload.mode} tone="success" />
          {"redacted" in payload && payload.redacted ? <StatusBadge label="redacted" tone="warning" /> : null}
          {"path" in payload ? <StatusBadge label={payload.path} tone="neutral" /> : null}
        </div>
      }
    >
      {ownershipSummary ? <OwnershipSummaryPanel lang={lang} summary={ownershipSummary} /> : null}
      {ownership ? <OwnershipPanel lang={lang} ownership={ownership} /> : null}
      {result.type === "logs" ? <AdminLogsSnapshotPanel lang={lang} logs={result.payload} /> : null}
      {result.type === "watch" ? <WatchPreviewPanel lang={lang} watch={result.payload} /> : null}
      {items.length ? (
        <div className="mb-4 overflow-hidden rounded-lg border border-border/70">
          <div className="grid grid-cols-[minmax(0,1fr)_150px_120px_160px] gap-3 border-b border-border/70 bg-secondary/30 px-4 py-2 text-xs font-semibold uppercase text-muted-foreground">
            <div>Name</div>
            <div>Namespace</div>
            <div>Kind</div>
            <div>Owner</div>
          </div>
          <div className="max-h-72 overflow-auto">
            {items.slice(0, 80).map((item, index) => {
              const itemOwnership = item.webterm_ownership;
              return (
                <div key={`${resourceName(item)}-${index}`} className="grid grid-cols-[minmax(0,1fr)_150px_120px_160px] gap-3 border-b border-border/50 px-4 py-2 text-xs last:border-b-0">
                  <div className="min-w-0 truncate font-medium text-foreground">{resourceName(item) || "-"}</div>
                  <div className="truncate text-muted-foreground">{resourceNamespace(item) || "-"}</div>
                  <div className="truncate text-muted-foreground">{String(item.kind || "-")}</div>
                  <div className="min-w-0">
                    {itemOwnership ? <StatusBadge label={ownerLabel(itemOwnership.owner)} tone={ownerTone(itemOwnership.owner)} /> : "-"}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
      <pre className="max-h-[42rem] overflow-auto rounded-lg border border-border/70 bg-secondary/25 p-4 text-xs leading-5 text-foreground">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </SectionCard>
  );
}

function FieldLabel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function activeSessionForCluster(sessions: KubernetesAdminSession[], cluster: KubernetesCluster | undefined, preferredId: string) {
  const active = sessions.filter((session) => session.status === "active" && session.mode === "read");
  if (preferredId) {
    const preferred = active.find((session) => session.id === preferredId);
    if (preferred) return preferred;
  }
  return active.find((session) => !session.cluster_id || session.cluster_id === cluster?.id) || active[0] || null;
}

function operationTitle(lang: string, type: AdminResult["type"]) {
  if (type === "discovery") return localize(lang, "API discovery", "API discovery");
  if (type === "crds") return "CRDs";
  if (type === "yaml") return "YAML";
  if (type === "logs") return "Logs";
  if (type === "watch") return "Watch preview";
  return localize(lang, "Resources", "Resources");
}

function resourceName(item: Record<string, unknown>) {
  const metadata = item.metadata;
  return typeof metadata === "object" && metadata && "name" in metadata ? String((metadata as Record<string, unknown>).name || "") : "";
}

function resourceNamespace(item: Record<string, unknown>) {
  const metadata = item.metadata;
  return typeof metadata === "object" && metadata && "namespace" in metadata ? String((metadata as Record<string, unknown>).namespace || "") : "";
}
