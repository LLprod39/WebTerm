import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  meta,
  className,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between", className)}>
      <div className="min-w-0 space-y-2">
        {eyebrow ? <div className="text-xs font-semibold uppercase tracking-wide text-primary">{eyebrow}</div> : null}
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold leading-8 tracking-normal text-foreground md:text-2xl">{title}</h1>
          {description ? <p className="max-w-3xl text-sm leading-5 text-muted-foreground md:text-[15px]">{description}</p> : null}
        </div>
        {meta ? <div className="flex flex-wrap items-center gap-2 pt-1">{meta}</div> : null}
      </div>
      {actions ? <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">{actions}</div> : null}
    </header>
  );
}
