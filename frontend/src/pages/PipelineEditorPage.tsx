import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  type Connection,
  type NodeMouseHandler,
  BackgroundVariant,
  Panel,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Save,
  Play,
  Plus,
  ArrowLeft,
  Bell,
  ChevronRight,
  Loader2,
  XCircle,
  Clock,
  Zap,
  Wand2,
  MoreHorizontal,
  Info,
  Link2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useToast } from "@/hooks/use-toast";
import {
  studioPipelines,
  studioRuns,
  studioNodeManifests,
  getStudioPipelineRunWsUrl,
  type PipelineNode,
  type PipelineEdge,
  type PipelineRun,
  type StudioCapabilityNode,
} from "@/lib/api";
import type { StudioPipelineAssistantResponse } from "@/lib/studioPipelineDraftsApi";
import { cn } from "@/lib/utils";
import { applyAssistantGraphPatch } from "@/components/pipeline/assistantPatch";
import { getPipelineClientValidationErrors } from "@/components/pipeline/pipelineClientValidation";
import { getPipelineActivityState } from "@/components/pipeline/pipelineActivity";
import { buildPipelineRunGraphState } from "@/components/pipeline/pipelineRunGraph";
import { buildPipelineRiskSummary } from "@/components/pipeline/pipelineRiskSummary";
import { type NodeType } from "@/components/pipeline/nodes";
import { RunMonitorPanel } from "./pipeline-editor/RunMonitorPanel";
import { NodePalette } from "./pipeline-editor/NodePalette";
import { PipelineAssistantPanel } from "./pipeline-editor/PipelineAssistantPanel";
import { NodeConfigPanel } from "./pipeline-editor/NodeConfigPanel";
import { PipelineRunDialog, type PipelineRunDialogMode } from "./pipeline-editor/PipelineRunDialog";
import { PipelineFlowSummaryBar } from "./pipeline-editor/PipelineFlowSummaryBar";
import { useRunContextFields } from "./pipeline-editor/useRunContextFields";
import { useRouteRunDialogRequest } from "./pipeline-editor/useRouteRunDialogRequest";
import {
  getPipelineActivityCopy,
  isNodeType,
  localize,
  nodeTypes,
} from "./pipeline-editor/presentation";
import { parseJsonObjectText } from "./pipeline-editor/jsonSchemaUtils";
import {
  buildConnectionAutofillPatch,
  buildDefaultNodeData,
  buildPipelineSavePayload,
  getActiveManualTriggerOptions,
  getActiveStoredTriggers,
  getActiveTriggerNodes,
  getNodeDisplayLabel,
  getPipelineNodeStatusLabel,
  isLivePipelineRunStatus,
  normaliseAssistantPatch,
  normalisePipelineGraph,
} from "./pipeline-editor/pipelineGraphUtils";

export { buildPipelineSavePayload } from "./pipeline-editor/pipelineGraphUtils";
function PipelineEditorInner({ pipelineId }: { pipelineId: number | null }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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
  const [graphRunLive, setGraphRunLive] = useState<PipelineRun | null>(null);
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [runTaskText, setRunTaskText] = useState("");
  const [runRequester, setRunRequester] = useState("");
  const [runTicketId, setRunTicketId] = useState("");
  const [runAdvancedOpen, setRunAdvancedOpen] = useState(false);
  const [runContextText, setRunContextText] = useState("{}");
  const [runContextError, setRunContextError] = useState<string | null>(null);
  const [runEntryNodeId, setRunEntryNodeId] = useState("");
  const [runTriggerError, setRunTriggerError] = useState<string | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantInput, setAssistantInput] = useState("");
  const [assistantHistory, setAssistantHistory] = useState<Array<{ role: "user" | "assistant"; content: string }>>([]);
  const [assistantProposal, setAssistantProposal] = useState<StudioPipelineAssistantResponse | null>(null);
  const [hasHydratedPipeline, setHasHydratedPipeline] = useState(!pipelineId);
  const [hasLocalChanges, setHasLocalChanges] = useState(false);
  const nodeIdCounter = useRef(1);
  const manualTriggerOptions = useMemo(
    () => getActiveManualTriggerOptions(nodes as unknown as PipelineNode[], lang),
    [lang, nodes],
  );
  const webhookTriggerNodes = useMemo(
    () => getActiveTriggerNodes(nodes as unknown as PipelineNode[], "trigger/webhook"),
    [nodes],
  );
  const scheduleTriggerNodes = useMemo(
    () => getActiveTriggerNodes(nodes as unknown as PipelineNode[], "trigger/schedule"),
    [nodes],
  );
  const monitoringTriggerNodes = useMemo(
    () => getActiveTriggerNodes(nodes as unknown as PipelineNode[], "trigger/monitoring"),
    [nodes],
  );
  const activeWebhookTriggers = useMemo(
    () => getActiveStoredTriggers(pipeline?.triggers, "webhook"),
    [pipeline?.triggers],
  );
  const activeScheduleTriggers = useMemo(
    () => getActiveStoredTriggers(pipeline?.triggers, "schedule"),
    [pipeline?.triggers],
  );
  const activeMonitoringTriggers = useMemo(
    () => getActiveStoredTriggers(pipeline?.triggers, "monitoring"),
    [pipeline?.triggers],
  );
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
  const runDialogMode: PipelineRunDialogMode = manualTriggerOptions.length
    ? "manual"
    : webhookTriggerNodes.length
      ? "webhook"
      : scheduleTriggerNodes.length
        ? "schedule"
        : monitoringTriggerNodes.length
          ? "monitoring"
          : "manual";
  const runRiskSummary = useMemo(() => buildPipelineRiskSummary(nodes as unknown as PipelineNode[], edges as unknown as PipelineEdge[]), [edges, nodes]);
  const { runtimeContextFields, handleApplyRuntimeContextFields, validateRuntimeContextFields } = useRunContextFields({ lang, nodes: nodes as unknown as PipelineNode[], runContextText, setRunContextText, setRunContextError, setRunAdvancedOpen });
  const nodeManifests = useMemo(() => ((nodeManifestRegistry?.nodes || []) as StudioCapabilityNode[]), [nodeManifestRegistry?.nodes]);
  const { data: graphRunData } = useQuery({
    queryKey: ["studio", "run", graphRunId],
    queryFn: () => (graphRunId ? studioRuns.get(graphRunId) : null),
    enabled: !!graphRunId,
    refetchInterval: (query) => {
      const status = query.state.data?.status || graphRunLive?.status;
      return isLivePipelineRunStatus(status) ? 2000 : false;
    },
    refetchIntervalInBackground: true,
  });

  const clearGraphOverlay = useCallback(() => {
    setGraphRunId(null);
    setGraphRunLive(null);
  }, []);

  useEffect(() => {
    setHasHydratedPipeline(!pipelineId);
    setHasLocalChanges(false);
    setLastRun(null);
    setAssistantInput("");
    setAssistantHistory([]);
    setAssistantProposal(null);
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

  useEffect(() => {
    setGraphRunLive((current) => (current && current.id === graphRunId ? current : null));
  }, [graphRunId]);

  useEffect(() => {
    if (!graphRunId) {
      setGraphRunLive(null);
      return;
    }
    if (graphRunData) {
      setGraphRunLive(graphRunData);
      if (lastRun?.id === graphRunData.id) {
        setLastRun(graphRunData);
      }
    }
  }, [graphRunData, graphRunId, lastRun?.id]);

  useEffect(() => {
    if (hasLocalChanges || graphRunId) {
      return;
    }
    if (!pipeline?.last_run?.id || !isLivePipelineRunStatus(pipeline.last_run.status)) {
      return;
    }
    setGraphRunId(pipeline.last_run.id);
  }, [graphRunId, hasLocalChanges, pipeline?.last_run?.id, pipeline?.last_run?.status]);

  useEffect(() => {
    if (!graphRunId || !isLivePipelineRunStatus(graphRunLive?.status || graphRunData?.status)) {
      return;
    }

    let cancelled = false;
    let reconnectTimer: number | null = null;
    let attempts = 0;
    let ws: WebSocket | null = null;

    const connect = () => {
      if (cancelled) {
        return;
      }
      ws = new WebSocket(getStudioPipelineRunWsUrl(graphRunId));

      ws.onopen = () => {
        attempts = 0;
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "node_state" && msg.node_id && msg.state) {
            setGraphRunLive((current) => {
              if (!current || current.id !== graphRunId) {
                return current;
              }
              return {
                ...current,
                node_states: {
                  ...(current.node_states || {}),
                  [msg.node_id]: msg.state,
                },
              };
            });
            return;
          }
          if (msg.type === "run_status" && msg.status) {
            setGraphRunLive((current) => {
              if (!current || current.id !== graphRunId) {
                return current;
              }
              return {
                ...current,
                status: typeof msg.status === "string" ? msg.status : current.status,
                error: typeof msg.error === "string" ? msg.error : current.error,
                summary: typeof msg.summary === "string" ? msg.summary : current.summary,
                finished_at: typeof msg.finished_at === "string" ? msg.finished_at : current.finished_at,
                started_at: typeof msg.started_at === "string" ? msg.started_at : current.started_at,
              };
            });
          }
        } catch {
          // ignore malformed live messages
        }
      };

      ws.onclose = () => {
        if (cancelled || !isLivePipelineRunStatus(graphRunLive?.status || graphRunData?.status)) {
          return;
        }
        attempts += 1;
        const delay = Math.min(5000, attempts <= 1 ? 1000 : attempts <= 2 ? 2000 : 4000);
        reconnectTimer = window.setTimeout(() => {
          reconnectTimer = null;
          connect();
        }, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      ws?.close();
    };
  }, [graphRunData?.status, graphRunId, graphRunLive?.status]);

  useEffect(() => {
    if (manualTriggerOptions.length === 1) {
      setRunEntryNodeId((current) => current || manualTriggerOptions[0].node_id);
      setRunTriggerError(null);
      return;
    }
    if (runEntryNodeId && manualTriggerOptions.some((item) => item.node_id === runEntryNodeId)) {
      return;
    }
    setRunEntryNodeId("");
  }, [manualTriggerOptions, runEntryNodeId]);

  const saveMutation = useMutation({
    mutationFn: (data: { nodes: PipelineNode[]; edges: PipelineEdge[]; name: string }) =>
      pipelineId
        ? studioPipelines.update(pipelineId, data)
        : studioPipelines.create({ ...data, icon: "W" }),
    onSuccess: (p) => {
      queryClient.setQueryData(["studio", "pipeline", p.id], p);
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      queryClient.invalidateQueries({ queryKey: ["studio", "pipeline", p.id] });
      setPipelineName(p.name);
      const normalisedGraph = normalisePipelineGraph(
        (p.nodes || []) as PipelineNode[],
        (p.edges || []) as PipelineEdge[],
      );
      setNodes(normalisedGraph.nodes as never[]);
      setEdges(normalisedGraph.edges as never[]);
      setHasHydratedPipeline(true);
      setHasLocalChanges(false);
      toast({ description: "Pipeline saved" });
      if (!pipelineId) navigate(`/studio/pipeline/${p.id}`, { replace: true });
    },
    onError: (err: Error) => toast({ variant: "destructive", description: err.message }),
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
    onSuccess: (run) => {
      setLastRun(run);
      setGraphRunId(run.id);
      setGraphRunLive(run);
      setActiveRunId(run.id);
      setSelectedNode(null);
      setRunDialogOpen(false);
      setRunTaskText("");
      setRunRequester("");
      setRunTicketId("");
      setRunAdvancedOpen(false);
      setRunContextText("{}");
      setRunContextError(null);
      setRunEntryNodeId("");
      setRunTriggerError(null);
      toast({ description: `Pipeline started — run #${run.id}` });
    },
    onError: (err: Error) => toast({ variant: "destructive", description: err.message }),
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
    onError: (err: Error) => toast({ variant: "destructive", description: err.message }),
  });

  const assistantMutation = useMutation({
    mutationFn: ({
      intent,
      message,
      history,
    }: {
      intent: "create" | "edit" | "validate" | "fix_run";
      message: string;
      history: Array<{ role: "user" | "assistant"; content: string }>;
    }) =>
      studioPipelines.assistant({
        pipeline_id: pipelineId,
        pipeline_name: pipelineName || pipeline?.name || "Untitled",
        nodes: nodes as unknown as PipelineNode[],
        edges: edges as unknown as PipelineEdge[],
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
        { role: "user", content: variables.message },
        { role: "assistant", content: response.reply || response.patch_summary || "Draft ready." },
      ].slice(-12));
      toast({ description: response.validation?.ok === false ? "Draft needs fixes before apply." : "Draft is ready for review." });
    },
    onError: (err: Error) => toast({ variant: "destructive", description: err.message }),
  });

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

  const handleNodesChange = useCallback(
    (changes: Parameters<typeof onNodesChangeRaw>[0]) => {
      if (changes?.length) {
        setHasLocalChanges(true);
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

  const handleOpenRunDialog = () => {
    setRunTriggerError(null);
    if (manualTriggerOptions.length === 1) {
      setRunEntryNodeId(manualTriggerOptions[0].node_id);
    }
    setRunDialogOpen(true);
  };
  useRouteRunDialogRequest({ hasHydratedPipeline, manualTriggerOptions, setRunDialogOpen, setRunEntryNodeId });

  const prepareManualRunRequest = useCallback((): { context: Record<string, unknown>; entryNodeId: string } | null => {
    if (!manualTriggerOptions.length) {
      setRunTriggerError(
        localize(
          lang,
          "У этого пайплайна нет ручного триггера. Используйте webhook или триггер расписания.",
          "This pipeline has no manual trigger. Use its webhook or schedule trigger instead.",
        ),
      );
      return;
    }
    const parsedContext = parseJsonObjectText(runContextText);
    if (parsedContext.error) {
      setRunContextError(parsedContext.error);
      return;
    }
    if (!validateRuntimeContextFields(parsedContext.value || {})) return;
    setRunContextError(null);
    if (showClientValidationError()) return;

    const context: Record<string, unknown> = {
      ...(parsedContext.value || {}),
    };
    if (runTaskText.trim()) context.task = runTaskText.trim();
    if (runRequester.trim()) context.requester = runRequester.trim();
    if (runTicketId.trim()) context.ticket_id = runTicketId.trim();
    const selectedEntryNodeId =
      manualTriggerOptions.length === 1
        ? manualTriggerOptions[0].node_id
        : runEntryNodeId.trim();
    if (!selectedEntryNodeId) {
      setRunTriggerError(localize(lang, "Выберите ручной триггер для запуска.", "Select the manual trigger that should start this run."));
      return;
    }
    setRunTriggerError(null);

    return { context, entryNodeId: selectedEntryNodeId };
  }, [
    lang,
    manualTriggerOptions,
    runContextText,
    runEntryNodeId,
    runRequester,
    runTaskText,
    runTicketId,
    showClientValidationError,
    validateRuntimeContextFields,
  ]);

  const handleRunSubmit = async () => {
    const manualRunRequest = prepareManualRunRequest();
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
    const manualRunRequest = prepareManualRunRequest();
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

  const handleAssistantSend = (
    intent: "create" | "edit" | "validate" | "fix_run",
    messageOverride?: string,
  ) => {
    const message = (messageOverride || assistantInput).trim();
    if (!message) return;
    setAssistantOpen(true);
    const resolvedIntent = intent === "edit" && !(nodes as unknown as PipelineNode[]).length ? "create" : intent;
    assistantMutation.mutate({
      intent: resolvedIntent,
      message,
      history: assistantHistory.slice(-10),
    });
    if (!messageOverride) {
      setAssistantInput("");
    }
  };

  const applyAssistantProposal = (saveAfterApply: boolean) => {
    if (!assistantProposal) return;
    if (assistantProposal.validation?.ok === false) {
      toast({ variant: "destructive", description: "Fix validation errors before applying this draft." });
      return;
    }
    if (assistantProposal.risk?.level === "dangerous") {
      toast({ variant: "destructive", description: localize(lang, "В черновике есть опасная SSH-команда. Добавьте подтверждение или перепишите шаг безопасно.", "This draft contains a dangerous SSH command. Add approval or rewrite it safely.") });
      return;
    }

    const result = applyAssistantGraphPatch({
      nodes: nodes as unknown as PipelineNode[],
      edges: edges as unknown as PipelineEdge[],
      response: assistantProposal,
      normalizeNodeData: (data) => normaliseAssistantPatch(data, { mcpList: [] }),
    });
    setNodes(result.nodes as never[]);
    setEdges(result.edges as never[]);
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
      saveMutation.mutate({
        name: pipelineName || pipeline?.name || "Untitled",
        nodes: result.nodes,
        edges: result.edges,
      });
      return;
    }
    toast({ description: localize(lang, "Черновик применён локально. Нажмите Save, чтобы сохранить pipeline.", "Draft applied locally. Click Save to persist the pipeline.") });
  };

  const handleApplyAssistantProposal = () => applyAssistantProposal(false);

  const handleApplyAndSaveAssistantProposal = () => applyAssistantProposal(true);

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      setHasLocalChanges(true);
      setEdges((eds) => addEdge(connection, eds));

      const sourceNode = (nodes as unknown as PipelineNode[]).find((item) => item.id === connection.source);
      const targetNode = (nodes as unknown as PipelineNode[]).find((item) => item.id === connection.target);
      if (!targetNode) return;

      clearGraphOverlay();
      setActiveRunId(null);
      if (!sourceNode) {
        setSelectedNode(targetNode);
        return;
      }

      const patch = buildConnectionAutofillPatch(targetNode, sourceNode, pipelineName);
      if (!Object.keys(patch).length) {
        setSelectedNode(targetNode);
        return;
      }

      const nextTarget = { ...targetNode, data: { ...(targetNode.data || {}), ...patch } } as PipelineNode;
      setNodes((nds) => nds.map((item) => (item.id === targetNode.id ? (nextTarget as never) : item)));
      setSelectedNode(nextTarget);
      toast({
        description: localize(
          lang,
          `${getNodeDisplayLabel(nextTarget, lang)} получил стартовые настройки из соединения.`,
          `${getNodeDisplayLabel(nextTarget, lang)} picked up starter settings from the connection.`,
        ),
      });
    },
    [clearGraphOverlay, lang, nodes, pipelineName, setEdges, setNodes, toast],
  );

  const onNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      setActiveRunId(null);
      const rawNode =
        (nodes as unknown as PipelineNode[]).find((item) => item.id === node.id) ||
        (node as unknown as PipelineNode);
      setSelectedNode(rawNode);
    },
    [nodes],
  );

  const handleAddNode = useCallback(
    (type: NodeType) => {
      const id = `node_${nodeIdCounter.current++}`;
      const selected = selectedNode ? (nodes as unknown as PipelineNode[]).find((item) => item.id === selectedNode.id) : null;
      const newNode = {
        id,
        type,
        position: selected
          ? { x: selected.position.x + 260, y: selected.position.y + 24 }
          : screenToFlowPosition({ x: 300, y: 200 + nodeIdCounter.current * 80 }),
        data: buildDefaultNodeData(type),
      };
      setHasLocalChanges(true);
      setNodes((nds) => [...nds, newNode as never]);
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(newNode as PipelineNode);
    },
    [clearGraphOverlay, nodes, selectedNode, setNodes, screenToFlowPosition],
  );

  const handleDuplicateNode = useCallback(
    (nodeId: string) => {
      const sourceNode = (nodes as unknown as PipelineNode[]).find((item) => item.id === nodeId);
      if (!sourceNode) return;

      const duplicatedNode = {
        ...sourceNode,
        id: `node_${nodeIdCounter.current++}`,
        position: {
          x: sourceNode.position.x + 40,
          y: sourceNode.position.y + 40,
        },
        data: { ...(sourceNode.data || {}) },
      } satisfies PipelineNode;

      setHasLocalChanges(true);
      setNodes((nds) => [...nds, duplicatedNode as never]);
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(duplicatedNode);
      toast({
        description: localize(lang, `${getNodeDisplayLabel(sourceNode, lang)} продублирован.`, `${getNodeDisplayLabel(sourceNode, lang)} duplicated.`),
      });
    },
    [clearGraphOverlay, lang, nodes, setNodes, toast],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const type = e.dataTransfer.getData("application/pipeline-node-type");
      if (!type || !isNodeType(type)) return;
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      const id = `node_${nodeIdCounter.current++}`;
      const newNode = { id, type, position, data: buildDefaultNodeData(type as NodeType) };
      setHasLocalChanges(true);
      setNodes((nds) => [...nds, newNode as never]);
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(newNode as PipelineNode);
    },
    [clearGraphOverlay, screenToFlowPosition, setNodes],
  );

  const handleUpdateNodeData = useCallback(
    (nodeId: string, data: Record<string, unknown>) => {
      setHasLocalChanges(true);
      setNodes((nds) =>
        nds.map((n) => (n.id === nodeId ? { ...n, data } : n)),
      );
      setSelectedNode((prev) => (prev?.id === nodeId ? { ...prev, data } : prev));
    },
    [setNodes],
  );

  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      setHasLocalChanges(true);
      setNodes((nds) => nds.filter((n) => n.id !== nodeId));
      setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      clearGraphOverlay();
      setActiveRunId(null);
      setSelectedNode(null);
    },
    [clearGraphOverlay, setNodes, setEdges],
  );

  const onPaneClick = useCallback(() => setSelectedNode(null), []);
  const pipelineNodes = nodes as unknown as PipelineNode[];
  const pipelineEdges = edges as unknown as PipelineEdge[];
  const graphState = useMemo(
    () => buildPipelineRunGraphState(pipelineNodes, pipelineEdges, graphRunLive),
    [graphRunLive, pipelineEdges, pipelineNodes],
  );
  const highlightedNodeId = graphState.currentNodeId || graphRunLive?.entry_node_id || null;
  const highlightedNode = highlightedNodeId
    ? pipelineNodes.find((node) => node.id === highlightedNodeId) || null
    : null;
  const displayNodes = useMemo(
    () =>
      nodes.map((node) => {
        const nodeState = graphRunLive?.node_states?.[node.id] as Record<string, unknown> | undefined;
        const status = typeof nodeState?.status === "string" ? nodeState.status : undefined;
        return {
          ...node,
          data: {
            ...(node.data || {}),
            status,
            status_label: getPipelineNodeStatusLabel(status, lang, nodeState),
            is_current_step: node.id === graphState.currentNodeId,
            is_in_active_path: graphState.traversedNodeIds.has(node.id),
            is_queued_step: graphState.queuedNodeIds.has(node.id),
            is_entry_point: graphRunLive?.entry_node_id === node.id,
          },
        };
      }),
    [graphRunLive?.entry_node_id, graphRunLive?.node_states, graphState.activeEdgeIds, graphState.currentNodeId, graphState.queuedNodeIds, graphState.traversedNodeIds, lang, nodes],
  );
  const displayEdges = useMemo(
    () =>
      edges.map((edge) => {
        const isCurrent = graphState.currentEdgeIds.has(edge.id);
        const isActivePath = graphState.activeEdgeIds.has(edge.id);
        return {
          ...edge,
          animated: isCurrent || (isActivePath && isLivePipelineRunStatus(graphRunLive?.status)),
          style: {
            ...(edge.style || {}),
            strokeWidth: isCurrent ? 3.6 : isActivePath ? 2.8 : 2,
            stroke: isCurrent
              ? "rgb(59 130 246)"
              : isActivePath
                ? "rgb(45 212 191)"
                : "hsl(var(--muted-foreground) / 0.3)",
            opacity: isActivePath ? 1 : 0.42,
          },
          labelStyle: {
            ...(edge.labelStyle || {}),
            fontSize: 10,
            fill: isActivePath ? "rgb(125 211 252)" : "hsl(var(--muted-foreground))",
          },
          labelBgStyle: {
            ...(edge.labelBgStyle || {}),
            fill: "hsl(var(--background))",
            fillOpacity: isActivePath ? 0.92 : 0.78,
          },
          zIndex: isActivePath ? 20 : 1,
        };
      }),
    [edges, graphRunLive?.status, graphState.activeEdgeIds, graphState.currentEdgeIds],
  );

  if (pipelineId && isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        Loading pipeline...
      </div>
    );
  }
  const showMiniMap = nodes.length >= 6;
  const toolbarActivityToneClass =
    pipelineActivityState.tone === "primary"
      ? "border-primary/25 bg-primary/10 text-primary"
      : pipelineActivityState.tone === "success"
        ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300"
        : pipelineActivityState.tone === "info"
          ? "border-sky-500/25 bg-sky-500/10 text-sky-300"
          : "border-amber-500/25 bg-amber-500/10 text-amber-300";
  const ToolbarActivityIcon =
    pipelineActivityState.icon === "running"
      ? Loader2
      : pipelineActivityState.icon === "pending"
        ? Clock
        : pipelineActivityState.icon === "manual"
          ? Play
          : pipelineActivityState.icon === "webhook"
            ? Link2
          : pipelineActivityState.icon === "schedule"
            ? Clock
            : pipelineActivityState.icon === "monitoring"
              ? Bell
            : pipelineActivityState.icon === "warning"
              ? XCircle
              : Zap;
  const pipelineActivityCopy = getPipelineActivityCopy(pipelineActivityState, lang);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="z-10 flex flex-col gap-2 border-b border-border bg-card px-3 py-3 lg:flex-row lg:items-center lg:px-4">
        <div className="flex min-w-0 items-center gap-2">
          <Button size="icon" variant="ghost" className="h-9 w-9 shrink-0" onClick={() => navigate("/studio")} aria-label={localize(lang, "Вернуться в Studio", "Back to Studio")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
        <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <Input
          value={pipelineName}
          onChange={(e) => {
            setPipelineName(e.target.value);
            setHasLocalChanges(true);
          }}
          className="h-9 min-w-0 flex-1 border-0 px-0 text-sm font-medium shadow-none focus-visible:ring-0 sm:w-72"
          placeholder={localize(lang, "Название pipeline…", "Pipeline name…")}
        />
        </div>
        <div className="flex flex-wrap items-center gap-2 lg:ml-auto lg:justify-end">
          {resolvedLastRun && (
            <button
              type="button"
              onClick={() => {
                setGraphRunId(resolvedLastRun.id);
                setActiveRunId(resolvedLastRun.id);
              }}
              className="hidden min-h-9 items-center gap-2 rounded-md border border-border/70 bg-background/35 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-border hover:bg-background/50 hover:text-foreground sm:flex"
            >
              {resolvedLastRun.status === "running" && <Loader2 className="h-2.5 w-2.5 animate-spin mr-1" />}
              Run #{resolvedLastRun.id}: {resolvedLastRun.status}
            </button>
          )}
          <Button
            size="sm"
            onClick={handleSave}
            disabled={saveMutation.isPending || (Boolean(pipelineId) && !hasHydratedPipeline)}
            className="h-9 gap-1.5"
          >
            {saveMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            {localize(lang, "Сохранить", "Save")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setPaletteOpen(true)}
            className="h-9 gap-1.5 lg:hidden"
          >
            <Plus className="h-3 w-3" />
            {localize(lang, "Ноды", "Nodes")}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={handleOpenRunDialog}
            disabled={runMutation.isPending || validateRunMutation.isPending || saveMutation.isPending || (Boolean(pipelineId) && !hasHydratedPipeline)}
            className="h-9 gap-1.5"
          >
            {runMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
            {localize(lang, "Запуск", "Run")}
          </Button>
          <Button
            size="sm"
            variant={assistantOpen ? "default" : "outline"}
            onClick={() => {
              setAssistantOpen(true);
              setActiveRunId(null);
            }}
            className="h-9 gap-1.5"
          >
            <Wand2 className="h-3 w-3" />
            {localize(lang, "AI", "AI")}
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="icon" variant="ghost" className="h-9 w-9 rounded-md text-muted-foreground" aria-label={localize(lang, "Ещё действия", "More actions")}>
                <MoreHorizontal className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              {resolvedLastRun && (
                <DropdownMenuItem onClick={() => setActiveRunId(resolvedLastRun.id)}>
                  <Clock className="mr-2 h-3.5 w-3.5" />
                  {localize(lang, "Открыть запуск #", "Open run #")}
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="flex flex-col items-start gap-2 border-b border-border/80 bg-[#15191f] px-4 py-2.5 text-xs sm:flex-row sm:items-center lg:gap-3">
        <div className={`flex items-center gap-2 rounded-full border px-2.5 py-1.5 ${toolbarActivityToneClass}`}>
          <ToolbarActivityIcon
            className={`h-3.5 w-3.5 ${pipelineActivityState.icon === "running" ? "animate-spin" : ""}`}
          />
          <span className="font-medium">{pipelineActivityCopy.label}</span>
        </div>
        <p className="min-w-0 flex-1 leading-5 text-muted-foreground/90 sm:truncate">{pipelineActivityCopy.detail}</p>
        {graphRunId && highlightedNode ? (
          <div className="inline-flex items-center gap-2 rounded-full border border-sky-500/25 bg-sky-500/10 px-2.5 py-1 text-sky-200">
            {isLivePipelineRunStatus(graphRunLive?.status) ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Info className="h-3.5 w-3.5" />}
            <span>
              {localize(lang, "Текущий шаг", "Current step")}: {getNodeDisplayLabel(highlightedNode, lang)}
            </span>
          </div>
        ) : null}
        {pipelineId && !hasHydratedPipeline ? (
          <div className="ml-auto inline-flex items-center gap-2 rounded-full border border-amber-500/25 bg-amber-500/10 px-2.5 py-1 text-amber-200">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>{localize(lang, "Обновляем свежую версию графа…", "Refreshing the latest graph…")}</span>
          </div>
        ) : null}
      </div>

      <PipelineFlowSummaryBar
        nodes={pipelineNodes}
        edges={pipelineEdges}
        graphState={graphState}
        selectedNodeId={selectedNode?.id || null}
        lang={lang}
        onSelectNode={(node) => {
          setSelectedNode(node);
          setActiveRunId(null);
        }}
      />

      {/* Main area */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Left: Node palette */}
        <div className="hidden h-full min-h-0 w-64 shrink-0 lg:block">
          <NodePalette onAddNode={handleAddNode} lang={lang} />
        </div>
        <Sheet open={paletteOpen} onOpenChange={setPaletteOpen}>
          <SheetContent side="left" className="flex w-[88vw] max-w-sm flex-col overflow-hidden border-border bg-card p-0 lg:hidden">
            <SheetHeader className="border-b border-border px-4 py-4 text-left">
              <SheetTitle className="text-base">{localize(lang, "Добавить ноду", "Add node")}</SheetTitle>
              <SheetDescription>
                {localize(lang, "Выберите шаг, и он появится на холсте.", "Choose a step and it will be added to the canvas.")}
              </SheetDescription>
            </SheetHeader>
            <div className="min-h-0 flex-1">
              <NodePalette
                lang={lang}
                onAddNode={(type) => {
                  handleAddNode(type);
                  setPaletteOpen(false);
                }}
              />
            </div>
          </SheetContent>
        </Sheet>

        {/* Center: Canvas */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-[#111317]">
          <div className="min-h-0 flex-1">
            <ReactFlow
            nodes={displayNodes}
            edges={displayEdges}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            nodeTypes={nodeTypes}
            fitView
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{
              style: { strokeWidth: 2 },
              animated: true,
              labelStyle: { fontSize: 10, fill: "hsl(var(--muted-foreground))" },
              labelBgStyle: { fill: "hsl(var(--background))", fillOpacity: 0.8 },
            }}
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
            <Controls className="!border-border/70 !bg-background/78 !backdrop-blur [&>button]:!border-border/70 [&>button]:!bg-background/80 [&>button]:!text-foreground [&>button:hover]:!bg-background" />
            {showMiniMap && (
              <MiniMap
                style={{ background: "hsl(var(--background) / 0.85)", border: "1px solid hsl(var(--border))" }}
                maskColor="hsl(var(--background) / 0.82)"
                nodeColor={(node) => {
                  const type = node.type || "";
                  if (type.startsWith("trigger/")) return "rgb(251 191 36 / 0.8)";
                  if (type.startsWith("agent/"))   return "rgb(167 139 250 / 0.8)";
                  if (type.startsWith("logic/"))   return "rgb(192 132 252 / 0.8)";
                  if (type.startsWith("output/"))  return "rgb(52 211 153 / 0.8)";
                  return "hsl(var(--muted-foreground))";
                }}
              />
            )}
            {nodes.length === 0 && (
              <Panel position="top-center" style={{ pointerEvents: "none", marginTop: "25%" }}>
                <div className="text-center select-none space-y-3">
                  <Zap className="h-12 w-12 text-primary/20 mx-auto" />
                  <p className="text-sm text-muted-foreground/70 font-medium">
                    {localize(lang, "Соберите OPS pipeline", "Build an OPS pipeline")}
                  </p>
                  <p className="text-xs text-muted-foreground/50 max-w-xs mx-auto">
                    {localize(lang, "Добавьте шаги из палитры и соедините их в порядок выполнения.", "Add steps from the palette and connect them into an execution flow.")}
                  </p>
                </div>
              </Panel>
            )}
            </ReactFlow>
          </div>
        </div>

        {/* Right: run monitor, assistant, or node config panel */}
        {(activeRunId || assistantOpen || selectedNode) && (
          <div className={cn(
            "fixed inset-x-3 bottom-3 top-32 z-30 flex flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl lg:static lg:inset-auto lg:h-full lg:min-h-0 lg:shrink-0 lg:rounded-none lg:border-y-0 lg:border-r-0 lg:shadow-none",
            assistantOpen && !activeRunId ? "lg:w-96" : "lg:w-80",
          )}>
            {activeRunId ? (
              <RunMonitorPanel
                runId={activeRunId}
                onClose={() => setActiveRunId(null)}
              />
            ) : assistantOpen ? (
              <PipelineAssistantPanel
                lang={lang}
                selectedNode={selectedNode}
                input={assistantInput}
                history={assistantHistory}
                proposal={assistantProposal}
                isPending={assistantMutation.isPending || saveMutation.isPending}
                onInputChange={setAssistantInput}
                onSend={handleAssistantSend}
                onApply={handleApplyAssistantProposal}
                onApplyAndSave={handleApplyAndSaveAssistantProposal}
                onDiscard={() => setAssistantProposal(null)}
                onClose={() => setAssistantOpen(false)}
              />
            ) : selectedNode ? (
              <NodeConfigPanel
                key={selectedNode.id}
                node={selectedNode}
                pipelineId={pipelineId}
                trigger={pipeline?.triggers?.find((item) => item.node_id === selectedNode.id) || null}
                lang={lang}
                onUpdate={handleUpdateNodeData}
                onClose={() => setSelectedNode(null)}
                onDelete={handleDeleteNode}
                onDuplicate={handleDuplicateNode}
              />
            ) : null}
          </div>
        )}
      </div>

      <PipelineRunDialog
        open={runDialogOpen}
        onOpenChange={setRunDialogOpen}
        mode={runDialogMode}
        lang={lang}
        manualTriggerOptions={manualTriggerOptions}
        runEntryNodeId={runEntryNodeId}
        onRunEntryNodeIdChange={setRunEntryNodeId}
        runTriggerError={runTriggerError}
        onRunTriggerErrorChange={setRunTriggerError}
        runRiskSummary={runRiskSummary}
        runtimeContextFields={runtimeContextFields}
        onApplyRuntimeContextFields={handleApplyRuntimeContextFields}
        runTaskText={runTaskText}
        onRunTaskTextChange={setRunTaskText}
        runAdvancedOpen={runAdvancedOpen}
        onRunAdvancedOpenChange={setRunAdvancedOpen}
        runRequester={runRequester}
        onRunRequesterChange={setRunRequester}
        runTicketId={runTicketId}
        onRunTicketIdChange={setRunTicketId}
        runContextText={runContextText}
        onRunContextTextChange={setRunContextText}
        runContextError={runContextError}
        onRunContextErrorChange={setRunContextError}
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
