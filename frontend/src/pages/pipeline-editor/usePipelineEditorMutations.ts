import type { Dispatch, SetStateAction } from "react";
import type { NavigateFunction } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { PipelineDetail, PipelineEdge, PipelineNode, PipelineRun } from "@/lib/api";
import { studioPipelines } from "@/lib/api";

import { localize } from "./presentation";
import { normalisePipelineGraph } from "./pipelineGraphUtils";

type ToastFn = (options: { variant?: "default" | "destructive"; description?: string }) => void;

export function usePipelineEditorMutations({
  lang,
  navigate,
  pipelineId,
  resetRunDialog,
  setActiveRunId,
  setEdges,
  setGraphRunId,
  setGraphRunLive,
  setHasHydratedPipeline,
  setHasLocalChanges,
  setLastRun,
  setNodes,
  setPipelineName,
  setSelectedNode,
  toast,
}: {
  lang: "en" | "ru";
  navigate: NavigateFunction;
  pipelineId: number | null;
  resetRunDialog: () => void;
  setActiveRunId: (runId: number | null) => void;
  setEdges: Dispatch<SetStateAction<never[]>>;
  setGraphRunId: (runId: number | null) => void;
  setGraphRunLive: (run: PipelineRun | null) => void;
  setHasHydratedPipeline: (value: boolean) => void;
  setHasLocalChanges: (value: boolean) => void;
  setLastRun: (run: PipelineRun | null) => void;
  setNodes: Dispatch<SetStateAction<never[]>>;
  setPipelineName: (name: string) => void;
  setSelectedNode: (node: PipelineNode | null) => void;
  toast: ToastFn;
}) {
  const queryClient = useQueryClient();

  const saveMutation = useMutation({
    mutationFn: (data: { nodes: PipelineNode[]; edges: PipelineEdge[]; name: string }) =>
      pipelineId
        ? studioPipelines.update(pipelineId, data)
        : studioPipelines.create({ ...data, icon: "W" }),
    onSuccess: (pipeline: PipelineDetail) => {
      queryClient.setQueryData(["studio", "pipeline", pipeline.id], pipeline);
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      queryClient.invalidateQueries({ queryKey: ["studio", "pipeline", pipeline.id] });
      setPipelineName(pipeline.name);
      const normalisedGraph = normalisePipelineGraph(
        (pipeline.nodes || []) as PipelineNode[],
        (pipeline.edges || []) as PipelineEdge[],
      );
      setNodes(normalisedGraph.nodes as never[]);
      setEdges(normalisedGraph.edges as never[]);
      setHasHydratedPipeline(true);
      setHasLocalChanges(false);
      toast({ description: "Pipeline saved" });
      if (!pipelineId) navigate(`/studio/pipeline/${pipeline.id}`, { replace: true });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const runMutation = useMutation({
    mutationFn: ({
      targetPipelineId,
      context,
      entryNodeId,
    }: {
      targetPipelineId: number;
      context: Record<string, unknown>;
      entryNodeId?: string;
    }) => studioPipelines.run(targetPipelineId, context, entryNodeId),
    onSuccess: (run: PipelineRun) => {
      setLastRun(run);
      setGraphRunId(run.id);
      setGraphRunLive(run);
      setActiveRunId(run.id);
      setSelectedNode(null);
      resetRunDialog();
      toast({ description: `Pipeline started — run #${run.id}` });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const validateRunMutation = useMutation({
    mutationFn: ({
      targetPipelineId,
      context,
      entryNodeId,
    }: {
      targetPipelineId: number;
      context: Record<string, unknown>;
      entryNodeId?: string;
    }) => studioPipelines.validateRun(targetPipelineId, context, entryNodeId),
    onSuccess: (result) => {
      const validationErrors = result.validation?.errors?.filter(Boolean) || [];
      const isOk = result.ok !== false && result.validation?.ok !== false && result.dry_run?.ok !== false;
      if (!isOk) {
        toast({
          variant: "destructive",
          description: validationErrors[0] || localize(lang, "Dry-run нашёл блокер перед запуском.", "Dry-run found a blocker before run."),
        });
        return;
      }
      toast({
        description: localize(
          lang,
          "Проверка пройдена: run не создан, действия не выполнялись.",
          "Dry-run passed: no run was created and no actions were executed.",
        ),
      });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  return { runMutation, saveMutation, validateRunMutation };
}
