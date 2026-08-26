/**
 * Shared Kubernetes ops shell — industrial control-room aesthetic.
 * Syne + mono, acid lime accents, hard borders (catalog design system).
 */
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Boxes, GitBranch, Layers3, ShieldCheck, Settings2 } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { PageShell } from "@/components/ui/page-shell";
import { cn } from "@/lib/utils";
import { localize, useI18n } from "@/lib/i18n";

const NAV = [
  { to: "/kubernetes", end: true, icon: Boxes, ru: "Пульт", en: "Cockpit" },
  { to: "/kubernetes/fleet", end: false, icon: GitBranch, ru: "Fleet", en: "Fleet" },
  { to: "/kubernetes/devtron", end: false, icon: Layers3, ru: "Приложения", en: "Apps" },
  { to: "/kubernetes/admin", end: false, icon: ShieldCheck, ru: "Администрирование", en: "Admin" },
  { to: "/settings/kubernetes", end: false, icon: Settings2, ru: "Настройка", en: "Setup" },
] as const;

const DENSITY_KEY = "webterm.k8s.density";
export type K8sDensity = "comfort" | "compact";

export function useK8sDensity(): [K8sDensity, (d: K8sDensity) => void] {
  const [density, setDensityState] = useState<K8sDensity>(() => {
    try {
      const raw = localStorage.getItem(DENSITY_KEY);
      return raw === "compact" ? "compact" : "comfort";
    } catch {
      return "comfort";
    }
  });
  const setDensity = (d: K8sDensity) => {
    setDensityState(d);
    try {
      localStorage.setItem(DENSITY_KEY, d);
    } catch {
      /* ignore */
    }
  };
  return [density, setDensity];
}

export function KubernetesShell({
  children,
  className,
  width = "7xl",
}: {
  children: ReactNode;
  className?: string;
  width?: "full" | "7xl" | "6xl" | "5xl";
}) {
  const { lang } = useI18n();
  const location = useLocation();
  const [density, setDensity] = useK8sDensity();

  useEffect(() => {
    document.documentElement.dataset.k8sDensity = density;
    return () => {
      delete document.documentElement.dataset.k8sDensity;
    };
  }, [density]);

  return (
    <PageShell
      width={width}
      className={cn(
        "relative space-y-5 pb-10",
        density === "compact" && "space-y-3 [&_.type-body]:text-xs",
        className,
      )}
    >
      {/* atmospheric grid */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 -z-10 opacity-[0.035]"
        style={{
          backgroundImage:
            "linear-gradient(hsl(var(--foreground)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--foreground)) 1px, transparent 1px)",
          backgroundSize: density === "compact" ? "32px 32px" : "48px 48px",
        }}
      />

      <nav
        data-ui-slot="kubernetes-nav"
        data-page-kind="kubernetes"
        className="sticky top-0 z-20 -mx-1 flex flex-wrap items-center gap-1 rounded-sm border border-border bg-card/95 p-1 shadow-elev-1 backdrop-blur-sm"
        aria-label={localize(lang, "Навигация Kubernetes", "Kubernetes navigation")}
      >
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = item.end
            ? location.pathname === item.to
            : location.pathname === item.to || location.pathname.startsWith(`${item.to}/`);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={cn(
                "inline-flex h-9 items-center gap-2 rounded-sm px-3 text-xs font-medium tracking-wide transition-colors",
                active
                  ? "bg-primary text-primary-foreground shadow-elev-1"
                  : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground",
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {localize(lang, item.ru, item.en)}
            </NavLink>
          );
        })}
        <div className="ml-auto flex items-center gap-1 px-1">
          <button
            type="button"
            onClick={() => setDensity("comfort")}
            className={cn(
              "rounded-sm px-2 py-1 text-2xs uppercase tracking-wide",
              density === "comfort" ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            Comfort
          </button>
          <button
            type="button"
            onClick={() => setDensity("compact")}
            className={cn(
              "rounded-sm px-2 py-1 text-2xs uppercase tracking-wide",
              density === "compact" ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            Compact
          </button>
        </div>
      </nav>

      {children}
    </PageShell>
  );
}

export function KubernetesPageHeader({
  kicker,
  title,
  description,
  actions,
  meta,
}: {
  kicker: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <header
      data-ui-slot="kubernetes-page-header"
      data-page-kind="kubernetes"
      className="relative overflow-hidden rounded-sm border border-border bg-card px-5 py-5 shadow-elev-1 sm:px-6"
    >
      <div className="absolute left-0 top-0 h-full w-1 bg-primary" />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-8 -top-10 h-40 w-40 rounded-full bg-primary/10 blur-2xl"
      />
      <div className="relative flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0 space-y-2 pl-2">
          <div className="enterprise-kicker">{kicker}</div>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
            {title}
          </h1>
          {description ? (
            <p className="type-body max-w-2xl text-muted-foreground">{description}</p>
          ) : null}
          {meta ? <div className="flex flex-wrap items-center gap-2 pt-1">{meta}</div> : null}
        </div>
        {actions ? (
          <div className="flex w-full shrink-0 flex-wrap items-center gap-2 lg:w-auto lg:justify-end">
            {actions}
          </div>
        ) : null}
      </div>
    </header>
  );
}

export function K8sRefreshButton({
  onClick,
  label,
}: {
  onClick: () => void;
  label: string;
}) {
  return (
    <Button type="button" variant="outline" size="sm" className="h-10 gap-2" onClick={onClick}>
      <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-none bg-primary" />
      {label}
    </Button>
  );
}
