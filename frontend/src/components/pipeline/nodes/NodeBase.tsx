import { type CSSProperties, type ReactNode } from "react";
import { Handle, Position } from "@xyflow/react";
import { CheckCircle2, XCircle, Loader2, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

export interface NodePort {
  id?: string;
  label?: string;
  className?: string;
  style?: CSSProperties;
  labelClassName?: string;
}

interface NodeBaseProps {
  selected?: boolean;
  label: string;
  icon: ReactNode;
  description?: string;
  status?: string;
  statusLabel?: string;
  isCurrentStep?: boolean;
  isInActivePath?: boolean;
  isQueuedStep?: boolean;
  isEntryPoint?: boolean;
  hasSource?: boolean;
  hasTarget?: boolean;
  hasSourceTrue?: boolean;
  hasSourceFalse?: boolean;
  sourcePorts?: NodePort[];
  accentColor?: string;
  categoryColor?: string;
  children?: ReactNode;
}

function StatusIcon({ status }: { status: string }) {
  if (status === "running") return <Loader2 className="h-3 w-3 animate-spin text-info" />;
  if (status === "awaiting_approval") return <Clock className="h-3 w-3 text-warning animate-pulse" />;
  if (status === "awaiting_operator_reply") return <Clock className="h-3 w-3 text-info animate-pulse" />;
  if (status === "completed") return <CheckCircle2 className="h-3 w-3 text-success" />;
  if (status === "failed") return <XCircle className="h-3 w-3 text-destructive" />;
  if (status === "pending") return <Clock className="h-3 w-3 text-muted-foreground" />;
  return null;
}

export function NodeBase({
  selected,
  label,
  icon,
  description,
  status,
  statusLabel,
  isCurrentStep = false,
  isInActivePath = false,
  isQueuedStep = false,
  isEntryPoint = false,
  hasSource = true,
  hasTarget = true,
  hasSourceTrue,
  hasSourceFalse,
  sourcePorts,
  accentColor = "border-border",
  categoryColor,
  children,
}: NodeBaseProps) {
  const resolvedSourcePorts: NodePort[] = sourcePorts?.length
    ? sourcePorts
    : hasSourceTrue || hasSourceFalse
      ? [
          ...(hasSourceTrue ? [{ id: "true", label: "TRUE", className: "!bg-success/70 hover:!bg-success" }] : []),
          ...(hasSourceFalse ? [{ id: "false", label: "FALSE", className: "!bg-destructive/70 hover:!bg-destructive" }] : []),
        ]
      : hasSource
        ? [{ id: "out" }]
        : [];
  const hasPortLabels = resolvedSourcePorts.some((port) => Boolean(port.label));
  return (
    <div
      className={cn(
        "relative min-h-[76px] w-[248px] max-w-[288px] overflow-hidden rounded-sm border bg-card shadow-elev-1 transition-[border-color,box-shadow]",
        selected ? "border-primary ring-1 ring-primary/20" : accentColor,
        status === "running" && "border-info/60",
        status === "awaiting_approval" && "border-warning/70 bg-warning/5",
        status === "awaiting_operator_reply" && "border-ai/70 bg-ai/5",
        status === "completed" && "border-success/60",
        status === "failed" && "border-destructive/60",
        isInActivePath && !status && "border-info/40 bg-info/5",
        isQueuedStep && "ring-2 ring-ai/30",
        isEntryPoint && "ring-2 ring-success/30",
        isCurrentStep && "ring-2 ring-info/50",
      )}
    >
      {categoryColor && <div className="absolute left-0 top-0 bottom-0 w-1" style={{ backgroundColor: categoryColor }} />}

      {hasTarget && (
        <Handle
          type="target"
          position={Position.Left}
          className="!w-3.5 !h-3.5 !bg-muted-foreground/50 !border-2 !border-background hover:!bg-primary hover:!scale-125 transition-all"
        />
      )}

      <div className={cn("px-3 py-3", hasPortLabels && "pr-12")}>
        <div className="flex items-start gap-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-border/80 bg-background text-base">
            {icon}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[12px] font-semibold leading-5 text-foreground truncate">{label}</span>
              {status && <StatusIcon status={status} />}
            </div>
            {description && (
              <span className="mt-1 block text-xs leading-4.5 text-foreground/75 line-clamp-2">{description}</span>
            )}
            {statusLabel && (
              <div className="mt-2">
                <span className="rounded-md border border-border/70 bg-background/60 px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
                  {statusLabel}
                </span>
              </div>
            )}
          </div>
        </div>
        {children && <div className="mt-2 space-y-1.5">{children}</div>}
      </div>

      {resolvedSourcePorts.map((port, index) => {
        const top = `${((index + 1) / (resolvedSourcePorts.length + 1)) * 100}%`;
        return (
          <div key={`${port.id || "out"}-${index}`}>
            <Handle
              type="source"
              position={Position.Right}
              id={port.id}
              style={{ top, ...(port.style || {}) }}
              className={cn(
                "!w-3.5 !h-3.5 !bg-muted-foreground/50 !border-2 !border-background transition-all hover:!bg-primary hover:!scale-125",
                port.className,
              )}
            />
            {port.label ? (
              <span
                className={cn(
                  "pointer-events-none absolute right-3 -translate-y-1/2 text-right text-xs font-medium text-muted-foreground",
                  port.labelClassName,
                )}
                style={{ top }}
              >
                {port.label}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
