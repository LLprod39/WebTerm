import { AlertOctagon, AlertTriangle, ArrowRight, Info, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { localize } from "@/lib/i18n";
import { cn, relativeTime } from "@/lib/utils";

export type AttentionSeverity = "critical" | "warning" | "info";

export interface AttentionItem {
  id: string;
  severity: AttentionSeverity;
  title: string;
  detail?: string;
  /** ISO timestamp, rendered as relative time. */
  time?: string | null;
  action?: { label: string; to: string };
}

const severityRank: Record<AttentionSeverity, number> = { critical: 0, warning: 1, info: 2 };

const severityStyles: Record<
  AttentionSeverity,
  { row: string; icon: string; Icon: typeof AlertTriangle }
> = {
  critical: {
    row: "border-destructive/40 bg-destructive/5 hover:border-destructive/70",
    icon: "text-destructive",
    Icon: AlertOctagon,
  },
  warning: {
    row: "border-warning/40 bg-warning/5 hover:border-warning/70",
    icon: "text-warning",
    Icon: AlertTriangle,
  },
  info: {
    row: "border-border bg-surface-1 hover:border-primary/40",
    icon: "text-info",
    Icon: Info,
  },
};

/**
 * Triage list: everything that needs an operator's attention right now,
 * sorted by severity, each row with a one-click follow-up action.
 */
export function AttentionPanel({
  items,
  lang,
  maxItems = 6,
  allClearTitle,
  allClearDetail,
}: {
  items: AttentionItem[];
  lang: string;
  maxItems?: number;
  allClearTitle?: string;
  allClearDetail?: string;
}) {
  const sorted = [...items].sort((a, b) => severityRank[a.severity] - severityRank[b.severity]);
  const visible = sorted.slice(0, maxItems);
  const hiddenCount = sorted.length - visible.length;
  const criticalCount = sorted.filter((item) => item.severity === "critical").length;
  const warningCount = sorted.filter((item) => item.severity === "warning").length;

  if (sorted.length === 0) {
    return (
      <div className="flex items-center gap-4 rounded-sm border border-success/30 bg-success/5 px-5 py-5">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-sm border border-success/40 bg-success/10 text-success">
          <ShieldCheck className="h-6 w-6" />
        </div>
        <div className="min-w-0">
          <div className="font-display text-base font-bold text-success">
            {allClearTitle ?? localize(lang, "Все системы в норме", "All systems nominal")}
          </div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            {allClearDetail ??
              localize(
                lang,
                "Алертов нет, серверы на связи, агенты отрабатывают штатно.",
                "No alerts, servers reachable, agent runs healthy.",
              )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-2xs font-medium uppercase tracking-[0.12em]">
        {criticalCount > 0 && (
          <span className="inline-flex items-center gap-1.5 rounded-sm border border-destructive/30 bg-destructive/10 px-2 py-0.5 text-destructive">
            <AlertOctagon className="h-3 w-3" />
            {criticalCount} {localize(lang, "критично", "critical")}
          </span>
        )}
        {warningCount > 0 && (
          <span className="inline-flex items-center gap-1.5 rounded-sm border border-warning/30 bg-warning/10 px-2 py-0.5 text-warning">
            <AlertTriangle className="h-3 w-3" />
            {warningCount} {localize(lang, "внимание", "warning")}
          </span>
        )}
        <span className="text-muted-foreground/60 normal-case tracking-normal">
          {localize(lang, "отсортировано по важности", "sorted by severity")}
        </span>
      </div>

      <div className="space-y-2">
        {visible.map((item) => {
          const styles = severityStyles[item.severity];
          const SeverityIcon = styles.Icon;
          return (
            <div
              key={item.id}
              className={cn(
                "flex items-center gap-3 rounded-sm border px-3 py-2.5 text-xs transition-colors",
                styles.row,
              )}
            >
              <SeverityIcon className={cn("h-4 w-4 shrink-0", styles.icon)} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate font-semibold text-foreground/95">{item.title}</span>
                  {item.time ? (
                    <span className="shrink-0 font-mono text-2xs text-muted-foreground/60">{relativeTime(item.time)}</span>
                  ) : null}
                </div>
                {item.detail ? (
                  <p className="mt-0.5 truncate text-2xs leading-4 text-muted-foreground">{item.detail}</p>
                ) : null}
              </div>
              {item.action ? (
                <Button size="xs" variant="outline" asChild className="shrink-0">
                  <Link to={item.action.to}>
                    {item.action.label}
                    <ArrowRight className="ml-1 h-3 w-3" />
                  </Link>
                </Button>
              ) : null}
            </div>
          );
        })}
      </div>

      {hiddenCount > 0 && (
        <div className="text-2xs text-muted-foreground/70">
          {localize(lang, `Ещё ${hiddenCount} — смотрите разделы алертов и запусков`, `${hiddenCount} more — see alerts & runs sections`)}
        </div>
      )}
    </div>
  );
}
