import { cn } from "@/lib/utils";
import { severityMeta, type Severity } from "@/lib/severity";

interface SeverityBadgeProps {
  severity: Severity;
  /** override label */
  label?: string;
  variant?: "solid" | "soft";
  size?: "sm" | "md";
  showIcon?: boolean;
  className?: string;
}

export function SeverityBadge({
  severity,
  label,
  variant = "soft",
  size = "sm",
  showIcon = true,
  className,
}: SeverityBadgeProps) {
  const meta = severityMeta[severity];
  const Icon = meta.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border font-medium leading-none",
        size === "sm" ? "px-2 py-1 text-xs" : "px-2.5 py-1.5 text-sm",
        variant === "solid" ? meta.badge : meta.chip,
        className,
      )}
    >
      {showIcon && <Icon className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} />}
      {label ?? meta.label}
    </span>
  );
}
