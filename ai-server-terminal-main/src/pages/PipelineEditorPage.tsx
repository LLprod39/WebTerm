// @ts-nocheck
import { useCallback, useEffect, useRef, useState } from "react";
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
  BookOpen,
  ChevronRight,
  X,
  Loader2,
  Trash2,
  CheckCircle2,
  XCircle,
  Clock,
  Square,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Zap,
  Bot,
  Wand2,
  MoreHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/hooks/use-toast";
import {
  studioPipelines,
  studioAgents,
  studioServers,
  studioRuns,
  studioMCP,
  studioSkills,
  fetchModels,
  refreshModels,
  type MCPServerInspection,
  type PipelineNode,
  type PipelineEdge,
  type PipelineRun,
  type PipelineTrigger,
  type StudioPipelineGraphPatch,
} from "@/lib/api";
import {
  TriggerNode,
  AgentNode,
  SSHCommandNode,
  ConditionNode,
  ParallelNode,
  OutputNode,
  LLMQueryNode,
  MCPCallNode,
  EmailNode,
  WaitNode,
  HumanApprovalNode,
  TelegramNode,
  NODE_PALETTE,
  type NodeType,
} from "@/components/pipeline/nodes";

// ---------------------------------------------------------------------------
// React Flow node type map
// ---------------------------------------------------------------------------
const nodeTypes = {
  "trigger/manual": TriggerNode,
  "trigger/webhook": TriggerNode,
  "trigger/schedule": TriggerNode,
  "agent/react": AgentNode,
  "agent/multi": AgentNode,
  "agent/ssh_cmd": SSHCommandNode,
  "agent/llm_query": LLMQueryNode,
  "agent/mcp_call": MCPCallNode,
  "logic/condition": ConditionNode,
  "logic/parallel": ParallelNode,
  "logic/wait": WaitNode,
  "logic/human_approval": HumanApprovalNode,
  "output/report": OutputNode,
  "output/webhook": OutputNode,
  "output/email": EmailNode,
  "output/telegram": TelegramNode,
};

// ---------------------------------------------------------------------------
// Node type friendly names
// ---------------------------------------------------------------------------
const NODE_TYPE_LABELS: Record<string, { label: string; icon: string }> = {
  "trigger/manual":        { label: "Manual Trigger",   icon: "▶️" },
  "trigger/webhook":       { label: "Webhook Trigger",  icon: "🔗" },
  "trigger/schedule":      { label: "Schedule Trigger", icon: "⏰" },
  "agent/react":           { label: "ReAct Agent",      icon: "🤖" },
  "agent/multi":           { label: "Multi-Agent",      icon: "🦾" },
  "agent/ssh_cmd":         { label: "SSH Command",      icon: "💻" },
  "agent/llm_query":       { label: "LLM Query",        icon: "🧠" },
  "agent/mcp_call":        { label: "MCP Call",         icon: "🧩" },
  "logic/condition":       { label: "Condition",        icon: "🔀" },
  "logic/parallel":        { label: "Parallel",         icon: "⚡" },
  "logic/wait":            { label: "Wait",             icon: "⏱️" },
  "logic/human_approval":  { label: "Human Approval",  icon: "👤" },
  "output/report":         { label: "Report",           icon: "📋" },
  "output/webhook":        { label: "Send Webhook",     icon: "📤" },
  "output/email":          { label: "Send Email",       icon: "✉️" },
  "output/telegram":       { label: "Telegram",         icon: "📱" },
};

function localize(lang: string, ru: string, en: string) {
  return lang === "ru" ? ru : en;
}

// ---------------------------------------------------------------------------
// Run Monitor Panel
// ---------------------------------------------------------------------------
const NODE_STATUS_ICON: Record<string, React.ReactNode> = {
  running:            <Loader2      className="h-3 w-3 animate-spin text-blue-400" />,
  awaiting_approval:  <Clock        className="h-3 w-3 text-yellow-400 animate-pulse" />,
  completed:          <CheckCircle2 className="h-3 w-3 text-green-400" />,
  failed:             <XCircle      className="h-3 w-3 text-red-400" />,
  pending:            <Clock        className="h-3 w-3 text-muted-foreground" />,
  skipped:            <ChevronRight className="h-3 w-3 text-muted-foreground" />,
};

function RunMonitorPanel({
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
    failed:    "text-red-400",
    running:   "text-blue-400",
    pending:   "text-muted-foreground",
    stopped:   "text-yellow-400",
  };

  const nodeStates: Record<string, Record<string, unknown>> = (run?.node_states as Record<string, Record<string, unknown>>) || {};

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
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

      {/* Body */}
      <div className="flex-1 overflow-auto p-3 space-y-2 text-xs">
        {/* Error banner */}
        {run?.error && (
          <div className="rounded bg-red-900/20 border border-red-500/30 px-3 py-2 text-red-300">
            <strong>Error:</strong> {run.error}
          </div>
        )}

        {/* Summary */}
        {run?.summary && (
          <div className="rounded bg-muted/30 border border-border px-3 py-2 text-muted-foreground whitespace-pre-wrap max-h-40 overflow-auto">
            {run.summary}
          </div>
        )}

        {/* Node states */}
        {run?.nodes_snapshot && (run.nodes_snapshot as PipelineNode[]).filter((n) => !n.type?.startsWith("trigger/")).map((node) => {
          const state = nodeStates[node.id] || {};
          const status = (state.status as string) || "pending";
          const output = (state.output as string) || "";
          const error = (state.error as string) || "";
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

              {/* Human Approval waiting state — always show links */}
              {status === "awaiting_approval" && (
                <div className="border-t border-border px-3 py-2 space-y-2">
                  <p className="text-yellow-400 text-[11px] font-medium">⏳ Waiting for your decision...</p>
                  {(state.approve_url as string) && (
                    <div className="flex gap-2">
                      <a
                        href={state.approve_url as string}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 text-center text-xs py-1.5 rounded bg-green-800/40 border border-green-600/40 text-green-300 hover:bg-green-700/50 transition-colors"
                      >
                        ✅ Approve
                      </a>
                      <a
                        href={state.reject_url as string}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 text-center text-xs py-1.5 rounded bg-red-900/30 border border-red-600/40 text-red-300 hover:bg-red-800/40 transition-colors"
                      >
                        ❌ Reject
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

// ---------------------------------------------------------------------------
// Node config panel
// ---------------------------------------------------------------------------
const AGENT_PROVIDER_OPTIONS = [
  { value: "auto", label: "Auto" },
  { value: "gemini", label: "Gemini" },
  { value: "openai", label: "OpenAI" },
  { value: "grok", label: "Grok" },
  { value: "claude", label: "Claude" },
] as const;

const DIRECT_LLM_PROVIDERS = AGENT_PROVIDER_OPTIONS.filter((item) => item.value !== "auto");

const CRON_PRESETS = [
  { label: "Every 5 min", value: "*/5 * * * *" },
  { label: "Hourly", value: "0 * * * *" },
  { label: "Daily 04:00", value: "0 4 * * *" },
] as const;

function toJsonEditorText(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "{}";
  const entries = Object.keys(value as Record<string, unknown>);
  if (!entries.length) return "{}";
  return JSON.stringify(value, null, 2);
}

function parseJsonObjectText(text: string): { value: Record<string, unknown> | null; error: string | null } {
  const trimmed = text.trim();
  if (!trimmed) return { value: {}, error: null };
  try {
    const parsed = JSON.parse(trimmed);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { value: null, error: "JSON must be an object" };
    }
    return { value: parsed as Record<string, unknown>, error: null };
  } catch (error) {
    return { value: null, error: error instanceof Error ? error.message : "Invalid JSON" };
  }
}

function buildSchemaTemplate(inputSchema?: Record<string, unknown>) {
  const properties = (inputSchema?.properties as Record<string, Record<string, unknown>> | undefined) || {};
  const next: Record<string, unknown> = {};
  Object.entries(properties).forEach(([key, property]) => {
    const type = property?.type;
    if (type === "boolean") next[key] = false;
    else if (type === "number" || type === "integer") next[key] = 0;
    else if (type === "array") next[key] = [];
    else if (type === "object") next[key] = {};
    else next[key] = `{${key}}`;
  });
  return next;
}

function formatStudioDateTime(value?: string | null) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

type AssistantMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  targetNodeId?: string | null;
  nodePatch?: Record<string, unknown>;
  graphPatch?: StudioPipelineGraphPatch | null;
  warnings?: string[];
};

function getNodeDisplayLabel(node: PipelineNode | { id: string; type: string; label?: string }) {
  if ("data" in node) {
    const label = typeof node.data?.label === "string" ? node.data.label.trim() : "";
    if (label) return label;
  }
  if ("label" in node && typeof node.label === "string" && node.label.trim()) return node.label.trim();
  return NODE_TYPE_LABELS[node.type]?.label || node.id;
}

function buildDefaultNodeData(type: NodeType) {
  switch (type) {
    case "trigger/manual":
      return { is_active: true };
    case "trigger/webhook":
      return { is_active: true, webhook_payload_map: {}, webhook_payload_map_text: "{}" };
    case "trigger/schedule":
      return { is_active: true, cron_expression: "*/5 * * * *" };
    case "agent/react":
    case "agent/multi":
      return { max_iterations: 6, on_failure: "abort" };
    case "agent/llm_query":
      return { provider: "gemini", on_failure: "abort" };
    case "agent/mcp_call":
      return { arguments: {}, arguments_text: "{}", on_failure: "abort" };
    case "logic/condition":
      return { check_type: "contains" };
    case "logic/wait":
      return { wait_minutes: 20 };
    case "logic/human_approval":
      return { timeout_minutes: 120 };
    case "output/email":
      return { subject: "Pipeline Report: {pipeline_name}" };
    default:
      return {};
  }
}

function buildConnectionAutofillPatch(target: PipelineNode, source: PipelineNode, pipelineName: string) {
  const data = (target.data || {}) as Record<string, unknown>;
  const outputToken = `{${source.id}_output}`;
  const sourceLabel = getNodeDisplayLabel(source);
  const patch: Record<string, unknown> = {};

  if (target.type === "logic/condition") {
    if (!String(data.source_node_id || "").trim()) patch.source_node_id = source.id;
    if (!String(data.check_type || "").trim()) patch.check_type = "contains";
  }

  if (target.type === "agent/llm_query" && !String(data.prompt || "").trim()) {
    patch.prompt = `Review ${outputToken} from ${sourceLabel} and explain the key result, risks, and recommended next action.`;
  }

  if (target.type === "output/report" && !String(data.template || "").trim()) {
    patch.template = `# ${pipelineName || "Pipeline"} report\n\n## ${sourceLabel}\n\n${outputToken}`;
  }

  if (target.type === "output/email") {
    if (!String(data.subject || "").trim()) patch.subject = "Pipeline Report: {pipeline_name}";
    if (!String(data.body || "").trim()) {
      patch.body = `# ${pipelineName || "Pipeline"}\n\n## ${sourceLabel}\n\n${outputToken}`;
    }
  }

  if (target.type === "output/telegram" && !String(data.message || "").trim()) {
    patch.message = `*{pipeline_name}*\n\n## ${sourceLabel}\n\n${outputToken}`;
  }

  if (target.type === "logic/human_approval") {
    if (!String(data.message || "").trim()) {
      patch.message = `Approval required for ${sourceLabel}\n\n${outputToken}\n\nApprove: {approve_url}\nReject: {reject_url}`;
    }
    if (!String(data.email_body || "").trim()) {
      patch.email_body = `Approval required for ${sourceLabel}\n\n${outputToken}\n\nApprove: {approve_url}\nReject: {reject_url}`;
    }
  }

  return patch;
}

function normaliseAssistantPatch(
  patch: Record<string, unknown>,
  opts: {
    mcpList: Array<{ id: number; name: string }>;
  },
) {
  const next: Record<string, unknown> = { ...patch };

  if (typeof next.mcp_server_id === "string" && next.mcp_server_id.trim()) {
    const parsed = Number(next.mcp_server_id);
    if (!Number.isNaN(parsed)) next.mcp_server_id = parsed;
  }

  if (typeof next.agent_config_id === "string" && next.agent_config_id.trim()) {
    const parsed = Number(next.agent_config_id);
    if (!Number.isNaN(parsed)) next.agent_config_id = parsed;
  }

  if (typeof next.server_id === "string" && next.server_id.trim()) {
    const parsed = Number(next.server_id);
    if (!Number.isNaN(parsed)) next.server_id = parsed;
  }

  if (Array.isArray(next.server_ids)) {
    next.server_ids = next.server_ids.map((item) => Number(item)).filter((item) => Number.isInteger(item));
  }

  if (Array.isArray(next.mcp_server_ids)) {
    next.mcp_server_ids = next.mcp_server_ids.map((item) => Number(item)).filter((item) => Number.isInteger(item));
  }

  if (next.arguments && typeof next.arguments === "object" && !Array.isArray(next.arguments) && !next.arguments_text) {
    next.arguments_text = JSON.stringify(next.arguments, null, 2);
  }
  if (typeof next.arguments_text === "string" && !next.arguments && !parseJsonObjectText(next.arguments_text).error) {
    next.arguments = parseJsonObjectText(next.arguments_text).value || {};
  }

  if (
    next.webhook_payload_map &&
    typeof next.webhook_payload_map === "object" &&
    !Array.isArray(next.webhook_payload_map) &&
    !next.webhook_payload_map_text
  ) {
    next.webhook_payload_map_text = JSON.stringify(next.webhook_payload_map, null, 2);
  }
  if (typeof next.webhook_payload_map_text === "string" && !next.webhook_payload_map && !parseJsonObjectText(next.webhook_payload_map_text).error) {
    next.webhook_payload_map = parseJsonObjectText(next.webhook_payload_map_text).value || {};
  }

  if (typeof next.mcp_server_id === "number" && !next.mcp_server_name) {
    const match = opts.mcpList.find((item) => item.id === next.mcp_server_id);
    if (match) next.mcp_server_name = match.name;
  }

  return next;
}

function isNodeType(value: string): value is NodeType {
  return value in nodeTypes;
}

function describeGraphPatch(graphPatch: StudioPipelineGraphPatch | null | undefined) {
  if (!graphPatch || (!graphPatch.nodes.length && !graphPatch.edges.length)) return null;
  return {
    nodeCount: graphPatch.nodes.length,
    edgeCount: graphPatch.edges.length,
    nodeLabels: graphPatch.nodes.map((item) => item.label || NODE_TYPE_LABELS[item.type]?.label || item.type),
    edgeLabels: graphPatch.edges.map((item) => `${item.source} -> ${item.target}${item.label ? ` (${item.label})` : ""}`),
  };
}

function PipelineAssistantDialog({
  open,
  onOpenChange,
  pipelineId,
  pipelineName,
  nodes,
  edges,
  selectedNode,
  onApplyPatch,
  onApplyGraphPatch,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pipelineId: number | null;
  pipelineName: string;
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  selectedNode: PipelineNode | null;
  onApplyPatch: (targetNodeId: string, patch: Record<string, unknown>) => void;
  onApplyGraphPatch: (graphPatch: StudioPipelineGraphPatch) => void;
}) {
  const { toast } = useToast();
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<AssistantMessage[]>([]);

  useEffect(() => {
    if (!open) return;
    setDraft("");
    setMessages([
      {
        id: `pipeline-assistant-intro-${pipelineId ?? "new"}`,
        role: "assistant",
        content: "I can review this pipeline, suggest targeted node patches, or generate the next part of the graph without changing the current UI layout.",
      },
    ]);
  }, [open, pipelineId]);

  const assistantMutation = useMutation({
    mutationFn: (message: string) =>
      studioPipelines.assistant({
        pipeline_id: pipelineId,
        pipeline_name: pipelineName || "Untitled",
        nodes,
        edges,
        selected_node: selectedNode,
        user_message: message,
      }),
    onSuccess: (result) => {
      setMessages((prev) => [
        ...prev,
        {
          id: `pipeline-assistant-${Date.now()}`,
          role: "assistant",
          content: result.reply,
          targetNodeId: result.target_node_id,
          nodePatch: result.node_patch,
          graphPatch: result.graph_patch,
          warnings: result.warnings,
        },
      ]);
    },
    onError: (error) => {
      toast({
        variant: "destructive",
        description: error instanceof Error ? error.message : "Pipeline assistant failed.",
      });
    },
  });

  const submitPrompt = async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || assistantMutation.isPending) return;
    setMessages((prev) => [
      ...prev,
      {
        id: `pipeline-user-${Date.now()}`,
        role: "user",
        content: trimmed,
      },
    ]);
    setDraft("");
    await assistantMutation.mutateAsync(trimmed);
  };

  const quickPrompts = [
    "Explain what this pipeline currently does.",
    "What looks weak or incomplete before production?",
    "Suggest the next nodes to add.",
    "Generate a starter graph patch for the next stage.",
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bot className="h-4 w-4" />
            Pipeline Assistant
          </DialogTitle>
          <DialogDescription>
            Ask for targeted node changes or a graph patch. The current strict UI stays the same; only the editor logic is restored.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline">Nodes: {nodes.length}</Badge>
            <Badge variant="outline">Edges: {edges.length}</Badge>
            {selectedNode ? <Badge variant="outline">Focus: {getNodeDisplayLabel(selectedNode)}</Badge> : null}
          </div>

          <div className="flex flex-wrap gap-2">
            {quickPrompts.map((prompt) => (
              <Button key={prompt} type="button" size="sm" variant="outline" className="h-auto py-1.5 text-[11px]" onClick={() => void submitPrompt(prompt)}>
                {prompt}
              </Button>
            ))}
          </div>

          <div className="rounded-md border border-border">
            <ScrollArea className="max-h-[50vh]">
              <div className="space-y-3 p-4">
                {messages.map((message) => {
                  const hasPatch = Boolean(message.nodePatch && Object.keys(message.nodePatch).length && message.targetNodeId);
                  const graphPatchSummary = describeGraphPatch(message.graphPatch);
                  return (
                    <div key={message.id} className="rounded-md border border-border bg-card px-4 py-3">
                      <div className="mb-2 flex items-center gap-2">
                        <Badge variant={message.role === "assistant" ? "outline" : "default"} className="text-[10px]">
                          {message.role === "assistant" ? "AI" : "You"}
                        </Badge>
                        {message.targetNodeId ? (
                          <Badge variant="outline" className="text-[10px]">
                            Target: {message.targetNodeId}
                          </Badge>
                        ) : null}
                      </div>
                      <div className="whitespace-pre-wrap text-sm leading-6">{message.content}</div>
                      {message.warnings?.length ? (
                        <div className="mt-3 space-y-1">
                          {message.warnings.map((warning) => (
                            <p key={warning} className="text-xs text-amber-300">
                              {warning}
                            </p>
                          ))}
                        </div>
                      ) : null}
                      {hasPatch ? (
                        <div className="mt-3 space-y-3">
                          <pre className="max-h-48 overflow-auto rounded-md border border-border bg-muted/30 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                            {JSON.stringify(message.nodePatch, null, 2)}
                          </pre>
                          <Button type="button" size="sm" className="gap-2" onClick={() => onApplyPatch(message.targetNodeId || "", message.nodePatch || {})}>
                            <Wand2 className="h-4 w-4" />
                            Apply node patch
                          </Button>
                        </div>
                      ) : null}
                      {graphPatchSummary ? (
                        <div className="mt-3 space-y-3">
                          <div className="rounded-md border border-border bg-muted/20 px-3 py-3 text-xs text-muted-foreground">
                            <p>{graphPatchSummary.nodeCount} node(s), {graphPatchSummary.edgeCount} edge(s)</p>
                            {graphPatchSummary.nodeLabels.length ? <p className="mt-1">Nodes: {graphPatchSummary.nodeLabels.join(", ")}</p> : null}
                            {graphPatchSummary.edgeLabels.length ? <p className="mt-1">Edges: {graphPatchSummary.edgeLabels.join(", ")}</p> : null}
                          </div>
                          <Button type="button" size="sm" variant="outline" className="gap-2" onClick={() => onApplyGraphPatch(message.graphPatch || { anchor_node_id: null, nodes: [], edges: [] })}>
                            <Sparkles className="h-4 w-4" />
                            Apply graph changes
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </ScrollArea>
          </div>

          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={4}
            placeholder="Ask about weak spots, missing nodes, MCP usage, or request a graph patch."
            className="text-sm resize-none"
          />
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button type="button" className="gap-2" disabled={!draft.trim() || assistantMutation.isPending} onClick={() => void submitPrompt(draft)}>
            {assistantMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Send
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NodeConfigPanel({
  node,
  pipelineId,
  trigger,
  onUpdate,
  onClose,
  onDelete,
}: {
  node: PipelineNode;
  pipelineId: number | null;
  trigger?: PipelineTrigger | null;
  onUpdate: (id: string, data: Record<string, unknown>) => void;
  onClose: () => void;
  onDelete: (id: string) => void;
}) {
  const { data: agents = [] } = useQuery({ queryKey: ["studio", "agents"], queryFn: studioAgents.list });
  const { data: servers = [] } = useQuery({ queryKey: ["studio", "servers"], queryFn: studioServers.list });
  const { data: mcpList = [] } = useQuery({ queryKey: ["studio", "mcp"], queryFn: studioMCP.list });
  const { data: skillList = [] } = useQuery({ queryKey: ["studio", "skills"], queryFn: studioSkills.list });
  const queryClient = useQueryClient();
  const { data: modelsData } = useQuery({ queryKey: ["api", "models"], queryFn: fetchModels });
  const [d, setD] = useState<Record<string, unknown>>(node.data || {});
  const [loadingModelsFor, setLoadingModelsFor] = useState<string | null>(null);
  const [webhookMapText, setWebhookMapText] = useState(() => toJsonEditorText(node.data?.webhook_payload_map));
  const [mcpArgsText, setMcpArgsText] = useState(
    () => (typeof node.data?.arguments_text === "string" ? String(node.data.arguments_text) : toJsonEditorText(node.data?.arguments || {})),
  );

  const set = (key: string, val: unknown) => {
    const next = { ...d, [key]: val };
    setD(next);
    onUpdate(node.id, next);
  };

  const setMany = (patch: Record<string, unknown>) => {
    const next = { ...d, ...patch };
    setD(next);
    onUpdate(node.id, next);
  };

  const type = node.type as NodeType;
  const provider =
    type === "agent/llm_query"
      ? ((d.provider as string) || "gemini")
      : type === "agent/react" || type === "agent/multi"
        ? ((d.provider as string) || "auto")
        : "";
  const modelProvider = provider && provider !== "auto" ? provider : "";
  const modelList = (modelProvider && modelsData && (modelsData as Record<string, string[] | undefined>)[modelProvider]) ?? [];
  const selectedAgent = agents.find((agent) => String(agent.id) === String(d.agent_config_id || ""));
  const selectedMcpId = d.mcp_server_id ? Number(d.mcp_server_id) : null;
  const selectedMcp = mcpList.find((mcp) => mcp.id === selectedMcpId) || null;
  const selectedSkillSlugs = Array.isArray(d.skill_slugs) ? (d.skill_slugs as string[]) : [];
  const selectedSkills = skillList.filter((skill) => selectedSkillSlugs.includes(skill.slug));
  const webhookState = parseJsonObjectText(webhookMapText);
  const mcpArgsState = parseJsonObjectText(mcpArgsText);

  useEffect(() => {
    setD(node.data || {});
    setWebhookMapText(toJsonEditorText(node.data?.webhook_payload_map));
    setMcpArgsText(
      typeof node.data?.arguments_text === "string"
        ? String(node.data.arguments_text)
        : toJsonEditorText(node.data?.arguments || {}),
    );
    setLoadingModelsFor(null);
  }, [node.id, node.data]);

  const { data: mcpInspection, isFetching: isFetchingMcpTools } = useQuery({
    queryKey: ["studio", "mcp", selectedMcpId, "tools"],
    queryFn: () => studioMCP.tools(selectedMcpId as number),
    enabled: type === "agent/mcp_call" && !!selectedMcpId,
  });
  const mcpTools = (mcpInspection as MCPServerInspection | undefined)?.tools || [];
  const selectedTool = mcpTools.find((tool) => tool.name === String(d.tool_name || "")) || null;

  const providerRef = useRef(provider);
  useEffect(() => {
    providerRef.current = provider;
  }, [provider]);

  useEffect(() => {
    if (!(type === "agent/llm_query" || type === "agent/react" || type === "agent/multi") || !modelProvider || !modelList.length) return;
    const current = (d.model as string) || "";
    if (current && !modelList.includes(current)) set("model", modelList[0]);
  }, [type, modelsData, modelProvider, modelList.length]);

  useEffect(() => {
    if (!(type === "agent/llm_query" || type === "agent/react" || type === "agent/multi") || !modelProvider || loadingModelsFor !== null) return;
    const list = (modelsData && (modelsData as Record<string, string[] | undefined>)[modelProvider]) ?? [];
    if (list.length > 0) return;
    const prov = modelProvider;
    setLoadingModelsFor(prov);
    refreshModels(prov as "gemini" | "grok" | "openai" | "claude")
      .then((res) => {
        queryClient.setQueryData(["api", "models"], (old: Record<string, unknown> | undefined) => ({
          ...(old ?? {}),
          [prov]: res.models,
        }));
        if (res.models.length && providerRef.current === prov) {
          const next = { ...d, provider: prov, model: res.models[0] };
          setD(next);
          onUpdate(node.id, next);
        }
      })
      .finally(() => setLoadingModelsFor(null));
  }, [type, modelProvider, modelsData]);

  const typeInfo = NODE_TYPE_LABELS[type] || { label: type, icon: "🔧" };
  const triggerWebhookUrl = trigger?.webhook_url ? new URL(trigger.webhook_url, window.location.origin).toString() : "";

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <span>{typeInfo.icon}</span>
          <span>{typeInfo.label}</span>
        </h3>
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive hover:text-destructive" onClick={() => onDelete(node.id)}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onClose}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        {/* Guidance */}
        {(() => {
          const guidance = getNodeTypeGuidance(type, "en");
          return (
            <div className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-2.5 space-y-1.5">
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-primary">
                <Info className="h-3 w-3" />
                {guidance.category} — {typeInfo.label}
              </div>
              <p className="text-[10px] text-muted-foreground leading-relaxed">{guidance.summary}</p>
              <ul className="space-y-0.5">
                {guidance.checklist.map((item, i) => (
                  <li key={i} className="text-[10px] text-muted-foreground flex items-start gap-1">
                    <span className="text-primary/60 mt-px">•</span> {item}
                  </li>
                ))}
              </ul>
            </div>
          );
        })()}

        {/* Common: label */}
        <div className="space-y-1.5">
          <Label className="text-xs">Label (optional)</Label>
          <Input value={(d.label as string) || ""} onChange={(e) => set("label", e.target.value)} placeholder="Node label" className="h-7 text-xs" />
        </div>

        {(type === "trigger/manual" || type === "trigger/webhook" || type === "trigger/schedule") && (
          <>
            <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 text-[11px] text-muted-foreground">
              Trigger settings are created from this node when you click <strong>Save</strong>.
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
              <div>
                <p className="text-xs font-medium">Trigger enabled</p>
                <p className="text-[10px] text-muted-foreground">Disable the start without deleting the node</p>
              </div>
              <Switch checked={(d.is_active as boolean) ?? true} onCheckedChange={(checked) => set("is_active", checked)} />
            </div>
          </>
        )}

        {type === "trigger/manual" && (
          <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 space-y-1">
            <p className="text-xs font-medium">Manual start</p>
            <p className="text-[11px] text-muted-foreground">
              Start this pipeline from the Studio <strong>Run</strong> button
              {pipelineId ? ` or POST /api/studio/pipelines/${pipelineId}/run/.` : "."}
            </p>
          </div>
        )}

        {type === "trigger/webhook" && (
          <>
            <div className="space-y-1.5">
              <Label className="text-xs">Webhook URL</Label>
              <div className="text-xs text-muted-foreground bg-muted/30 rounded px-2 py-1.5 break-all">
                {pipelineId && triggerWebhookUrl ? triggerWebhookUrl : "Save the pipeline once to generate the webhook URL"}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Payload mapping (JSON)</Label>
              <Textarea
                value={webhookMapText}
                onChange={(e) => {
                  const value = e.target.value;
                  setWebhookMapText(value);
                  const parsed = parseJsonObjectText(value);
                  if (!parsed.error) set("webhook_payload_map", parsed.value || {});
                }}
                placeholder={'{\n  "branch": "ref",\n  "commit": "head_commit.id"\n}'}
                className="text-xs font-mono resize-none"
                rows={6}
              />
              <p className="text-[10px] text-muted-foreground">
                Map incoming payload fields into pipeline variables, for example <code>head_commit.id</code>.
              </p>
              {webhookState.error && <p className="text-[10px] text-red-400">{webhookState.error}</p>}
            </div>
            {trigger && (
              <p className="text-[10px] text-muted-foreground">Last webhook run: {formatStudioDateTime(trigger.last_triggered_at)}</p>
            )}
          </>
        )}

        {type === "trigger/schedule" && (
          <>
            <div className="space-y-1.5">
              <Label className="text-xs">Quick presets</Label>
              <div className="flex flex-wrap gap-2">
                {CRON_PRESETS.map((preset) => (
                  <Button key={preset.value} type="button" size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => set("cron_expression", preset.value)}>
                    {preset.label}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Cron Expression</Label>
              <Input
                value={(d.cron_expression as string) || ""}
                onChange={(e) => set("cron_expression", e.target.value)}
                placeholder="*/5 * * * *"
                className="h-7 text-xs font-mono"
              />
              <p className="text-[10px] text-muted-foreground">Examples: <code>0 * * * *</code> (hourly), <code>0 0 * * *</code> (daily)</p>
            </div>
            {trigger && (
              <p className="text-[10px] text-muted-foreground">Last schedule run: {formatStudioDateTime(trigger.last_triggered_at)}</p>
            )}
          </>
        )}

        {/* Agent nodes */}
        {(type === "agent/react" || type === "agent/multi") && (
          <>
            <div className="space-y-1.5">
              <Label className="text-xs">Goal</Label>
              <Textarea
                value={(d.goal as string) || ""}
                onChange={(e) => set("goal", e.target.value)}
                placeholder="What should this agent accomplish?"
                className="text-xs resize-none"
                rows={3}
              />
              <p className="text-[10px] text-muted-foreground">Use {"{variable}"} for context substitution</p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Agent Config</Label>
              <Select
                value={(d.agent_config_id as string) || "__none__"}
                onValueChange={(v) => {
                  if (v === "__none__") {
                    setMany({ agent_config_id: null, agent_name: "" });
                    return;
                  }
                  const agent = agents.find((item) => String(item.id) === v);
                  setMany({ agent_config_id: v, agent_name: agent?.name || "" });
                }}
              >
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue placeholder="Configure directly in this pipeline" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Configure directly in this pipeline</SelectItem>
                  {agents.map((a) => (
                    <SelectItem key={a.id} value={String(a.id)}>{a.icon} {a.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {selectedAgent && (
              <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 space-y-2">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline" className="text-[10px]">{selectedAgent.model}</Badge>
                  <Badge variant="secondary" className="text-[10px]">{selectedAgent.max_iterations} iter</Badge>
                  {selectedAgent.mcp_servers?.length > 0 && <Badge variant="secondary" className="text-[10px]">{selectedAgent.mcp_servers.length} MCP</Badge>}
                  {selectedAgent.skills?.length > 0 && <Badge variant="secondary" className="text-[10px]">{selectedAgent.skills.length} skills</Badge>}
                </div>
                <p className="text-[10px] text-muted-foreground">
                  Saved agent config controls prompt, model, tools, attached MCP servers, and skill policies. This agent can invoke those MCP tools directly during the run.
                </p>
                {selectedAgent.skill_errors?.length ? (
                  <div className="space-y-1">
                    {selectedAgent.skill_errors.slice(0, 2).map((error) => (
                      <p key={error} className="text-[10px] text-amber-300">{error}</p>
                    ))}
                  </div>
                ) : null}
              </div>
            )}
            {!(d.agent_config_id) && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">System Prompt</Label>
                  <Textarea
                    value={(d.system_prompt as string) || ""}
                    onChange={(e) => set("system_prompt", e.target.value)}
                    placeholder="You are a DevOps agent..."
                    className="text-xs resize-none"
                    rows={2}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Provider</Label>
                    <Select
                      value={provider || "auto"}
                      onValueChange={(nextProvider) => {
                        if (nextProvider === "auto") {
                          setMany({ provider: "auto", model: "" });
                          return;
                        }
                        set("provider", nextProvider);
                        setLoadingModelsFor(nextProvider);
                        refreshModels(nextProvider as "gemini" | "grok" | "openai" | "claude")
                          .then((res) => {
                            queryClient.setQueryData(["api", "models"], (old: Record<string, unknown> | undefined) => ({
                              ...(old ?? {}),
                              [nextProvider]: res.models,
                            }));
                            if (res.models.length && providerRef.current === nextProvider) {
                              setMany({ provider: nextProvider, model: res.models[0] });
                            }
                          })
                          .finally(() => setLoadingModelsFor(null));
                      }}
                    >
                      <SelectTrigger className="h-7 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {AGENT_PROVIDER_OPTIONS.map((item) => (
                          <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Model</Label>
                    {provider === "auto" ? (
                      <div className="h-7 rounded-md border border-border bg-muted/30 px-2 flex items-center text-[11px] text-muted-foreground">
                        Uses the global default agent model
                      </div>
                    ) : (
                      <Select value={(d.model as string) || ""} onValueChange={(v) => set("model", v)} disabled={loadingModelsFor === provider}>
                        <SelectTrigger className="h-7 text-xs">
                          <SelectValue placeholder={loadingModelsFor === provider ? "Loading models..." : "Select model"} />
                        </SelectTrigger>
                        <SelectContent>
                          {modelList.length
                            ? modelList.map((model) => <SelectItem key={model} value={model}>{model}</SelectItem>)
                            : <SelectItem value="_empty" disabled>No models available</SelectItem>}
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Max Iterations</Label>
                  <Input
                    type="number"
                    value={(d.max_iterations as number) || 10}
                    onChange={(e) => set("max_iterations", parseInt(e.target.value) || 10)}
                    className="h-7 text-xs"
                    min={1}
                    max={50}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">MCP Servers</Label>
                  <div className="space-y-1">
                    {((d.mcp_server_ids as number[]) || []).map((mcpId) => {
                      const mcp = mcpList.find((item) => item.id === mcpId);
                      return (
                        <div key={mcpId} className="flex items-center justify-between bg-muted/30 rounded px-2 py-1 text-xs">
                          <span>{mcp?.name || `MCP #${mcpId}`}</span>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-5 w-5"
                            onClick={() => set("mcp_server_ids", ((d.mcp_server_ids as number[]) || []).filter((id) => id !== mcpId))}
                          >
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                      );
                    })}
                    <Select
                      onValueChange={(value) => {
                        const ids = ((d.mcp_server_ids as number[]) || []);
                        const nextId = parseInt(value);
                        if (!ids.includes(nextId)) set("mcp_server_ids", [...ids, nextId]);
                      }}
                    >
                      <SelectTrigger className="h-7 text-xs">
                        <SelectValue placeholder="Add MCP server..." />
                      </SelectTrigger>
                      <SelectContent>
                        {mcpList.map((mcp) => (
                          <SelectItem key={mcp.id} value={String(mcp.id)}>
                            {mcp.name} ({mcp.transport})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    Attached MCP servers expose their tools directly to this agent at runtime.
                  </p>
                </div>
              </>
            )}
            <div className="space-y-1.5">
              <Label className="text-xs">Target Servers</Label>
              <div className="space-y-1">
                {((d.server_ids as number[]) || []).map((sid) => {
                  const srv = servers.find((s) => s.id === sid);
                  return (
                    <div key={sid} className="flex items-center justify-between bg-muted/30 rounded px-2 py-1 text-xs">
                      <span>{srv?.name || `Server #${sid}`}</span>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-5 w-5"
                        onClick={() => set("server_ids", ((d.server_ids as number[]) || []).filter((id) => id !== sid))}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  );
                })}
                <Select
                  onValueChange={(v) => {
                    const ids = ((d.server_ids as number[]) || []);
                    const n = parseInt(v);
                    if (!ids.includes(n)) set("server_ids", [...ids, n]);
                  }}
                >
                  <SelectTrigger className="h-7 text-xs">
                    <SelectValue placeholder="Add server..." />
                  </SelectTrigger>
                  <SelectContent>
                    {servers.map((s) => (
                      <SelectItem key={s.id} value={String(s.id)}>{s.name} ({s.host})</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {skillList.length > 0 && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <Label className="text-xs">{selectedAgent ? "Extra Skills" : "Skills / Policies"}</Label>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 gap-1.5 text-[11px]"
                    onClick={() => navigate("/studio/skills")}
                  >
                    <BookOpen className="h-3 w-3" />
                    Browse Catalog
                  </Button>
                </div>
                <p className="text-[10px] text-muted-foreground">
                  {selectedAgent
                    ? "These node-level skills are merged with the selected agent config at runtime."
                    : "Attach service playbooks, guardrails, and runtime policy directly to this node."}
                </p>
                <div className="space-y-1">
                  {skillList.map((skill) => (
                    <label key={skill.slug} className="flex items-start gap-2 cursor-pointer rounded border border-border px-2 py-2 hover:bg-muted/30 transition-colors">
                      <input
                        type="checkbox"
                        className="mt-0.5 h-3.5 w-3.5 rounded border-border bg-background"
                        checked={selectedSkillSlugs.includes(skill.slug)}
                        onChange={() => {
                          const next = selectedSkillSlugs.includes(skill.slug)
                            ? selectedSkillSlugs.filter((item) => item !== skill.slug)
                            : [...selectedSkillSlugs, skill.slug];
                          set("skill_slugs", next);
                        }}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-xs font-medium">{skill.name}</span>
                          {skill.service ? <Badge variant="outline" className="text-[9px]">{skill.service}</Badge> : null}
                          {skill.runtime_enforced ? <Badge variant="secondary" className="text-[9px]">runtime</Badge> : null}
                          {skill.safety_level ? <Badge variant="outline" className="text-[9px]">{skill.safety_level}</Badge> : null}
                        </div>
                        {skill.guardrail_summary?.length ? (
                          <p className="mt-1 text-[10px] text-muted-foreground">{skill.guardrail_summary.slice(0, 2).join(" • ")}</p>
                        ) : null}
                      </div>
                    </label>
                  ))}
                </div>
                {selectedSkills.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {selectedSkills.map((skill) => (
                      <span key={skill.slug} className="text-[9px] bg-muted/60 rounded px-1 py-0.5 text-muted-foreground">
                        {skill.name}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            )}
            <div className="space-y-1.5">
              <Label className="text-xs">On Failure</Label>
              <Select value={(d.on_failure as string) || "abort"} onValueChange={(v) => set("on_failure", v)}>
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="abort">Abort pipeline</SelectItem>
                  <SelectItem value="continue">Continue</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </>
        )}

        {/* SSH Command */}
        {type === "agent/ssh_cmd" && (
          <>
            <div className="space-y-1.5">
              <Label className="text-xs">Target Server</Label>
              <Select value={String(d.server_id || "")} onValueChange={(v) => set("server_id", parseInt(v))}>
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue placeholder="Select server..." />
                </SelectTrigger>
                <SelectContent>
                  {servers.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>{s.name} ({s.host})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Command</Label>
              <Textarea
                value={(d.command as string) || ""}
                onChange={(e) => set("command", e.target.value)}
                placeholder="df -h && free -h"
                className="text-xs font-mono resize-none"
                rows={3}
              />
            </div>
          </>
        )}

        {/* Condition */}
        {type === "logic/condition" && (
          <>
            <div className="space-y-1.5">
              <Label className="text-xs">Check Type</Label>
              <Select value={(d.check_type as string) || "contains"} onValueChange={(v) => set("check_type", v)}>
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="contains">Output contains</SelectItem>
                  <SelectItem value="not_contains">Output does not contain</SelectItem>
                  <SelectItem value="status_ok">Previous node succeeded</SelectItem>
                  <SelectItem value="status_failed">Previous node failed</SelectItem>
                  <SelectItem value="always_true">Always true</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {((d.check_type as string) || "contains").includes("contains") && (
              <div className="space-y-1.5">
                <Label className="text-xs">Check Value</Label>
                <Input
                  value={(d.check_value as string) || ""}
                  onChange={(e) => set("check_value", e.target.value)}
                  placeholder="error"
                  className="h-7 text-xs"
                />
              </div>
            )}
          </>
        )}

        {/* Output/Webhook */}
        {type === "output/webhook" && (
          <div className="space-y-1.5">
            <Label className="text-xs">Webhook URL</Label>
            <Input
              value={(d.url as string) || ""}
              onChange={(e) => set("url", e.target.value)}
              placeholder="https://hooks.example.com/..."
              className="h-7 text-xs"
            />
          </div>
        )}

        {/* Output/Report */}
        {type === "output/report" && (
          <div className="space-y-1.5">
            <Label className="text-xs">Report Template (optional)</Label>
            <Textarea
              value={(d.template as string) || ""}
              onChange={(e) => set("template", e.target.value)}
              placeholder="# Report\n\n{node_id_output}"
              className="text-xs font-mono resize-none"
              rows={4}
            />
            <p className="text-[10px] text-muted-foreground">Leave empty for auto-generated report</p>
          </div>
        )}

        {/* LLM Query */}
        {type === "agent/llm_query" && (
          <>
            <div className="space-y-1.5">
              <Label className="text-xs">Prompt</Label>
              <Textarea
                value={(d.prompt as string) || ""}
                onChange={(e) => set("prompt", e.target.value)}
                placeholder="Analyze the data from previous steps and provide recommendations..."
                className="text-xs resize-none"
                rows={5}
              />
              <p className="text-[10px] text-muted-foreground">
                Use <code>{"{all_outputs}"}</code> for all previous node outputs, or <code>{"{node_id}"}</code> for a specific node
              </p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">System Prompt</Label>
              <Textarea
                value={(d.system_prompt as string) || ""}
                onChange={(e) => set("system_prompt", e.target.value)}
                placeholder="You are a senior DevOps engineer..."
                className="text-xs resize-none"
                rows={2}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Provider</Label>
                <Select
                  value={(d.provider as string) || "gemini"}
                  onValueChange={(nextProvider) => {
                    set("provider", nextProvider);
                    setLoadingModelsFor(nextProvider);
                    refreshModels(nextProvider as "gemini" | "grok" | "openai" | "claude")
                      .then((res) => {
                        queryClient.setQueryData(["api", "models"], (old: Record<string, unknown> | undefined) => ({
                          ...(old ?? {}),
                          [nextProvider]: res.models,
                        }));
                        if (res.models.length && providerRef.current === nextProvider) {
                          setMany({ provider: nextProvider, model: res.models[0] });
                        }
                      })
                      .finally(() => setLoadingModelsFor(null));
                  }}
                >
                  <SelectTrigger className="h-7 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DIRECT_LLM_PROVIDERS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Model</Label>
                <Select value={(d.model as string) || ""} onValueChange={(v) => set("model", v)} disabled={loadingModelsFor === provider}>
                  <SelectTrigger className="h-7 text-xs">
                    <SelectValue placeholder={loadingModelsFor === provider ? "Loading models..." : "Select model"} />
                  </SelectTrigger>
                  <SelectContent>
                    {modelList.length
                      ? modelList.map((model) => <SelectItem key={model} value={model}>{model}</SelectItem>)
                      : <SelectItem value="_empty" disabled>No models available</SelectItem>}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <p className="text-[10px] text-muted-foreground">
              Output is available for next nodes as <code>{`{${node.id}}`}</code> and <code>{`{${node.id}_output}`}</code>
            </p>
          </>
        )}

        {type === "agent/mcp_call" && (
          <>
            <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 text-[11px] text-muted-foreground">
              Use this node when the pipeline must call a specific MCP tool directly, without waiting for an LLM or agent to decide.
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">MCP Server</Label>
              <Select
                value={selectedMcpId ? String(selectedMcpId) : "__none__"}
                onValueChange={(value) => {
                  if (value === "__none__") {
                    setMany({ mcp_server_id: null, mcp_server_name: "", tool_name: "", arguments_text: "{}", arguments: {} });
                    setMcpArgsText("{}");
                    return;
                  }
                  const nextMcp = mcpList.find((item) => String(item.id) === value);
                  setMany({ mcp_server_id: Number(value), mcp_server_name: nextMcp?.name || "", tool_name: "" });
                }}
              >
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue placeholder="Select MCP server..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Select MCP server...</SelectItem>
                  {mcpList.map((mcp) => (
                    <SelectItem key={mcp.id} value={String(mcp.id)}>
                      {mcp.name} ({mcp.transport})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedMcp && (
                <p className="text-[10px] text-muted-foreground">
                  {selectedMcp.last_test_ok === true ? "Last connection test passed." : selectedMcp.last_test_ok === false ? "Last connection test failed." : "Server has not been tested yet."}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Tool</Label>
              <Select
                value={(d.tool_name as string) || "__none__"}
                onValueChange={(value) => {
                  const tool = mcpTools.find((item) => item.name === value);
                  if (!tool) {
                    set("tool_name", "");
                    return;
                  }
                  const shouldSeedArgs = !String(d.arguments_text || "").trim() || String(d.arguments_text || "").trim() === "{}";
                  if (shouldSeedArgs) {
                    const template = buildSchemaTemplate(tool.inputSchema);
                    const text = JSON.stringify(template, null, 2);
                    setMcpArgsText(text);
                    setMany({ tool_name: tool.name, arguments_text: text, arguments: template });
                    return;
                  }
                  set("tool_name", tool.name);
                }}
                disabled={!selectedMcpId || isFetchingMcpTools}
              >
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue placeholder={isFetchingMcpTools ? "Loading tools..." : "Select tool"} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__" disabled>Select tool</SelectItem>
                  {mcpTools.map((tool) => (
                    <SelectItem key={tool.name} value={tool.name}>{tool.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {selectedTool && (
              <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 space-y-2">
                {selectedTool.description && <p className="text-xs">{selectedTool.description}</p>}
                {selectedTool.inputSchema && (
                  <pre className="text-[10px] text-muted-foreground whitespace-pre-wrap break-all max-h-40 overflow-auto">
                    {JSON.stringify(selectedTool.inputSchema, null, 2)}
                  </pre>
                )}
              </div>
            )}
            <div className="space-y-1.5">
              <Label className="text-xs">Arguments (JSON)</Label>
              <Textarea
                value={mcpArgsText}
                onChange={(e) => {
                  const value = e.target.value;
                  setMcpArgsText(value);
                  const parsed = parseJsonObjectText(value);
                  if (!parsed.error) setMany({ arguments_text: value, arguments: parsed.value || {} });
                  else setMany({ arguments_text: value, arguments: null });
                }}
                placeholder={'{\n  "path": "{repo_path}"\n}'}
                className="text-xs font-mono resize-none"
                rows={8}
              />
              <p className="text-[10px] text-muted-foreground">
                Arguments support pipeline variables like <code>{"{branch}"}</code> and <code>{"{node_2_output}"}</code>.
              </p>
              {mcpArgsState.error && <p className="text-[10px] text-red-400">{mcpArgsState.error}</p>}
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">On Failure</Label>
              <Select value={(d.on_failure as string) || "abort"} onValueChange={(value) => set("on_failure", value)}>
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="abort">Abort pipeline</SelectItem>
                  <SelectItem value="continue">Continue</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </>
        )}

        {/* Email Output */}
        {type === "output/email" && (
          <>
            <div className="space-y-1.5">
              <Label className="text-xs">To Email(s)</Label>
              <Input
                value={(d.to_email as string) || ""}
                onChange={(e) => set("to_email", e.target.value)}
                placeholder="admin@example.com, team@example.com"
                className="h-7 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Subject</Label>
              <Input
                value={(d.subject as string) || ""}
                onChange={(e) => set("subject", e.target.value)}
                placeholder="Pipeline Report: {pipeline_name}"
                className="h-7 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Body Template (optional)</Label>
              <Textarea
                value={(d.body as string) || ""}
                onChange={(e) => set("body", e.target.value)}
                placeholder="# Report\n\n{all_outputs}"
                className="text-xs font-mono resize-none"
                rows={3}
              />
              <p className="text-[10px] text-muted-foreground">Leave empty for auto-generated body</p>
            </div>
            <div className="border-t border-border pt-3 space-y-1.5">
              <Label className="text-xs text-muted-foreground uppercase">SMTP Settings (override Django settings)</Label>
              <Input
                value={(d.smtp_host as string) || ""}
                onChange={(e) => set("smtp_host", e.target.value)}
                placeholder="smtp.gmail.com"
                className="h-7 text-xs"
              />
              <div className="flex gap-2">
                <Input
                  value={(d.smtp_user as string) || ""}
                  onChange={(e) => set("smtp_user", e.target.value)}
                  placeholder="user@gmail.com"
                  className="h-7 text-xs flex-1"
                />
                <Input
                  value={(d.smtp_password as string) || ""}
                  onChange={(e) => set("smtp_password", e.target.value)}
                  placeholder="app password"
                  type="password"
                  className="h-7 text-xs w-28"
                />
              </div>
            </div>
          </>
        )}

        {/* Wait */}
        {type === "logic/wait" && (
          <div className="space-y-1.5">
            <Label className="text-xs">Wait Duration (minutes)</Label>
            <Input
              type="number"
              value={(d.wait_minutes as number) ?? 20}
              onChange={(e) => set("wait_minutes", parseFloat(e.target.value) || 1)}
              className="h-7 text-xs"
              min={0.1}
              max={1440}
              step={0.5}
            />
            <p className="text-[10px] text-muted-foreground">Range: 0.1 – 1440 minutes (24h max)</p>
          </div>
        )}

        {/* Human Approval */}
        {type === "logic/human_approval" && (
          <>
            <div className="space-y-1.5">
              <Label className="text-xs">Кому (email)</Label>
              <Input
                value={(d.to_email as string) || ""}
                onChange={(e) => set("to_email", e.target.value)}
                placeholder="или из Studio → Notifications"
                className="h-7 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Тема письма (шаблон)</Label>
              <Input
                value={(d.email_subject as string) || ""}
                onChange={(e) => set("email_subject", e.target.value)}
                placeholder="Пусто = тема по умолчанию"
                className="h-7 text-xs"
              />
              <p className="text-[10px] text-muted-foreground">
                Переменные: {"{pipeline_name}"}, {"{run_id}"}
              </p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Текст письма (шаблон)</Label>
              <Textarea
                value={(d.email_body as string) || ""}
                onChange={(e) => set("email_body", e.target.value)}
                placeholder="Пусто = текст по умолчанию. Переменные ниже."
                className="text-xs resize-none"
                rows={8}
              />
              <p className="text-[10px] text-muted-foreground">
                {"{approve_url}"}, {"{reject_url}"}, {"{all_outputs}"}, {"{timeout_minutes}"}
              </p>
            </div>
            <div className="border-t border-border pt-3 space-y-1.5">
              <Label className="text-xs text-muted-foreground uppercase">Telegram</Label>
              <Input
                value={(d.tg_bot_token as string) || ""}
                onChange={(e) => set("tg_bot_token", e.target.value)}
                placeholder="Bot Token (from @BotFather)"
                className="h-7 text-xs font-mono"
              />
              <Input
                value={(d.tg_chat_id as string) || ""}
                onChange={(e) => set("tg_chat_id", e.target.value)}
                placeholder="Chat ID (e.g. -100123456)"
                className="h-7 text-xs font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Base URL (for approval links)</Label>
              <Input
                value={(d.base_url as string) || ""}
                onChange={(e) => set("base_url", e.target.value)}
                placeholder="https://your-server.example.com"
                className="h-7 text-xs"
              />
              <p className="text-[10px] text-muted-foreground">Used in approve/reject URLs sent in notifications</p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Timeout (minutes)</Label>
              <Input
                type="number"
                value={(d.timeout_minutes as number) ?? 120}
                onChange={(e) => set("timeout_minutes", parseFloat(e.target.value) || 120)}
                className="h-7 text-xs"
                min={5}
                max={10080}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Сообщение в Telegram (шаблон)</Label>
              <Textarea
                value={(d.message as string) || ""}
                onChange={(e) => set("message", e.target.value)}
                placeholder="{approve_url}, {reject_url}..."
                className="text-xs resize-none"
                rows={4}
              />
            </div>
            <div className="border-t border-border pt-3 space-y-1.5">
              <Label className="text-xs text-muted-foreground uppercase">SMTP (for approval email)</Label>
              <Input
                value={(d.smtp_host as string) || ""}
                onChange={(e) => set("smtp_host", e.target.value)}
                placeholder="smtp.gmail.com"
                className="h-7 text-xs"
              />
              <div className="flex gap-2">
                <Input
                  value={(d.smtp_user as string) || ""}
                  onChange={(e) => set("smtp_user", e.target.value)}
                  placeholder="user@gmail.com"
                  className="h-7 text-xs flex-1"
                />
                <Input
                  value={(d.smtp_password as string) || ""}
                  onChange={(e) => set("smtp_password", e.target.value)}
                  placeholder="app password"
                  type="password"
                  className="h-7 text-xs w-28"
                />
              </div>
            </div>
          </>
        )}

        {/* Telegram Output */}
        {type === "output/telegram" && (
          <>
            <div className="space-y-1.5">
              <Label className="text-xs">Bot Token</Label>
              <Input
                value={(d.bot_token as string) || ""}
                onChange={(e) => set("bot_token", e.target.value)}
                placeholder="1234567890:AAF..."
                className="h-7 text-xs font-mono"
              />
              <p className="text-[10px] text-muted-foreground">Get from @BotFather on Telegram</p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Chat ID</Label>
              <Input
                value={(d.chat_id as string) || ""}
                onChange={(e) => set("chat_id", e.target.value)}
                placeholder="-100123456789"
                className="h-7 text-xs font-mono"
              />
              <p className="text-[10px] text-muted-foreground">
                Use @userinfobot or @getidsbot to find your chat ID
              </p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Message Template (optional)</Label>
              <Textarea
                value={(d.message as string) || ""}
                onChange={(e) => set("message", e.target.value)}
                placeholder="📊 *{pipeline_name}*\n\n{all_outputs}"
                className="text-xs resize-none"
                rows={4}
              />
              <p className="text-[10px] text-muted-foreground">
                Supports Markdown. Variables: <code>{"{all_outputs}"}</code>,{" "}
                <code>{"{node_id_output}"}</code>
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Node Palette (left panel) — with search, drag, category icons
// ---------------------------------------------------------------------------
const CATEGORY_ICONS: Record<string, string> = {
  Triggers: "🚀",
  Agents: "🤖",
  Logic: "⚙️",
  Output: "📤",
};

function NodePalette({ onAddNode }: { onAddNode: (type: NodeType) => void }) {
  const [search, setSearch] = useState("");
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set(NODE_PALETTE.map((c) => c.category)));

  const toggleCat = (cat: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const filtered = NODE_PALETTE.map((cat) => ({
    ...cat,
    nodes: cat.nodes.filter(
      (n) =>
        !search.trim() ||
        n.label.toLowerCase().includes(search.toLowerCase()) ||
        n.description.toLowerCase().includes(search.toLowerCase()),
    ),
  })).filter((cat) => cat.nodes.length > 0);

  return (
    <div className="flex flex-col h-full border-r border-border bg-card">
      <div className="px-3 py-3 border-b border-border space-y-2">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
          <Plus className="h-3 w-3" /> Add Node
        </h3>
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search nodes..."
          className="h-7 text-xs"
        />
      </div>
      <div className="flex-1 overflow-auto p-2 space-y-1">
        {filtered.map((cat) => (
          <div key={cat.category}>
            <button
              onClick={() => toggleCat(cat.category)}
              className="w-full text-left flex items-center gap-1.5 px-1 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase hover:text-foreground transition-colors"
            >
              <span>{CATEGORY_ICONS[cat.category] || "📦"}</span>
              <span className="flex-1">{cat.category}</span>
              <span className="text-[9px] font-normal bg-muted/50 rounded px-1">{cat.nodes.length}</span>
              {expandedCats.has(cat.category) ? (
                <ChevronUp className="h-2.5 w-2.5" />
              ) : (
                <ChevronDown className="h-2.5 w-2.5" />
              )}
            </button>
            {expandedCats.has(cat.category) && cat.nodes.map((node) => (
              <button
                key={node.type}
                onClick={() => onAddNode(node.type)}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("application/pipeline-node-type", node.type);
                  e.dataTransfer.effectAllowed = "copy";
                }}
                className="w-full text-left flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-primary/5 border border-transparent hover:border-border/50 transition-all group cursor-grab active:cursor-grabbing"
                title={node.description}
              >
                <span className="text-base h-8 w-8 flex items-center justify-center rounded-lg bg-muted/40 group-hover:bg-primary/10 transition-colors shrink-0">
                  {node.icon}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-foreground truncate">{node.label}</div>
                  <div className="text-[10px] text-muted-foreground truncate leading-tight mt-0.5">{node.description}</div>
                </div>
                <Plus className="h-3.5 w-3.5 ml-auto text-primary opacity-0 group-hover:opacity-100 shrink-0 transition-opacity" />
              </button>
            ))}
          </div>
        ))}
        {filtered.length === 0 && search.trim() && (
          <p className="text-[11px] text-muted-foreground text-center py-4">No nodes match "{search}"</p>
        )}
      </div>
      <div className="px-3 py-2 border-t border-border">
        <p className="text-[9px] text-muted-foreground text-center">Click or drag nodes to canvas</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Editor (needs ReactFlowProvider)
// ---------------------------------------------------------------------------
function PipelineEditorInner({ pipelineId }: { pipelineId: number | null }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { screenToFlowPosition, fitView } = useReactFlow();
  const lang =
    typeof document !== "undefined" && document.documentElement.lang.toLowerCase().startsWith("ru")
      ? "ru"
      : "en";

  const { data: pipeline, isLoading } = useQuery({
    queryKey: ["studio", "pipeline", pipelineId],
    queryFn: () => (pipelineId ? studioPipelines.get(pipelineId) : null),
    enabled: !!pipelineId,
  });
  const { data: pipelineCopilotMcpList = [] } = useQuery({ queryKey: ["studio", "mcp"], queryFn: studioMCP.list });

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<PipelineNode | null>(null);
  const [pipelineName, setPipelineName] = useState("");
  const [lastRun, setLastRun] = useState<PipelineRun | null>(null);
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [pipelineCopilotOpen, setPipelineCopilotOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(true);
  const [runTaskText, setRunTaskText] = useState("");
  const [runRequester, setRunRequester] = useState("");
  const [runTicketId, setRunTicketId] = useState("");
  const [runAdvancedOpen, setRunAdvancedOpen] = useState(false);
  const [runContextText, setRunContextText] = useState("{}");
  const [runContextError, setRunContextError] = useState<string | null>(null);
  const nodeIdCounter = useRef(1);

  // Load pipeline data
  useEffect(() => {
    if (pipeline) {
      setPipelineName(pipeline.name);
      setNodes((pipeline.nodes || []) as never[]);
      setEdges((pipeline.edges || []) as never[]);
      if (pipeline.nodes?.length) {
        const maxId = pipeline.nodes.reduce((max, n) => {
          const num = parseInt(n.id.replace(/\D/g, "") || "0");
          return Math.max(max, num);
        }, 0);
        nodeIdCounter.current = maxId + 1;
        // Fit view after nodes load
        setTimeout(() => fitView({ padding: 0.15, duration: 300 }), 100);
      }
    }
  }, [pipeline, setNodes, setEdges, fitView]);

  const saveMutation = useMutation({
    mutationFn: (data: { nodes: PipelineNode[]; edges: PipelineEdge[]; name: string }) =>
      pipelineId
        ? studioPipelines.update(pipelineId, data)
        : studioPipelines.create({ ...data, icon: "⚡" }),
    onSuccess: (p) => {
      queryClient.setQueryData(["studio", "pipeline", p.id], p);
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      queryClient.invalidateQueries({ queryKey: ["studio", "pipeline", p.id] });
      toast({ description: "Pipeline saved" });
      if (!pipelineId) navigate(`/studio/pipeline/${p.id}`, { replace: true });
    },
    onError: (err: Error) => toast({ variant: "destructive", description: err.message }),
  });

  const runMutation = useMutation({
    mutationFn: ({ targetPipelineId, context }: { targetPipelineId: number; context: Record<string, unknown> }) =>
      studioPipelines.run(targetPipelineId, context),
    onSuccess: (run) => {
      setLastRun(run);
      setActiveRunId(run.id);
      setSelectedNode(null);
      setRunDialogOpen(false);
      setRunTaskText("");
      setRunRequester("");
      setRunTicketId("");
      setRunAdvancedOpen(false);
      setRunContextText("{}");
      setRunContextError(null);
      toast({ description: `Pipeline started — run #${run.id}` });
    },
    onError: (err: Error) => toast({ variant: "destructive", description: err.message }),
  });

  const handleSave = () => {
    saveMutation.mutate({
      name: pipelineName || "Untitled",
      nodes: nodes as unknown as PipelineNode[],
      edges: edges as unknown as PipelineEdge[],
    });
  };

  const handleRunSubmit = async () => {
    const parsedContext = parseJsonObjectText(runContextText);
    if (parsedContext.error) {
      setRunContextError(parsedContext.error);
      return;
    }
    setRunContextError(null);

    const context: Record<string, unknown> = {
      ...(parsedContext.value || {}),
    };
    if (runTaskText.trim()) context.task = runTaskText.trim();
    if (runRequester.trim()) context.requester = runRequester.trim();
    if (runTicketId.trim()) context.ticket_id = runTicketId.trim();

    try {
      const saved = await saveMutation.mutateAsync({
        name: pipelineName || "Untitled",
        nodes: nodes as unknown as PipelineNode[],
        edges: edges as unknown as PipelineEdge[],
      });
      await runMutation.mutateAsync({ targetPipelineId: pipelineId ?? saved.id, context });
    } catch {
      // Error notifications are handled in mutation callbacks.
    }
  };

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      setEdges((eds) => addEdge(connection, eds));

      const sourceNode = (nodes as unknown as PipelineNode[]).find((item) => item.id === connection.source);
      const targetNode = (nodes as unknown as PipelineNode[]).find((item) => item.id === connection.target);
      if (!targetNode) return;

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
      toast({ description: `${getNodeDisplayLabel(nextTarget)} picked up starter settings from the connection.` });
    },
    [nodes, pipelineName, setEdges, setNodes, toast],
  );

  const onNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      setActiveRunId(null);
      setSelectedNode(node as unknown as PipelineNode);
    },
    [],
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
      setNodes((nds) => [...nds, newNode as never]);
      setActiveRunId(null);
      setSelectedNode(newNode as PipelineNode);
    },
    [nodes, selectedNode, setNodes, screenToFlowPosition],
  );

  const handleUpdateNodeData = useCallback(
    (nodeId: string, data: Record<string, unknown>) => {
      setNodes((nds) =>
        nds.map((n) => (n.id === nodeId ? { ...n, data } : n)),
      );
      setSelectedNode((prev) => (prev?.id === nodeId ? { ...prev, data } : prev));
    },
    [setNodes],
  );

  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== nodeId));
      setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      setActiveRunId(null);
      setSelectedNode(null);
    },
    [setNodes, setEdges],
  );

  const handleApplyPipelineAssistantPatch = useCallback(
    (targetNodeId: string, patch: Record<string, unknown>) => {
      if (!targetNodeId || !Object.keys(patch).length) return;
      const normalized = normaliseAssistantPatch(patch, {
        mcpList: pipelineCopilotMcpList.map((item) => ({ id: item.id, name: item.name })),
      });
      const targetNode = (nodes as unknown as PipelineNode[]).find((item) => item.id === targetNodeId);
      if (!targetNode) {
        toast({ variant: "destructive", description: `Node ${targetNodeId} was not found.` });
        return;
      }

      const merged = { ...(targetNode.data || {}), ...normalized };
      setNodes((nds) => nds.map((item) => (item.id === targetNodeId ? ({ ...item, data: merged } as never) : item)));
      setActiveRunId(null);
      setSelectedNode({ ...targetNode, data: merged });
      toast({ description: `AI suggestion applied to ${getNodeDisplayLabel({ ...targetNode, data: merged })}.` });
    },
    [nodes, pipelineCopilotMcpList, setNodes, toast],
  );

  const handleApplyPipelineAssistantGraphPatch = useCallback(
    (graphPatch: StudioPipelineGraphPatch) => {
      if (!graphPatch.nodes.length && !graphPatch.edges.length) {
        toast({ description: "This suggestion does not include graph changes." });
        return;
      }

      const existingNodes = nodes as unknown as PipelineNode[];
      const existingNodeIds = new Set(existingNodes.map((item) => item.id));
      const anchorNode =
        existingNodes.find((item) => item.id === graphPatch.anchor_node_id) ||
        (selectedNode ? existingNodes.find((item) => item.id === selectedNode.id) : null) ||
        existingNodes[existingNodes.length - 1] ||
        null;
      const anchorPosition = anchorNode?.position || screenToFlowPosition({ x: 420, y: 260 });

      const refToId = new Map<string, string>();
      const createdNodes: PipelineNode[] = [];
      graphPatch.nodes.forEach((spec, index) => {
        if (!spec.ref || !isNodeType(spec.type)) return;
        const newId = `node_${nodeIdCounter.current++}`;
        refToId.set(spec.ref, newId);
        const data = {
          ...buildDefaultNodeData(spec.type),
          ...(spec.data || {}),
        };
        if (spec.label && !String(data.label || "").trim()) data.label = spec.label;
        createdNodes.push({
          id: newId,
          type: spec.type,
          position: {
            x: anchorPosition.x + (typeof spec.x_offset === "number" ? spec.x_offset : 280 * (index + 1)),
            y: anchorPosition.y + (typeof spec.y_offset === "number" ? spec.y_offset : (index % 3) * 120),
          },
          data,
        });
      });

      const resolveNodeId = (token: string) => {
        if (!token) return null;
        if (refToId.has(token)) return refToId.get(token) || null;
        if (existingNodeIds.has(token)) return token;
        return null;
      };

      const existingEdgeKeys = new Set((edges as unknown as PipelineEdge[]).map((edge) => `${edge.source}:${edge.target}:${edge.label || ""}`));
      const createdEdges: PipelineEdge[] = [];
      graphPatch.edges.forEach((spec, index) => {
        const source = resolveNodeId(spec.source);
        const target = resolveNodeId(spec.target);
        if (!source || !target) return;
        const edgeKey = `${source}:${target}:${spec.label || ""}`;
        if (existingEdgeKeys.has(edgeKey)) return;
        existingEdgeKeys.add(edgeKey);
        createdEdges.push({
          id: `edge_${Date.now()}_${index}_${source}_${target}`,
          source,
          target,
          label: spec.label,
          sourceHandle: spec.source_handle,
          targetHandle: spec.target_handle,
        });
      });

      if (!createdNodes.length && !createdEdges.length) {
        toast({ description: "No valid graph changes were found in this AI suggestion." });
        return;
      }

      if (createdNodes.length) {
        setNodes((nds) => [...nds, ...(createdNodes as never[])]);
        setSelectedNode(createdNodes[0]);
      }
      if (createdEdges.length) {
        setEdges((eds) => [...eds, ...(createdEdges as never[])]);
      }
      setActiveRunId(null);
      toast({ description: `Applied ${createdNodes.length} node(s) and ${createdEdges.length} edge(s) from the AI suggestion.` });
      setTimeout(() => fitView({ padding: 0.18, duration: 300 }), 60);
    },
    [edges, fitView, nodes, screenToFlowPosition, selectedNode, setEdges, setNodes, toast],
  );

  const onPaneClick = useCallback(() => setSelectedNode(null), []);

  if (pipelineId && isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        Loading pipeline...
      </div>
    );
  }

  const showMiniMap = nodes.length >= 6;

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-card z-10">
        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => navigate("/studio")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        <Input
          value={pipelineName}
          onChange={(e) => setPipelineName(e.target.value)}
          className="h-7 text-sm font-medium w-64 border-0 shadow-none focus-visible:ring-0 px-0"
          placeholder="Pipeline name..."
        />
        <div className="ml-auto flex items-center gap-2">
          {lastRun && (
            <button
              type="button"
              onClick={() => setActiveRunId(lastRun.id)}
              className="hidden items-center gap-2 rounded-md border border-border/70 bg-background/35 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-border hover:bg-background/50 hover:text-foreground sm:flex"
            >
              {lastRun.status === "running" && <Loader2 className="h-2.5 w-2.5 animate-spin mr-1" />}
              Run #{lastRun.id}: {lastRun.status}
            </button>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => setPipelineCopilotOpen(true)}
            className="h-7 gap-1.5"
          >
            <Bot className="h-3.5 w-3.5" />
            Assistant
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={handleSave}
            disabled={saveMutation.isPending}
            className="h-7 gap-1.5"
          >
            {saveMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            Save
          </Button>
          <Button
            size="sm"
            onClick={() => setRunDialogOpen(true)}
            disabled={runMutation.isPending || saveMutation.isPending}
            className="h-7 gap-1.5"
          >
            {runMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
            Run
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="ghost" className="h-8 gap-1.5 rounded-md px-3 text-muted-foreground">
                <MoreHorizontal className="h-3.5 w-3.5" />
                {localize(lang, "Ещё", "More")}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuItem onClick={() => setPipelineCopilotOpen(true)}>
                <Bot className="mr-2 h-3.5 w-3.5" />
                {localize(lang, "AI помощник пайплайна", "Pipeline AI Assistant")}
              </DropdownMenuItem>
              {lastRun && (
                <DropdownMenuItem onClick={() => setActiveRunId(lastRun.id)}>
                  <Clock className="mr-2 h-3.5 w-3.5" />
                  {localize(lang, `Открыть запуск #${lastRun.id}`, `Open run #${lastRun.id}`)}
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <PipelineAssistantDialog
        open={pipelineCopilotOpen}
        onOpenChange={setPipelineCopilotOpen}
        pipelineId={pipelineId}
        pipelineName={pipelineName}
        nodes={nodes as unknown as PipelineNode[]}
        edges={edges as unknown as PipelineEdge[]}
        selectedNode={selectedNode}
        onApplyPatch={handleApplyPipelineAssistantPatch}
        onApplyGraphPatch={handleApplyPipelineAssistantGraphPatch}
      />

      {/* Main area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Node palette */}
        <div className="w-52 shrink-0">
          <NodePalette onAddNode={handleAddNode} />
        </div>

        {/* Center: Canvas */}
        <div className="flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            fitView
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{
              style: { strokeWidth: 2 },
              animated: true,
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
                  if (type.startsWith("trigger/")) return "#6b7280";
                  if (type.startsWith("agent/")) return "#4b5563";
                  if (type.startsWith("logic/")) return "#9ca3af";
                  if (type.startsWith("output/")) return "#374151";
                  return "#6b7280";
                }}
              />
            )}
            {/* Empty state hint inside React Flow */}
            {nodes.length === 0 && (
              <Panel position="top-center" style={{ pointerEvents: "none", marginTop: "30%" }}>
                <div className="text-center select-none">
                  <Zap className="h-10 w-10 text-muted-foreground/20 mx-auto mb-3" />
                  <p className="text-sm text-muted-foreground/60">Click a node type on the left to add it</p>
                </div>
              </Panel>
            )}
          </ReactFlow>
        </div>

        {/* Right: Run monitor OR Node config panel */}
        {(activeRunId || selectedNode) && (
          <div className="w-80 shrink-0 border-l border-border bg-card flex flex-col">
            {activeRunId ? (
              <RunMonitorPanel
                runId={activeRunId}
                onClose={() => setActiveRunId(null)}
              />
            ) : selectedNode ? (
              <NodeConfigPanel
                key={selectedNode.id}
                node={selectedNode}
                pipelineId={pipelineId}
                trigger={pipeline?.triggers?.find((item) => item.node_id === selectedNode.id) || null}
                onUpdate={handleUpdateNodeData}
                onClose={() => setSelectedNode(null)}
                onDelete={handleDeleteNode}
              />
            ) : null}
          </div>
        )}
      </div>

      <Dialog open={runDialogOpen} onOpenChange={setRunDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Run Pipeline</DialogTitle>
            <DialogDescription>
              Add optional task text and JSON context for this run.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="run-task">Task</Label>
              <Textarea
                id="run-task"
                value={runTaskText}
                onChange={(event) => setRunTaskText(event.target.value)}
                placeholder="e.g. Check staging, apply updates, and report blockers"
                rows={4}
              />
            </div>

            <div className="rounded-md border border-border">
              <button
                type="button"
                className="flex w-full items-center justify-between px-3 py-2 text-left"
                onClick={() => setRunAdvancedOpen((open) => !open)}
              >
                <div>
                  <p className="text-xs font-medium">Advanced context</p>
                  <p className="text-[11px] text-muted-foreground">Optional requester metadata and extra JSON fields.</p>
                </div>
                {runAdvancedOpen ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
              </button>
              {runAdvancedOpen ? (
                <div className="space-y-4 border-t border-border px-3 py-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label htmlFor="run-requester">Requester</Label>
                      <Input
                        id="run-requester"
                        value={runRequester}
                        onChange={(event) => setRunRequester(event.target.value)}
                        placeholder="Service Desk, CI job, operator"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="run-ticket-id">Ticket or reference ID</Label>
                      <Input
                        id="run-ticket-id"
                        value={runTicketId}
                        onChange={(event) => setRunTicketId(event.target.value)}
                        placeholder="INC-1428"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="run-context">Run context (JSON object)</Label>
                    <Textarea
                      id="run-context"
                      value={runContextText}
                      onChange={(event) => {
                        setRunContextText(event.target.value);
                        if (runContextError) setRunContextError(null);
                      }}
                      placeholder='{"env":"staging","priority":"high"}'
                      rows={8}
                      className="font-mono text-xs"
                    />
                    <p className="text-[11px] text-muted-foreground">
                      These fields are merged with the task text before the run starts.
                    </p>
                    {runContextError ? <p className="text-xs text-red-400">{runContextError}</p> : null}
                  </div>
                </div>
              ) : null}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRunDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleRunSubmit} disabled={runMutation.isPending || saveMutation.isPending}>
              {runMutation.isPending || saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Run
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Export (wrapped in provider)
// ---------------------------------------------------------------------------
export default function PipelineEditorPage() {
  const { id } = useParams<{ id?: string }>();
  const pipelineId = id ? parseInt(id) : null;

  return (
    <ReactFlowProvider>
      <div className="h-full">
        <PipelineEditorInner pipelineId={pipelineId} />
      </div>
    </ReactFlowProvider>
  );
}
