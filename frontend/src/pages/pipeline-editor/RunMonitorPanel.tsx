import { useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Clock,
  Loader2,
  Square,
  X,
  XCircle,
} from "lucide-react";

import { studioRuns, type PipelineNode } from "@/lib/api";

const NODE_STATUS_ICON: Record<string, ReactNode> = {
  running: <Loader2 className="h-3 w-3 animate-spin text-blue-400" />,
  awaiting_approval: <Clock className="h-3 w-3 text-yellow-400 animate-pulse" />,
  awaiting_operator_reply: <Clock className="h-3 w-3 text-cyan-400 animate-pulse" />,
  completed: <CheckCircle2 className="h-3 w-3 text-green-400" />,
  failed: <XCircle className="h-3 w-3 text-red-400" />,
  pending: <Clock className="h-3 w-3 text-muted-foreground" />,
  skipped: <ChevronRight className="h-3 w-3 text-muted-foreground" />,
};

export function RunMonitorPanel({
  runId,
  onClose,
}: {
  runId: number;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const [expandedNode, setExpandedNode] = useState<string | null>(null);

  const { data: run } = useQuery({
    queryKey: ["studio", "run", runId],
    queryFn: () => studioRuns.get(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" || status === "pending" ? 2000 : false;
    },
    refetchIntervalInBackground: true,
  });

  const stopMutation = useMutation({
    mutationFn: () => studioRuns.stop(runId),
  });

  const isActive = run?.status === "running" || run?.status === "pending";

  const statusColor: Record<string, string> = {
    completed: "text-green-400",
    failed: "text-red-400",
    running: "text-blue-400",
    pending: "text-muted-foreground",
    stopped: "text-yellow-400",
  };

  const nodeStates = run?.node_states || {};

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          {isActive
            ? <Loader2 className="h-4 w-4 animate-spin text-blue-400" />
            : run?.status === "completed"
              ? <CheckCircle2 className="h-4 w-4 text-green-400" />
              : run?.status === "failed"
                ? <XCircle className="h-4 w-4 text-red-400" />
                : <Clock className="h-4 w-4 text-muted-foreground" />
          }
          <span className="text-sm font-semibold">Run #{runId}</span>
          <span className={`text-xs font-medium ${statusColor[run?.status || ""] || ""}`}>
            {run?.status || "loading..."}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {isActive && (
            <button
              className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1 px-2 py-1 rounded hover:bg-muted/40"
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending}
            >
              <Square className="h-3 w-3" /> Stop
            </button>
          )}
          <button
            className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 px-2 py-1 rounded hover:bg-muted/40"
            onClick={() => navigate("/studio/runs")}
            title="Все логи"
          >
            <ChevronRight className="h-3 w-3" /> Логи
          </button>
          <button className="p-1 rounded hover:bg-muted/40 text-muted-foreground hover:text-foreground" onClick={onClose}>
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-3 space-y-2 text-xs">
        {run?.error && (
          <div className="rounded bg-red-900/20 border border-red-500/30 px-3 py-2 text-red-300">
            <strong>Error:</strong> {run.error}
          </div>
        )}

        {run?.summary && (
          <div className="rounded bg-muted/30 border border-border px-3 py-2 text-muted-foreground whitespace-pre-wrap max-h-40 overflow-auto">
            {run.summary}
          </div>
        )}

        {run?.nodes_snapshot && (run.nodes_snapshot as PipelineNode[]).filter((n) => !n.type?.startsWith("trigger/")).map((node) => {
          const state = nodeStates[node.id];
          const stateExtra: Record<string, unknown> = (state as (typeof state & Record<string, unknown>) | undefined) || {};
          const status = state?.status || "pending";
          const output = state?.output || "";
          const error = state?.error || "";
          const isExpanded = expandedNode === node.id;
          const hasContent = output || error;

          return (
            <div key={node.id} className="rounded border border-border bg-card/50">
              <button
                className="w-full flex items-center gap-2 px-3 py-2 text-left"
                onClick={() => hasContent && setExpandedNode(isExpanded ? null : node.id)}
              >
                <span className="shrink-0">{NODE_STATUS_ICON[status] || NODE_STATUS_ICON.pending}</span>
                <span className="flex-1 truncate font-medium">{(node.data?.label as string) || node.id}</span>
                <span className="text-muted-foreground text-[10px] shrink-0">{node.type}</span>
                {hasContent && (
                  isExpanded
                    ? <ChevronUp className="h-3 w-3 text-muted-foreground shrink-0" />
                    : <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
                )}
              </button>

              {status === "awaiting_approval" && (
                <div className="border-t border-border px-3 py-2 space-y-2">
                  <p className="text-yellow-400 text-[11px] font-medium">Waiting for your decision...</p>
                  {typeof stateExtra.approve_url === "string" && (
                    <div className="flex gap-2">
                      <a
                        href={stateExtra.approve_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 text-center text-xs py-1.5 rounded bg-green-800/40 border border-green-600/40 text-green-300 hover:bg-green-700/50 transition-colors"
                      >
                        Approve
                      </a>
                      <a
                        href={typeof stateExtra.reject_url === "string" ? stateExtra.reject_url : "#"}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 text-center text-xs py-1.5 rounded bg-red-900/30 border border-red-600/40 text-red-300 hover:bg-red-800/40 transition-colors"
                      >
                        Reject
                      </a>
                    </div>
                  )}
                </div>
              )}

              {isExpanded && hasContent && status !== "awaiting_approval" && (
                <div className="border-t border-border px-3 py-2 space-y-1">
                  {error && (
                    <div className="text-red-300 bg-red-900/20 rounded px-2 py-1">{error}</div>
                  )}
                  {output && (
                    <pre className="text-muted-foreground whitespace-pre-wrap break-all max-h-48 overflow-auto leading-relaxed">
                      {output.length > 2000 ? output.slice(0, 2000) + "\n…[truncated]" : output}
                    </pre>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {!run && (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading…
          </div>
        )}
      </div>
    </div>
  );
}
