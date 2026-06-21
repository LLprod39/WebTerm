import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import type { StatusTone } from "@/design/status";
import { statusToneClasses } from "@/design/status";
import { cn } from "@/lib/utils";

const icons = {
  neutral: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
  info: Info,
  ai: Info,
} satisfies Record<StatusTone, typeof Info>;

export function InlineAlert({
  title,
  description,
  tone = "info",
  className,
}: {
  title?: ReactNode;
  description: ReactNode;
  tone?: StatusTone;
  className?: string;
}) {
  const Icon = icons[tone];
  const styles = statusToneClasses[tone];

  return (
    <div className={cn("rounded-lg border px-4 py-3", styles.badge, className)}>
      <div className="flex items-start gap-3">
        <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", styles.icon)} aria-hidden />
        <div className="min-w-0 space-y-0.5">
          {title ? <div className="text-sm font-semibold leading-5 text-foreground">{title}</div> : null}
          <div className="text-sm leading-5">{description}</div>
        </div>
      </div>
    </div>
  );
}
