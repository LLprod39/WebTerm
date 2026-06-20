import { kpis } from "@/data/mockReport";
import { severityMeta } from "@/lib/severity";
import { cn } from "@/lib/utils";

export function KpiCards() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {kpis.map((kpi) => {
        const meta = severityMeta[kpi.severity];
        const Icon = meta.icon;
        return (
          <div
            key={kpi.id}
            className="report-card flex items-start gap-3 p-4 transition-colors hover:border-primary/40"
          >
            <div
              className={cn(
                "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
                meta.chip,
              )}
            >
              <Icon className="h-[18px] w-[18px]" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {kpi.label}
              </p>
              <p className="mt-1 truncate text-xl font-semibold text-foreground">{kpi.value}</p>
              <p className="mt-0.5 truncate text-xs text-muted-foreground">{kpi.hint}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
