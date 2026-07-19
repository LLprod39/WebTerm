/**
 * Minimalist Kubernetes cockpit visuals — pure CSS/SVG, catalog design tokens.
 */
import type { ReactNode } from "react";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type HealthSlice = {
  key: string;
  label: string;
  value: number;
  color: string;
};

export function HealthDonut({
  slices,
  centerLabel,
  centerValue,
  size = 160,
}: {
  slices: HealthSlice[];
  centerLabel: string;
  centerValue: string | number;
  size?: number;
}) {
  const total = Math.max(1, slices.reduce((sum, s) => sum + Math.max(0, s.value), 0));
  const r = 54;
  const c = 2 * Math.PI * r;
  let offset = 0;
  const stroke = 12;

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox="0 0 140 140" className="-rotate-90">
        <circle cx="70" cy="70" r={r} fill="none" stroke="hsl(var(--border))" strokeWidth={stroke} />
        {slices.map((slice) => {
          const len = (Math.max(0, slice.value) / total) * c;
          const dash = `${len} ${c - len}`;
          const el = (
            <circle
              key={slice.key}
              cx="70"
              cy="70"
              r={r}
              fill="none"
              stroke={slice.color}
              strokeWidth={stroke}
              strokeDasharray={dash}
              strokeDashoffset={-offset}
              strokeLinecap="butt"
              className="transition-all duration-700 ease-out"
            />
          );
          offset += len;
          return el;
        })}
      </svg>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
        <div className="font-display text-3xl font-semibold tracking-tight text-foreground">{centerValue}</div>
        <div className="mt-0.5 max-w-[7rem] text-2xs uppercase tracking-[0.14em] text-muted-foreground">
          {centerLabel}
        </div>
      </div>
    </div>
  );
}

export function HealthLegend({ slices }: { slices: HealthSlice[]; lang?: string }) {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <div className="w-full min-w-[10rem] space-y-2">
      {slices.map((slice) => (
        <div key={slice.key} className="flex items-center gap-2 text-xs">
          <span className="h-2.5 w-2.5 shrink-0 rounded-none" style={{ background: slice.color }} />
          <span className="min-w-0 flex-1 text-muted-foreground">{slice.label}</span>
          <span className="font-display font-semibold tabular-nums text-foreground">{slice.value}</span>
          <span className="w-10 text-right font-mono text-2xs tabular-nums text-muted-foreground">
            {Math.round((slice.value / total) * 100)}%
          </span>
        </div>
      ))}
    </div>
  );
}

export function MiniBar({
  value,
  max = 100,
  tone = "default",
  className,
}: {
  value: number;
  max?: number;
  tone?: "default" | "success" | "warning" | "danger";
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, max > 0 ? (value / max) * 100 : 0));
  const color =
    tone === "success"
      ? "bg-emerald-400"
      : tone === "warning"
        ? "bg-amber-400"
        : tone === "danger"
          ? "bg-red-400"
          : "bg-primary";
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-none bg-secondary/80", className)}>
      <div className={cn("h-full rounded-none transition-all duration-500", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function CockpitChip({
  children,
  active,
  onClick,
}: {
  children: ReactNode;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-sm border px-3 py-1.5 text-2xs font-medium uppercase tracking-[0.12em] transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground shadow-elev-1"
          : "border-border bg-card text-muted-foreground hover:border-border-strong hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

export function AskAgentBar({
  lang,
  value,
  onChange,
  onSubmit,
  pending,
  placeholder,
}: {
  lang: string;
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  pending?: boolean;
  placeholder?: string;
}) {
  return (
    <form
      className="relative overflow-hidden rounded-sm border border-border bg-card p-4 shadow-elev-1"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <div className="absolute left-0 top-0 h-full w-1 bg-ai" />
      <div className="flex flex-col gap-3 pl-2 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 animate-pulse bg-ai" />
            <div className="text-2xs font-semibold uppercase tracking-[0.16em] text-ai">
              {localize(lang, "Сказать агенту", "Ask the agent")}
            </div>
          </div>
          <input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={
              placeholder ||
              localize(
                lang,
                "Разбери 502 на nginx в prod-web, предложи restart с проверкой…",
                "Investigate nginx 502 on prod-web, suggest restart with verify…",
              )
            }
            className="h-11 w-full rounded-sm border border-border bg-surface-0 px-3 font-mono text-sm text-foreground outline-none ring-primary/40 placeholder:text-muted-foreground focus:ring-2"
          />
        </div>
        <button
          type="submit"
          disabled={pending || !value.trim()}
          className="h-11 shrink-0 rounded-sm bg-primary px-5 text-xs font-semibold uppercase tracking-wide text-primary-foreground shadow-elev-1 transition hover:translate-x-px hover:translate-y-px disabled:opacity-50"
        >
          {pending
            ? localize(lang, "Создаю…", "Creating…")
            : localize(lang, "Диагностика", "Diagnose")}
        </button>
      </div>
    </form>
  );
}

export function QuickLinkTile({
  title,
  description,
  href,
  icon,
}: {
  title: string;
  description: string;
  href: string;
  icon: ReactNode;
}) {
  return (
    <a
      href={href}
      className="group flex min-h-[92px] flex-col justify-between rounded-sm border border-border bg-surface-0 p-3 shadow-elev-1 transition hover:border-primary hover:bg-primary/5"
    >
      <div className="flex items-center gap-2 text-muted-foreground group-hover:text-primary">
        {icon}
        <span className="font-display text-sm font-semibold text-foreground">{title}</span>
      </div>
      <p className="mt-2 text-2xs leading-snug text-muted-foreground">{description}</p>
    </a>
  );
}

export function KpiTile({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "success" | "warning" | "danger" | "info";
}) {
  const barTone =
    tone === "success" || tone === "warning" || tone === "danger" ? tone : "default";
  return (
    <div className="rounded-sm border border-border bg-surface-0 p-3 shadow-elev-1">
      <div className="text-2xs uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
      <div className="mt-1 font-display text-3xl font-semibold tabular-nums tracking-tight text-foreground">
        {value}
      </div>
      {hint ? <div className="mt-1 text-2xs text-muted-foreground">{hint}</div> : null}
      <div className="mt-3">
        <MiniBar value={typeof value === "number" ? value : 1} max={Math.max(typeof value === "number" ? value : 1, 8)} tone={barTone} />
      </div>
    </div>
  );
}

export function countHealth(items: Array<{ health?: string }>) {
  const buckets = { healthy: 0, warning: 0, degraded: 0, unknown: 0 };
  for (const item of items) {
    const h = String(item.health || "unknown");
    if (h === "healthy") buckets.healthy += 1;
    else if (h === "warning") buckets.warning += 1;
    else if (h === "degraded") buckets.degraded += 1;
    else buckets.unknown += 1;
  }
  return buckets;
}

export function WorkloadReadyBar({ ready, desired }: { ready: number; desired: number }) {
  const max = Math.max(desired, 1);
  const tone = ready >= desired ? "success" : ready === 0 ? "danger" : "warning";
  return (
    <div className="space-y-1">
      <div className="flex justify-between font-mono text-2xs text-muted-foreground">
        <span>
          {ready}/{desired}
        </span>
        <span>{Math.round((ready / max) * 100)}%</span>
      </div>
      <MiniBar value={ready} max={max} tone={tone} />
    </div>
  );
}
