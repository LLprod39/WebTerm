import { ShieldCheck } from "lucide-react";

import type {
  KubernetesAdminResourceDiscoveryResponse,
  KubernetesAdminSession,
  KubernetesCluster,
} from "@/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";

export function AdminWorkspaceToolbar({
  lang,
  clusters,
  selectedCluster,
  clusterId,
  onClusterChange,
  activeSession,
  sessionId,
  createPending,
  createError,
  onCreateSession,
  canCreate,
  catalog,
}: {
  lang: string;
  clusters: KubernetesCluster[];
  selectedCluster?: KubernetesCluster;
  clusterId: string;
  onClusterChange: (value: string) => void;
  activeSession: KubernetesAdminSession | null;
  sessionId: string;
  createPending: boolean;
  createError: unknown;
  onCreateSession: () => void;
  canCreate: boolean;
  catalog?: KubernetesAdminResourceDiscoveryResponse;
}) {
  const resourceCatalog = catalog?.resource_catalog;
  return (
    <section className="overflow-hidden rounded-lg border border-border/80 bg-card/95 shadow-[0_14px_42px_hsl(var(--background)_/_0.2)]">
      <div className="grid gap-4 px-5 py-4 lg:grid-cols-[260px_minmax(0,1fr)_auto] lg:items-center">
        <label className="block space-y-2">
          <span className="text-xs font-medium text-muted-foreground">{localize(lang, "Cluster", "Cluster")}</span>
          <Select value={clusterId} onValueChange={onClusterChange}>
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
        </label>

        <div className="min-w-0 rounded-lg border border-border/70 bg-background/45 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge
              label={activeSession?.status || (sessionId ? "active" : localize(lang, "Нет read session", "No read session"))}
              tone={sessionId ? "success" : "warning"}
            />
            {activeSession ? <StatusBadge label={activeSession.mode} tone="info" /> : null}
            {selectedCluster ? <StatusBadge label={selectedCluster.name} tone="neutral" /> : null}
            {resourceCatalog ? (
              <StatusBadge
                label={`${resourceCatalog.counts.total} resources`}
                tone={resourceCatalog.status === "ready" ? "success" : "warning"}
              />
            ) : null}
          </div>
          <div className="mt-2 break-all font-mono text-xs text-muted-foreground">
            {sessionId || localize(lang, "Active read session появится здесь.", "The active read session will appear here.")}
          </div>
          {activeSession?.expires_at ? (
            <div className="mt-1 text-xs text-muted-foreground">
              {localize(lang, "TTL:", "TTL:")} {new Date(activeSession.expires_at).toLocaleString()}
            </div>
          ) : null}
        </div>

        <div className="flex flex-col gap-2 lg:items-end">
          <Button disabled={!canCreate || createPending} onClick={onCreateSession}>
            <ShieldCheck className="h-4 w-4" />
            {createPending ? localize(lang, "Создаю session", "Creating session") : localize(lang, "Создать read session", "Create read session")}
          </Button>
          {createError ? (
            <div className="max-w-xs text-xs text-destructive">
              {createError instanceof Error ? createError.message : localize(lang, "Session request failed", "Session request failed")}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">
              {localize(lang, "Read-only, TTL 60 мин", "Read-only, 60 min TTL")}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
