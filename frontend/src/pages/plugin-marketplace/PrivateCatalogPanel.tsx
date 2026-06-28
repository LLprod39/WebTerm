import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CloudDownload, DatabaseZap, Download, FileJson, Plus, XCircle } from "lucide-react";

import {
  createMarketplaceSource,
  fetchMarketplaceCatalog,
  fetchMarketplaceSources,
  installRemotePluginPackage,
  installMarketplaceItem,
  runMarketplaceCompatibilityJob,
  syncFederatedMarketplaceSource,
  syncMarketplaceSource,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import type { MarketplaceCatalogItem } from "@/plugins/types";

const EMPTY_PAYLOAD = JSON.stringify({ plugins: [] }, null, 2);

function itemName(item: MarketplaceCatalogItem) {
  return String(item.manifest?.name || item.plugin_id);
}

function itemSummary(item: MarketplaceCatalogItem) {
  return String(item.manifest?.summary || "No summary");
}

function itemPublisher(item: MarketplaceCatalogItem) {
  const publisher = item.manifest?.publisher;
  if (publisher && typeof publisher === "object" && "name" in publisher) {
    return String((publisher as { name?: unknown }).name || "Unknown publisher");
  }
  return "Unknown publisher";
}

function manifestList(item: MarketplaceCatalogItem, key: string): Array<Record<string, unknown>> {
  const value = item.manifest?.[key];
  return Array.isArray(value) ? value.filter((entry): entry is Record<string, unknown> => Boolean(entry && typeof entry === "object")) : [];
}

function surfaceCounts(item: MarketplaceCatalogItem) {
  const surfaces = item.manifest?.surfaces;
  if (!surfaces || typeof surfaces !== "object") return [];
  return Object.entries(surfaces as Record<string, unknown>)
    .map(([kind, entries]) => ({ kind, count: Array.isArray(entries) ? entries.length : 0 }))
    .filter((entry) => entry.count > 0);
}

function tone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "verified" || status === "signed" || status === "builtin") return "success";
  if (status === "rejected" || status === "invalid" || status === "suspended") return "danger";
  if (status === "pending" || status === "unsigned") return "warning";
  return "neutral";
}

function CatalogItemCard({
  item,
  selected,
  onSelect,
}: {
  item: MarketplaceCatalogItem;
  selected: boolean;
  onSelect: () => void;
}) {
  const compatible = item.compatibility_report.compatible;
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full rounded-lg border bg-card px-4 py-4 text-left transition-colors hover:border-primary/50",
        selected ? "border-primary/45 ring-1 ring-primary/25" : "border-border/70",
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">{itemName(item)}</h3>
            <StatusBadge label={compatible ? "compatible" : "blocked"} tone={compatible ? "success" : "danger"} />
            {item.installed ? <StatusBadge label="installed" tone="info" /> : null}
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{itemSummary(item)}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <StatusBadge label={item.review_status} tone={tone(item.review_status)} />
          <StatusBadge label={item.signature_status} tone={tone(item.signature_status)} />
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge variant="outline">{item.plugin_id}</Badge>
        <Badge variant="outline">{item.version}</Badge>
        <Badge variant="secondary">{itemPublisher(item)}</Badge>
      </div>
    </button>
  );
}

function CatalogDetail({
  item,
  installing,
  checking,
  onInstall,
  onRunCompatibility,
}: {
  item: MarketplaceCatalogItem | null;
  installing: boolean;
  checking: boolean;
  onInstall: (itemId: number) => void;
  onRunCompatibility: (itemId: number) => void;
}) {
  if (!item) {
    return (
      <div className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-6 text-sm text-muted-foreground">
        Select a catalog plugin to inspect risk, permissions, compatibility, and install state.
      </div>
    );
  }

  const permissions = Array.isArray(item.manifest?.permissions) ? item.manifest.permissions : [];
  const secrets = manifestList(item, "secrets");
  const egress = manifestList(item, "egress");
  const surfaces = surfaceCounts(item);
  const compatible = item.compatibility_report.compatible;
  return (
    <div className="space-y-4 rounded-lg border border-border/70 bg-card px-4 py-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{itemName(item)}</h3>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{itemSummary(item)}</p>
        </div>
        <Button
          size="sm"
          disabled={!compatible || item.installed || installing}
          onClick={() => onInstall(item.id)}
        >
          <Download className="h-4 w-4" />
          Install disabled
        </Button>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <div className="rounded-lg border border-border/60 bg-secondary/15 px-3 py-2">
          <div className="text-xs font-semibold text-muted-foreground">Compatibility</div>
          <div className="mt-2 flex items-center gap-2 text-sm text-foreground">
            {compatible ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <XCircle className="h-4 w-4 text-destructive" />}
            {compatible ? "Supported" : "Blocked"}
          </div>
          {item.compatibility_report.errors.length ? (
            <ul className="mt-2 space-y-1 text-xs text-destructive">
              {item.compatibility_report.errors.map((error) => <li key={error}>{error}</li>)}
            </ul>
          ) : null}
          <Button className="mt-3" size="sm" variant="outline" onClick={() => onRunCompatibility(item.id)} disabled={checking}>
            <CheckCircle2 className="h-4 w-4" />
            Run compatibility
          </Button>
        </div>
        <div className="rounded-lg border border-border/60 bg-secondary/15 px-3 py-2">
          <div className="text-xs font-semibold text-muted-foreground">Package</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <StatusBadge label={item.review_status} tone={tone(item.review_status)} />
            <StatusBadge label={item.signature_status} tone={tone(item.signature_status)} />
          </div>
        </div>
      </div>

      <div>
        <div className="text-xs font-semibold text-muted-foreground">Requested permissions</div>
        <div className="mt-2 space-y-2">
          {permissions.length ? permissions.map((permission, index) => {
            const value = permission as { scope?: unknown; reason?: unknown; risk_tier?: unknown };
            return (
              <div key={`${value.scope || index}`} className="rounded-lg border border-border/60 bg-secondary/15 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-foreground">{String(value.scope || "")}</span>
                  <Badge variant="outline">{String(value.risk_tier || "read")}</Badge>
                </div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{String(value.reason || "")}</p>
              </div>
            );
          }) : (
            <p className="text-xs text-muted-foreground">No explicit permissions.</p>
          )}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-border/60 bg-secondary/15 px-3 py-2">
          <div className="text-xs font-semibold text-muted-foreground">Secrets</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {secrets.length ? secrets.map((secret, index) => (
              <Badge key={`${String(secret.id || secret.key || index)}`} variant="outline">
                {String(secret.id || secret.key || `secret-${index + 1}`)}
              </Badge>
            )) : <span className="text-xs text-muted-foreground">none</span>}
          </div>
        </div>
        <div className="rounded-lg border border-border/60 bg-secondary/15 px-3 py-2">
          <div className="text-xs font-semibold text-muted-foreground">Egress</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {egress.length ? egress.map((entry, index) => (
              <Badge key={`${String(entry.host || index)}`} variant="outline">
                {String(entry.host || entry.url || `egress-${index + 1}`)}
              </Badge>
            )) : <span className="text-xs text-muted-foreground">none</span>}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-border/60 bg-secondary/15 px-3 py-2">
        <div className="text-xs font-semibold text-muted-foreground">Surfaces</div>
        <div className="mt-2 flex flex-wrap gap-2">
          {surfaces.length ? surfaces.map((surface) => (
            <Badge key={surface.kind} variant="outline">{surface.kind}: {surface.count}</Badge>
          )) : <span className="text-xs text-muted-foreground">none</span>}
        </div>
      </div>

      <div className="rounded-lg border border-border/60 bg-secondary/15 px-3 py-2">
        <div className="text-xs font-semibold text-muted-foreground">Source and package</div>
        <div className="mt-2 space-y-1 text-xs text-muted-foreground">
          <div className="truncate">source: {item.source.name}</div>
          <div className="truncate">url: {item.source.source_url}</div>
          <div className="truncate">package: {item.package_url || "metadata only"}</div>
        </div>
      </div>
    </div>
  );
}

export function PrivateCatalogPanel() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [sourceName, setSourceName] = useState("Private catalog");
  const [sourceUrl, setSourceUrl] = useState("local://private-catalog");
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [syncPayload, setSyncPayload] = useState(EMPTY_PAYLOAD);
  const [remotePackageUrl, setRemotePackageUrl] = useState("");
  const [remotePackageSha, setRemotePackageSha] = useState("");

  const sourcesQuery = useQuery({ queryKey: ["plugins", "marketplace", "sources"], queryFn: fetchMarketplaceSources });
  const catalogQuery = useQuery({ queryKey: ["plugins", "marketplace", "catalog"], queryFn: fetchMarketplaceCatalog });
  const sources = sourcesQuery.data?.sources ?? [];
  const items = catalogQuery.data?.items ?? [];
  const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null);
  const activeSourceId = selectedSourceId ?? sources[0]?.id ?? null;
  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedItemId) ?? items[0] ?? null,
    [items, selectedItemId],
  );

  const invalidateMarketplace = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["plugins", "marketplace"] }),
      queryClient.invalidateQueries({ queryKey: ["plugins", "installed"] }),
    ]);
  };

  const createSource = useMutation({
    mutationFn: createMarketplaceSource,
    onSuccess: () => {
      invalidateMarketplace();
      toast({ description: "Private extension source created." });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const syncSource = useMutation({
    mutationFn: ({ sourceId, payload }: { sourceId: number; payload: Record<string, unknown> }) => syncMarketplaceSource(sourceId, payload),
    onSuccess: (result) => {
      invalidateMarketplace();
      toast({ description: `Catalog synced: ${result.synced} plugin(s).` });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const syncFederatedSource = useMutation({
    mutationFn: syncFederatedMarketplaceSource,
    onSuccess: (result) => {
      invalidateMarketplace();
      toast({ description: `Federated source synced: ${result.synced} plugin(s).` });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const installItem = useMutation({
    mutationFn: installMarketplaceItem,
    onSuccess: () => {
      invalidateMarketplace();
      toast({ description: "Catalog plugin installed disabled." });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const installRemote = useMutation({
    mutationFn: installRemotePluginPackage,
    onSuccess: () => {
      invalidateMarketplace();
      toast({ description: "Remote package staged disabled." });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });
  const runCompatibility = useMutation({
    mutationFn: runMarketplaceCompatibilityJob,
    onSuccess: (result) => {
      invalidateMarketplace();
      toast({ description: `Compatibility job ${result.job.status}.` });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const handleSync = () => {
    const sourceId = activeSourceId;
    if (!sourceId) {
      toast({ variant: "destructive", description: "Create a private extension source first." });
      return;
    }
    try {
      const payload = JSON.parse(syncPayload) as Record<string, unknown>;
      syncSource.mutate({ sourceId, payload });
    } catch {
      toast({ variant: "destructive", description: "Catalog JSON is invalid." });
    }
  };

  return (
    <SectionCard title="Private extension catalog" description="Internal catalog metadata installs plugins into disabled state." icon={<DatabaseZap className="h-4 w-4" />}>
      <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-4">
          <div className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4">
            <div className="text-xs font-semibold text-muted-foreground">Source</div>
            <div className="mt-3 space-y-2">
              <Input value={sourceName} onChange={(event) => setSourceName(event.target.value)} />
              <Input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} />
              <Button
                size="sm"
                variant="outline"
                onClick={() => createSource.mutate({ name: sourceName, source_url: sourceUrl, is_enabled: true })}
                disabled={createSource.isPending}
              >
                <Plus className="h-4 w-4" />
                Add source
              </Button>
            </div>
            <QueryStateBlock loading={sourcesQuery.isLoading} error={sourcesQuery.error}>
              <div className="mt-3 space-y-2">
                {sources.map((source) => (
                  <div
                    key={source.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedSourceId(source.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") setSelectedSourceId(source.id);
                    }}
                    className={cn(
                      "w-full rounded-md border bg-background/60 px-3 py-2 text-left transition-colors hover:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/25",
                      source.id === activeSourceId ? "border-primary/45 ring-1 ring-primary/25" : "border-border/60",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 text-xs font-semibold text-foreground">{source.name}</div>
                      <div className="flex shrink-0 gap-1">
                        {source.credentials_redacted ? <Badge variant="outline">redacted</Badge> : null}
                        <Badge variant={source.federated ? "default" : "outline"}>{source.sync_mode || "manual"}</Badge>
                      </div>
                    </div>
                    <div className="mt-0.5 truncate text-xs text-muted-foreground">{source.source_url}</div>
                    {source.last_error ? <div className="mt-1 text-xs text-destructive">{source.last_error}</div> : null}
                    {source.federated ? (
                      <Button
                        className="mt-2"
                        size="sm"
                        variant="outline"
                        onClick={() => syncFederatedSource.mutate(source.id)}
                        disabled={syncFederatedSource.isPending}
                      >
                        <CloudDownload className="h-4 w-4" />
                        Sync remote
                      </Button>
                    ) : null}
                  </div>
                ))}
              </div>
            </QueryStateBlock>
          </div>

          <div className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
              <FileJson className="h-4 w-4" />
              Sync payload
            </div>
            <Textarea value={syncPayload} onChange={(event) => setSyncPayload(event.target.value)} className="min-h-52 font-mono text-xs" />
            <Button className="mt-3" size="sm" onClick={handleSync} disabled={syncSource.isPending}>
              Sync catalog
            </Button>
          </div>

          <div className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
              <CloudDownload className="h-4 w-4" />
              Remote package
            </div>
            <div className="space-y-2">
              <Input placeholder="https://example.com/plugin.wtp" value={remotePackageUrl} onChange={(event) => setRemotePackageUrl(event.target.value)} />
              <Input placeholder="expected sha256" value={remotePackageSha} onChange={(event) => setRemotePackageSha(event.target.value)} />
              <Button
                size="sm"
                variant="outline"
                onClick={() => installRemote.mutate({ url: remotePackageUrl, expected_sha256: remotePackageSha })}
                disabled={installRemote.isPending || !remotePackageUrl || !remotePackageSha}
              >
                <CloudDownload className="h-4 w-4" />
                Stage disabled
              </Button>
            </div>
          </div>
        </div>

        <QueryStateBlock loading={catalogQuery.isLoading} error={catalogQuery.error}>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
            <div className="space-y-3">
              {items.length ? items.map((item) => (
                <CatalogItemCard
                  key={item.id}
                  item={item}
                  selected={item.id === selectedItem?.id}
                  onSelect={() => setSelectedItemId(item.id)}
                />
              )) : (
                <div className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-6 text-sm text-muted-foreground">
                  No private catalog items synced.
                </div>
              )}
            </div>
            <CatalogDetail
              item={selectedItem}
              installing={installItem.isPending}
              checking={runCompatibility.isPending}
              onInstall={(itemId) => installItem.mutate(itemId)}
              onRunCompatibility={(itemId) => runCompatibility.mutate(itemId)}
            />
          </div>
        </QueryStateBlock>
      </div>
    </SectionCard>
  );
}
