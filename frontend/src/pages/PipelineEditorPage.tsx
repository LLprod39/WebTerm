import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Loader2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import {
  studioPipelines,
  studioNodeManifests,
  type PipelineNode,
  type PipelineEdge,
  type PipelineRun,
  type StudioCapabilityNode,
} from "@/lib/api";
import { getPipelineClientValidationErrors } from "@/components/pipeline/pipelineClientValidation";
import { getPipelineActivityState } from "@/components/pipeline/pipelineActivity";
import { PipelineEditorMainArea } from "./pipeline-editor/PipelineEditorMainArea";
import { PipelineRunDialogHost } from "./pipeline-editor/PipelineRunDialogHost";
import { PipelineActivityBar, PipelineEditorToolbar } from "./pipeline-editor/PipelineEditorToolbar";
import { PipelineFlowSummaryBar } from "./pipeline-editor/PipelineFlowSummaryBar";
import { usePipelineRunGraphOverlay } from "./pipeline-editor/usePipelineRunGraphOverlay";
import { usePipelineRunDialogState } from "./pipeline-editor/usePipelineRunDialogState";
import { localize } from "./pipeline-editor/presentation";
import {
  buildPipelineSavePayload,
  normalisePipelineGraph,
} from "./pipeline-editor/pipelineGraphUtils";
import { usePipelineAssistantDraft } from "./pipeline-editor/usePipelineAssistantDraft";
import { usePipelineEditorGraphActions } from "./pipeline-editor/usePipelineEditorGraphActions";
import { usePipelineEditorMutations } from "./pipeline-editor/usePipelineEditorMutations";
import { usePipelineEditorTriggers } from "./pipeline-editor/usePipelineEditorTriggers";
import { usePipelineGraphDisplayState } from "./pipeline-editor/usePipelineGraphDisplayState";

function PipelineEditorInner({ pipelineId }: { pipelineId: number | null }) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { screenToFlowPosition, fitView } = useReactFlow();
  const lang =
    typeof document !== "undefined" && document.documentElement.lang.toLowerCase().startsWith("ru")
      ? "ru"
      : "en";

  const { data: pipeline, isLoading, isFetchedAfterMount } = useQuery({
    queryKey: ["studio", "pipeline", pipelineId],
    queryFn: () => (pipelineId ? studioPipelines.get(pipelineId) : null),
    enabled: !!pipelineId,
    refetchOnMount: "always",
  });
  const { data: nodeManifestRegistry } = useQuery({
    queryKey: ["studio", "node-manifests"],
    queryFn: studioNodeManifests.get,
    staleTime: 5 * 60_000,
  });
  const [nodes, setNodes, onNodesChangeRaw] = useNodesState([]);
  const [edges, setEdges, onEdgesChangeRaw] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<PipelineNode | null>(null);
  const [pipelineName, setPipelineName] = useState("");
  const [lastRun, setLastRun] = useState<PipelineRun | null>(null);
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [graphRunId, setGraphRunId] = useState<number | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [hasHydratedPipeline, setHasHydratedPipeline] = useState(!pipelineId);
  const [hasLocalChanges, setHasLocalChanges] = useState(false);
  const [flowSummaryCollapsed, setFlowSummaryCollapsed] = useState(false);
  const nodeIdCounter = useRef(1);
  const pipelineNodes = nodes as unknown as PipelineNode[];
  const pipelineEdges = edges as unknown as PipelineEdge[];
  const {
    activeMonitoringTriggers,
    activeScheduleTriggers,
    activeWebhookTriggers,
    manualTriggerOptions,
    monitoringTriggerNodes,
    runDialogMode,
    runRiskSummary,
    scheduleTriggerNodes,
    webhookTriggerNodes,
  } = usePipelineEditorTriggers({
    edges: pipelineEdges,
    lang,
    nodes: pipelineNodes,
    triggers: pipeline?.triggers,
  });
  const resolvedLastRun = lastRun ?? pipeline?.last_run ?? null;
  const pipelineActivityState = useMemo(
    () =>
      getPipelineActivityState({
        lastRun: resolvedLastRun,
        triggers: pipeline?.triggers,
        graphVersion: pipeline?.graph_version,
      }),
    [resolvedLastRun, pipeline?.graph_version, pipeline?.triggers],
  );
  const nodeManifests = useMemo(() => ((nodeManifestRegistry?.nodes || []) as StudioCapabilityNode[]), [nodeManifestRegistry?.nodes]);
  const { clearGraphOverlay, graphRunLive, setGraphRunLive } = usePipelineRunGraphOverlay({
    graphRunId,
    hasLocalChanges,
    lastRunId: lastRun?.id,
    pipelineLastRun: pipeline?.last_run,
    setGraphRunId,
    setLastRun,
  });

  useEffect(() => {
    setHasHydratedPipeline(!pipelineId);
    setHasLocalChanges(false);
    setLastRun(null);
    clearGraphOverlay();
    if (pipelineId) {
      setSelectedNode(null);
      setActiveRunId(null);
    }
  }, [pipelineId, clearGraphOverlay]);

  // Load pipeline data only after the editor has fetched the latest server copy
  useEffect(() => {
    if (!pipeline) {
      return;
    }
    if (pipelineId && !isFetchedAfterMount) {
      return;
    }
    setPipelineName(pipeline.name);
    const normalisedGraph = normalisePipelineGraph(
      (pipeline.nodes || []) as PipelineNode[],
      (pipeline.edges || []) as PipelineEdge[],
    );
    setNodes(normalisedGraph.nodes as never[]);
    setEdges(normalisedGraph.edges as never[]);
    setHasHydratedPipeline(true);
    setHasLocalChanges(false);
    if (pipeline.nodes?.length) {
      const maxId = pipeline.nodes.reduce((max, n) => {
        const num = parseInt(n.id.replace(/\D/g, "") || "0");
        return Math.max(max, num);
      }, 0);
      nodeIdCounter.current = maxId + 1;
      // Fit view after nodes load
      setTimeout(() => fitView({ padding: 0.22, duration: 300 }), 100);
    }
  }, [pipeline, pipelineId, isFetchedAfterMount, setNodes, setEdges, fitView]);

  const showClientValidationError = useCallback(() => {
    const pipelineNodes = nodes as unknown as PipelineNode[];
    const validationErrors = getPipelineClientValidationErrors(pipelineNodes, nodeManifests);
    const firstError = validationErrors[0];
    if (!firstError) return false;

    const problemNode = pipelineNodes.find((item) => item.id === firstError.nodeId);
    if (problemNode) setSelectedNode(problemNode);
    toast({
      variant: "destructive",
      description: lang === "ru" ? firstError.messageRu : firstError.messageEn,
    });
    return true;
  }, [lang, nodeManifests, nodes, toast]);

  const runDialog = usePipelineRunDialogState({
    hasHydratedPipeline,
    lang,
    manualTriggerOptions,
    nodes: nodes as unknown as PipelineNode[],
    showClientValidationError,
  });

  const { runMutation, saveMutation, validateRunMutation } = usePipelineEditorMutations({
    lang,
    navigate,
    pipelineId,
    resetRunDialog: runDialog.resetRunDialog,
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
  });
  const {
    assistantHistory,
    assistantInput,
    assistantOpen,
    assistantPending,
    assistantProposal,
    handleApplyAndSaveAssistantProposal,
    handleApplyAssistantProposal,
    handleAssistantSend,
    setAssistantInput,
    setAssistantOpen,
    setAssistantProposal,
  } = usePipelineAssistantDraft({
    clearGraphOverlay,
    edges: pipelineEdges,
    fitView,
    graphRunLive,
    lang,
    nodeIdCounter,
    nodes: pipelineNodes,
    pipelineFallbackName: pipeline?.name,
    pipelineId,
    pipelineName,
    saveAppliedGraph: saveMutation.mutate,
    selectedNode,
    setActiveRunId,
    setEdges,
    setHasLocalChanges,
    setNodes,
    setSelectedNode,
    toast,
  });

  const handleSave = () => {
    if (pipelineId && !hasHydratedPipeline) {
      toast({
        variant: "destructive",
        description: localize(
          lang,
          "Редактор еще загружает актуальную версию графа. Подождите секунду и попробуйте снова.",
          "The editor is still loading the latest graph from the server. Wait a moment and try again.",
        ),
      });
      return;
    }
    if (showClientValidationError()) return;
    saveMutation.mutate(
      buildPipelineSavePayload({
        pipelineId,
        pipeline,
        pipelineName,
        nodes: nodes as unknown as PipelineNode[],
        edges: edges as unknown as PipelineEdge[],
        hasLocalChanges,
      }),
    );
  };

  const handleValidateGraph = () => {
    if (pipelineId && !hasHydratedPipeline) {
      toast({
        variant: "destructive",
        description: localize(
          lang,
          "Редактор еще загружает актуальную версию графа. Подождите секунду и попробуйте снова.",
          "The editor is still loading the latest graph from the server. Wait a moment and try again.",
        ),
      });
      return;
    }
    if (showClientValidationError()) return;
    toast({
      description: localize(
        lang,
        "Граф прошёл локальную проверку. Для проверки runtime context используйте dry-run в диалоге запуска.",
        "Graph passed local validation. Use dry-run in the run dialog to validate runtime context.",
      ),
    });
  };

  const handleNodesChange = useCallback(
    (changes: Parameters<typeof onNodesChangeRaw>[0]) => {
      if (changes?.length) {
        if (changes.some((change) => change.type !== "dimensions" && change.type !== "select")) {
          setHasLocalChanges(true);
        }
        if (
          changes.some(
            (change) =>
              change.type !== "position" &&
              change.type !== "dimensions" &&
              change.type !== "select",
          )
        ) {
          clearGraphOverlay();
        }
      }
      onNodesChangeRaw(changes);
    },
    [clearGraphOverlay, onNodesChangeRaw],
  );

  const handleEdgesChange = useCallback(
    (changes: Parameters<typeof onEdgesChangeRaw>[0]) => {
      if (changes?.length) {
        setHasLocalChanges(true);
        clearGraphOverlay();
      }
      onEdgesChangeRaw(changes);
    },
    [clearGraphOverlay, onEdgesChangeRaw],
  );

  const handleRunSubmit = async () => {
    const manualRunRequest = runDialog.prepareManualRunRequest();
    if (!manualRunRequest) return;

    try {
      const saved = await saveMutation.mutateAsync({
        name: pipelineName || "Untitled",
        nodes: nodes as unknown as PipelineNode[],
        edges: edges as unknown as PipelineEdge[],
      });
      await runMutation.mutateAsync({
        targetPipelineId: pipelineId ?? saved.id,
        context: manualRunRequest.context,
        entryNodeId: manualRunRequest.entryNodeId,
      });
    } catch {
      // Error notifications are handled in mutation callbacks.
    }
  };

  const handleValidateRun = async () => {
    const manualRunRequest = runDialog.prepareManualRunRequest();
    if (!manualRunRequest) return;

    try {
      const saved = await saveMutation.mutateAsync({
        name: pipelineName || "Untitled",
        nodes: nodes as unknown as PipelineNode[],
        edges: edges as unknown as PipelineEdge[],
      });
      await validateRunMutation.mutateAsync({
        targetPipelineId: pipelineId ?? saved.id,
        context: manualRunRequest.context,
        entryNodeId: manualRunRequest.entryNodeId,
      });
    } catch {
      // Error notifications are handled in mutation callbacks.
    }
  };

  const {
    handleAddNode,
    handleDeleteNode,
    handleDragOver,
    handleDrop,
    handleDuplicateNode,
    handleUpdateNodeData,
    onConnect,
    onNodeClick,
    onPaneClick,
  } = usePipelineEditorGraphActions({
    clearGraphOverlay,
    lang,
    nodeIdCounter,
    nodes: pipelineNodes,
    pipelineName,
    screenToFlowPosition,
    selectedNode,
    setActiveRunId,
    setEdges,
    setHasLocalChanges,
    setNodes,
    setSelectedNode,
    toast,
  });
  const {
    displayEdges,
    displayNodes,
    graphState,
    highlightedNode,
    highlightedNodeLabel,
  } = usePipelineGraphDisplayState({
    edges: pipelineEdges,
    graphRunLive,
    lang,
    nodes: pipelineNodes,
  });

  if (pipelineId && isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        Loading pipeline...
      </div>
    );
  }
  const showMiniMap = nodes.length >= 6;
  const showPipelineActivityBar =
    Boolean(graphRunId) ||
    !hasHydratedPipeline ||
    pipelineActivityState.icon === "running" ||
    pipelineActivityState.icon === "pending" ||
    pipelineActivityState.icon === "warning";

  return (
    <div className="flex flex-col h-full">
      <PipelineEditorToolbar
        assistantOpen={assistantOpen}
        hasHydratedPipeline={hasHydratedPipeline}
        hasLocalChanges={hasLocalChanges}
        lang={lang}
        pipelineId={pipelineId}
        pipelineName={pipelineName}
        resolvedLastRun={resolvedLastRun}
        runDisabled={runMutation.isPending || validateRunMutation.isPending || saveMutation.isPending || (Boolean(pipelineId) && !hasHydratedPipeline)}
        runPending={runMutation.isPending}
        saveDisabled={saveMutation.isPending || (Boolean(pipelineId) && !hasHydratedPipeline)}
        savePending={saveMutation.isPending}
        onBack={() => navigate("/studio")}
        onOpenAssistant={() => {
          setAssistantOpen(true);
          setActiveRunId(null);
        }}
        onOpenLastRun={(runId) => {
          setGraphRunId(runId);
          setActiveRunId(runId);
        }}
        onOpenPalette={() => setPaletteOpen(true)}
        onOpenRunDialog={runDialog.handleOpenRunDialog}
        onPipelineNameChange={(value) => {
          setPipelineName(value);
          setHasLocalChanges(true);
        }}
        onSave={handleSave}
        onValidateGraph={handleValidateGraph}
      />

      {showPipelineActivityBar ? (
        <PipelineActivityBar
          activityState={pipelineActivityState}
          graphRunId={graphRunId}
          graphRunLive={graphRunLive}
          hasHydratedPipeline={hasHydratedPipeline}
          highlightedNode={highlightedNode}
          highlightedNodeLabel={highlightedNodeLabel}
          lang={lang}
          pipelineId={pipelineId}
        />
      ) : null}
      <PipelineFlowSummaryBar
        nodes={pipelineNodes}
        edges={pipelineEdges}
        graphState={graphState}
        selectedNodeId={selectedNode?.id || null}
        collapsed={flowSummaryCollapsed}
        lang={lang}
        onCollapsedChange={setFlowSummaryCollapsed}
        onSelectNode={(node) => {
          setSelectedNode(node);
          setActiveRunId(null);
        }}
      />

      <PipelineEditorMainArea
        activeRunId={activeRunId}
        assistantHistory={assistantHistory}
        assistantInput={assistantInput}
        assistantOpen={assistantOpen}
        assistantPending={assistantPending || saveMutation.isPending}
        assistantProposal={assistantProposal}
        displayEdges={displayEdges}
        displayNodes={displayNodes}
        lang={lang}
        paletteOpen={paletteOpen}
        pipelineId={pipelineId}
        selectedNode={selectedNode}
        showMiniMap={showMiniMap}
        trigger={selectedNode ? pipeline?.triggers?.find((item) => item.node_id === selectedNode.id) || null : null}
        onAddNode={handleAddNode}
        onApplyAssistantProposal={handleApplyAssistantProposal}
        onApplyAndSaveAssistantProposal={handleApplyAndSaveAssistantProposal}
        onAssistantInputChange={setAssistantInput}
        onAssistantSend={handleAssistantSend}
        onCloseAssistant={() => setAssistantOpen(false)}
        onCloseNode={() => setSelectedNode(null)}
        onCloseRun={() => setActiveRunId(null)}
        onConnect={onConnect}
        onDeleteNode={handleDeleteNode}
        onDiscardAssistantProposal={() => setAssistantProposal(null)}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onDuplicateNode={handleDuplicateNode}
        onEdgesChange={handleEdgesChange}
        onNodeClick={onNodeClick}
        onNodesChange={handleNodesChange}
        onPaneClick={onPaneClick}
        onUpdateNodeData={handleUpdateNodeData}
        setPaletteOpen={setPaletteOpen}
      />
      <PipelineRunDialogHost
        controller={runDialog}
        mode={runDialogMode}
        lang={lang}
        manualTriggerOptions={manualTriggerOptions}
        runRiskSummary={runRiskSummary}
        activeWebhookTriggers={activeWebhookTriggers}
        activeScheduleTriggers={activeScheduleTriggers}
        activeMonitoringTriggers={activeMonitoringTriggers}
        scheduleTriggerNodes={scheduleTriggerNodes}
        monitoringTriggerNodes={monitoringTriggerNodes}
        isRunPending={runMutation.isPending}
        isValidatePending={validateRunMutation.isPending}
        isSavePending={saveMutation.isPending}
        saveDisabled={saveMutation.isPending || (Boolean(pipelineId) && !hasHydratedPipeline)}
        onValidateRun={handleValidateRun}
        onRunSubmit={handleRunSubmit}
        onSaveTrigger={handleSave}
      />
    </div>
  );
}

export default function PipelineEditorPage() {
  const { id } = useParams<{ id?: string }>();
  const pipelineId = id ? parseInt(id) : null;

  return (
    <ReactFlowProvider>
      <div className="h-full min-h-0">
        <PipelineEditorInner pipelineId={pipelineId} />
      </div>
    </ReactFlowProvider>
  );
}
