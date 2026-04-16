import type { ReactNode } from "react";
import { Loader2, AlertCircle } from "lucide-react";
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

  return <div className={cn("mx-auto space-y-5 px-4 py-5 md:px-6 xl:px-8", widthClass, className)}>{children}</div>;
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
          <p className="text-[11px] font-medium text-muted-foreground">{label}</p>
          <div className="mt-2 text-2xl font-semibold text-foreground">{value}</div>
          <div className="mt-2 text-sm leading-5 text-muted-foreground">{description}</div>
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
            <h2 className="text-base font-semibold text-foreground">{title}</h2>
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
    <div className={cn("flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-white/[0.08] bg-white/[0.01] px-6 py-10 text-center", className)}>
      {icon ? (
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/[0.04] text-muted-foreground/40">
          {icon}
        </div>
      ) : null}
      <div className="space-y-1">
        <div className="text-sm font-semibold text-foreground/80">{title}</div>
        <div className="max-w-sm text-xs text-muted-foreground/50">{description}</div>
      </div>
      {actions ? <div className="flex flex-wrap items-center justify-center gap-2 mt-1">{actions}</div> : null}
      {hint ? <div className="rounded-lg bg-white/[0.03] px-3 py-2 text-[11px] text-muted-foreground/50 mt-1 max-w-xs">{hint}</div> : null}
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
      ? "bg-emerald-500/10 text-emerald-400"
      : tone === "warning"
        ? "bg-amber-500/10 text-amber-400"
        : tone === "danger"
          ? "bg-red-500/10 text-red-400"
          : tone === "info"
            ? "bg-primary/10 text-primary"
            : "bg-white/[0.04] text-muted-foreground";
  const dotClass =
    tone === "success"
      ? "bg-emerald-400"
      : tone === "warning"
        ? "bg-amber-400"
        : tone === "danger"
          ? "bg-red-400"
          : tone === "info"
            ? "bg-primary"
            : "bg-muted-foreground/60";

  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium", toneClass, className)}>
      {dot ? <span className={cn("h-1.5 w-1.5 rounded-full", dotClass)} /> : null}
      {label}
    </span>
  );
}

export function QueryStateBlock({
  loading,
  error,
  loadingText = "Загрузка...",
  errorText,
  onRetry,
  children,
  className,
}: {
  loading?: boolean;
  error?: unknown;
  loadingText?: string;
  errorText?: string;
  onRetry?: () => void;
  children: ReactNode;
  className?: string;
}) {
  if (loading) {
    return (
      <div className={cn("flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground", className)}>
        <Loader2 className="h-4 w-4 animate-spin" />
        {loadingText}
      </div>
    );
  }

  if (error) {
    const message = errorText ?? (error instanceof Error ? error.message : "Произошла ошибка");
    return (
      <div className={cn("rounded-lg border border-destructive/30 bg-destructive/8 px-5 py-4", className)}>
        <div className="flex items-start gap-3">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-destructive">{message}</p>
            {onRetry ? (
              <button
                type="button"
                onClick={onRetry}
                className="mt-1 text-xs text-destructive/70 underline-offset-2 hover:underline"
              >
                Попробовать снова
              </button>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
