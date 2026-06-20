import { useState } from "react";
import { agentSteps } from "@/data/mockReport";
import { severityMeta } from "@/lib/severity";
import { SeverityBadge } from "../SeverityBadge";
import { cn } from "@/lib/utils";
import { ChevronDown, Clock } from "lucide-react";

export function AgentRunTab() {
  const [open, setOpen] = useState<string | null>(agentSteps[0]?.id ?? null);

  return (
    <div className="report-card p-4 sm:p-5">
      <div className="mb-4">
        <h3 className="text-base font-semibold text-foreground">Ход агента</h3>
        <p className="mt-0.5 text-sm text-muted-foreground">
          5 шагов выполнения — нажмите для технических деталей
        </p>
      </div>

      <ol className="space-y-2.5">
        {agentSteps.map((step, i) => {
          const meta = severityMeta[step.status];
          const Icon = meta.icon;
          const isOpen = open === step.id;
          return (
            <li
              key={step.id}
              className="overflow-hidden rounded-lg border border-border bg-surface/50"
            >
              <button
                onClick={() => setOpen(isOpen ? null : step.id)}
                className="flex w-full items-center gap-3 p-3.5 text-left transition-colors hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-expanded={isOpen}
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-card font-mono text-xs font-semibold text-muted-foreground">
                  {step.index}
                </span>
                <div
                  className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
                    meta.chip,
                  )}
                >
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">{step.title}</p>
                  <p className="truncate font-mono text-xs text-muted-foreground">{step.command}</p>
                </div>
                <SeverityBadge
                  severity={step.status}
                  label={step.statusLabel}
                  showIcon={false}
                  className="hidden sm:inline-flex"
                />
                <span className="hidden items-center gap-1 font-mono text-xs text-muted-foreground sm:flex">
                  <Clock className="h-3.5 w-3.5" />
                  {step.duration}
                </span>
                <ChevronDown
                  className={cn(
                    "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
                    isOpen && "rotate-180",
                  )}
                />
              </button>

              {isOpen && (
                <div className="animate-fade-in border-t border-border bg-background/40 p-4">
                  <div className="mb-3 flex flex-wrap items-center gap-2 sm:hidden">
                    <SeverityBadge severity={step.status} label={step.statusLabel} showIcon={false} />
                    <span className="inline-flex items-center gap-1 font-mono text-xs text-muted-foreground">
                      <Clock className="h-3.5 w-3.5" />
                      {step.duration}
                    </span>
                  </div>
                  <pre className="mb-3 overflow-x-auto rounded-md border border-border bg-surface p-3 font-mono text-xs text-primary">
                    $ {step.command}
                  </pre>
                  <p className="text-sm leading-relaxed text-muted-foreground">{step.details}</p>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
