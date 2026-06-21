import { AlertTriangle, CheckCircle2, Circle, Info, Loader2, Sparkles, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import { statusToneClasses, type StatusTone } from "@/design/status";
import { cn } from "@/lib/utils";

const toneIcon = {
  neutral: Circle,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
  info: Info,
  ai: Sparkles,
} satisfies Record<StatusTone, typeof Circle>;

export function StatusBadge({
  label,
  tone = "neutral",
  pulse = false,
  className,
}: {
  label: ReactNode;
  tone?: StatusTone;
  pulse?: boolean;
  className?: string;
}) {
  const Icon = pulse ? Loader2 : toneIcon[tone];
  const styles = statusToneClasses[tone];

  return (
    <span
      className={cn(
        "inline-flex min-h-7 items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium leading-4",
        styles.badge,
        className,
      )}
    >
      <Icon className={cn("h-3.5 w-3.5", pulse && "animate-spin", styles.icon)} aria-hidden />
      {label}
    </span>
  );
}
