import { type ReactNode } from "react";
import { Handle, Position } from "@xyflow/react";
import { CheckCircle2, XCircle, Loader2, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

interface NodeBaseProps {
  selected?: boolean;
  label: string;
  icon: string;
  description?: string;
  status?: string;
  hasSource?: boolean;
  hasTarget?: boolean;
  hasSourceTrue?: boolean;
  hasSourceFalse?: boolean;
  accentColor?: string;
  children?: ReactNode;
}

function StatusIcon({ status }: { status: string }) {
  if (status === "running") return <Loader2 className="h-3 w-3 animate-spin text-blue-500" />;
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
  hasSource = true,
  hasTarget = true,
  hasSourceTrue,
  hasSourceFalse,
  accentColor = "border-border",
  children,
}: NodeBaseProps) {
  return (
    <div
      className={cn(
        "min-w-[200px] max-w-[280px] rounded-2xl border bg-card/95 shadow-sm transition-all backdrop-blur",
        selected ? "border-primary shadow-lg shadow-primary/10 ring-1 ring-primary/20" : accentColor,
        status === "running" && "border-blue-500/60",
        status === "completed" && "border-green-500/60",
        status === "failed" && "border-red-500/60",
      )}
    >
      {hasTarget && (
        <Handle
          type="target"
          position={Position.Top}
          className="!w-3 !h-3 !bg-muted-foreground/50 !border-2 !border-background hover:!bg-primary transition-colors"
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
          </div>
        </div>
        {children && <div className="mt-2.5 space-y-1.5">{children}</div>}
      </div>

      {hasSourceTrue && (
        <Handle
          type="source"
          position={Position.Bottom}
          id="true"
          style={{ left: "35%" }}
          className="!w-3 !h-3 !bg-green-500/70 !border-2 !border-background hover:!bg-green-500 transition-colors"
        />
      )}
      {hasSourceFalse && (
        <Handle
          type="source"
          position={Position.Bottom}
          id="false"
          style={{ left: "65%" }}
          className="!w-3 !h-3 !bg-red-500/70 !border-2 !border-background hover:!bg-red-500 transition-colors"
        />
      )}
      {hasSource && !hasSourceTrue && !hasSourceFalse && (
        <Handle
          type="source"
          position={Position.Bottom}
          className="!w-3 !h-3 !bg-muted-foreground/50 !border-2 !border-background hover:!bg-primary transition-colors"
        />
      )}
    </div>
  );
}
