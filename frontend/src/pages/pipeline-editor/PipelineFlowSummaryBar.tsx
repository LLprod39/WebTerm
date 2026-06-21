import { useMemo, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import type { PipelineEdge, PipelineNode } from "@/lib/api";
import type { PipelineRunGraphState } from "@/components/pipeline/pipelineRunGraph";
import { cn } from "@/lib/utils";

import {
  NODE_TYPE_LOOKUP,
  getNodePhaseBadgeClass,
  getNodePhaseLabel,
  localize,
} from "./presentation";
import { getNodeDisplayLabel } from "./pipelineGraphUtils";

type PipelineFlowSummaryBarProps = {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  graphState: PipelineRunGraphState;
  selectedNodeId: string | null;
  collapsed?: boolean;
  lang: "en" | "ru";
  onCollapsedChange?: (collapsed: boolean) => void;
  onSelectNode: (node: PipelineNode) => void;
};

function buildVisibleFlowChain(nodes: PipelineNode[], edges: PipelineEdge[]) {
  const visited = new Set<string>();
  const chain: PipelineNode[] = [];
  const triggers = nodes.filter((node) => node.type?.startsWith("trigger/"));
  const queue = triggers.length ? [...triggers] : nodes.slice(0, 1);

  while (queue.length && chain.length < 12) {
    const current = queue.shift()!;
    if (visited.has(current.id)) continue;
    visited.add(current.id);
    chain.push(current);

    const downstream = edges
      .filter((edge) => edge.source === current.id)
      .map((edge) => nodes.find((node) => node.id === edge.target))
      .filter(Boolean) as PipelineNode[];
    queue.push(...downstream);
  }

  nodes.forEach((node) => {
    if (!visited.has(node.id) && chain.length < 15) {
      chain.push(node);
    }
  });

  return chain;
}

export function PipelineFlowSummaryBar({
  nodes,
  edges,
  graphState,
  selectedNodeId,
  collapsed = false,
  lang,
  onCollapsedChange,
  onSelectNode,
}: PipelineFlowSummaryBarProps) {
  const chain = useMemo(() => buildVisibleFlowChain(nodes, edges), [edges, nodes]);
  const visibleChain = chain.slice(0, 6);
  const hiddenCount = Math.max(0, chain.length - visibleChain.length);
  const items: ReactNode[] = [];
  let previousPhase = "";

  if (!nodes.length) {
    return null;
  }

  if (collapsed) {
    return (
      <div className="flex items-center gap-2 border-b border-border/80 bg-card/50 px-4 py-2">
        <button
          type="button"
          className="inline-flex min-h-8 items-center gap-2 rounded-lg border border-border/70 bg-background/55 px-3 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground"
          onClick={() => onCollapsedChange?.(false)}
        >
          <ChevronRight className="h-3.5 w-3.5" />
          {localize(lang, "Показать flow", "Show flow")}
        </button>
        <span className="text-xs text-muted-foreground">
          {nodes.length} {localize(lang, "нод", "nodes")} / {edges.length} {localize(lang, "связей", "edges")}
        </span>
      </div>
    );
  }

  visibleChain.forEach((node, index) => {
    const phaseLabel = getNodePhaseLabel(node.type, lang);
    const meta = NODE_TYPE_LOOKUP[node.type || ""];
    const StepIcon = meta?.icon;

    if (phaseLabel !== previousPhase) {
      items.push(
        <span
          key={`${node.id}-phase`}
          className={cn(
            "ml-1 inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-xs font-semibold uppercase tracking-wide",
            getNodePhaseBadgeClass(node.type),
          )}
        >
          {phaseLabel}
        </span>,
      );
      previousPhase = phaseLabel;
    }

    items.push(
      <span key={node.id} className="flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          onClick={() => onSelectNode(node)}
          className={cn(
            "inline-flex min-h-8 max-w-[190px] items-center gap-1.5 rounded-lg border px-2 py-1 text-xs transition-colors",
            graphState.currentNodeId === node.id
              ? "border-blue-500/40 bg-blue-500/10 text-blue-200 shadow-[0_0_16px_rgba(59,130,246,0.18)]"
              : graphState.traversedNodeIds.has(node.id)
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                : graphState.queuedNodeIds.has(node.id)
                  ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-200"
                  : selectedNodeId === node.id
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "border-border/60 bg-background/60 text-muted-foreground hover:border-border hover:bg-muted/40 hover:text-foreground",
          )}
        >
          {StepIcon ? (
            <StepIcon className={`h-3.5 w-3.5 shrink-0 ${meta.iconClassName || "text-foreground"}`} />
          ) : null}
          <span className="truncate">{getNodeDisplayLabel(node, lang)}</span>
        </button>
        {index < visibleChain.length - 1 ? <ChevronRight className="h-2.5 w-2.5 text-muted-foreground/40" /> : null}
      </span>,
    );
  });

  if (hiddenCount > 0) {
    items.push(
      <span
        key="flow-overflow"
        className="inline-flex shrink-0 items-center rounded-full border border-border/70 bg-background/60 px-2 py-0.5 text-xs text-muted-foreground"
      >
        +{hiddenCount} {localize(lang, "этапов", "more")}
      </span>,
    );
  }

  return (
    <div className="flex items-center gap-2 overflow-x-auto border-b border-border/80 bg-card/50 px-4 py-2">
      <button
        type="button"
        className="mr-1 inline-flex min-h-8 shrink-0 items-center gap-1.5 rounded-lg border border-border/70 bg-background/55 px-2.5 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground"
        onClick={() => onCollapsedChange?.(true)}
      >
        <ChevronDown className="h-3.5 w-3.5" />
        {localize(lang, "Flow", "Flow")}
      </button>
      {items}
    </div>
  );
}
