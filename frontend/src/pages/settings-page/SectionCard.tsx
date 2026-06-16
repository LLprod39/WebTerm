import type { ElementType, ReactNode } from "react";

type SectionCardProps = {
  title: string;
  icon: ElementType;
  children: ReactNode;
  description?: string;
  actions?: ReactNode;
};

export function SectionCard({ title, icon: Icon, children, description, actions }: SectionCardProps) {
  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="flex flex-col gap-4 border-b border-border bg-secondary/20 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-lg bg-background text-primary">
            <Icon className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">{title}</h2>
            {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
          </div>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}
