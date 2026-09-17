import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

const widthClasses = {
  /** Form-oriented pages — centered readable column. */
  default: "mx-auto max-w-[56rem]",
  /** Dense admin grids (limits, CLI connections, readiness). */
  wide: "mx-auto max-w-[64rem]",
  /** Appearance / full-bleed pickers. */
  full: "max-w-none",
} as const;

/** Shared content column rhythm for every settings tab. */
export function SettingsPageShell({
  children,
  className,
  width = "default",
  slot = "settings-page",
}: {
  children: ReactNode;
  className?: string;
  width?: keyof typeof widthClasses;
  slot?: string;
}) {
  return (
    <div
      data-ui-slot={slot}
      className={cn("w-full space-y-5 pb-10", widthClasses[width], className)}
    >
      {children}
    </div>
  );
}

/** Consistent primary-action row inside a settings section. */
export function SettingsSectionActions({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      data-ui-slot="settings-section-actions"
      className={cn(
        "flex flex-wrap items-center justify-end gap-2 border-t border-border/70 pt-4",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Label + control stack used across settings forms. */
export function SettingsField({
  label,
  htmlFor,
  hint,
  children,
  className,
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div data-ui-slot="settings-field" className={cn("min-w-0 space-y-1.5", className)}>
      <label
        htmlFor={htmlFor}
        className="block text-sm font-medium text-muted-foreground"
      >
        {label}
      </label>
      {children}
      {hint ? <p className="text-sm leading-6 text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
