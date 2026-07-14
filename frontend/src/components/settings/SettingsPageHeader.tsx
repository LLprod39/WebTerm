import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/** Consistent page hat inside Settings content column. */
export function SettingsPageHeader({
  title,
  description,
  icon: Icon,
  actions,
  className,
}: {
  title: string;
  description?: string;
  icon?: LucideIcon;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "relative mb-5 overflow-hidden rounded-sm border border-border bg-card/80 px-4 py-4 sm:px-5",
        className,
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "linear-gradient(120deg, hsl(var(--primary) / 0.06), transparent 50%)",
        }}
      />
      <div aria-hidden className="absolute inset-x-0 top-0 h-0.5 bg-primary/80" />
      <div className="relative flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          {Icon ? (
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border border-border bg-surface-0 text-primary">
              <Icon className="h-4 w-4" />
            </div>
          ) : null}
          <div className="min-w-0">
            <h1 className="font-display text-xl font-bold tracking-tight text-foreground">{title}</h1>
            {description ? (
              <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">{description}</p>
            ) : null}
          </div>
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}
