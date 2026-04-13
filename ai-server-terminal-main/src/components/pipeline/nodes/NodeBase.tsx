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
  if (status === "running") return <Loader2 className="h-3 w-3 animate-spin text-blue-500" />;
  if (status === "awaiting_approval") return <Clock className="h-3 w-3 text-amber-500 animate-pulse" />;
  if (status === "awaiting_operator_reply") return <Clock className="h-3 w-3 text-cyan-500 animate-pulse" />;
  if (status === "completed") return <CheckCircle2 className="h-3 w-3 text-green-500" />;
  if (status === "failed") return <XCircle className="h-3 w-3 text-red-500" />;
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
          ...(hasSourceTrue ? [{ id: "true", label: "TRUE", className: "!bg-green-500/70 hover:!bg-green-500" }] : []),
          ...(hasSourceFalse ? [{ id: "false", label: "FALSE", className: "!bg-red-500/70 hover:!bg-red-500" }] : []),
        ]
      : hasSource
        ? [{ id: "out" }]
        : [];
  return (
    <div
      className={cn(
        "min-w-[200px] max-w-[280px] rounded-2xl border bg-card/95 shadow-sm transition-all backdrop-blur overflow-hidden",
        "relative",
        selected ? "border-primary shadow-lg shadow-primary/10 ring-1 ring-primary/20" : accentColor,
        status === "running" && "border-blue-500/60",
        status === "awaiting_approval" && "border-amber-500/70 bg-amber-500/5",
        status === "awaiting_operator_reply" && "border-cyan-500/70 bg-cyan-500/5",
        status === "completed" && "border-green-500/60",
        status === "failed" && "border-red-500/60",
        isInActivePath && !status && "border-sky-500/40 bg-sky-500/5",
        isQueuedStep && "ring-2 ring-cyan-500/30",
        isEntryPoint && "ring-2 ring-emerald-500/30",
        isCurrentStep && "ring-2 ring-blue-500/50 shadow-[0_0_28px_rgba(59,130,246,0.22)]",
      )}
    >
      {categoryColor && <div className="absolute left-0 top-0 bottom-0 w-1" style={{ backgroundColor: categoryColor }} />}
      
      {hasTarget && (
        <Handle
          type="target"
          position={Position.Top}
          className="!w-4 !h-4 !bg-muted-foreground/50 !border-2 !border-background hover:!bg-primary hover:!scale-125 transition-all"
        />
      )}

      <div className="px-3.5 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-border/70 bg-background/70 text-base">
            {icon}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-[12px] font-semibold text-foreground truncate">{label}</span>
              {status && <StatusIcon status={status} />}
            </div>
            {description && (
              <span className="mt-0.5 block text-[10px] leading-4 text-muted-foreground line-clamp-2">{description}</span>
            )}
            {statusLabel && (
              <div className="mt-1.5">
                <span className="rounded-full border border-border/70 bg-background/60 px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">
                  {statusLabel}
                </span>
              </div>
            )}
          </div>
        </div>
        {children && <div className="mt-2.5 space-y-1.5">{children}</div>}
      </div>

      {resolvedSourcePorts.map((port, index) => {
        const spacing = 100 / (resolvedSourcePorts.length + 1);
        const left = `${spacing * (index + 1)}%`;
        return (
          <div key={`${port.id || "out"}-${index}`}>
            <Handle
              type="source"
              position={Position.Bottom}
              id={port.id}
              style={{ left, ...(port.style || {}) }}
              className={cn(
                "!w-4 !h-4 !bg-muted-foreground/50 !border-2 !border-background transition-all hover:!bg-primary hover:!scale-125",
                port.className,
              )}
            />
            {port.label ? (
              <span
                className={cn(
                  "pointer-events-none absolute -bottom-5 text-[9px] font-medium text-muted-foreground",
                  port.labelClassName,
                )}
                style={{ left, transform: "translateX(-50%)" }}
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
