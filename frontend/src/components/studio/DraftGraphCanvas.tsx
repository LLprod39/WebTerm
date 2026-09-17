import { useEffect, useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AlertTriangle, GitBranch, Loader2 } from "lucide-react";

import {
  AgentNode,
  ConditionNode,
  EmailNode,
  HumanApprovalNode,
  LLMQueryNode,
  MCPCallNode,
  MergeNode,
  OutputNode,
  ParallelNode,
  SSHCommandNode,
  TelegramInputNode,
  TelegramNode,
  TriggerNode,
  WaitNode,
} from "@/components/pipeline/nodes";
import { buildDraftCanvasModel, responseFromDraftSession } from "@/components/studio/draftGraphModel";
import { localize } from "@/lib/i18n";
import type {
  PipelineEdge,
  PipelineNode,
} from "@/lib/api";
import type { StudioPipelineAssistantResponse, StudioPipelineDraftSession } from "@/lib/studioPipelineDraftsApi";

const draftNodeTypes = {
  "trigger/manual": TriggerNode,
  "trigger/webhook": TriggerNode,
  "trigger/schedule": TriggerNode,
  "trigger/monitoring": TriggerNode,
  "agent/react": AgentNode,
  "agent/multi": AgentNode,
  "agent/ssh_cmd": SSHCommandNode,
  "agent/llm_query": LLMQueryNode,
  "agent/mcp_call": MCPCallNode,
  "logic/condition": ConditionNode,
  "logic/parallel": ParallelNode,
  "logic/merge": MergeNode,
  "logic/wait": WaitNode,
  "logic/human_approval": HumanApprovalNode,
  "logic/telegram_input": TelegramInputNode,
  "output/report": OutputNode,
  "output/webhook": OutputNode,
  "output/email": EmailNode,
  "output/telegram": TelegramNode,
};

function decorateNodes(nodes: PipelineNode[], response: StudioPipelineAssistantResponse | null, lang: string): Node[] {
  const riskNodeIds = new Set((response?.risk?.items || []).map((item) => item.node_id).filter(Boolean));
  return nodes.map((node, index) => ({
    ...node,
    draggable: false,
    selectable: true,
    data: {
      ...(node.data || {}),
      status_label: riskNodeIds.has(node.id) ? localize(lang, "Проверка риска", "Risk review") : localize(lang, "Черновик", "Draft"),
      is_entry_point: index === 0 || node.type.startsWith("trigger/"),
    },
  }));
}

function decorateEdges(edges: PipelineEdge[]): Edge[] {
  return edges.map((edge) => ({
    ...edge,
    animated: true,
    style: {
      strokeWidth: 2,
      stroke: "hsl(var(--primary) / 0.55)",
      opacity: 0.76,
    },
    labelStyle: {
      fontSize: 10,
      fill: "hsl(var(--muted-foreground))",
    },
    labelBgStyle: {
      fill: "hsl(var(--background))",
      fillOpacity: 0.82,
    },
  }));
}

function DraftGraphCanvasInner({
  session,
  lang,
  loading = false,
}: {
  session: StudioPipelineDraftSession | null;
  lang: string;
  loading?: boolean;
}) {
  const { fitView } = useReactFlow();
  const response = responseFromDraftSession(session);
  const model = useMemo(() => buildDraftCanvasModel(session), [session]);
  const nodes = useMemo(() => decorateNodes(model.nodes, response, lang), [model.nodes, response, lang]);
  const edges = useMemo(() => decorateEdges(model.edges), [model.edges]);
  const hasGraph = nodes.length > 0 || edges.length > 0;

  useEffect(() => {
    if (!hasGraph) return;
    const frame = window.requestAnimationFrame(() => {
      fitView({ padding: 0.28, duration: 0, includeHiddenNodes: false });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [fitView, hasGraph, nodes.length, edges.length]);

  if (loading) {
    return (
      <div className="flex h-full min-h-[440px] items-center justify-center bg-background/35 text-sm text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        {localize(lang, "Загружаю граф черновика...", "Loading draft graph...")}
      </div>
    );
  }

  return (
    <div className="relative h-full min-h-[440px] overflow-hidden bg-background">
      {hasGraph ? (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={draftNodeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          fitView
          fitViewOptions={{ padding: 0.28, includeHiddenNodes: false }}
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{
            animated: true,
            style: { strokeWidth: 2 },
          }}
        >
          <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="hsl(var(--border))" />
          <Controls className="!border-border !bg-card [&>button]:!border-border [&>button]:!bg-card [&>button]:!text-foreground [&>button:hover]:!bg-secondary" />
          {nodes.length >= 6 ? (
            <MiniMap
              style={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }}
              maskColor="hsl(var(--background) / 0.72)"
              nodeColor={(node) => {
                const type = node.type || "";
                if (type.startsWith("trigger/")) return "hsl(var(--warning))";
                if (type.startsWith("agent/")) return "hsl(var(--ai))";
                if (type.startsWith("logic/")) return "hsl(var(--info))";
                if (type.startsWith("output/")) return "hsl(var(--success))";
                return "hsl(var(--muted-foreground))";
              }}
            />
          ) : null}
          <Panel position="top-left">
            <div className="flex items-center gap-2 rounded-sm border border-border bg-card px-3 py-2 text-xs text-muted-foreground shadow-elev-1">
              <GitBranch className="h-3.5 w-3.5 text-primary" />
              <span>{model.source === "preview" ? localize(lang, "Предпросмотр графа", "Preview graph") : localize(lang, "Граф правки", "Patch graph")}</span>
              <span className="rounded border border-border/70 px-1.5 py-0.5">{nodes.length} {localize(lang, "нод", "nodes")}</span>
              <span className="rounded border border-border/70 px-1.5 py-0.5">{edges.length} {localize(lang, "связей", "edges")}</span>
            </div>
          </Panel>
          {response?.risk?.items?.length ? (
            <Panel position="top-right">
              <div className="flex items-center gap-2 rounded-sm border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning shadow-elev-1">
                <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
                {localize(lang, "Проверка риска", "Risk review")}
              </div>
            </Panel>
          ) : null}
        </ReactFlow>
      ) : (
        <div className="flex h-full min-h-[440px] items-center justify-center px-6">
          <div className="max-w-sm rounded-sm border border-dashed border-border bg-card p-6 text-center">
            <h3 className="text-sm font-semibold text-foreground">
              {localize(lang, "Граф появится после черновика", "Graph appears after a draft")}
            </h3>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              {localize(
                lang,
                "Опишите задачу справа — здесь появится проверяемый граф.",
                "Describe the task on the right — a verifiable graph will appear here.",
              )}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export function DraftGraphCanvas(props: {
  session: StudioPipelineDraftSession | null;
  lang: string;
  loading?: boolean;
}) {
  return (
    <ReactFlowProvider>
      <DraftGraphCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
