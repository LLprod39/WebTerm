import type { ReactNode } from "react";
import { Loader2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

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
    <section className={cn("relative overflow-hidden rounded-lg border border-border/80 bg-card/95 px-5 py-5 shadow-[0_18px_60px_hsl(var(--background)_/_0.24)] sm:px-6", className)}>
      <div className="absolute left-0 top-0 h-full w-0.5 bg-primary/60" />
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0 space-y-1.5 pl-1">
          <div className="enterprise-kicker">{kicker}</div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground">{title}</h1>
          <div className="max-w-3xl text-sm leading-6 text-muted-foreground">{description}</div>
        </div>
        {actions ? <div className="flex w-full shrink-0 flex-wrap items-center gap-2 lg:w-auto lg:justify-end">{actions}</div> : null}
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
  const toneStyles = {
    success: { card: "border-emerald-500/20 bg-emerald-500/6", icon: "bg-emerald-500/12 text-emerald-400", bar: "bg-emerald-500" },
    warning: { card: "border-amber-500/20 bg-amber-500/6", icon: "bg-amber-500/12 text-amber-400", bar: "bg-amber-500" },
    danger: { card: "border-red-500/20 bg-red-500/6", icon: "bg-red-500/12 text-red-400", bar: "bg-red-500" },
    info: { card: "border-primary/20 bg-primary/6", icon: "bg-primary/12 text-primary", bar: "bg-primary" },
    default: { card: "border-border/80 bg-card/95", icon: "border border-border/70 bg-secondary/70 text-muted-foreground", bar: "bg-border" },
  }[tone];

  return (
    <div className={cn("group relative overflow-hidden rounded-lg border transition-all duration-200 hover:shadow-[0_14px_42px_hsl(var(--background)_/_0.22)]", toneStyles.card, className)}>
      <div className={cn("absolute left-0 top-0 h-full w-0.5", toneStyles.bar)} />
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground/70">{label}</p>
            <div className="mt-2 text-3xl font-bold tracking-tight text-foreground">{value}</div>
            <div className="mt-1.5 text-xs leading-5 text-muted-foreground/80">{description}</div>
          </div>
          {icon ? (
            <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors", toneStyles.icon)}>
              {icon}
            </div>
          ) : null}
        </div>
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
    <section className={cn("overflow-hidden rounded-lg border border-border/80 bg-card/95 shadow-[0_14px_42px_hsl(var(--background)_/_0.2)]", className)}>
      <div className="flex flex-col gap-3 border-b border-border/70 bg-secondary/25 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2.5">
          {icon ? (
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              {icon}
            </div>
          ) : null}
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-foreground">{title}</h2>
            {description ? <div className="mt-0.5 text-xs leading-5 text-muted-foreground">{description}</div> : null}
          </div>
        </div>
        {actions ? <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">{actions}</div> : null}
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
    <div className={cn("flex flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-border/60 bg-secondary/20 px-6 py-12 text-center", className)}>
      {icon ? (
        <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-border/70 bg-card/90 text-muted-foreground/60 shadow-sm">
          {icon}
        </div>
      ) : null}
      <div className="space-y-1.5">
        <div className="text-sm font-semibold text-foreground/80">{title}</div>
        <div className="max-w-sm text-xs leading-5 text-muted-foreground/60">{description}</div>
      </div>
      {actions ? <div className="flex flex-wrap items-center justify-center gap-2">{actions}</div> : null}
      {hint ? <div className="rounded-lg border border-border/40 bg-card/60 px-3 py-2 text-xs text-muted-foreground/50 max-w-xs">{hint}</div> : null}
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
  const styles = {
    success: { badge: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20", dot: "bg-emerald-400", pulse: false },
    warning: { badge: "bg-amber-500/10 text-amber-400 border-amber-500/20", dot: "bg-amber-400", pulse: false },
    danger: { badge: "bg-red-500/10 text-red-400 border-red-500/20", dot: "bg-red-400", pulse: false },
    info: { badge: "bg-primary/10 text-primary border-primary/20", dot: "bg-primary", pulse: true },
    neutral: { badge: "bg-secondary/60 text-muted-foreground border-border/70", dot: "bg-muted-foreground/50", pulse: false },
  }[tone];

  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-semibold uppercase tracking-wide", styles.badge, className)}>
      {dot ? (
        <span className="relative flex h-1.5 w-1.5">
          {styles.pulse && <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", styles.dot)} />}
          <span className={cn("relative inline-flex h-1.5 w-1.5 rounded-full", styles.dot)} />
        </span>
      ) : null}
      {label}
    </span>
  );
}

export function QueryStateBlock({
  loading,
  error,
  loadingText,
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
  const { t } = useI18n();
  const resolvedLoadingText = loadingText ?? t("loading");

  if (loading) {
    return (
      <div className={cn("flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground", className)}>
        <Loader2 className="h-4 w-4 animate-spin" />
        {resolvedLoadingText}
      </div>
    );
  }

  if (error) {
    const message = errorText ?? (error instanceof Error ? error.message : t("ui.error_default"));
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
                {t("ui.retry")}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
