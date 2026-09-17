import { Link } from "react-router-dom";

import { localize } from "@/lib/i18n";
import { cn, relativeTime } from "@/lib/utils";

export interface RunPulseItem {
  id: number;
  status: string;
  agent_name?: string;
  started_at?: string;
}

function tickTone(status: string): string {
  if (status === "succeeded" || status === "success" || status === "completed") return "bg-success";
  if (status === "failed" || status === "error") return "bg-destructive";
  if (status === "running" || status === "pending") return "bg-info animate-pulse";
  return "bg-muted-foreground/30";
}

/**
 * Heartbeat strip of the latest agent runs (oldest → newest): one tick per
 * run, green/red/blue. Reads at a glance like an ECG of automation health.
 */
export function RunPulse({
  runs,
  lang,
  maxTicks = 24,
  className,
}: {
  runs: RunPulseItem[];
  lang: string;
  maxTicks?: number;
  className?: string;
}) {
  // API returns newest first; render oldest → newest so "now" is on the right.
  const ticks = runs.slice(0, maxTicks).reverse();

  if (ticks.length === 0) return null;

  return (
    <div className={cn("flex items-center gap-3", className)}>
      <span className="shrink-0 text-2xs font-medium uppercase tracking-[0.12em] text-muted-foreground/60">
        {localize(lang, "Пульс запусков", "Run pulse")}
      </span>
      <div className="flex h-5 flex-1 items-end gap-[3px]">
        {ticks.map((run) => (
          <Link
            key={run.id}
            to={`/agents/run/${run.id}`}
            title={`${run.agent_name ?? "run"} — ${run.status}${run.started_at ? ` · ${relativeTime(run.started_at)}` : ""}`}
            className={cn(
              "h-full w-1.5 rounded-[1px] transition-transform hover:scale-y-125 hover:opacity-80",
              tickTone(run.status),
            )}
          />
        ))}
      </div>
      <span className="shrink-0 font-mono text-2xs text-muted-foreground/50">
        {localize(lang, "старые → новые", "old → new")}
      </span>
    </div>
  );
}
