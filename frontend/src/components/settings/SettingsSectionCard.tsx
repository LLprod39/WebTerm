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
      <div data-ui-slot="settings-section-card-header" className="flex flex-col gap-3 border-b border-border bg-surface-0/50 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-primary/25 bg-primary/10 text-primary">
            <Icon className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-foreground">{title}</h2>
            {description ? (
              <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{description}</p>
            ) : null}
          </div>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}
