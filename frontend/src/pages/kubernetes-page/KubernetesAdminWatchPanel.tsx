import type { KubernetesAdminResourceWatchResponse } from "@/api";
import { StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";

export function WatchPreviewPanel({ lang, watch }: { lang: string; watch: KubernetesAdminResourceWatchResponse }) {
  return (
    <div className="mb-4 rounded-lg border border-border/70 bg-background/45 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge label={localize(lang, "Watch preview", "Watch preview")} tone={watch.available ? "success" : "warning"} />
        <StatusBadge label={`${watch.event_count} events`} tone="info" />
        <StatusBadge label={watch.policy.streaming ? "streaming" : "bounded"} tone="neutral" />
        {watch.truncated ? <StatusBadge label="truncated" tone="warning" /> : null}
      </div>
      <div className="mt-3 grid gap-2 text-xs text-muted-foreground md:grid-cols-3">
        <div>
          <span className="font-semibold text-foreground">Source:</span> {watch.source}
        </div>
        <div>
          <span className="font-semibold text-foreground">Latest RV:</span> {watch.latest_resource_version || "-"}
        </div>
        <div>
          <span className="font-semibold text-foreground">Audit body:</span> metadata only
        </div>
      </div>
      {watch.message ? <div className="mt-3 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">{watch.message}</div> : null}
    </div>
  );
}
