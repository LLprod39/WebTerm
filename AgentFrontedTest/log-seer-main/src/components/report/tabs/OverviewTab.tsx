import { Timeline } from "../Timeline";
import { ActionPlan } from "../ActionPlan";
import { ArtifactsCard } from "../ArtifactsCard";
import { SeverityBadge } from "../SeverityBadge";
import { summary, rootCause, signals } from "@/data/mockReport";
import { severityMeta } from "@/lib/severity";
import { cn } from "@/lib/utils";
import { Target, Radio, Box, RotateCcw, ShieldCheck } from "lucide-react";

interface OverviewTabProps {
  onGoToArtifacts: () => void;
}

const impact = [
  { icon: Box, label: "Затронуто контейнеров", value: "1" },
  { icon: RotateCcw, label: "Перезапусков", value: "1" },
  { icon: ShieldCheck, label: "Потери данных", value: "Не обнаружены" },
];

export function OverviewTab({ onGoToArtifacts }: OverviewTabProps) {
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
      {/* Left 8 */}
      <div className="space-y-5 lg:col-span-8">
        <div className="report-card p-5 sm:p-6">
          <h3 className="text-base font-semibold text-foreground">Что произошло</h3>
          <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{summary}</p>

          <div className="mt-5 rounded-lg border border-critical/30 bg-critical/[0.07] p-4">
            <div className="flex items-center gap-2">
              <Target className="h-4 w-4 text-critical" />
              <h4 className="text-sm font-semibold text-foreground">Корневая причина</h4>
              <SeverityBadge severity="critical" className="ml-auto" />
            </div>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{rootCause}</p>
          </div>

          <div className="mt-5">
            <div className="flex items-center gap-2">
              <Radio className="h-4 w-4 text-primary" />
              <h4 className="text-sm font-semibold text-foreground">Подтверждающие сигналы</h4>
            </div>
            <ul className="mt-3 divide-y divide-border overflow-hidden rounded-lg border border-border">
              {signals.map((s) => {
                const meta = severityMeta[s.severity];
                return (
                  <li
                    key={s.id}
                    className="flex items-start gap-3 bg-surface/40 p-3 transition-colors hover:bg-surface"
                  >
                    <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", meta.dot)} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                          {s.source}
                        </span>
                        <span className="font-mono text-xs text-muted-foreground">{s.time}</span>
                        <SeverityBadge severity={s.severity} showIcon={false} />
                      </div>
                      <p className="mt-1 break-words font-mono text-[13px] text-foreground">{s.text}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>

        <Timeline />
      </div>

      {/* Right 4 */}
      <div className="space-y-5 lg:col-span-4">
        <ActionPlan />
        <ArtifactsCard onViewAll={onGoToArtifacts} />

        <div className="report-card p-5">
          <h3 className="text-base font-semibold text-foreground">Влияние</h3>
          <ul className="mt-3 space-y-2">
            {impact.map((it) => {
              const Icon = it.icon;
              return (
                <li
                  key={it.label}
                  className="flex items-center gap-3 rounded-lg border border-border bg-surface/60 px-3 py-2.5"
                >
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">{it.label}</span>
                  <span className="ml-auto text-sm font-semibold text-foreground">{it.value}</span>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
