import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function ContentPanel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-lg border border-border/80 bg-card/95", className)}>
      {children}
    </section>
  );
}

export function ContentSection({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("border-t border-border/70 first:border-t-0", className)}>
      {(title || description || actions) ? (
        <div className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1">
            {title ? <h2 className="text-base font-semibold leading-6 text-foreground">{title}</h2> : null}
            {description ? <p className="text-sm leading-5 text-muted-foreground">{description}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      <div className={cn((title || description || actions) ? "px-5 pb-5" : "p-5")}>{children}</div>
    </section>
  );
}

export function MetaPill({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex min-h-7 items-center rounded-md border border-border/70 bg-secondary/50 px-2.5 text-xs font-medium text-muted-foreground", className)}>
      {children}
    </span>
  );
}
