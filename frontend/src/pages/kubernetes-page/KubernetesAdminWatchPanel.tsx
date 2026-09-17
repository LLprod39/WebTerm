import type { KubernetesAdminResourceWatchResponse } from "@/api";
import { StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";

export function WatchPreviewPanel({ lang, watch }: { lang: string; watch: KubernetesAdminResourceWatchResponse }) {
  return (
    <div className="mb-4 rounded-lg border border-border/70 bg-background/45 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge label={localize(lang, "Последние изменения", "Watch preview")} tone={watch.available ? "success" : "warning"} />
        <StatusBadge label={`${watch.event_count} ${localize(lang, "событий", "events")}`} tone="info" />
        <StatusBadge label={watch.policy.streaming ? localize(lang, "поток", "streaming") : localize(lang, "ограниченная выборка", "bounded")} tone="neutral" />
        {watch.truncated ? <StatusBadge label={localize(lang, "обрезано", "truncated")} tone="warning" /> : null}
      </div>
      <div className="mt-3 grid gap-2 text-xs text-muted-foreground md:grid-cols-3">
        <div>
          <span className="font-semibold text-foreground">{localize(lang, "Источник:", "Source:")}</span> {watch.source}
        </div>
        <div>
          <span className="font-semibold text-foreground">{localize(lang, "Последняя версия:", "Latest RV:")}</span> {watch.latest_resource_version || "-"}
        </div>
        <div>
          <span className="font-semibold text-foreground">{localize(lang, "В аудите:", "Audit body:")}</span> {localize(lang, "только метаданные", "metadata only")}
        </div>
      </div>
      {watch.message ? <div className="mt-3 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">{watch.message}</div> : null}
    </div>
  );
}
