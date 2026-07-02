import { Network } from "lucide-react";

import type { KubernetesNetworkRef } from "@/api";
import { EmptyState, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";
import { formatSync, statusLabel, statusTone } from "@/pages/kubernetes-page/kubernetesPageSections";

function summarizeList(values: unknown[], fallback: string) {
  const items = values.map((value) => {
    if (typeof value === "string" || typeof value === "number") return String(value);
    if (value && typeof value === "object") {
      const row = value as Record<string, unknown>;
      return String(row.host || row.ip || row.port || row.name || "").trim();
    }
    return "";
  }).filter(Boolean);
  return items.slice(0, 3).join(", ") || fallback;
}

export function KubernetesNetworkPanel({ lang, networkRefs }: { lang: string; networkRefs: KubernetesNetworkRef[] }) {
  const services = networkRefs.filter((item) => item.kind === "service");
  const ingresses = networkRefs.filter((item) => item.kind === "ingress");
  return (
    <SectionCard
      title={localize(lang, "Services / Ingress", "Services / Ingress")}
      description={localize(lang, "Native Rancher network inventory, read-only.", "Native Rancher network inventory, read-only.")}
      icon={<Network className="h-4 w-4" />}
    >
      {networkRefs.length ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-md bg-secondary/30 px-3 py-2">
              <div className="font-semibold text-foreground">{services.length}</div>
              <div className="text-muted-foreground">services</div>
            </div>
            <div className="rounded-md bg-secondary/30 px-3 py-2">
              <div className="font-semibold text-foreground">{ingresses.length}</div>
              <div className="text-muted-foreground">ingress</div>
            </div>
          </div>
          <div className="space-y-2">
            {networkRefs.map((item) => (
              <div key={item.id} className="rounded-lg border border-border/70 bg-background/45 px-4 py-3 text-sm">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-foreground">{item.name}</span>
                      <StatusBadge label={item.kind} tone="info" />
                      <StatusBadge label={statusLabel(lang, item.health)} tone={statusTone(item.health)} />
                      {item.service_type ? <StatusBadge label={item.service_type} tone="neutral" /> : null}
                    </div>
                    <div className="mt-1 truncate text-xs text-muted-foreground">{item.namespace}</div>
                    <div className="mt-2 text-xs text-muted-foreground">
                      {item.kind === "ingress"
                        ? summarizeList(item.hosts, localize(lang, "hosts не заданы", "hosts not set"))
                        : summarizeList(item.ports, localize(lang, "ports не заданы", "ports not set"))}
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground sm:text-right">{formatSync(lang, item.last_sync_at)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <EmptyState
          icon={<Network className="h-5 w-5" />}
          title={localize(lang, "Services/Ingress не синхронизированы", "Services/Ingress are not synced")}
          description={localize(lang, "Появятся после Rancher service/ingress sync.", "They will appear after Rancher service/ingress sync.")}
        />
      )}
    </SectionCard>
  );
}
