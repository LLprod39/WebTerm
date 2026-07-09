import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Cable, RadioTower, RefreshCw } from "lucide-react";

import { fetchPluginConnectorHealth, fetchPluginSurfaces, pingPluginConnector } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

function connectorId(connector: Record<string, unknown>) {
  return `${String(connector.plugin_id || "")}:${String(connector.id || "")}`;
}

export function PluginConnectorsPanel() {
  const { toast } = useToast();
  const [selectedKey, setSelectedKey] = useState("");
  const surfacesQuery = useQuery({ queryKey: ["plugins", "surfaces", "connectors"], queryFn: fetchPluginSurfaces });
  const connectors = surfacesQuery.data?.surfaces?.connectors ?? [];
  const selected = useMemo(
    () => connectors.find((item) => connectorId(item) === selectedKey) ?? connectors[0] ?? null,
    [connectors, selectedKey],
  );
  const pluginId = String(selected?.plugin_id || "");
  const selectedConnectorId = String(selected?.id || "");
  const healthQuery = useQuery({
    queryKey: ["plugins", "connectors", pluginId, selectedConnectorId, "health"],
    queryFn: () => fetchPluginConnectorHealth(pluginId, selectedConnectorId),
    enabled: Boolean(pluginId && selectedConnectorId),
    retry: false,
  });
  const pingMutation = useMutation({
    mutationFn: () => pingPluginConnector(pluginId, selectedConnectorId),
    onSuccess: () => toast({ description: "Connector ping completed." }),
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  return (
    <SectionCard title="Connectors" description="Enabled plugin connectors with health checks." icon={<Cable className="h-4 w-4" />}>
      <QueryStateBlock loading={surfacesQuery.isLoading} error={surfacesQuery.error}>
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
          <div className="space-y-3">
            {connectors.length ? connectors.map((connector) => {
              const key = connectorId(connector);
              const active = key === connectorId(selected ?? {});
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSelectedKey(key)}
                  className={cn(
                    "w-full rounded-lg border bg-card px-4 py-4 text-left transition-colors hover:border-primary/50",
                    active ? "border-primary/45 ring-1 ring-primary/25" : "border-border/70",
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-foreground">{String(connector.title || connector.id)}</span>
                    <Badge variant="outline">{String(connector.plugin_id)}</Badge>
                  </div>
                  {connector.description ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{String(connector.description)}</p> : null}
                </button>
              );
            }) : (
              <p className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground">
                No enabled plugin connectors.
              </p>
            )}
          </div>

          <QueryStateBlock loading={healthQuery.isLoading} error={healthQuery.error}>
            {selected ? (
              <div className="space-y-4 rounded-lg border border-border/70 bg-card px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-foreground">{String(selected.title || selected.id)}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{pluginId}</div>
                  </div>
                  <StatusBadge
                    label={healthQuery.data?.health.status || "unknown"}
                    tone={healthQuery.data?.health.status === "healthy" ? "success" : "warning"}
                  />
                </div>
                <div className="space-y-2">
                  {(healthQuery.data?.health.checks ?? []).map((check, index) => (
                    <div key={index} className="flex items-center justify-between rounded-lg border border-border/60 bg-secondary/15 px-3 py-2 text-xs">
                      <span className="font-medium text-foreground">{String(check.name || "check")}</span>
                      <StatusBadge label={check.ok ? "ok" : "blocked"} tone={check.ok ? "success" : "warning"} dot={false} />
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => healthQuery.refetch()}>
                    <RefreshCw className="h-4 w-4" />
                    Refresh
                  </Button>
                  <Button size="sm" onClick={() => pingMutation.mutate()} disabled={pingMutation.isPending}>
                    <RadioTower className="h-4 w-4" />
                    Ping
                  </Button>
                </div>
              </div>
            ) : null}
          </QueryStateBlock>
        </div>
      </QueryStateBlock>
    </SectionCard>
  );
}
