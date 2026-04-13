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
  Copy,
  Info,
  Search,
  RotateCcw,
  ArrowUp,
  PanelRightClose,
  PanelRightOpen,
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
  getStudioPipelineRunWsUrl,
  type MCPServerInspection,
  type ModelsResponse,
  type PipelineNode,
  type PipelineEdge,
  type PipelineRun,
  type PipelineTrigger,
  type StudioPipelineGraphPatch,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { getPipelineActivityState } from "@/components/pipeline/pipelineActivity";
import { buildPipelineRunGraphState } from "@/components/pipeline/pipelineRunGraph";
import {
  TriggerNode,
  AgentNode,
  SSHCommandNode,
  ConditionNode,
  ParallelNode,
  MergeNode,
  OutputNode,
  LLMQueryNode,
  MCPCallNode,
  EmailNode,
  WaitNode,
  HumanApprovalNode,
  TelegramNode,
  TelegramInputNode,
  NODE_PALETTE,
  type NodeType,
} from "@/components/pipeline/nodes";
import { getNodeTypeGuidance } from "@/components/pipeline/nodes/nodeMeta";

// ---------------------------------------------------------------------------
// React Flow node type map
// ---------------------------------------------------------------------------
const nodeTypes = {
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

// ---------------------------------------------------------------------------
// Node type friendly names
// ---------------------------------------------------------------------------
const NODE_TYPE_LABELS: Record<string, { label: string; icon: string }> = {
  "trigger/manual":        { label: "Manual Trigger",   icon: "▶️" },
  "trigger/webhook":       { label: "Webhook Trigger",  icon: "🔗" },
  "trigger/schedule":      { label: "Schedule Trigger", icon: "⏰" },
  "trigger/monitoring":    { label: "Monitoring Trigger", icon: "🚨" },
  "agent/react":           { label: "ReAct Agent",      icon: "🤖" },
  "agent/multi":           { label: "Multi-Agent",      icon: "🦾" },
  "agent/ssh_cmd":         { label: "SSH Command",      icon: "💻" },
  "agent/llm_query":       { label: "LLM Query",        icon: "🧠" },
  "agent/mcp_call":        { label: "MCP Call",         icon: "🧩" },
  "logic/condition":       { label: "Condition",        icon: "🔀" },
  "logic/parallel":        { label: "Parallel",         icon: "⚡" },
  "logic/merge":           { label: "Merge",            icon: "🪢" },
  "logic/wait":            { label: "Wait",             icon: "⏱️" },
  "logic/human_approval":  { label: "Human Approval",  icon: "👤" },
  "logic/telegram_input":  { label: "Telegram Input",  icon: "💬" },
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
  awaiting_operator_reply: <Clock   className="h-3 w-3 text-cyan-400 animate-pulse" />,
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

  const nodeStates = run?.node_states || {};

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

              {/* Human Approval waiting state — always show links */}
              {status === "awaiting_approval" && (
                <div className="border-t border-border px-3 py-2 space-y-2">
                  <p className="text-yellow-400 text-[11px] font-medium">⏳ Waiting for your decision...</p>
                  {typeof stateExtra.approve_url === "string" && (
                    <div className="flex gap-2">
                      <a
                        href={stateExtra.approve_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 text-center text-xs py-1.5 rounded bg-green-800/40 border border-green-600/40 text-green-300 hover:bg-green-700/50 transition-colors"
                      >
                        ✅ Approve
                      </a>
                      <a
                        href={typeof stateExtra.reject_url === "string" ? stateExtra.reject_url : "#"}
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
  { value: "ollama", label: "Ollama" },
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
  omitFromHistory?: boolean;
};

function getNodeDisplayLabel(node: PipelineNode | { id: string; type: string; label?: string }) {
  if ("data" in node) {
    const label = typeof node.data?.label === "string" ? node.data.label.trim() : "";
    if (label) return label;
  }
  if ("label" in node && typeof node.label === "string" && node.label.trim()) return node.label.trim();
  return NODE_TYPE_LABELS[node.type]?.label || node.id;
}

function getActiveManualTriggerOptions(nodes: PipelineNode[]) {
  return nodes
    .filter((node) => node.type === "trigger/manual" && node.data?.is_active !== false)
    .map((node) => ({
      node_id: node.id,
      label: getNodeDisplayLabel(node),
    }));
}

function getActiveTriggerNodes(nodes: PipelineNode[], type: PipelineNode["type"]) {
  return nodes.filter((node) => node.type === type && node.data?.is_active !== false);
}

export function buildPipelineSavePayload({
  pipelineId,
  pipeline,
  pipelineName,
  nodes,
  edges,
  hasLocalChanges,
}: {
  pipelineId: number | null;
  pipeline:
    | {
        name?: string;
        nodes?: PipelineNode[];
        edges?: PipelineEdge[];
      }
    | null
    | undefined;
  pipelineName: string;
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  hasLocalChanges: boolean;
}) {
  if (pipelineId && pipeline && !hasLocalChanges) {
    return {
      name: pipeline.name || pipelineName || "Untitled",
      nodes: pipeline.nodes || [],
      edges: pipeline.edges || [],
    };
  }

  return {
    name: pipelineName || pipeline?.name || "Untitled",
    nodes,
    edges,
  };
}

function getActiveStoredTriggers(
  pipelineTriggers: PipelineTrigger[] | undefined,
  type: PipelineTrigger["trigger_type"],
) {
  if (!Array.isArray(pipelineTriggers)) {
    return [];
  }
  return pipelineTriggers.filter((trigger) => trigger.trigger_type === type && trigger.is_active);
}

function toAbsoluteWebhookUrl(webhookUrl: string): string {
  return new URL(webhookUrl, window.location.origin).toString();
}

function getPipelineNodeStatusLabel(
  status: string | undefined,
  lang: string,
  state?: Record<string, unknown> | null,
) {
  if (!status) return undefined;
  if (status === "awaiting_approval") {
    return localize(lang, "Ждет approve", "Waiting approval");
  }
  if (status === "awaiting_operator_reply") {
    return localize(lang, "Ждет ответ", "Waiting reply");
  }
  if (status === "running") {
    return localize(lang, "Выполняется", "Running");
  }
  if (status === "pending") {
    return localize(lang, "В очереди", "Queued");
  }
  if (status === "completed") {
    const decision = typeof state?.decision === "string" ? state.decision : "";
    if (decision === "approved") return localize(lang, "Одобрено", "Approved");
    if (decision === "rejected") return localize(lang, "Отклонено", "Rejected");
    if (decision === "received") return localize(lang, "Ответ получен", "Reply received");
    return localize(lang, "Выполнено", "Completed");
  }
  if (status === "failed") {
    return localize(lang, "Ошибка", "Failed");
  }
  if (status === "skipped") {
    return localize(lang, "Пропущен", "Skipped");
  }
  if (status === "stopped") {
    return localize(lang, "Остановлен", "Stopped");
  }
  return status;
}

function isLivePipelineRunStatus(status: string | null | undefined) {
  return status === "running" || status === "pending";
}

type ModelProvider = Exclude<keyof ModelsResponse, "current">;

const MODEL_PROVIDERS: ModelProvider[] = ["gemini", "grok", "openai", "claude", "ollama"];

function isModelProvider(value: string): value is ModelProvider {
  return MODEL_PROVIDERS.includes(value as ModelProvider);
}

function getModelsForProvider(models: ModelsResponse | undefined, provider: string): string[] {
  if (!models || !isModelProvider(provider)) return [];
  return models[provider];
}

function buildDefaultNodeData(type: NodeType): Record<string, unknown> {
  switch (type) {
    case "trigger/manual":
      return { is_active: true };
    case "trigger/webhook":
      return { is_active: true, webhook_payload_map: {}, webhook_payload_map_text: "{}" };
    case "trigger/schedule":
      return { is_active: true, cron_expression: "*/5 * * * *" };
    case "trigger/monitoring":
      return {
        is_active: true,
        server_ids: [],
        severities: ["critical"],
        alert_types: ["service", "unreachable"],
        container_names: [],
        match_text: "",
        monitoring_filters: {
          severities: ["critical"],
          alert_types: ["service", "unreachable"],
        },
      };
    case "agent/react":
    case "agent/multi":
      return { max_iterations: 6, on_failure: "abort" };
    case "agent/llm_query":
      return { provider: "gemini", on_failure: "abort" };
    case "agent/mcp_call":
      return { arguments: {}, arguments_text: "{}", on_failure: "abort" };
    case "logic/condition":
      return { check_type: "contains" };
    case "logic/merge":
      return { mode: "all" };
    case "logic/wait":
      return { wait_minutes: 20 };
    case "logic/human_approval":
      return { timeout_minutes: 120 };
    case "logic/telegram_input":
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

  if (target.type === "logic/telegram_input" && !String(data.message || "").trim()) {
    patch.message = `Operator input required after ${sourceLabel}\n\n${outputToken}\n\nReply to this Telegram message with the next instruction for the agent.`;
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
  const rawMonitoringFilters =
    next.monitoring_filters && typeof next.monitoring_filters === "object" && !Array.isArray(next.monitoring_filters)
      ? (next.monitoring_filters as Record<string, unknown>)
      : null;

  if (rawMonitoringFilters) {
    if (!Array.isArray(next.server_ids) && Array.isArray(rawMonitoringFilters.server_ids)) {
      next.server_ids = rawMonitoringFilters.server_ids;
    }
    if (!Array.isArray(next.severities) && Array.isArray(rawMonitoringFilters.severities)) {
      next.severities = rawMonitoringFilters.severities;
    }
    if (!Array.isArray(next.alert_types) && Array.isArray(rawMonitoringFilters.alert_types)) {
      next.alert_types = rawMonitoringFilters.alert_types;
    }
    if (!Array.isArray(next.container_names) && Array.isArray(rawMonitoringFilters.container_names)) {
      next.container_names = rawMonitoringFilters.container_names;
    }
    if (!String(next.match_text || "").trim() && typeof rawMonitoringFilters.match_text === "string") {
      next.match_text = rawMonitoringFilters.match_text;
    }
  }

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

  for (const fieldName of ["severities", "alert_types", "container_names"] as const) {
    if (Array.isArray(next[fieldName])) {
      next[fieldName] = next[fieldName]
        .map((item) => String(item || "").trim())
        .filter(Boolean);
    }
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

function normalisePipelineGraph(nodes: PipelineNode[], edges: PipelineEdge[]) {
  return {
    nodes: nodes.map((node) => ({
      ...node,
      data: normaliseAssistantPatch((node.data || {}) as Record<string, unknown>, { mcpList: [] }),
    })),
    edges,
  };
}

function isNodeType(value: string): value is NodeType {
  return value in nodeTypes;
}

function describeGraphPatch(graphPatch: StudioPipelineGraphPatch | null | undefined) {
  if (
    !graphPatch ||
    (!graphPatch.nodes.length &&
      !graphPatch.edges.length &&
      !(graphPatch.update_nodes || []).length &&
      !(graphPatch.remove_node_ids || []).length &&
      !(graphPatch.remove_edge_ids || []).length)
  ) {
    return null;
  }
  return {
    addNodeCount: graphPatch.nodes.length,
    addEdgeCount: graphPatch.edges.length,
    updateNodeCount: (graphPatch.update_nodes || []).length,
    removeNodeCount: (graphPatch.remove_node_ids || []).length,
    removeEdgeCount: (graphPatch.remove_edge_ids || []).length,
    nodeLabels: graphPatch.nodes.map((item) => item.label || NODE_TYPE_LABELS[item.type]?.label || item.type),
    edgeLabels: graphPatch.edges.map((item) => `${item.source} -> ${item.target}${item.label ? ` (${item.label})` : ""}`),
    updatedNodeIds: (graphPatch.update_nodes || []).map((item) => item.node_id),
    removedNodeIds: graphPatch.remove_node_ids || [],
  };
}

function buildAssistantIntroMessage(
  pipelineId: number | null,
  pipelineName: string,
  lang: string,
): AssistantMessage {
  return {
    id: `pipeline-assistant-intro-${pipelineId ?? "new"}`,
    role: "assistant",
    omitFromHistory: true,
    content: localize(
      lang,
      `Опишите задачу обычным языком, и я соберу или доработаю пайплайн${pipelineName ? ` **${pipelineName}**` : ""}.\n\nЯ умею строить основу автоматизации, менять существующие шаги, добавлять safety/approval и возвращать конкретные правки для канваса.`,
      `Describe the task in plain language and I will build or refine the pipeline${pipelineName ? ` **${pipelineName}**` : ""}.\n\nI can create the automation structure, edit existing steps, add safety or approval, and return concrete graph changes for the canvas.`,
    ),
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
  hasLocalChanges,
  activityLabel,
  lang,
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
  hasLocalChanges: boolean;
  activityLabel: string;
  lang: string;
  onApplyPatch: (targetNodeId: string, patch: Record<string, unknown>) => void;
  onApplyGraphPatch: (graphPatch: StudioPipelineGraphPatch) => void;
}) {
  const { toast } = useToast();
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<AssistantMessage[]>(() => [
    buildAssistantIntroMessage(pipelineId, pipelineName, lang),
  ]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setDraft("");
    setMessages([buildAssistantIntroMessage(pipelineId, pipelineName, lang)]);
  }, [pipelineId, lang]);

  useEffect(() => {
    if (!open) return;
    setTimeout(() => inputRef.current?.focus(), 100);
  }, [open]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, open]);

  const history = useMemo(
    () =>
      messages
        .filter((message) => !message.omitFromHistory)
        .map((message) => ({ role: message.role, content: message.content }))
        .slice(-10),
    [messages],
  );

  const assistantMutation = useMutation({
    mutationFn: ({ message, history }: { message: string; history: Array<{ role: "user" | "assistant"; content: string }> }) =>
      studioPipelines.assistant({
        pipeline_id: pipelineId,
        pipeline_name: pipelineName || "Untitled",
        nodes,
        edges,
        selected_node: selectedNode,
        user_message: message,
        history,
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
        description:
          error instanceof Error
            ? error.message
            : localize(lang, "AI помощник пайплайна не ответил.", "Pipeline assistant failed."),
      });
    },
  });

  const submitPrompt = async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || assistantMutation.isPending) return;
    const nextHistory = [...history, { role: "user" as const, content: trimmed }].slice(-10);
    setMessages((prev) => [
      ...prev,
      { id: `pipeline-user-${Date.now()}`, role: "user", content: trimmed },
    ]);
    setDraft("");
    await assistantMutation.mutateAsync({ message: trimmed, history: nextHistory });
  };

  const quickPrompts = [
    {
      key: "build",
      icon: "🧩",
      title: localize(lang, "Собери автоматизацию по описанию", "Build automation from a task"),
      prompt: localize(
        lang,
        "Построй качественный стартовый пайплайн под эту задачу. Добавь подходящий trigger, основные шаги, safety или approval там где это нужно, и финальный отчет.",
        "Build a solid starter pipeline for this task. Add the right trigger, main steps, safety or approval where needed, and a final report.",
      ),
    },
    {
      key: "improve",
      icon: "⚙️",
      title: localize(lang, "Улучши текущий граф", "Improve the current graph"),
      prompt: localize(
        lang,
        "Проанализируй текущий пайплайн как production automation. Найди слабые места и верни конкретные правки графа и конфигов, а не только общие советы.",
        "Review this pipeline as a production automation. Find weak spots and return concrete graph and config changes, not just general advice.",
      ),
    },
    {
      key: "selected",
      icon: "🎯",
      title: selectedNode
        ? localize(lang, `Доработай шаг: ${getNodeDisplayLabel(selectedNode)}`, `Refine step: ${getNodeDisplayLabel(selectedNode)}`)
        : localize(lang, "Предложи следующий шаг", "Suggest the next step"),
      prompt: selectedNode
        ? localize(
            lang,
            `Сфокусируйся на ноде ${getNodeDisplayLabel(selectedNode)}. Улучши ее настройки и при необходимости добавь недостающие шаги до или после нее.`,
            `Focus on the node ${getNodeDisplayLabel(selectedNode)}. Improve its configuration and add missing steps before or after it if needed.`,
          )
        : localize(
            lang,
            "Предложи следующий полезный шаг в текущем пайплайне и верни конкретные изменения графа.",
            "Suggest the next useful step in the current pipeline and return concrete graph changes.",
          ),
    },
    {
      key: "safety",
      icon: "🛡️",
      title: localize(lang, "Добавь safety и оператора", "Add safety and operator control"),
      prompt: localize(
        lang,
        "Добавь в этот пайплайн операционные guardrails: approval, fallback, операторский ответ через Telegram и финальный отчет там, где это уместно.",
        "Add operational guardrails to this pipeline: approval, fallback, operator reply via Telegram, and a final report where appropriate.",
      ),
    },
  ];

  return (
    <div className="border-t border-border bg-background/95 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-xl bg-primary/10 flex items-center justify-center">
              <Bot className="h-4 w-4 text-primary" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold">{localize(lang, "AI Builder для Studio", "Studio AI Builder")}</h3>
                <Badge variant="secondary" className="text-[10px]">
                  {nodes.length} {localize(lang, "нод", "nodes")}
                </Badge>
                <Badge variant="outline" className="text-[10px]">
                  {edges.length} {localize(lang, "связей", "edges")}
                </Badge>
                {selectedNode ? (
                  <Badge variant="outline" className="text-[10px]">
                    {localize(lang, "Фокус", "Focus")}: {getNodeDisplayLabel(selectedNode)}
                  </Badge>
                ) : null}
                {hasLocalChanges ? (
                  <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-[10px] text-amber-300">
                    {localize(lang, "Есть несохраненные правки", "Unsaved changes")}
                  </Badge>
                ) : null}
              </div>
              <p className="text-[10px] text-muted-foreground">
                {localize(lang, "Опишите задачу или попросите изменить текущий граф. Статус пайплайна", "Describe the task or ask to change the current graph. Pipeline status")}:
                {" "}
                {activityLabel}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {messages.length > 1 ? (
              <Button
                size="sm"
                variant="ghost"
                className="h-8 text-xs"
                onClick={() => {
                  setDraft("");
                  setMessages([buildAssistantIntroMessage(pipelineId, pipelineName, lang)]);
                }}
              >
                {localize(lang, "Сбросить диалог", "Reset chat")}
              </Button>
            ) : null}
            <Button size="sm" variant={open ? "secondary" : "outline"} className="h-8 gap-1.5 text-xs" onClick={() => onOpenChange(!open)}>
              <Bot className="h-3.5 w-3.5" />
              {open ? localize(lang, "Свернуть чат", "Collapse chat") : localize(lang, "Открыть чат", "Open chat")}
            </Button>
          </div>
      </div>

      {open ? (
        <>
          {messages.length <= 1 && (
            <div className="px-5 pt-2 pb-3 border-t border-border bg-muted/10">
              <p className="text-[9px] text-muted-foreground mb-2 uppercase font-medium tracking-wider">
                {localize(lang, "Быстрые сценарии", "Quick actions")}
              </p>
              <div className="flex flex-wrap gap-1.5">
              {quickPrompts.map((qp) => (
                <button
                  key={qp.key}
                  onClick={() => void submitPrompt(qp.prompt)}
                  disabled={assistantMutation.isPending}
                  title={qp.prompt}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border bg-card hover:bg-primary/8 hover:border-primary/40 transition-all text-xs font-medium text-foreground/80 hover:text-foreground"
                >
                  <span className="text-sm">{qp.icon}</span>
                  {qp.title}
                </button>
              ))}
              </div>
          </div>
          )}

          <div ref={scrollRef} className="overflow-auto px-5 py-4 space-y-4 min-h-[220px] max-h-[360px] border-t border-border">
          {messages.map((message) => {
            const isAI = message.role === "assistant";
            const hasPatch = Boolean(message.nodePatch && Object.keys(message.nodePatch).length && message.targetNodeId);
            const graphPatchSummary = describeGraphPatch(message.graphPatch);

            return (
              <div key={message.id} className={cn("flex gap-3", !isAI && "flex-row-reverse")}>
                {/* Avatar */}
                <div className={cn(
                  "h-7 w-7 rounded-full flex items-center justify-center shrink-0 text-xs",
                  isAI ? "bg-primary/10 text-primary" : "bg-muted/60 text-muted-foreground"
                )}>
                  {isAI ? <Bot className="h-3.5 w-3.5" /> : "U"}
                </div>

                {/* Bubble */}
                <div className={cn(
                  "max-w-[85%] space-y-2",
                  !isAI && "text-right"
                )}>
                  <div className={cn(
                    "rounded-xl px-3.5 py-2.5 text-sm leading-relaxed",
                    isAI
                      ? "bg-card border border-border text-foreground"
                      : "bg-muted/50 border border-border/50 text-foreground"
                  )}>
                    <div className="whitespace-pre-wrap">{message.content}</div>
                  </div>

                  {/* Warnings */}
                  {message.warnings?.length ? (
                    <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 space-y-1">
                      {message.warnings.map((w) => (
                        <p key={w} className="text-[11px] text-amber-600 dark:text-amber-400 flex items-start gap-1.5">
                          <span className="shrink-0">⚠️</span> {w}
                        </p>
                      ))}
                    </div>
                  ) : null}

                  {/* Node patch action */}
                  {hasPatch && (
                    <div className="rounded-xl border border-border bg-card overflow-hidden">
                      <div className="px-3 py-2 border-b border-border bg-muted/30 flex items-center gap-2">
                        <Wand2 className="h-3 w-3 text-primary" />
                        <span className="text-[11px] font-medium">
                          {localize(lang, "Правка ноды", "Node patch")}: {message.targetNodeId}
                        </span>
                      </div>
                      <pre className="px-3 py-2 text-[10px] leading-4 text-muted-foreground max-h-32 overflow-auto font-mono">
                        {JSON.stringify(message.nodePatch, null, 2)}
                      </pre>
                      <div className="px-3 py-2 border-t border-border">
                        <Button
                          size="sm"
                          className="h-7 gap-1.5 text-xs w-full"
                          onClick={() => onApplyPatch(message.targetNodeId || "", message.nodePatch || {})}
                        >
                          <Wand2 className="h-3 w-3" />
                          {localize(lang, "Применить правку", "Apply patch")}
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* Graph patch action */}
                  {graphPatchSummary && (
                    <div className="rounded-xl border border-border bg-card overflow-hidden">
                      <div className="px-3 py-2 border-b border-border bg-muted/30 flex items-center gap-2">
                        <Sparkles className="h-3 w-3 text-primary" />
                        <span className="text-[11px] font-medium">
                          {localize(lang, "Изменение графа", "Graph change")}
                        </span>
                      </div>
                      <div className="px-3 py-2 space-y-2 text-[11px] text-muted-foreground">
                        <div className="flex flex-wrap gap-2">
                          {graphPatchSummary.addNodeCount ? (
                            <span className="bg-primary/10 text-primary rounded px-1.5 py-0.5 font-medium">
                              +{graphPatchSummary.addNodeCount} {localize(lang, "нод", "nodes")}
                            </span>
                          ) : null}
                          {graphPatchSummary.addEdgeCount ? (
                            <span className="bg-muted rounded px-1.5 py-0.5">
                              +{graphPatchSummary.addEdgeCount} {localize(lang, "связей", "edges")}
                            </span>
                          ) : null}
                          {graphPatchSummary.updateNodeCount ? (
                            <span className="rounded px-1.5 py-0.5 bg-cyan-500/10 text-cyan-300">
                              {localize(lang, "обновить", "update")} {graphPatchSummary.updateNodeCount}
                            </span>
                          ) : null}
                          {graphPatchSummary.removeNodeCount ? (
                            <span className="rounded px-1.5 py-0.5 bg-red-500/10 text-red-300">
                              {localize(lang, "удалить ноды", "remove nodes")} {graphPatchSummary.removeNodeCount}
                            </span>
                          ) : null}
                          {graphPatchSummary.removeEdgeCount ? (
                            <span className="rounded px-1.5 py-0.5 bg-red-500/10 text-red-300">
                              {localize(lang, "удалить связи", "remove edges")} {graphPatchSummary.removeEdgeCount}
                            </span>
                          ) : null}
                        </div>
                        {graphPatchSummary.nodeLabels.length > 0 && (
                          <p className="text-[10px]">{graphPatchSummary.nodeLabels.join(" → ")}</p>
                        )}
                        {graphPatchSummary.updatedNodeIds.length > 0 && (
                          <p className="text-[10px]">
                            {localize(lang, "Обновит", "Updates")}: {graphPatchSummary.updatedNodeIds.join(", ")}
                          </p>
                        )}
                        {graphPatchSummary.removedNodeIds.length > 0 && (
                          <p className="text-[10px]">
                            {localize(lang, "Удалит", "Removes")}: {graphPatchSummary.removedNodeIds.join(", ")}
                          </p>
                        )}
                      </div>
                      <div className="px-3 py-2 border-t border-border">
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 gap-1.5 text-xs w-full"
                          onClick={() =>
                            onApplyGraphPatch(
                              message.graphPatch || {
                                anchor_node_id: null,
                                nodes: [],
                                edges: [],
                                update_nodes: [],
                                remove_node_ids: [],
                                remove_edge_ids: [],
                              },
                            )
                          }
                        >
                          <Sparkles className="h-3 w-3" />
                          {localize(lang, "Применить изменения графа", "Apply graph changes")}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {/* Typing indicator */}
          {assistantMutation.isPending && (
            <div className="flex gap-3">
              <div className="h-7 w-7 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 text-xs">🤖</div>
              <div className="bg-card border border-border rounded-xl px-4 py-3 flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-pulse" />
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-pulse [animation-delay:150ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-pulse [animation-delay:300ms]" />
              </div>
            </div>
          )}
        </div>

          <div className="border-t border-border px-4 py-3 bg-card/50">
          <div className="flex items-end gap-2">
            <Textarea
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void submitPrompt(draft);
                }
              }}
              rows={2}
              placeholder={localize(
                lang,
                "Опишите задачу или попросите изменить текущий пайплайн…",
                "Describe the task or ask to change the current pipeline…",
              )}
              className="text-sm resize-none min-h-[48px] max-h-[120px] flex-1"
            />
            <Button
              size="icon"
              className="h-10 w-10 shrink-0 rounded-xl"
              disabled={!draft.trim() || assistantMutation.isPending}
              onClick={() => void submitPrompt(draft)}
            >
              {assistantMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowUp className="h-4 w-4" />
              )}
            </Button>
          </div>
            <div className="mt-1.5 flex items-center justify-between gap-4 text-[9px] text-muted-foreground">
              <span>{localize(lang, "Enter — отправить, Shift+Enter — новая строка", "Enter — send, Shift+Enter — new line")}</span>
              <span>{localize(lang, "Чат учитывает текущий граф и выбранную ноду", "The chat uses the current graph and focused node")}</span>
            </div>
          </div>
        </>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-3">
          <div className="min-w-0">
            <p className="text-sm font-medium">
              {localize(lang, "Попросите AI собрать или доработать автоматизацию", "Ask AI to build or refine the automation")}
            </p>
            <p className="text-xs text-muted-foreground">
              {localize(
                lang,
                "Например: «Собери мониторинг Docker-сервиса с Telegram approval и восстановлением»",
                `For example: "Build Docker service monitoring with Telegram approval and recovery"`,
              )}
            </p>
          </div>
          <Button size="sm" className="gap-1.5" onClick={() => onOpenChange(true)}>
            <Bot className="h-3.5 w-3.5" />
            {localize(lang, "Открыть AI Builder", "Open AI Builder")}
          </Button>
        </div>
      )}
    </div>
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
  const navigate = useNavigate();
  const { data: agents = [] } = useQuery({ queryKey: ["studio", "agents"], queryFn: studioAgents.list });
  const { data: servers = [] } = useQuery({ queryKey: ["studio", "servers"], queryFn: studioServers.list });
  const { data: mcpList = [] } = useQuery({ queryKey: ["studio", "mcp"], queryFn: studioMCP.list });
  const { data: skillList = [] } = useQuery({ queryKey: ["studio", "skills"], queryFn: studioSkills.list });
  const queryClient = useQueryClient();
  const { data: modelsData } = useQuery({ queryKey: ["api", "models"], queryFn: fetchModels });
  const [d, setD] = useState<Record<string, unknown>>(node.data || {});
  const [guidanceOpen, setGuidanceOpen] = useState(false);
  const [loadingModelsFor, setLoadingModelsFor] = useState<string | null>(null);
  const [webhookMapText, setWebhookMapText] = useState(() => toJsonEditorText(node.data?.webhook_payload_map));
  const [mcpArgsText, setMcpArgsText] = useState(
    () => (typeof node.data?.arguments_text === "string" ? String(node.data.arguments_text) : toJsonEditorText(node.data?.arguments || {})),
  );

  const set = useCallback((key: string, val: unknown) => {
    setD((prev) => {
      const next = { ...prev, [key]: val };
      onUpdate(node.id, next);
      return next;
    });
  }, [node.id, onUpdate]);

  const setMany = useCallback((patch: Record<string, unknown>) => {
    setD((prev) => {
      const next = { ...prev, ...patch };
      onUpdate(node.id, next);
      return next;
    });
  }, [node.id, onUpdate]);

  const setMonitoringFilters = useCallback((patch: Record<string, unknown>) => {
    setD((prev) => {
      const next = { ...prev, ...patch } as Record<string, unknown>;
      const monitoringFilters: Record<string, unknown> = {};

      if (Array.isArray(next.server_ids) && next.server_ids.length) monitoringFilters.server_ids = next.server_ids;
      if (Array.isArray(next.severities) && next.severities.length) monitoringFilters.severities = next.severities;
      if (Array.isArray(next.alert_types) && next.alert_types.length) monitoringFilters.alert_types = next.alert_types;
      if (Array.isArray(next.container_names) && next.container_names.length) monitoringFilters.container_names = next.container_names;
      if (String(next.match_text || "").trim()) monitoringFilters.match_text = String(next.match_text || "").trim();

      next.monitoring_filters = monitoringFilters;
      onUpdate(node.id, next);
      return next;
    });
  }, [node.id, onUpdate]);

  const type = node.type as NodeType;
  const provider =
    type === "agent/llm_query"
      ? ((d.provider as string) || "gemini")
      : type === "agent/react" || type === "agent/multi"
        ? ((d.provider as string) || "auto")
        : "";
  const currentModel = (d.model as string) || "";
  const modelProvider = provider && provider !== "auto" ? provider : "";
  const modelList = useMemo(
    () => getModelsForProvider(modelsData, modelProvider),
    [modelProvider, modelsData],
  );
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
    if (currentModel && !modelList.includes(currentModel)) set("model", modelList[0]);
  }, [currentModel, modelList, modelProvider, set, type]);

  useEffect(() => {
    if (!(type === "agent/llm_query" || type === "agent/react" || type === "agent/multi") || !modelProvider || loadingModelsFor !== null) return;
    const list = getModelsForProvider(modelsData, modelProvider);
    if (list.length > 0) return;
    if (!isModelProvider(modelProvider)) return;
    const prov = modelProvider;
    setLoadingModelsFor(prov);
    refreshModels(prov)
      .then((res) => {
        queryClient.setQueryData(["api", "models"], (old: ModelsResponse | undefined) => ({
          ...(old ?? {}),
          [prov]: res.models,
        }));
        if (res.models.length && providerRef.current === prov) {
          setD((prev) => {
            const next = { ...prev, provider: prov, model: res.models[0] };
            onUpdate(node.id, next);
            return next;
          });
        }
      })
      .finally(() => setLoadingModelsFor(null));
  }, [loadingModelsFor, modelProvider, modelsData, node.id, onUpdate, queryClient, type]);

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
        {/* Guidance — collapsible */}
        {(() => {
          const guidance = getNodeTypeGuidance(type, "en");
          return (
            <div className="rounded-lg border border-border/50 overflow-hidden">
              <button
                type="button"
                className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-muted/30 transition-colors"
                onClick={() => setGuidanceOpen((v) => !v)}
              >
                <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                  <Info className="h-3 w-3" />
                  {guidance.category} · {typeInfo.label}
                </div>
                {guidanceOpen
                  ? <ChevronUp className="h-3 w-3 text-muted-foreground" />
                  : <ChevronDown className="h-3 w-3 text-muted-foreground" />}
              </button>
              {guidanceOpen && (
                <div className="px-3 pb-2.5 space-y-1.5 border-t border-border/40 bg-muted/10">
                  <p className="text-[10px] text-muted-foreground leading-relaxed pt-2">{guidance.summary}</p>
                  <ul className="space-y-0.5">
                    {guidance.checklist.map((item, i) => (
                      <li key={i} className="text-[10px] text-muted-foreground flex items-start gap-1.5">
                        <span className="text-primary shrink-0 mt-px">✓</span> {item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          );
        })()}

        {/* Common: label */}
        <div className="space-y-1.5">
          <Label className="text-xs">Label (optional)</Label>
          <Input value={(d.label as string) || ""} onChange={(e) => set("label", e.target.value)} placeholder="Node label" className="h-7 text-xs" />
        </div>

        {(type === "trigger/manual" || type === "trigger/webhook" || type === "trigger/schedule" || type === "trigger/monitoring") && (
          <>
            <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 text-[11px] text-muted-foreground">
              Trigger settings are created from this node when you click <strong>Save</strong>. Each trigger launches only its own branch of the graph.
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
              Start this pipeline from the Studio <strong>Run</strong> dialog
              {pipelineId ? ` or POST /api/studio/pipelines/${pipelineId}/run/.` : "."}
            </p>
            <p className="text-[11px] text-muted-foreground">
              If the graph has multiple manual triggers, the operator chooses which trigger node starts the run.
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
                          refreshModels(nextProvider as "gemini" | "grok" | "openai" | "claude" | "ollama")
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

        {type === "trigger/monitoring" && (
          <>
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-100">
              Monitoring trigger waits for a server alert. It does not start from the Run dialog. Save the pipeline and let the monitor open a matching alert.
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Target Servers</Label>
              <div className="space-y-1">
                {((d.server_ids as number[]) || []).map((sid) => {
                  const srv = servers.find((s) => s.id === sid);
                  return (
                    <div key={sid} className="flex items-center justify-between rounded bg-muted/30 px-2 py-1 text-xs">
                      <span>{srv ? `${srv.name} (${srv.host})` : `Server #${sid}`}</span>
                      <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        className="h-5 w-5"
                        onClick={() => setMonitoringFilters({ server_ids: ((d.server_ids as number[]) || []).filter((id) => id !== sid) })}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  );
                })}
                <Select
                  onValueChange={(value) => {
                    const ids = ((d.server_ids as number[]) || []);
                    const nextId = parseInt(value, 10);
                    if (!ids.includes(nextId)) setMonitoringFilters({ server_ids: [...ids, nextId] });
                  }}
                >
                  <SelectTrigger className="h-7 text-xs">
                    <SelectValue placeholder="Add server..." />
                  </SelectTrigger>
                  <SelectContent>
                    {servers.map((s) => (
                      <SelectItem key={s.id} value={String(s.id)}>
                        {s.name} ({s.host})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground">Leave empty to react to alerts from any accessible server.</p>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Severity filters</Label>
              <div className="grid grid-cols-1 gap-2">
                {[
                  { value: "info", label: "info" },
                  { value: "warning", label: "warning" },
                  { value: "critical", label: "critical" },
                ].map((item) => {
                  const selected = ((d.severities as string[]) || []).includes(item.value);
                  return (
                    <label key={item.value} className="flex items-center gap-2 rounded border border-border px-2 py-2 text-xs">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5"
                        checked={selected}
                        onChange={() => {
                          const current = ((d.severities as string[]) || []).filter(Boolean);
                          setMonitoringFilters({
                            severities: selected ? current.filter((value) => value !== item.value) : [...current, item.value],
                          });
                        }}
                      />
                      <span>{item.label}</span>
                    </label>
                  );
                })}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Alert types</Label>
              <div className="grid grid-cols-1 gap-2">
                {[
                  "service",
                  "unreachable",
                  "cpu",
                  "memory",
                  "disk",
                  "log_error",
                ].map((value) => {
                  const selected = ((d.alert_types as string[]) || []).includes(value);
                  return (
                    <label key={value} className="flex items-center gap-2 rounded border border-border px-2 py-2 text-xs">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5"
                        checked={selected}
                        onChange={() => {
                          const current = ((d.alert_types as string[]) || []).filter(Boolean);
                          setMonitoringFilters({
                            alert_types: selected ? current.filter((item) => item !== value) : [...current, value],
                          });
                        }}
                      />
                      <span>{value}</span>
                    </label>
                  );
                })}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Docker container names</Label>
              <Textarea
                value={((d.container_names as string[]) || []).join("\n")}
                onChange={(e) =>
                  setMonitoringFilters({
                    container_names: e.target.value
                      .split(/\r?\n/)
                      .map((value) => value.trim())
                      .filter(Boolean),
                  })
                }
                placeholder={"mini-prod-mcp-demo"}
                className="text-xs font-mono resize-none"
                rows={3}
              />
              <p className="text-[10px] text-muted-foreground">Optional. One container name per line.</p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Text match</Label>
              <Input
                value={(d.match_text as string) || ""}
                onChange={(e) => setMonitoringFilters({ match_text: e.target.value })}
                placeholder="Optional substring to match in title/message/metadata"
                className="h-7 text-xs"
              />
            </div>
            {trigger ? (
              <p className="text-[10px] text-muted-foreground">
                Last monitoring-triggered run: {formatStudioDateTime(trigger.last_triggered_at)}
              </p>
            ) : null}
          </>
        )}

        {type === "logic/merge" && (
          <>
            <div className="space-y-1.5">
              <Label className="text-xs">Merge Mode</Label>
              <Select value={(d.mode as string) || "all"} onValueChange={(value) => set("mode", value)}>
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">all: wait for every activated branch</SelectItem>
                  <SelectItem value="any">any: continue after the first completed branch</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <p className="text-[10px] text-muted-foreground">
              Use merge nodes instead of wiring multiple incoming edges directly into an action or output node.
            </p>
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
                          refreshModels(nextProvider as "gemini" | "grok" | "openai" | "claude" | "ollama")
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

        {type === "logic/telegram_input" && (
          <>
            <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/10 px-3 py-2 text-[11px] text-cyan-100">
              Этот узел отправляет сообщение в Telegram и ждёт обычный текстовый reply от оператора.
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Bot Token</Label>
              <Input
                value={(d.tg_bot_token as string) || ""}
                onChange={(e) => set("tg_bot_token", e.target.value)}
                placeholder="или глобально в Studio → Notifications"
                className="h-7 text-xs font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Chat ID</Label>
              <Input
                value={(d.tg_chat_id as string) || ""}
                onChange={(e) => set("tg_chat_id", e.target.value)}
                placeholder="-100123456789"
                className="h-7 text-xs font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Message Template</Label>
              <Textarea
                value={(d.message as string) || ""}
                onChange={(e) => set("message", e.target.value)}
                placeholder="Опишите, какой ответ вы ждёте от оператора"
                className="text-xs resize-none"
                rows={6}
              />
              <p className="text-[10px] text-muted-foreground">
                Переменные: {"{pipeline_name}"}, {"{run_id}"}, {"{all_outputs}"}
              </p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Timeout (minutes)</Label>
              <Input
                type="number"
                value={(d.timeout_minutes as number) ?? 120}
                onChange={(e) => set("timeout_minutes", parseFloat(e.target.value) || 120)}
                className="h-7 text-xs"
                min={1}
                max={10080}
              />
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

  const { data: pipeline, isLoading, isFetchedAfterMount } = useQuery({
    queryKey: ["studio", "pipeline", pipelineId],
    queryFn: () => (pipelineId ? studioPipelines.get(pipelineId) : null),
    enabled: !!pipelineId,
    refetchOnMount: "always",
  });
  const { data: pipelineCopilotMcpList = [] } = useQuery({ queryKey: ["studio", "mcp"], queryFn: studioMCP.list });

  const [nodes, setNodes, onNodesChangeRaw] = useNodesState([]);
  const [edges, setEdges, onEdgesChangeRaw] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<PipelineNode | null>(null);
  const [pipelineName, setPipelineName] = useState("");
  const [lastRun, setLastRun] = useState<PipelineRun | null>(null);
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [graphRunId, setGraphRunId] = useState<number | null>(null);
  const [graphRunLive, setGraphRunLive] = useState<PipelineRun | null>(null);
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [pipelineCopilotOpen, setPipelineCopilotOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(true);
  const [runTaskText, setRunTaskText] = useState("");
  const [runRequester, setRunRequester] = useState("");
  const [runTicketId, setRunTicketId] = useState("");
  const [runAdvancedOpen, setRunAdvancedOpen] = useState(false);
  const [runContextText, setRunContextText] = useState("{}");
  const [runContextError, setRunContextError] = useState<string | null>(null);
  const [runEntryNodeId, setRunEntryNodeId] = useState("");
  const [runTriggerError, setRunTriggerError] = useState<string | null>(null);
  const [hasHydratedPipeline, setHasHydratedPipeline] = useState(!pipelineId);
  const [hasLocalChanges, setHasLocalChanges] = useState(false);
  const nodeIdCounter = useRef(1);
  const manualTriggerOptions = useMemo(
    () => getActiveManualTriggerOptions(nodes as unknown as PipelineNode[]),
    [nodes],
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
  const runDialogMode = manualTriggerOptions.length
    ? "manual"
    : webhookTriggerNodes.length
      ? "webhook"
      : scheduleTriggerNodes.length
        ? "schedule"
        : monitoringTriggerNodes.length
          ? "monitoring"
          : "manual";
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
      setTimeout(() => fitView({ padding: 0.15, duration: 300 }), 100);
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
        : studioPipelines.create({ ...data, icon: "⚡" }),
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

  const handleCopyWebhookUrl = async (webhookUrl: string) => {
    try {
      await navigator.clipboard.writeText(toAbsoluteWebhookUrl(webhookUrl));
      toast({ description: localize(lang, "Webhook URL скопирован.", "Webhook URL copied.") });
    } catch (error) {
      const message = error instanceof Error
        ? error.message
        : localize(lang, "Не удалось скопировать webhook URL.", "Failed to copy webhook URL.");
      toast({ variant: "destructive", description: message });
    }
  };

  const handleRunSubmit = async () => {
    if (!manualTriggerOptions.length) {
      setRunTriggerError(
        localize(
          lang,
          "У этого пайплайна нет ручного trigger. Используйте webhook или schedule trigger.",
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
    setRunContextError(null);

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
      setRunTriggerError(localize(lang, "Выберите ручной trigger для запуска.", "Select the manual trigger that should start this run."));
      return;
    }
    setRunTriggerError(null);

    try {
      const saved = await saveMutation.mutateAsync({
        name: pipelineName || "Untitled",
        nodes: nodes as unknown as PipelineNode[],
        edges: edges as unknown as PipelineEdge[],
      });
      await runMutation.mutateAsync({
        targetPipelineId: pipelineId ?? saved.id,
        context,
        entryNodeId: selectedEntryNodeId,
      });
    } catch {
      // Error notifications are handled in mutation callbacks.
    }
  };

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
      toast({ description: `${getNodeDisplayLabel(nextTarget)} picked up starter settings from the connection.` });
    },
    [clearGraphOverlay, nodes, pipelineName, setEdges, setNodes, toast],
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
      setHasLocalChanges(true);
      setNodes((nds) => nds.map((item) => (item.id === targetNodeId ? ({ ...item, data: merged } as never) : item)));
      setActiveRunId(null);
      setSelectedNode({ ...targetNode, data: merged });
      toast({ description: `AI suggestion applied to ${getNodeDisplayLabel({ ...targetNode, data: merged })}.` });
    },
    [nodes, pipelineCopilotMcpList, setNodes, toast],
  );

  const handleApplyPipelineAssistantGraphPatch = useCallback(
    (graphPatch: StudioPipelineGraphPatch) => {
      const updateSpecs = (graphPatch.update_nodes || []).filter(
        (item) => item && typeof item.node_id === "string" && item.data && typeof item.data === "object",
      );
      const removeNodeIds = new Set((graphPatch.remove_node_ids || []).filter((item): item is string => Boolean(item)));
      const removeEdgeIds = new Set((graphPatch.remove_edge_ids || []).filter((item): item is string => Boolean(item)));
      if (!graphPatch.nodes.length && !graphPatch.edges.length && !updateSpecs.length && !removeNodeIds.size && !removeEdgeIds.size) {
        toast({ description: localize(lang, "В этом ответе нет изменений графа.", "This suggestion does not include graph changes.") });
        return;
      }

      const existingNodes = nodes as unknown as PipelineNode[];
      const existingEdges = edges as unknown as PipelineEdge[];
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
        const data: Record<string, unknown> = {
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

      const existingEdgeKeys = new Set(existingEdges.map((edge) => `${edge.source}:${edge.target}:${edge.label || ""}`));
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

      const updateMap = new Map(
        updateSpecs.map((item) => [
          item.node_id,
          normaliseAssistantPatch(item.data as Record<string, unknown>, {
            mcpList: pipelineCopilotMcpList.map((entry) => ({ id: entry.id, name: entry.name })),
          }),
        ]),
      );
      const updatedNodes = existingNodes
        .filter((node) => updateMap.has(node.id))
        .map((node) => ({
          ...node,
          data: { ...(node.data || {}), ...(updateMap.get(node.id) || {}) },
        }));
      const updatedNodeMap = new Map(updatedNodes.map((node) => [node.id, node]));

      const nextNodes = existingNodes
        .filter((node) => !removeNodeIds.has(node.id))
        .map((node) => updatedNodeMap.get(node.id) || node);
      if (createdNodes.length) {
        nextNodes.push(...createdNodes);
      }

      const nextEdges = existingEdges
        .filter((edge) => !removeEdgeIds.has(edge.id))
        .filter((edge) => !removeNodeIds.has(edge.source) && !removeNodeIds.has(edge.target));
      if (createdEdges.length) {
        nextEdges.push(...createdEdges);
      }

      if (
        !createdNodes.length &&
        !createdEdges.length &&
        !updatedNodes.length &&
        !removeNodeIds.size &&
        !removeEdgeIds.size
      ) {
        toast({ description: localize(lang, "Не удалось извлечь валидные изменения графа.", "No valid graph changes were found in this AI suggestion.") });
        return;
      }

      setHasLocalChanges(true);
      setNodes(nextNodes as never[]);
      setEdges(nextEdges as never[]);
      setSelectedNode(createdNodes[0] || updatedNodes[0] || null);
      clearGraphOverlay();
      setActiveRunId(null);
      toast({
        description: localize(
          lang,
          `Применено: +${createdNodes.length} нод, +${createdEdges.length} связей, обновлено ${updatedNodes.length}, удалено ${removeNodeIds.size} нод и ${removeEdgeIds.size} связей.`,
          `Applied: +${createdNodes.length} nodes, +${createdEdges.length} edges, updated ${updatedNodes.length}, removed ${removeNodeIds.size} nodes and ${removeEdgeIds.size} edges.`,
        ),
      });
      setTimeout(() => fitView({ padding: 0.18, duration: 300 }), 60);
    },
    [clearGraphOverlay, edges, fitView, lang, nodes, pipelineCopilotMcpList, screenToFlowPosition, selectedNode, setEdges, setNodes, toast],
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
          : pipelineActivityState.icon === "schedule"
            ? Clock
            : pipelineActivityState.icon === "warning"
              ? XCircle
              : Zap;

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
          onChange={(e) => {
            setPipelineName(e.target.value);
            setHasLocalChanges(true);
          }}
          className="h-7 text-sm font-medium w-64 border-0 shadow-none focus-visible:ring-0 px-0"
          placeholder="Pipeline name..."
        />
        <div className="ml-auto flex items-center gap-2">
          {resolvedLastRun && (
            <button
              type="button"
              onClick={() => {
                setGraphRunId(resolvedLastRun.id);
                setActiveRunId(resolvedLastRun.id);
              }}
              className="hidden items-center gap-2 rounded-md border border-border/70 bg-background/35 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-border hover:bg-background/50 hover:text-foreground sm:flex"
            >
              {resolvedLastRun.status === "running" && <Loader2 className="h-2.5 w-2.5 animate-spin mr-1" />}
              Run #{resolvedLastRun.id}: {resolvedLastRun.status}
            </button>
          )}
          <Button
            size="sm"
            onClick={handleSave}
            disabled={saveMutation.isPending || (Boolean(pipelineId) && !hasHydratedPipeline)}
            className="h-7 gap-1.5"
          >
            {saveMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            {localize(lang, "���������", "Save")}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={handleOpenRunDialog}
            disabled={runMutation.isPending || saveMutation.isPending || (Boolean(pipelineId) && !hasHydratedPipeline)}
            className="h-7 gap-1.5"
          >
            {runMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
            {localize(lang, "������", "Run")}
          </Button>

          <div className="w-px h-4 bg-border mx-1" />

          <Button
            size="icon"
            variant={pipelineCopilotOpen ? "secondary" : "ghost"}
            onClick={() => setPipelineCopilotOpen((prev) => !prev)}
            className={cn("h-7 w-7", pipelineCopilotOpen && "bg-primary/10 text-primary")}
            aria-label="AI Builder"
            title={localize(lang, "AI ���������", "AI Assistant")}
          >
            {pipelineCopilotOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
          </Button>
          
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="ghost" className="h-7 gap-1.5 rounded-md px-2 text-muted-foreground">
                <MoreHorizontal className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              {resolvedLastRun && (
                <DropdownMenuItem onClick={() => setActiveRunId(resolvedLastRun.id)}>
                  <Clock className="mr-2 h-3.5 w-3.5" />
                  {localize(lang, "������� ������ #", "Open run #")}
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
        nodes={pipelineNodes}
        edges={pipelineEdges}
        selectedNode={selectedNode}
        hasLocalChanges={hasLocalChanges}
        activityLabel={pipelineActivityState.label}
        lang={lang}
        onApplyPatch={handleApplyPipelineAssistantPatch}
        onApplyGraphPatch={handleApplyPipelineAssistantGraphPatch}
      />

      <div className="flex items-center gap-3 border-b border-border bg-muted/20 px-4 py-2 text-xs">
        <div className={`flex items-center gap-2 rounded-full border px-2.5 py-1 ${toolbarActivityToneClass}`}>
          <ToolbarActivityIcon
            className={`h-3.5 w-3.5 ${pipelineActivityState.icon === "running" ? "animate-spin" : ""}`}
          />
          <span className="font-medium">{pipelineActivityState.label}</span>
        </div>
        <p className="text-muted-foreground">{pipelineActivityState.detail}</p>
        {graphRunId && highlightedNode ? (
          <div className="inline-flex items-center gap-2 rounded-full border border-sky-500/25 bg-sky-500/10 px-2.5 py-1 text-sky-200">
            {isLivePipelineRunStatus(graphRunLive?.status) ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Info className="h-3.5 w-3.5" />}
            <span>
              {localize(lang, "Текущий шаг", "Current step")}: {getNodeDisplayLabel(highlightedNode)}
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

      {/* Flow summary bar */}
      {nodes.length > 0 && (
        <div className="flex items-center gap-1 px-4 py-1.5 border-b border-border bg-muted/30 overflow-x-auto">
          <span className="text-[10px] text-muted-foreground shrink-0 mr-1">Flow:</span>
          {(() => {
            // Build a simple chain from triggers -> connected nodes
            const pNodes = pipelineNodes;
            const pEdges = pipelineEdges;
            const visited = new Set<string>();
            const chain: PipelineNode[] = [];
            const triggers = pNodes.filter((n) => n.type?.startsWith("trigger/"));
            const queue = triggers.length ? [...triggers] : pNodes.slice(0, 1);
            while (queue.length && chain.length < 12) {
              const current = queue.shift()!;
              if (visited.has(current.id)) continue;
              visited.add(current.id);
              chain.push(current);
              const downstream = pEdges
                .filter((e) => e.source === current.id)
                .map((e) => pNodes.find((n) => n.id === e.target))
                .filter(Boolean) as PipelineNode[];
              queue.push(...downstream);
            }
            // Add orphans
            pNodes.forEach((n) => { if (!visited.has(n.id) && chain.length < 15) chain.push(n); });
            return chain.map((n, i) => (
              <span key={n.id} className="flex items-center gap-1 shrink-0">
                {i > 0 && <ChevronRight className="h-2.5 w-2.5 text-muted-foreground/40" />}
                <button
                  onClick={() => {
                    setSelectedNode(n);
                    setActiveRunId(null);
                  }}
                  className={cn(
                    "text-[10px] px-1.5 py-0.5 rounded-md border transition-colors",
                    graphState.currentNodeId === n.id
                      ? "border-blue-500/40 bg-blue-500/10 text-blue-200 shadow-[0_0_16px_rgba(59,130,246,0.18)]"
                      : graphState.traversedNodeIds.has(n.id)
                        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                        : graphState.queuedNodeIds.has(n.id)
                          ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-200"
                          : selectedNode?.id === n.id
                            ? "border-primary/40 bg-primary/10 text-primary"
                            : "border-transparent hover:bg-muted/50 text-muted-foreground hover:text-foreground"
                  )}
                >
                  {NODE_TYPE_LABELS[n.type || ""]?.icon || "🔧"} {getNodeDisplayLabel(n)}
                </button>
              </span>
            ));
          })()}
        </div>
      )}

      {/* Main area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Node palette */}
        <div className="w-56 shrink-0">
          <NodePalette onAddNode={handleAddNode} />
        </div>

        {/* Center: Canvas */}
        <div className="flex flex-1 min-w-0 flex-col">
          <div className="flex-1">
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
                  <p className="text-sm text-muted-foreground/70 font-medium">Build your automation pipeline</p>
                  <p className="text-xs text-muted-foreground/50 max-w-xs mx-auto">
                    Click or drag nodes from the palette on the left. Connect them to define the execution flow.
                  </p>
                </div>
              </Panel>
            )}
            </ReactFlow>
          </div>
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
            <DialogTitle>
              {runDialogMode === "manual"
                ? "Run Pipeline"
                : runDialogMode === "webhook"
                  ? "Webhook Trigger"
                  : runDialogMode === "schedule"
                    ? "Scheduled Trigger"
                    : "Monitoring Trigger"}
            </DialogTitle>
            <DialogDescription>
              {runDialogMode === "manual"
                ? "Choose the manual trigger that should start this run, then add optional task text and JSON context."
                : runDialogMode === "webhook"
                  ? "Webhook pipelines do not start from Run. Save the graph, then send an HTTP POST request to the webhook URL."
                  : runDialogMode === "schedule"
                    ? "Scheduled pipelines do not start from Run. Save the graph and let the scheduler create runs from the cron trigger."
                    : "Monitoring pipelines do not start from Run. Save the graph and let server monitoring open a matching alert."}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            {runDialogMode === "manual" ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="run-entry-trigger">Manual trigger</Label>
                  <Select
                    value={runEntryNodeId}
                    onValueChange={(value) => {
                      setRunEntryNodeId(value);
                      if (runTriggerError) setRunTriggerError(null);
                    }}
                    disabled={manualTriggerOptions.length <= 1}
                  >
                    <SelectTrigger id="run-entry-trigger">
                      <SelectValue
                        placeholder={
                          manualTriggerOptions.length === 0
                            ? localize(lang, "Нет активных manual trigger нод", "No active manual trigger nodes")
                            : manualTriggerOptions.length === 1
                              ? manualTriggerOptions[0].label
                              : localize(lang, "Выберите trigger", "Select a trigger")
                        }
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {manualTriggerOptions.map((trigger) => (
                        <SelectItem key={trigger.node_id} value={trigger.node_id}>
                          {trigger.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-[11px] text-muted-foreground">
                    {manualTriggerOptions.length <= 1
                      ? localize(lang, "Если ручной trigger один, он будет выбран автоматически.", "When there is only one manual trigger, it is selected automatically.")
                      : localize(lang, "Этот trigger запустит только свою ветку графа.", "This trigger starts only its own branch of the graph.")}
                  </p>
                  {runTriggerError ? <p className="text-xs text-red-400">{runTriggerError}</p> : null}
                </div>

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
              </>
            ) : runDialogMode === "webhook" ? (
              <div className="space-y-4">
                {activeWebhookTriggers.length ? (
                  <div className="rounded-xl border border-sky-500/25 bg-sky-500/10 px-3 py-2 text-xs text-sky-200">
                    {localize(
                      lang,
                      "Trigger уже armed и ждёт входящий POST запрос. Новый run появится только когда webhook реально придёт.",
                      "This trigger is already armed and waiting for an incoming POST request. A new run will appear only when the webhook actually arrives.",
                    )}
                  </div>
                ) : (
                  <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                    {localize(
                      lang,
                      "Сначала сохраните граф, чтобы arm webhook trigger и получить URL.",
                      "Save the graph first to arm the webhook trigger and generate its URL.",
                    )}
                  </div>
                )}
                {activeWebhookTriggers.length ? (
                  activeWebhookTriggers.map((trigger) => (
                    <div key={trigger.id} className="space-y-2 rounded-xl border border-border bg-background/60 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium text-foreground">{trigger.name || "Webhook trigger"}</div>
                          <div className="text-[11px] text-muted-foreground">Node `{trigger.node_id}`</div>
                        </div>
                        <Button size="sm" variant="outline" onClick={() => void handleCopyWebhookUrl(trigger.webhook_url)}>
                          <Copy className="mr-1.5 h-3.5 w-3.5" />
                          {localize(lang, "Скопировать URL", "Copy URL")}
                        </Button>
                      </div>
                      <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground break-all">
                        {toAbsoluteWebhookUrl(trigger.webhook_url)}
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        {trigger.last_triggered_at
                          ? localize(lang, `Последний trigger: ${formatStudioDateTime(trigger.last_triggered_at)}`, `Last trigger: ${formatStudioDateTime(trigger.last_triggered_at)}`)
                          : localize(lang, "Ещё не вызывался.", "Has not been triggered yet.")}
                      </p>
                    </div>
                  ))
                ) : (
                  <div className="rounded-xl border border-dashed border-border px-3 py-3 text-xs text-muted-foreground">
                    {localize(
                      lang,
                      "Сначала сохраните pipeline, чтобы сгенерировать webhook URL для этой trigger ноды.",
                      "Save the pipeline first to generate a webhook URL for this trigger node.",
                    )}
                  </div>
                )}
              </div>
            ) : runDialogMode === "schedule" ? (
              <div className="space-y-4">
                <div className="rounded-xl border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                  {localize(
                    lang,
                    "Schedule trigger запускается планировщиком. Ручной Run для него не нужен.",
                    "Schedule triggers are started by the scheduler. They do not need a manual Run.",
                  )}
                </div>
                {(activeScheduleTriggers.length
                  ? activeScheduleTriggers.map((trigger) => ({
                      id: String(trigger.id),
                      label: trigger.name || trigger.node_id,
                      cron: trigger.cron_expression || "not set",
                    }))
                  : scheduleTriggerNodes.map((node) => ({
                      id: node.id,
                      label: getNodeDisplayLabel(node),
                      cron:
                        typeof node.data?.cron_expression === "string" && node.data.cron_expression.trim()
                          ? node.data.cron_expression
                          : "not set",
                    }))).map((trigger) => (
                  <div key={trigger.id} className="rounded-xl border border-border bg-background/60 p-3">
                    <div className="text-sm font-medium text-foreground">{trigger.label}</div>
                    <div className="mt-1 text-xs text-muted-foreground">Cron: {trigger.cron}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                  {localize(
                    lang,
                    "Monitoring trigger уже armed после сохранения и ждёт alert от server monitoring. Run появится только при реальной проблеме.",
                    "The monitoring trigger is armed after save and waits for a server monitoring alert. A run appears only when a real issue is detected.",
                  )}
                </div>
                {(activeMonitoringTriggers.length
                  ? activeMonitoringTriggers.map((trigger) => ({
                      id: String(trigger.id),
                      label: trigger.name || trigger.node_id,
                      filters: trigger.monitoring_filters || {},
                      lastTriggeredAt: trigger.last_triggered_at,
                    }))
                  : monitoringTriggerNodes.map((node) => ({
                      id: node.id,
                      label: getNodeDisplayLabel(node),
                      filters: node.data?.monitoring_filters || {},
                      lastTriggeredAt: null,
                    }))).map((trigger) => (
                  <div key={trigger.id} className="rounded-xl border border-border bg-background/60 p-3">
                    <div className="text-sm font-medium text-foreground">{trigger.label}</div>
                    <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                      <div>Servers: {Array.isArray((trigger.filters as Record<string, unknown>).server_ids) && ((trigger.filters as Record<string, unknown>).server_ids as unknown[]).length ? (((trigger.filters as Record<string, unknown>).server_ids as unknown[]).join(", ")) : "any"}</div>
                      <div>Severity: {Array.isArray((trigger.filters as Record<string, unknown>).severities) && ((trigger.filters as Record<string, unknown>).severities as unknown[]).length ? (((trigger.filters as Record<string, unknown>).severities as unknown[]).join(", ")) : "any"}</div>
                      <div>Alert type: {Array.isArray((trigger.filters as Record<string, unknown>).alert_types) && ((trigger.filters as Record<string, unknown>).alert_types as unknown[]).length ? (((trigger.filters as Record<string, unknown>).alert_types as unknown[]).join(", ")) : "any"}</div>
                      <div>Containers: {Array.isArray((trigger.filters as Record<string, unknown>).container_names) && ((trigger.filters as Record<string, unknown>).container_names as unknown[]).length ? (((trigger.filters as Record<string, unknown>).container_names as unknown[]).join(", ")) : "any"}</div>
                      {trigger.lastTriggeredAt ? <div>{localize(lang, `Последний trigger: ${formatStudioDateTime(trigger.lastTriggeredAt)}`, `Last trigger: ${formatStudioDateTime(trigger.lastTriggeredAt)}`)}</div> : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRunDialogOpen(false)}>
              {runDialogMode === "manual" ? "Cancel" : "Close"}
            </Button>
            {runDialogMode === "manual" ? (
              <Button onClick={handleRunSubmit} disabled={runMutation.isPending || saveMutation.isPending}>
                {runMutation.isPending || saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Run
              </Button>
            ) : (
              <Button onClick={handleSave} disabled={saveMutation.isPending || (Boolean(pipelineId) && !hasHydratedPipeline)}>
                {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                {localize(lang, "Сохранить trigger", "Save Trigger")}
              </Button>
            )}
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
