import { AlertTriangle, CheckCircle2, Circle, XCircle, type LucideIcon } from "lucide-react";

import { localize } from "@/lib/i18n";
import { StatusBadge } from "@/components/system/StatusBadge";
import { cn } from "@/lib/utils";
import type { AgentWizardCheck } from "./agentPageUtils";

type SummaryRow = { icon: LucideIcon; label: string; value: string };

type AgentWizardQuickSummaryProps = {
  lang: string;
  summaryRows: SummaryRow[];
  readiness: number;
  checks: AgentWizardCheck[];
};

export function AgentWizardQuickSummary({ lang, summaryRows, readiness, checks }: AgentWizardQuickSummaryProps) {
  return (
    <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start">
      <section className="rounded-lg border border-border/70 bg-secondary/20 p-4">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h3 className="text-base font-semibold leading-6 text-foreground">{localize(lang, "Готовность", "Readiness")}</h3>
          <StatusBadge
            label={`${readiness}%`}
            tone={readiness === 100 ? "success" : readiness >= 70 ? "warning" : "danger"}
          />
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-background/70">
          <div
            className={cn(
              "h-full rounded-full transition-all",
              readiness === 100 ? "bg-success" : readiness >= 70 ? "bg-warning" : "bg-destructive",
            )}
            style={{ width: `${readiness}%` }}
          />
        </div>
        <div className="mt-4 space-y-2">
          {checks.map((check) => {
            const Icon = check.passed ? CheckCircle2 : check.risk === "danger" ? XCircle : check.risk === "warning" ? AlertTriangle : Circle;
            return (
              <div key={check.key} className="flex gap-2.5 rounded-md border border-border/60 bg-background/25 px-3 py-2">
                <Icon
                  className={cn(
                    "mt-0.5 h-4 w-4 shrink-0",
                    check.passed ? "text-success" : check.risk === "danger" ? "text-destructive" : check.risk === "warning" ? "text-warning" : "text-muted-foreground",
                  )}
                />
                <div className="min-w-0">
                  <div className="text-xs font-semibold leading-4 text-foreground">
                    {localize(lang, check.labelRu, check.labelEn)}
                  </div>
                  <div className="mt-0.5 text-xs leading-4 text-muted-foreground">
                    {localize(lang, check.detailRu, check.detailEn)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="rounded-lg border border-border/70 bg-secondary/20 p-4">
        <h3 className="mb-4 text-base font-semibold leading-6 text-foreground">{localize(lang, "Краткий обзор", "Quick summary")}</h3>
        <div className="space-y-3">
          {summaryRows.map((row) => {
            const Icon = row.icon;
            return (
              <div key={row.label} className="flex gap-3">
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0">
                  <div className="text-xs leading-4 text-muted-foreground">{row.label}</div>
                  <div className="truncate text-sm leading-5 text-foreground">{row.value}</div>
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </aside>
  );
}
