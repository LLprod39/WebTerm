import type { LucideIcon } from "lucide-react";

import { localize } from "@/lib/i18n";

type SummaryRow = { icon: LucideIcon; label: string; value: string };

type AgentWizardQuickSummaryProps = {
  lang: string;
  summaryRows: SummaryRow[];
};

export function AgentWizardQuickSummary({ lang, summaryRows }: AgentWizardQuickSummaryProps) {
  return (
    <aside className="space-y-4">
      <section className="rounded-lg border border-border/70 bg-secondary/20 p-4">
        <h3 className="mb-4 text-base font-semibold text-foreground">{localize(lang, "Краткий обзор", "Quick summary")}</h3>
        <div className="space-y-4">
          {summaryRows.map((row) => {
            const Icon = row.icon;
            return (
              <div key={row.label} className="flex gap-3">
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0">
                  <div className="text-xs text-muted-foreground">{row.label}</div>
                  <div className="truncate text-sm text-foreground">{row.value}</div>
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </aside>
  );
}
