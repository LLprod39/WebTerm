import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function SettingsSectionCard({
  title,
  icon: Icon,
  children,
  description,
  actions,
  className,
}: {
  title: string;
  icon: React.ElementType;
  children: ReactNode;
  description?: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <section
      data-ui-slot="settings-section-card"
      className={cn(
        "overflow-hidden rounded-sm border border-border bg-card shadow-elev-1",
        className,
      )}
    >
      <div
        data-ui-slot="settings-section-card-header"
        className="flex flex-col gap-3 border-b border-border bg-surface-0/40 px-5 py-4 sm:flex-row sm:items-start sm:justify-between"
      >
        <div className="flex min-w-0 items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-primary/25 bg-primary/10 text-primary">
            <Icon className="h-4 w-4" strokeWidth={1.5} />
          </div>
          <div className="min-w-0">
            <h2 className="text-base font-semibold tracking-tight text-foreground">{title}</h2>
            {description ? (
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p>
            ) : null}
          </div>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}
