import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { useMutation } from "@tanstack/react-query";
import type { Edge, Node } from "@xyflow/react";
import { applyAssistantGraphPatch } from "@/components/pipeline/assistantPatch";
import type { PipelineEdge, PipelineNode, PipelineRun } from "@/lib/api";
import { studioPipelines } from "@/lib/api";
import type { StudioPipelineAssistantResponse } from "@/lib/studioPipelineDraftsApi";
import { localize } from "./presentation";
import { normaliseAssistantPatch } from "./pipelineGraphUtils";

type AssistantIntent = "create" | "edit" | "validate" | "fix_run";
type AssistantHistoryItem = { role: "user" | "assistant"; content: string };

export function usePipelineAssistantDraft({
  clearGraphOverlay,
  fitView,
  graphRunLive,
  lang,
  nodeIdCounter,
  nodes,
  edges,
  pipelineFallbackName,
  pipelineId,
  pipelineName,
  saveAppliedGraph,
  selectedNode,
  setActiveRunId,
  setEdges,
  setHasLocalChanges,
  setNodes,
  setSelectedNode,
  toast,
}: {
  clearGraphOverlay: () => void;
  fitView: (options: { padding: number; duration: number }) => void;
  graphRunLive: PipelineRun | null;
  lang: "en" | "ru";
  nodeIdCounter: { current: number };
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  pipelineFallbackName?: string;
  pipelineId: number | null;
  pipelineName: string;
  saveAppliedGraph: (data: { name: string; nodes: PipelineNode[]; edges: PipelineEdge[] }) => void;
  selectedNode: PipelineNode | null;
  setActiveRunId: Dispatch<SetStateAction<number | null>>;
  setEdges: Dispatch<SetStateAction<Edge[]>>;
  setHasLocalChanges: Dispatch<SetStateAction<boolean>>;
  setNodes: Dispatch<SetStateAction<Node[]>>;
  setSelectedNode: Dispatch<SetStateAction<PipelineNode | null>>;
  toast: (options: { description: string; variant?: "destructive" }) => void;
}) {
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantInput, setAssistantInput] = useState("");
  const [assistantHistory, setAssistantHistory] = useState<AssistantHistoryItem[]>([]);
  const [assistantProposal, setAssistantProposal] = useState<StudioPipelineAssistantResponse | null>(null);

  useEffect(() => {
    setAssistantInput("");
    setAssistantHistory([]);
    setAssistantProposal(null);
  }, [pipelineId]);

  const assistantMutation = useMutation({
    mutationFn: ({
      intent,
      message,
      history,
    }: {
      intent: AssistantIntent;
      message: string;
      history: AssistantHistoryItem[];
    }) =>
      studioPipelines.assistant({
        pipeline_id: pipelineId,
        pipeline_name: pipelineName || pipelineFallbackName || "Untitled",
        nodes,
        edges,
        selected_node: selectedNode,
        user_message: message,
        intent,
        draft_mode: true,
        history,
        last_validation_errors: assistantProposal?.validation?.errors || [],
        last_run_summary: graphRunLive
          ? {
              id: graphRunLive.id,
              status: graphRunLive.status,
              error: graphRunLive.error,
              summary: graphRunLive.summary,
              node_states: graphRunLive.node_states,
            }
          : {},
      }),
    onSuccess: (response, variables) => {
      setAssistantProposal(response);
      setAssistantHistory((current) => [
        ...current,
        { role: "user" as const, content: variables.message },
        { role: "assistant" as const, content: response.reply || response.patch_summary || "Draft ready." },
      ].slice(-12));
      toast({ description: response.validation?.ok === false ? "Draft needs fixes before apply." : "Draft is ready for review." });
    },
    onError: (err: Error) => toast({ variant: "destructive", description: err.message }),
  });

  const handleAssistantSend = useCallback(
    (intent: AssistantIntent, messageOverride?: string) => {
      const message = (messageOverride || assistantInput).trim();
      if (!message) return;
      setAssistantOpen(true);
      const resolvedIntent = intent === "edit" && !nodes.length ? "create" : intent;
      assistantMutation.mutate({
        intent: resolvedIntent,
        message,
        history: assistantHistory.slice(-10),
      });
      if (!messageOverride) {
        setAssistantInput("");
      }
    },
    [assistantHistory, assistantInput, assistantMutation, nodes.length],
  );

  const applyAssistantProposal = useCallback(
    (saveAfterApply: boolean) => {
      if (!assistantProposal) return;
      if (assistantProposal.validation?.ok === false) {
        toast({ variant: "destructive", description: "Fix validation errors before applying this draft." });
        return;
      }
      if (assistantProposal.risk?.level === "dangerous") {
        toast({
          variant: "destructive",
          description: localize(
            lang,
            "В черновике есть опасная SSH-команда. Добавьте подтверждение или перепишите шаг безопасно.",
            "This draft contains a dangerous SSH command. Add approval or rewrite it safely.",
          ),
        });
        return;
      }

      const result = applyAssistantGraphPatch({
        nodes,
        edges,
        response: assistantProposal,
        normalizeNodeData: (data) => normaliseAssistantPatch(data, { mcpList: [] }),
      });
      setNodes(result.nodes as unknown as Node[]);
      setEdges(result.edges as unknown as Edge[]);
      setHasLocalChanges(true);
      clearGraphOverlay();
      setActiveRunId(null);

      const firstNewId = Object.values(result.refToNodeId)[0];
      const firstUpdatedId =
        assistantProposal.target_node_id ||
        assistantProposal.graph_patch.update_nodes?.[0]?.node_id ||
        null;
      const nextSelectedId = firstNewId || firstUpdatedId;
      setSelectedNode(nextSelectedId ? result.nodes.find((node) => node.id === nextSelectedId) || null : null);
      setAssistantProposal(null);

      const maxNumericNodeId = result.nodes.reduce((max, node) => {
        const num = parseInt(node.id.replace(/\D/g, "") || "0");
        return Math.max(max, num);
      }, 0);
      nodeIdCounter.current = Math.max(nodeIdCounter.current, maxNumericNodeId + 1);
      setTimeout(() => fitView({ padding: 0.22, duration: 250 }), 50);
      if (saveAfterApply) {
        saveAppliedGraph({
          name: pipelineName || pipelineFallbackName || "Untitled",
          nodes: result.nodes,
          edges: result.edges,
        });
        return;
      }
      toast({ description: localize(lang, "Черновик применён. Нажмите «Сохранить», чтобы записать изменения.", "Draft applied. Select Save to persist the changes.") });
    },
    [
      assistantProposal,
      clearGraphOverlay,
      edges,
      fitView,
      lang,
      nodeIdCounter,
      nodes,
      pipelineFallbackName,
      pipelineName,
      saveAppliedGraph,
      setActiveRunId,
      setEdges,
      setHasLocalChanges,
      setNodes,
      setSelectedNode,
      toast,
    ],
  );

  return {
    assistantHistory,
    assistantInput,
    assistantOpen,
    assistantPending: assistantMutation.isPending,
    assistantProposal,
    handleApplyAndSaveAssistantProposal: () => applyAssistantProposal(true),
    handleApplyAssistantProposal: () => applyAssistantProposal(false),
    handleAssistantSend,
    setAssistantInput,
    setAssistantOpen,
    setAssistantProposal,
  };
}
