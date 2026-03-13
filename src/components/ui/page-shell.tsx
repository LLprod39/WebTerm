import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function PageShell({
  children,
  className,
  width = "7xl",
}: {
  children: ReactNode;
  className?: string;
  width?: "5xl" | "6xl" | "7xl" | "full";
}) {
  const widthClass =
    width === "5xl" ? "max-w-5xl" : width === "6xl" ? "max-w-6xl" : width === "full" ? "max-w-none" : "max-w-7xl";

  return <div className={cn("mx-auto space-y-6 px-6 py-6", widthClass, className)}>{children}</div>;
}

export function PageGrid({
  children,
  className,
  sidebar,
}: {
  children: ReactNode;
  className?: string;
  sidebar?: boolean;
}) {
  return (
    <div
      className={cn(
        "grid gap-6",
        sidebar ? "xl:grid-cols-[minmax(0,1fr)_320px]" : "xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function PageHero({
  kicker,
  title,
  description,
  actions,
  className,
}: {
  kicker: string;
  title: ReactNode;
  description: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("workspace-panel px-6 py-5", className)}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-2">
          <div className="enterprise-kicker">{kicker}</div>
          <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
          <div className="max-w-3xl text-sm leading-6 text-muted-foreground">{description}</div>
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </section>
  );
}

export function MetricGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("grid gap-4 sm:grid-cols-2 xl:grid-cols-4", className)}>{children}</div>;
}

export function MetricCard({
  label,
  value,
  description,
  icon,
  className,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  description: ReactNode;
  icon?: ReactNode;
  className?: string;
  tone?: "default" | "success" | "warning" | "danger" | "info";
}) {
  const toneClass =
    tone === "success"
      ? "border-emerald-500/18 bg-emerald-500/8"
      : tone === "warning"
        ? "border-amber-500/18 bg-amber-500/8"
        : tone === "danger"
          ? "border-red-500/18 bg-red-500/8"
          : tone === "info"
            ? "border-primary/18 bg-primary/8"
            : "border-border bg-secondary/45";

  return (
    <div className={cn("rounded-lg border px-4 py-4", toneClass, className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">{label}</p>
          <div className="mt-2 text-2xl font-semibold text-foreground">{value}</div>
          <div className="mt-2 text-xs leading-5 text-muted-foreground">{description}</div>
        </div>
        {icon ? <div className="text-muted-foreground">{icon}</div> : null}
      </div>
    </div>
  );
}

export function SectionCard({
  title,
  description,
  actions,
  icon,
  children,
  className,
  bodyClassName,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("workspace-panel overflow-hidden", className)}>
      <div className="flex flex-col gap-4 border-b border-border bg-secondary/20 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          {icon ? <div className="mt-0.5 text-muted-foreground">{icon}</div> : null}
          <div>
            <div className="text-base font-semibold text-foreground">{title}</div>
            {description ? <div className="mt-1 text-sm leading-6 text-muted-foreground">{description}</div> : null}
          </div>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className={cn("px-5 py-5", bodyClassName)}>{children}</div>
    </section>
  );
}

export function FilterBar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("workspace-subtle rounded-lg px-4 py-3", className)}>{children}</div>;
}

export function FilterGroup({
  label,
  description,
  children,
  className,
}: {
  label?: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-2", className)}>
      {label ? <div className="text-xs font-medium text-muted-foreground">{label}</div> : null}
      {description ? <div className="text-xs leading-5 text-muted-foreground">{description}</div> : null}
      {children}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  actions,
  hint,
  className,
}: {
  icon?: ReactNode;
  title: ReactNode;
  description: ReactNode;
  actions?: ReactNode;
  hint?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("workspace-empty", className)}>
      {icon ? (
        <div className="flex h-10 w-10 items-center justify-center rounded-md border border-border bg-secondary text-muted-foreground">
          {icon}
        </div>
      ) : null}
      <div className="space-y-2">
        <div className="text-base font-semibold text-foreground">{title}</div>
        <div className="max-w-2xl text-sm leading-6 text-muted-foreground">{description}</div>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-3">{actions}</div> : null}
      {hint ? <div className="rounded-md bg-secondary/60 px-4 py-3 text-xs leading-5 text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

export function StatusBadge({
  label,
  tone = "neutral",
  dot = true,
  className,
}: {
  label: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
  dot?: boolean;
  className?: string;
}) {
  const toneClass =
    tone === "success"
      ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
      : tone === "warning"
        ? "border-amber-500/20 bg-amber-500/10 text-amber-300"
        : tone === "danger"
          ? "border-red-500/20 bg-red-500/10 text-red-300"
          : tone === "info"
            ? "border-primary/20 bg-primary/10 text-primary"
            : "border-border bg-secondary/70 text-muted-foreground";
  const dotClass =
    tone === "success"
      ? "bg-emerald-400"
      : tone === "warning"
        ? "bg-amber-400"
        : tone === "danger"
          ? "bg-red-400"
          : tone === "info"
            ? "bg-primary"
            : "bg-muted-foreground";

  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-medium", toneClass, className)}>
      {dot ? <span className={cn("h-1.5 w-1.5 rounded-full", dotClass)} /> : null}
      {label}
    </span>
  );
}
