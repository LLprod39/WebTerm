import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
  Zap,
  Bot,
  Wand2,
  MoreHorizontal,
  Copy,
  FileText,
  Info,
  Link2,
  Search,
  RotateCcw,
  Terminal,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useToast } from "@/hooks/use-toast";
import {
  studioPipelines,
  studioAgents,
  studioServers,
  studioRuns,
  studioMCP,
  studioSkills,
  studioNodeManifests,
  fetchModels,
  refreshModels,
  getStudioPipelineRunWsUrl,
  type MCPServerInspection,
  type MCPServerTool,
  type ModelsResponse,
  type PipelineNode,
  type PipelineEdge,
  type PipelineRun,
  type PipelineTrigger,
  type StudioCapabilityNode,
} from "@/lib/api";
import type { StudioPipelineAssistantResponse } from "@/lib/studioPipelineDraftsApi";
import { cn } from "@/lib/utils";
import { applyAssistantGraphPatch, getAssistantPatchStats } from "@/components/pipeline/assistantPatch";
import { formatCommandListText, parseCommandListText } from "@/components/pipeline/commandList";
import { getPipelineClientValidationErrors } from "@/components/pipeline/pipelineClientValidation";
import { getPipelineActivityState } from "@/components/pipeline/pipelineActivity";
import { buildPipelineRunGraphState } from "@/components/pipeline/pipelineRunGraph";
import { buildPipelineRiskSummary, type PipelineRiskSummary } from "@/components/pipeline/pipelineRiskSummary";
import { getRunDialogCopy } from "@/components/studio/PipelineEditorCopy";
import { PipelineDraftReview } from "@/components/studio/PipelineDraftReview";
import { AgentNodePanel } from "@/components/pipeline/node-panel/AgentNodePanel";
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
import { getNodeCategoryLabel, getNodePaletteText, getNodeTypeGuidance, getNodeTypeInfo } from "@/components/pipeline/nodes/nodeMeta";

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
  "ops/server_snapshot": OutputNode,
  "ops/log_query": OutputNode,
  "ops/file_action": OutputNode,
  "ops/package_action": OutputNode,
  "ops/disk_cleanup": OutputNode,
  "ops/backup_restore_check": OutputNode,
  "ops/service_action": OutputNode,
  "ops/docker_action": OutputNode,
  "ops/process_action": OutputNode,
  "ops/http_check": OutputNode,
  "ops/alert_update": OutputNode,
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

const NODE_TYPE_LOOKUP = Object.fromEntries(
  NODE_PALETTE.flatMap((group) => group.nodes.map((node) => [node.type, node] as const)),
);

const CATEGORY_ICONS = {
  Triggers: Play,
  Agents: Bot,
  Ops: Terminal,
  Logic: Zap,
  Output: FileText,
} as const;

function getNodePhaseKey(type?: string) {
  if (type?.startsWith("trigger/")) return "trigger";
  if (type?.startsWith("agent/")) return "agent";
  if (type?.startsWith("ops/")) return "ops";
  if (type?.startsWith("logic/")) return "logic";
  if (type?.startsWith("output/")) return "output";
  return "other";
}

function getNodePhaseLabel(type: string | undefined, lang: string) {
  const phase = getNodePhaseKey(type);
  if (phase === "trigger") return localize(lang, "Триггеры", "Triggers");
  if (phase === "agent") return localize(lang, "Агенты", "Agents");
  if (phase === "ops") return localize(lang, "OPS", "Ops");
  if (phase === "logic") return localize(lang, "Логика", "Logic");
  if (phase === "output") return localize(lang, "Выход", "Output");
  return localize(lang, "Шаги", "Steps");
}

function getPipelineActivityCopy(state: ReturnType<typeof getPipelineActivityState>, lang: "en" | "ru") {
  if (lang !== "ru") return { label: state.label, detail: state.detail };
  if (state.label === "No active trigger") {
    return {
      label: "Нет активного триггера",
      detail: "Добавьте ручной запуск, webhook, расписание или мониторинг, чтобы подготовить pipeline к запуску.",
    };
  }
  if (state.label === "Legacy graph") {
    return {
      label: "Старый граф",
      detail: "Пересохраните pipeline как V2, прежде чем запускать его снова.",
    };
  }
  if (state.label === "Running") {
    return {
      label: "Выполняется",
      detail: state.detail.replace(/^Run #(\d+) is executing now\.$/, "Запуск #$1 выполняется сейчас."),
    };
  }
  if (state.label === "Pending") {
    return {
      label: "В очереди",
      detail: state.detail.replace(/^Run #(\d+) is queued and starting soon\.$/, "Запуск #$1 в очереди и скоро стартует."),
    };
  }
  if (state.label === "Manual ready") {
    return {
      label: "Ручной запуск готов",
      detail: state.detail.startsWith("Ready for one manual")
        ? "Готова одна ручная точка входа."
        : state.detail.replace(/^Ready for (\d+) manual entry points\.$/, "Готово ручных точек входа: $1."),
    };
  }
  if (state.label === "Active") {
    return {
      label: "Активен",
      detail: state.detail
        .replace("Waiting for webhook POST.", "Ожидает webhook POST.")
        .replace("Waiting for the schedule trigger.", "Ожидает запуск по расписанию.")
        .replace("Waiting for a monitoring alert.", "Ожидает алерт мониторинга.")
        .replace(/^Multiple trigger types are active: /, "Активны несколько типов триггеров: ")
        .replace(" Last trigger ", " Последний запуск ")
        .replace(/\bmanual\b/g, "ручной")
        .replace(/\bwebhook\b/g, "webhook")
        .replace(/\bschedule\b/g, "расписание")
        .replace(/\bmonitoring\b/g, "мониторинг"),
    };
  }
  return { label: state.label, detail: state.detail };
}

function getNodePhaseBadgeClass(type?: string) {
  const phase = getNodePhaseKey(type);
  if (phase === "trigger") return "border-sky-500/25 bg-sky-500/10 text-sky-200";
  if (phase === "agent") return "border-violet-500/25 bg-violet-500/10 text-violet-200";
  if (phase === "ops") return "border-cyan-500/25 bg-cyan-500/10 text-cyan-200";
  if (phase === "logic") return "border-orange-500/25 bg-orange-500/10 text-orange-200";
  if (phase === "output") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-200";
  return "border-border/70 bg-background/60 text-muted-foreground";
}

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
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
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

              {/* Human Approval waiting state - always show links */}
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

const MCP_MUTATING_TOOL_RE = /(^|[_\-.])(add|apply|assign|create|delete|disable|enable|grant|patch|remove|restart|revoke|set|start|stop|update|write)([_\-.]|$)/i;

const MCP_PERMISSION_MODE_OPTIONS = [
  { value: "PLAN", label: "Plan", descriptionRu: "Только чтение и планирование.", descriptionEn: "Read-only planning mode." },
  { value: "SAFE", label: "Safe", descriptionRu: "Безопасный режим по умолчанию с policy notes.", descriptionEn: "Default guarded mode with policy notes." },
  { value: "ASSISTED", label: "Assisted", descriptionRu: "Оператор контролирует рискованные действия.", descriptionEn: "Operator-assisted execution for risky actions." },
  { value: "AUTO_GUARDED", label: "Auto guarded", descriptionRu: "Авто-выполнение только через guardrails.", descriptionEn: "Automatic execution through guardrails only." },
] as const;

const CRON_PRESETS = [
  {
    id: "every_5_min",
    labelRu: "Каждые 5 минут",
    labelEn: "Every 5 minutes",
    descriptionRu: "Для частых health-check и быстрых проверок.",
    descriptionEn: "For frequent health checks and fast polling.",
    value: "*/5 * * * *",
  },
  {
    id: "hourly",
    labelRu: "Каждый час",
    labelEn: "Hourly",
    descriptionRu: "Запуск в начале каждого часа.",
    descriptionEn: "Runs at the top of every hour.",
    value: "0 * * * *",
  },
  {
    id: "daily",
    labelRu: "Каждый день",
    labelEn: "Daily",
    descriptionRu: "Один раз в день в выбранное время.",
    descriptionEn: "Runs once per day at the selected time.",
    value: "0 4 * * *",
  },
] as const;

function parseCronExpression(value: unknown): string[] | null {
  const parts = String(value || "").trim().split(/\s+/).filter(Boolean);
  return parts.length === 5 ? parts : null;
}

function padCronNumber(value: string) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? String(numeric).padStart(2, "0") : value;
}

function getDailyTimeFromCron(value: unknown) {
  const parts = parseCronExpression(value);
  if (!parts || parts[2] !== "*" || parts[3] !== "*" || parts[4] !== "*") return "04:00";
  const [minute, hour] = parts;
  if (!/^\d+$/.test(minute) || !/^\d+$/.test(hour)) return "04:00";
  return `${padCronNumber(hour)}:${padCronNumber(minute)}`;
}

function getMinuteIntervalFromCron(value: unknown) {
  const parts = parseCronExpression(value);
  if (!parts || parts[1] !== "*" || parts[2] !== "*" || parts[3] !== "*" || parts[4] !== "*") return 5;
  const match = parts[0].match(/^\*\/(\d+)$/);
  if (!match) return 5;
  return Math.max(1, Math.min(59, Number(match[1]) || 5));
}

function dailyTimeToCron(value: string) {
  const [hour = "4", minute = "0"] = value.split(":");
  return `${Number(minute) || 0} ${Number(hour) || 0} * * *`;
}

function describeCronExpression(value: unknown, lang: "en" | "ru") {
  const parts = parseCronExpression(value);
  if (!parts) {
    return localize(lang, "Расписание не настроено или cron заполнен неверно.", "Schedule is not set or the cron expression is invalid.");
  }
  const [minute, hour, day, month, weekday] = parts;
  if (/^\*\/\d+$/.test(minute) && hour === "*" && day === "*" && month === "*" && weekday === "*") {
    const interval = minute.replace("*/", "");
    return localize(lang, `Запуск каждые ${interval} мин.`, `Runs every ${interval} min.`);
  }
  if (minute === "0" && hour === "*" && day === "*" && month === "*" && weekday === "*") {
    return localize(lang, "Запуск каждый час в :00.", "Runs every hour at :00.");
  }
  if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && day === "*" && month === "*" && weekday === "*") {
    return localize(lang, `Запуск каждый день в ${padCronNumber(hour)}:${padCronNumber(minute)}.`, `Runs every day at ${padCronNumber(hour)}:${padCronNumber(minute)}.`);
  }
  if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && day === "*" && month === "*" && weekday === "1-5") {
    return localize(lang, `Запуск по будням в ${padCronNumber(hour)}:${padCronNumber(minute)}.`, `Runs on weekdays at ${padCronNumber(hour)}:${padCronNumber(minute)}.`);
  }
  return localize(lang, "Пользовательское cron-расписание.", "Custom cron schedule.");
}

function getCronPresetId(value: unknown) {
  const cron = String(value || "").trim();
  return CRON_PRESETS.find((preset) => preset.value === cron)?.id || "custom";
}

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

function getSchemaProperties(inputSchema?: Record<string, unknown>) {
  const properties = inputSchema?.properties;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) return {};
  return properties as Record<string, Record<string, unknown>>;
}

function getSchemaRequiredFields(inputSchema?: Record<string, unknown>) {
  const required = inputSchema?.required;
  return new Set(Array.isArray(required) ? required.map((item) => String(item)) : []);
}

function getSchemaType(property: Record<string, unknown>) {
  const rawType = property.type;
  if (Array.isArray(rawType)) return String(rawType.find((item) => item !== "null") || "string");
  return String(rawType || "string");
}

function coerceSchemaFormValue(rawValue: string | boolean, property: Record<string, unknown>) {
  const type = getSchemaType(property);
  if (type === "boolean") return Boolean(rawValue);
  if (type === "integer") {
    const parsed = Number.parseInt(String(rawValue), 10);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  if (type === "number") {
    const parsed = Number.parseFloat(String(rawValue));
    return Number.isFinite(parsed) ? parsed : 0;
  }
  if (type === "array" || type === "object") {
    try {
      const parsed = JSON.parse(String(rawValue || (type === "array" ? "[]" : "{}")));
      if (type === "array" && Array.isArray(parsed)) return parsed;
      if (type === "object" && parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
    } catch {
      // Keep the previous valid value from the JSON editor when a nested field is invalid.
    }
    return type === "array" ? [] : {};
  }
  return String(rawValue);
}

function getSchemaFormTextValue(value: unknown, property: Record<string, unknown>) {
  const type = getSchemaType(property);
  if (type === "array" || type === "object") return JSON.stringify(value ?? (type === "array" ? [] : {}), null, 2);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value === undefined || value === null) return "";
  return String(value);
}

function formatStudioDateTime(value?: string | null) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

function getNodeDisplayLabel(
  node: PipelineNode | { id: string; type: string; label?: string },
  lang: "en" | "ru" = "en",
) {
  if ("data" in node) {
    const label = typeof node.data?.label === "string" ? node.data.label.trim() : "";
    if (label) return label;
  }
  if ("label" in node && typeof node.label === "string" && node.label.trim()) return node.label.trim();
  return getNodeTypeInfo(node.type, lang).label || node.id;
}

function getActiveManualTriggerOptions(nodes: PipelineNode[], lang: "en" | "ru" = "en") {
  return nodes
    .filter((node) => node.type === "trigger/manual" && node.data?.is_active !== false)
    .map((node) => ({
      node_id: node.id,
      label: getNodeDisplayLabel(node, lang),
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
    return localize(lang, "Ждёт подтверждение", "Waiting approval");
  }
  if (status === "awaiting_operator_reply") {
    return localize(lang, "Ждёт ответ", "Waiting reply");
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
    case "agent/ssh_cmd":
      return { preflight_commands: [], verification_commands: [], permission_mode: "SAFE", on_failure: "abort" };
    case "agent/mcp_call":
      return { arguments: {}, arguments_text: "{}", permission_mode: "SAFE", skill_slugs: [], on_failure: "abort" };
    case "ops/server_snapshot":
      return { sections: ["overview", "services", "docker", "disk"], server_id_context_key: "server_id", on_failure: "continue" };
    case "ops/log_query":
      return { source: "journal", lines: 120, service: "", container: "", filter_text: "", server_id_context_key: "server_id", on_failure: "continue" };
    case "ops/file_action":
      return { action: "read", path: "", content: "", max_bytes: 131072, server_id_context_key: "server_id", on_failure: "continue" };
    case "ops/package_action":
      return { action: "list_updates", packages: [], verify: true, server_id_context_key: "server_id", on_failure: "continue" };
    case "ops/disk_cleanup":
      return { action: "inspect", dry_run: true, verify: true, min_age_days: 7, max_entries: 50, vacuum_time_days: 14, server_id_context_key: "server_id", on_failure: "continue" };
    case "ops/backup_restore_check":
      return { action: "inspect", path: "/var/backups", max_depth: 2, max_files: 20, max_age_hours: 24, server_id_context_key: "server_id", on_failure: "continue" };
    case "ops/service_action":
      return { action: "restart", verify: true, server_id_context_key: "server_id", on_failure: "continue" };
    case "ops/docker_action":
      return { action: "restart", include_logs: true, verify: true, server_id_context_key: "server_id", on_failure: "continue" };
    case "ops/process_action":
      return { action: "terminate", pid_context_key: "pid", server_id_context_key: "server_id", on_failure: "continue" };
    case "ops/http_check":
      return { method: "GET", expected_status: [200], timeout_seconds: 15, retries: 1, on_failure: "continue" };
    case "ops/alert_update":
      return { action: "resolve", alert_id_context_key: "alert_id", on_failure: "continue" };
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

function NodeFormSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3 rounded-lg border border-border/70 bg-background/55 px-3 py-3">
      <div className="space-y-1">
        <h4 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{title}</h4>
        {description ? <p className="text-[11px] leading-relaxed text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

function FieldHint({ children }: { children: ReactNode }) {
  return <p className="text-[10px] leading-relaxed text-muted-foreground">{children}</p>;
}

function RunRiskSummaryPanel({ summary, lang }: { summary: PipelineRiskSummary; lang: string }) {
  const levelText =
    summary.level === "safe"
      ? localize(lang, "Безопасно", "Safe")
      : summary.level === "dangerous"
        ? localize(lang, "Нужно подтверждение", "Needs approval")
        : localize(lang, "Проверьте", "Review");
  const toneClass =
    summary.level === "safe"
      ? "border-emerald-500/25 bg-emerald-500/5"
      : summary.level === "dangerous"
        ? "border-red-500/25 bg-red-500/5"
        : "border-amber-500/25 bg-amber-500/5";
  const iconClass =
    summary.level === "safe"
      ? "text-emerald-400"
      : summary.level === "dangerous"
        ? "text-red-400"
        : "text-amber-400";

  return (
    <section className={cn("rounded-xl border px-3 py-3", toneClass)}>
      <div className="flex items-start gap-3">
        {summary.level === "safe" ? (
          <CheckCircle2 className={cn("mt-0.5 h-4 w-4 shrink-0", iconClass)} />
        ) : summary.level === "dangerous" ? (
          <XCircle className={cn("mt-0.5 h-4 w-4 shrink-0", iconClass)} />
        ) : (
          <Info className={cn("mt-0.5 h-4 w-4 shrink-0", iconClass)} />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">{localize(lang, "Риск перед запуском", "Risk before run")}</p>
            <Badge variant={summary.level === "safe" ? "outline" : "secondary"} className="text-[10px]">
              {levelText}
            </Badge>
            {summary.missingApprovalCount > 0 ? (
              <Badge variant="destructive" className="text-[10px]">
                {localize(lang, `${summary.missingApprovalCount} без подтверждения`, `${summary.missingApprovalCount} missing approval`)}
              </Badge>
            ) : null}
          </div>
          <div className="mt-2 grid gap-2 text-[11px] text-muted-foreground sm:grid-cols-3">
            <div>{localize(lang, "Изменяющие шаги", "Mutating steps")}: <span className="text-foreground">{summary.mutatingCount}</span></div>
            <div>{localize(lang, "Подтверждения", "Approval gates")}: <span className="text-foreground">{summary.approvalCount}</span></div>
            <div>{localize(lang, "Проверки", "Verification")}: <span className="text-foreground">{summary.verificationCount}</span></div>
          </div>
          {summary.items.length ? (
            <ul className="mt-2 space-y-1 text-[11px] text-muted-foreground">
              {summary.items.slice(0, 4).map((item) => (
                <li key={item.nodeId} className="flex items-start gap-1.5">
                  <span className={item.hasApproval ? "text-emerald-400" : "text-red-400"}>{item.hasApproval ? "ok" : "!"}</span>
                  <span>
                    <span className="text-foreground">{item.label}</span>: {item.reason}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-[11px] text-muted-foreground">
              {localize(lang, "Изменяющих действий не найдено.", "No mutating actions detected.")}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function AdvancedDisclosure({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details
      className="group rounded-lg border border-dashed border-border/70 bg-muted/10 px-3 py-2"
      open={defaultOpen}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        {title}
        <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-3 space-y-3">{children}</div>
    </details>
  );
}

function FailureSelect({
  lang,
  value,
  onChange,
}: {
  lang: "en" | "ru";
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{localize(lang, "При ошибке", "On failure")}</Label>
      <Select value={value || "abort"} onValueChange={onChange}>
        <SelectTrigger className="h-8 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="abort">{localize(lang, "Остановить pipeline", "Abort pipeline")}</SelectItem>
          <SelectItem value="continue">{localize(lang, "Продолжить", "Continue")}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}

function NodeConfigPanel({
  node,
  pipelineId,
  trigger,
  lang,
  onUpdate,
  onClose,
  onDelete,
  onDuplicate,
}: {
  node: PipelineNode;
  pipelineId: number | null;
  trigger?: PipelineTrigger | null;
  lang?: "en" | "ru";
  onUpdate: (id: string, data: Record<string, unknown>) => void;
  onClose: () => void;
  onDelete: (id: string) => void;
  onDuplicate: (id: string) => void;
}) {
  const navigate = useNavigate();
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
  const uiLang: "en" | "ru" = lang === "ru" ? "ru" : "en";

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
  const scheduleCronExpression = String(d.cron_expression || trigger?.cron_expression || "");
  const schedulePresetId = getCronPresetId(scheduleCronExpression);
  const scheduleDailyTime = getDailyTimeFromCron(scheduleCronExpression);
  const scheduleMinuteInterval = getMinuteIntervalFromCron(scheduleCronExpression);

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
  const selectedToolName = String(d.tool_name || "");
  const embeddedInputSchema =
    d.input_schema && typeof d.input_schema === "object" && !Array.isArray(d.input_schema)
      ? (d.input_schema as Record<string, unknown>)
      : undefined;
  const embeddedTool: MCPServerTool | null =
    selectedToolName && embeddedInputSchema
      ? {
          name: selectedToolName,
          description: typeof d.tool_description === "string" ? d.tool_description : "",
          inputSchema: embeddedInputSchema,
        }
      : null;
  const selectedTool = mcpTools.find((tool) => tool.name === selectedToolName) || embeddedTool;
  const selectedToolProperties = useMemo(() => getSchemaProperties(selectedTool?.inputSchema), [selectedTool]);
  const selectedToolRequiredFields = useMemo(() => getSchemaRequiredFields(selectedTool?.inputSchema), [selectedTool]);
  const mcpArgsForForm = mcpArgsState.value || {};
  const mcpLooksMutating = MCP_MUTATING_TOOL_RE.test(selectedToolName);
  const mcpRiskReasons = useMemo(() => {
    const reasons: string[] = [];
    if (mcpLooksMutating) {
      reasons.push(localize(uiLang, "Имя инструмента похоже на изменение состояния.", "Tool name looks like a state-changing action."));
    }
    if (selectedMcp?.last_test_ok === false) {
      reasons.push(localize(uiLang, "Последняя проверка MCP-сервера завершилась ошибкой.", "Last MCP server test failed."));
    }
    if (mcpLooksMutating && selectedSkillSlugs.length === 0) {
      reasons.push(localize(uiLang, "Для mutating вызова лучше привязать skill/policy.", "Attach a skill/policy for mutating calls."));
    }
    if (!reasons.length) {
      reasons.push(localize(uiLang, "Риск низкий или неизвестный. Проверьте схему инструмента и аргументы.", "Read-only or unknown risk. Review the tool schema and arguments."));
    }
    return reasons;
  }, [mcpLooksMutating, selectedMcp?.last_test_ok, selectedSkillSlugs.length, uiLang]);

  const setMcpArgument = useCallback((key: string, property: Record<string, unknown>, rawValue: string | boolean) => {
    const parsed = parseJsonObjectText(mcpArgsText);
    const base = parsed.value || {};
    const nextArgs = { ...base, [key]: coerceSchemaFormValue(rawValue, property) };
    const text = JSON.stringify(nextArgs, null, 2);
    setMcpArgsText(text);
    setMany({ arguments_text: text, arguments: nextArgs });
  }, [mcpArgsText, setMany]);

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

  const typeInfo = getNodeTypeInfo(type, uiLang);
  const TypeIcon = NODE_TYPE_LOOKUP[type as NodeType]?.icon;
  const typeIconClassName = NODE_TYPE_LOOKUP[type as NodeType]?.iconClassName || "text-foreground";
  const nodeGuidance = getNodeTypeGuidance(type, uiLang);
  const triggerWebhookUrl = trigger?.webhook_url ? new URL(trigger.webhook_url, window.location.origin).toString() : "";

  const handleAgentProviderChange = useCallback((nextProvider: string) => {
    if (nextProvider === "auto") {
      setMany({ provider: "auto", model: "" });
      return;
    }
    if (!isModelProvider(nextProvider)) return;

    set("provider", nextProvider);
    setLoadingModelsFor(nextProvider);
    refreshModels(nextProvider)
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
  }, [queryClient, set, setMany]);

  const agentProviderOptions = useMemo(
    () =>
      AGENT_PROVIDER_OPTIONS.map((item) => {
        if (item.value === "auto") {
          return {
            value: item.value,
            label: item.label,
            modelLabel: localize(uiLang, "Глобальная модель агента", "Workspace default agent model"),
            hint: localize(uiLang, "Берётся из системного дефолта", "Uses the workspace default"),
          };
        }

        const availableModels = getModelsForProvider(modelsData, item.value);
        const modelLabel =
          loadingModelsFor === item.value
            ? localize(uiLang, "Загрузка моделей...", "Loading models...")
            : provider === item.value
              ? currentModel || availableModels[0] || localize(uiLang, "Модели недоступны", "No models available")
              : availableModels[0] || localize(uiLang, "Нажмите, чтобы загрузить", "Click to load");

        return {
          value: item.value,
          label: item.label,
          modelLabel,
          hint:
            provider === item.value
              ? localize(uiLang, "Активный провайдер", "Active provider")
              : localize(uiLang, "Доступно для выбора", "Available to select"),
        };
      }),
    [currentModel, loadingModelsFor, modelsData, provider, uiLang],
  );

  if (type === "agent/react" || type === "agent/multi") {
    const displayLabel = typeof d.label === "string" && d.label.trim() ? d.label.trim() : typeInfo.label;

    return (
      <AgentNodePanel
        lang={uiLang}
        node={node}
        data={d}
        title={displayLabel}
        breadcrumb={`${nodeGuidance.category} / ${typeInfo.label}`}
        guidanceSummary={nodeGuidance.summary}
        guidanceChecklist={nodeGuidance.checklist}
        icon={
          TypeIcon
            ? <TypeIcon className={`h-5 w-5 ${typeIconClassName}`} />
            : <span className="text-xs font-semibold text-foreground">#</span>
        }
        agents={agents}
        selectedAgent={selectedAgent}
        provider={provider || "auto"}
        providerOptions={agentProviderOptions}
        modelList={modelList}
        loadingModelsFor={loadingModelsFor}
        mcpList={mcpList}
        servers={servers}
        skillList={skillList}
        selectedSkillSlugs={selectedSkillSlugs}
        selectedSkills={selectedSkills}
        onSet={set}
        onSetMany={setMany}
        onProviderChange={handleAgentProviderChange}
        onClose={onClose}
        onDuplicate={() => onDuplicate(node.id)}
        onDelete={() => onDelete(node.id)}
        onBrowseCatalog={() => navigate("/studio/skills")}
      />
    );
  }

  return (
    <div className="flex h-full flex-col bg-card">
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-start gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-border/70 bg-background/70">
            {TypeIcon ? <TypeIcon className={`h-4 w-4 ${typeIconClassName}`} /> : <span className="text-xs">#</span>}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">{(d.label as string) || typeInfo.label}</p>
            <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
              {nodeGuidance.category} / {typeInfo.label} · {node.id}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            title={localize(uiLang, "Дублировать ноду", "Duplicate node")}
            onClick={() => onDuplicate(node.id)}
          >
            <Copy className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-destructive hover:text-destructive"
            title={localize(uiLang, "Удалить ноду", "Delete node")}
            onClick={() => onDelete(node.id)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
          <Button size="icon" variant="ghost" className="h-7 w-7" title={localize(uiLang, "Закрыть", "Close")} onClick={onClose}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        <section className="rounded-xl border border-primary/15 bg-primary/5 px-3 py-3">
          <div className="flex items-start gap-2">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <div className="min-w-0">
              <p className="text-xs font-semibold text-foreground">
                {localize(uiLang, "Что делает эта нода", "What this node does")}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{nodeGuidance.summary}</p>
            </div>
          </div>
          {nodeGuidance.checklist.length ? (
            <div className="mt-3 space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {localize(uiLang, "Нужно настроить", "Required setup")}
              </p>
              {nodeGuidance.checklist.map((item) => (
                <div key={item} className="flex items-start gap-2 text-[11px] leading-5 text-muted-foreground">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          ) : null}
        </section>

        <NodeFormSection
          title={localize(uiLang, "Основное", "Basic")}
          description={localize(uiLang, "Название и базовое поведение шага на схеме.", "Name and basic behavior for this graph step.")}
        >
          <div className="space-y-1.5">
            <Label className="text-xs">{localize(uiLang, "Название в схеме", "Node label")}</Label>
            <Input
              value={(d.label as string) || ""}
              onChange={(e) => set("label", e.target.value)}
              placeholder={localize(uiLang, "Например: Проверить alert", "Example: Check alert")}
              className="h-8 text-xs"
            />
          </div>

          {(type === "trigger/manual" || type === "trigger/webhook" || type === "trigger/schedule" || type === "trigger/monitoring") && (
            <>
              <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 text-[11px] text-muted-foreground">
                {localize(
                  uiLang,
                  "Настройки триггера сохраняются вместе с пайплайном. Каждый триггер запускает только свою ветку графа.",
                  "Trigger settings are saved with the pipeline. Each trigger launches only its own graph branch.",
                )}
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                <div>
                  <p className="text-xs font-medium">{localize(uiLang, "Триггер включён", "Trigger enabled")}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {localize(uiLang, "Можно выключить запуск, не удаляя ноду", "Disable the start without deleting the node")}
                  </p>
                </div>
                <Switch checked={(d.is_active as boolean) ?? true} onCheckedChange={(checked) => set("is_active", checked)} />
              </div>
            </>
          )}
        </NodeFormSection>

        {type === "trigger/manual" && (
          <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 space-y-1">
            <p className="text-xs font-medium">{localize(uiLang, "Ручной запуск", "Manual start")}</p>
            <p className="text-[11px] text-muted-foreground">
              {localize(uiLang, "Запускается из кнопки ", "Start this pipeline from the Studio ")}
              <strong>{localize(uiLang, "Запуск", "Run")}</strong>
              {pipelineId
                ? localize(uiLang, ` или через POST /api/studio/pipelines/${pipelineId}/run/.`, ` dialog or POST /api/studio/pipelines/${pipelineId}/run/.`)
                : "."}
            </p>
            <p className="text-[11px] text-muted-foreground">
              {localize(
                uiLang,
                "Если в графе несколько ручных триггеров, оператор выбирает, с какой ноды начать run.",
                "If the graph has multiple manual triggers, the operator chooses which trigger node starts the run.",
              )}
            </p>
          </div>
        )}

        {type === "trigger/webhook" && (
          <NodeFormSection title={localize(uiLang, "Вход / условие", "Input / condition")}>
            <div className="space-y-1.5">
              <Label className="text-xs">Webhook URL</Label>
              <div className="text-xs text-muted-foreground bg-muted/30 rounded px-2 py-1.5 break-all">
                {pipelineId && triggerWebhookUrl ? triggerWebhookUrl : localize(uiLang, "Сохраните pipeline один раз, чтобы получить Webhook URL", "Save the pipeline once to generate the webhook URL")}
              </div>
            </div>
            <AdvancedDisclosure title={localize(uiLang, "Дополнительно", "Advanced")}>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Маппинг payload (JSON)", "Payload mapping (JSON)")}</Label>
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
              <FieldHint>
                {localize(uiLang, "Сопоставьте поля входящего payload с переменными pipeline, например", "Map incoming payload fields into pipeline variables, for example")} <code>head_commit.id</code>.
              </FieldHint>
              {webhookState.error && <p className="text-[10px] text-red-400">{webhookState.error}</p>}
            </div>
            </AdvancedDisclosure>
            {trigger && (
              <FieldHint>{localize(uiLang, "Последний Webhook run:", "Last webhook run:")} {formatStudioDateTime(trigger.last_triggered_at)}</FieldHint>
            )}
          </NodeFormSection>
        )}

        {type === "trigger/schedule" && (
          <NodeFormSection
            title={localize(uiLang, "Расписание запуска", "Run schedule")}
            description={localize(
              uiLang,
              "Выберите понятный режим запуска. Cron доступен ниже только для нестандартных расписаний.",
              "Choose a readable schedule. Cron is below for advanced custom schedules.",
            )}
          >
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2">
              <div className="flex items-start gap-2">
                <Clock className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-foreground">
                    {describeCronExpression(scheduleCronExpression, uiLang)}
                  </div>
                  <div className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
                    {localize(uiLang, "Сохраните пайплайн, чтобы scheduler начал использовать это расписание.", "Save the pipeline so the scheduler starts using this schedule.")}
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-xs">{localize(uiLang, "Как часто запускать", "How often to run")}</Label>
              <div className="grid grid-cols-1 gap-2">
                {CRON_PRESETS.map((preset) => {
                  const active = schedulePresetId === preset.id;
                  return (
                    <button
                      key={preset.value}
                      type="button"
                      className={cn(
                        "rounded-lg border px-3 py-2 text-left transition-colors",
                        active
                          ? "border-primary/50 bg-primary/15 text-foreground"
                          : "border-border/70 bg-background/35 text-muted-foreground hover:border-primary/30 hover:bg-secondary/25",
                      )}
                      onClick={() => set("cron_expression", preset.value)}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-foreground">{localize(uiLang, preset.labelRu, preset.labelEn)}</span>
                        {active ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-primary" /> : null}
                      </span>
                      <span className="mt-1 block text-[10px] leading-relaxed">{localize(uiLang, preset.descriptionRu, preset.descriptionEn)}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label className="text-xs">{localize(uiLang, "Интервал в минутах", "Minute interval")}</Label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    min={1}
                    max={59}
                    value={scheduleMinuteInterval}
                    onChange={(event) => {
                      const minutes = Math.max(1, Math.min(59, Number(event.target.value) || 5));
                      set("cron_expression", `*/${minutes} * * * *`);
                    }}
                    className="h-8 text-xs"
                  />
                  <span className="text-[10px] text-muted-foreground">{localize(uiLang, "мин", "min")}</span>
                </div>
                <FieldHint>{localize(uiLang, "Для частых проверок. Например 5, 10 или 15 минут.", "For frequent checks, e.g. 5, 10, or 15 minutes.")}</FieldHint>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">{localize(uiLang, "Ежедневно в", "Daily at")}</Label>
                <Input
                  type="time"
                  value={scheduleDailyTime}
                  onChange={(event) => set("cron_expression", dailyTimeToCron(event.target.value || "04:00"))}
                  className="h-8 text-xs"
                />
                <FieldHint>{localize(uiLang, "Удобно для ежедневных отчетов в Telegram.", "Useful for daily Telegram reports.")}</FieldHint>
              </div>
            </div>

            <AdvancedDisclosure title={localize(uiLang, "Advanced: cron выражение", "Advanced: cron expression")}>
              <div className="space-y-1.5">
                <Label className="text-xs">Cron</Label>
                <Input
                  value={scheduleCronExpression}
                  onChange={(e) => set("cron_expression", e.target.value)}
                  placeholder="*/5 * * * *"
                  className="h-8 text-xs font-mono"
                />
                <FieldHint>
                  {localize(uiLang, "Формат из 5 полей:", "5-field format:")} <code>minute hour day month weekday</code>.
                  {" "}
                  {localize(uiLang, "Пример:", "Example:")} <code>0 4 * * *</code> = {localize(uiLang, "каждый день в 04:00", "daily at 04:00")}.
                </FieldHint>
              </div>
            </AdvancedDisclosure>

            {trigger && (
              <FieldHint>{localize(uiLang, "Последний запуск по расписанию:", "Last scheduled run:")} {formatStudioDateTime(trigger.last_triggered_at)}</FieldHint>
            )}
          </NodeFormSection>
        )}

        {/* Agent nodes */}
        {(type === "agent/react" || type === "agent/multi") && (
          <>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Цель", "Goal")}</Label>
              <Textarea
                value={(d.goal as string) || ""}
                onChange={(e) => set("goal", e.target.value)}
                placeholder={localize(uiLang, "Что агент должен сделать?", "What should this agent accomplish?")}
                className="text-xs resize-none"
                rows={3}
              />
              <p className="text-[10px] text-muted-foreground">{localize(uiLang, "Используйте", "Use")} {"{variable}"} {localize(uiLang, "для подстановки контекста", "for context substitution")}</p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Конфиг агента", "Agent Config")}</Label>
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
                  <SelectValue placeholder={localize(uiLang, "Настроить прямо в пайплайне", "Configure directly in this pipeline")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">{localize(uiLang, "Настроить прямо в пайплайне", "Configure directly in this pipeline")}</SelectItem>
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
                  {localize(
                    uiLang,
                    "Используется сохранённый конфиг: он управляет промптом, моделью, инструментами, MCP-серверами и политиками. Локальные поля модели скрыты.",
                    "Saved agent config controls the prompt, model, tools, MCP servers, and skill policies. Local model fields are hidden.",
                  )}
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
                  <Label className="text-xs">{localize(uiLang, "Системный промпт", "System Prompt")}</Label>
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
                    <Label className="text-xs">{localize(uiLang, "Провайдер", "Provider")}</Label>
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
                    <Label className="text-xs">{localize(uiLang, "Модель", "Model")}</Label>
                    {provider === "auto" ? (
                      <div className="h-7 rounded-md border border-border bg-muted/30 px-2 flex items-center text-[11px] text-muted-foreground">
                        {localize(uiLang, "Используется модель агента по умолчанию", "Uses the global default agent model")}
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
                  <Label className="text-xs">{localize(uiLang, "Максимум шагов", "Max Iterations")}</Label>
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
                  <Label className="text-xs">{localize(uiLang, "MCP-серверы", "MCP Servers")}</Label>
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
                        <SelectValue placeholder={localize(uiLang, "Добавить MCP-сервер...", "Add MCP server...")} />
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
                    {localize(uiLang, "Подключённые MCP-серверы дают агенту доступ к своим инструментам во время выполнения.", "Attached MCP servers expose their tools directly to this agent at runtime.")}
                  </p>
                </div>
              </>
            )}
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Целевые серверы", "Target Servers")}</Label>
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
                    <SelectValue placeholder={localize(uiLang, "Добавить сервер...", "Add server...")} />
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
                  <Label className="text-xs">{selectedAgent ? localize(uiLang, "Дополнительные skills", "Extra Skills") : localize(uiLang, "Skills / политики", "Skills / Policies")}</Label>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 gap-1.5 text-[11px]"
                    onClick={() => navigate("/studio/skills")}
                  >
                    <BookOpen className="h-3 w-3" />
                    {localize(uiLang, "Каталог", "Browse Catalog")}
                  </Button>
                </div>
                <p className="text-[10px] text-muted-foreground">
                  {selectedAgent
                    ? localize(uiLang, "Политики этой ноды дополняют выбранный конфиг агента во время запуска.", "These node-level skills are merged with the selected agent config at runtime.")
                    : localize(uiLang, "Подключите playbook, ограничения и runtime-политики прямо к этой ноде.", "Attach service playbooks, guardrails, and runtime policy directly to this node.")}
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
              <Label className="text-xs">{localize(uiLang, "При ошибке", "On Failure")}</Label>
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
          <NodeFormSection
            title={localize(uiLang, "Исполнение", "Execution")}
            description={localize(uiLang, "Команда будет выполнена напрямую по SSH без LLM-планирования.", "The command runs directly over SSH without LLM planning.")}
          >
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Целевой сервер", "Target server")}</Label>
              <Select value={String(d.server_id || "")} onValueChange={(v) => set("server_id", parseInt(v))}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder={localize(uiLang, "Выберите сервер...", "Select server...")} />
                </SelectTrigger>
                <SelectContent>
                  {servers.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>{s.name} ({s.host})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Команда", "Command")}</Label>
              <Textarea
                value={(d.command as string) || ""}
                onChange={(e) => set("command", e.target.value)}
                placeholder="df -h && free -h"
                className="text-xs font-mono resize-none"
                rows={3}
              />
            </div>
            <AdvancedDisclosure title={localize(uiLang, "Проверки до/после", "Pre/post checks")}>
              <div className="space-y-1.5">
                <Label className="text-xs">{localize(uiLang, "Preflight команды", "Preflight commands")}</Label>
                <Textarea
                  value={formatCommandListText(d.preflight_commands)}
                  onChange={(e) => set("preflight_commands", parseCommandListText(e.target.value))}
                  placeholder={"systemctl is-active nginx\nnginx -t"}
                  className="text-xs font-mono resize-none"
                  rows={3}
                />
                <FieldHint>
                  {localize(
                    uiLang,
                    "Одна read-only команда на строку. Если любая вернёт non-zero, основной SSH command не запустится.",
                    "One read-only command per line. If any command returns non-zero, the main SSH command will not run.",
                  )}
                </FieldHint>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{localize(uiLang, "Verification команды", "Verification commands")}</Label>
                <Textarea
                  value={formatCommandListText(d.verification_commands)}
                  onChange={(e) => set("verification_commands", parseCommandListText(e.target.value))}
                  placeholder={"systemctl is-active nginx\ncurl -fsS http://localhost/health"}
                  className="text-xs font-mono resize-none"
                  rows={3}
                />
                <FieldHint>
                  {localize(
                    uiLang,
                    "Команды выполняются после основной команды и попадают в секции output как verification evidence.",
                    "Commands run after the main command and are included in output sections as verification evidence.",
                  )}
                </FieldHint>
              </div>
            </AdvancedDisclosure>
            <FailureSelect lang={uiLang} value={(d.on_failure as string) || "abort"} onChange={(value) => set("on_failure", value)} />
          </NodeFormSection>
        )}

        {type.startsWith("ops/") && (
          <NodeFormSection
            title={localize(uiLang, "OPS-цель", "OPS target")}
            description={localize(uiLang, "Структурированные операции используют существующие WebTerm Linux UI проверки, аудит и безопасные параметры.", "Structured operations reuse existing WebTerm Linux UI checks, audit, and safe parameters.")}
          >
            {type !== "ops/http_check" && type !== "ops/alert_update" ? (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Целевой сервер", "Target server")}</Label>
                  <Select
                    value={String(d.server_id || "")}
                    onValueChange={(v) => set("server_id", parseInt(v, 10))}
                  >
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue placeholder={localize(uiLang, "Из контекста или выбрать...", "From context or select...")} />
                    </SelectTrigger>
                    <SelectContent>
                      {servers.map((s) => (
                        <SelectItem key={s.id} value={String(s.id)}>{s.name} ({s.host})</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Ключ server_id из контекста", "Context server_id key")}</Label>
                  <Input
                    value={(d.server_id_context_key as string) || "server_id"}
                    onChange={(e) => set("server_id_context_key", e.target.value)}
                    className="h-8 text-xs font-mono"
                    placeholder="server_id"
                  />
                </div>
              </>
            ) : null}

            {type === "ops/server_snapshot" && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Разделы снимка", "Snapshot sections")}</Label>
                  <div className="grid grid-cols-2 gap-2">
                    {["overview", "services", "processes", "docker", "logs", "disk", "network", "packages"].map((section) => {
                      const selected = ((d.sections as string[]) || []).includes(section);
                      return (
                        <label key={section} className="flex items-center gap-2 rounded border border-border px-2 py-2 text-xs">
                          <input
                            type="checkbox"
                            className="h-3.5 w-3.5"
                            checked={selected}
                            onChange={() => {
                              const current = ((d.sections as string[]) || []).filter(Boolean);
                              set("sections", selected ? current.filter((item) => item !== section) : [...current, section]);
                            }}
                          />
                          <span>{section}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">{localize(uiLang, "Log source", "Log source")}</Label>
                    <Input value={(d.log_source as string) || "journal"} onChange={(e) => set("log_source", e.target.value)} className="h-8 text-xs" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">{localize(uiLang, "Строк логов", "Log lines")}</Label>
                    <Input type="number" value={(d.lines as number) || 80} onChange={(e) => set("lines", parseInt(e.target.value, 10) || 80)} className="h-8 text-xs" />
                  </div>
                </div>
              </>
            )}

            {type === "ops/log_query" && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Источник логов", "Log source")}</Label>
                  <Select value={(d.source as string) || "journal"} onValueChange={(value) => set("source", value)}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="journal">journal</SelectItem>
                      <SelectItem value="service">service journal</SelectItem>
                      <SelectItem value="docker">docker logs</SelectItem>
                      <SelectItem value="syslog">syslog</SelectItem>
                      <SelectItem value="messages">messages</SelectItem>
                      <SelectItem value="auth">auth.log</SelectItem>
                      <SelectItem value="nginx_error">nginx error</SelectItem>
                      <SelectItem value="nginx_access">nginx access</SelectItem>
                      <SelectItem value="apache_error">apache error</SelectItem>
                      <SelectItem value="apache_access">apache access</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {(d.source as string) === "service" ? (
                  <div className="space-y-1.5">
                    <Label className="text-xs">systemd unit</Label>
                    <Input value={(d.service as string) || ""} onChange={(e) => set("service", e.target.value)} placeholder="nginx" className="h-8 text-xs font-mono" />
                  </div>
                ) : null}
                {(d.source as string) === "docker" ? (
                  <div className="space-y-1.5">
                    <Label className="text-xs">{localize(uiLang, "Контейнер", "Container")}</Label>
                    <Input value={(d.container as string) || ""} onChange={(e) => set("container", e.target.value)} placeholder="{container_name}" className="h-8 text-xs font-mono" />
                  </div>
                ) : null}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">{localize(uiLang, "Строк", "Lines")}</Label>
                    <Input type="number" value={(d.lines as number) || 120} onChange={(e) => set("lines", parseInt(e.target.value, 10) || 120)} className="h-8 text-xs" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">{localize(uiLang, "Фильтр текста", "Text filter")}</Label>
                    <Input value={(d.filter_text as string) || ""} onChange={(e) => set("filter_text", e.target.value)} placeholder="error, timeout, failed" className="h-8 text-xs" />
                  </div>
                </div>
              </>
            )}

            {type === "ops/file_action" && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Действие", "Action")}</Label>
                  <Select value={(d.action as string) || "read"} onValueChange={(value) => set("action", value)}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="read">read</SelectItem>
                      <SelectItem value="write">write</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Путь", "Path")}</Label>
                  <Input
                    value={(d.path as string) || ""}
                    onChange={(e) => set("path", e.target.value)}
                    placeholder="/etc/nginx/nginx.conf"
                    className="h-8 text-xs font-mono"
                  />
                </div>
                {(d.action as string) === "write" ? (
                  <div className="space-y-1.5">
                    <Label className="text-xs">{localize(uiLang, "Содержимое", "Content")}</Label>
                    <Textarea
                      value={(d.content as string) || ""}
                      onChange={(e) => set("content", e.target.value)}
                      placeholder="{generated_config}"
                      className="min-h-32 resize-y text-xs font-mono"
                    />
                    <FieldHint>{localize(uiLang, "Запись требует путь подтверждения; содержимое может использовать шаблоны.", "Write requires an approval path; content can use templates.")}</FieldHint>
                  </div>
                ) : null}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Max bytes</Label>
                    <Input
                      type="number"
                      value={(d.max_bytes as number) || 131072}
                      onChange={(e) => set("max_bytes", parseInt(e.target.value, 10) || 131072)}
                      className="h-8 text-xs"
                    />
                  </div>
                  {(d.action as string) === "write" ? (
                    <label className="mt-6 flex items-center gap-2 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        className="h-4 w-4"
                        checked={Boolean(d.allow_empty_content)}
                        onChange={(e) => set("allow_empty_content", e.target.checked)}
                      />
                      <span>{localize(uiLang, "Разрешить пустой файл", "Allow empty file")}</span>
                    </label>
                  ) : null}
                </div>
              </>
            )}

            {type === "ops/package_action" && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Действие", "Action")}</Label>
                  <Select value={(d.action as string) || "list_updates"} onValueChange={(value) => set("action", value)}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="list_updates">list_updates</SelectItem>
                      <SelectItem value="install">install</SelectItem>
                      <SelectItem value="update">update</SelectItem>
                      <SelectItem value="remove">remove</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {(d.action as string) !== "list_updates" ? (
                  <div className="space-y-1.5">
                    <Label className="text-xs">{localize(uiLang, "Пакеты", "Packages")}</Label>
                    <Input
                      value={Array.isArray(d.packages) ? (d.packages as string[]).join(", ") : String(d.packages || "")}
                      onChange={(e) => set("packages", e.target.value.split(",").map((item) => item.trim()).filter(Boolean))}
                      placeholder="nginx, curl"
                      className="h-8 text-xs font-mono"
                    />
                    <FieldHint>{localize(uiLang, "Только явный список пакетов; массовый upgrade всей системы здесь не поддерживается.", "Explicit package list only; whole-system upgrade is not supported here.")}</FieldHint>
                  </div>
                ) : null}
                {(d.action as string) !== "list_updates" ? (
                  <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                    <span className="text-xs">{localize(uiLang, "Post-change package verification", "Post-change package verification")}</span>
                    <input type="checkbox" className="h-4 w-4" checked={d.verify !== false} onChange={(e) => set("verify", e.target.checked)} />
                  </div>
                ) : null}
              </>
            )}

            {type === "ops/disk_cleanup" && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Действие", "Action")}</Label>
                  <Select value={(d.action as string) || "inspect"} onValueChange={(value) => set("action", value)}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="inspect">inspect</SelectItem>
                      <SelectItem value="journal_vacuum">journal_vacuum</SelectItem>
                      <SelectItem value="tmp_cleanup">tmp_cleanup</SelectItem>
                    </SelectContent>
                  </Select>
                  <FieldHint>{localize(uiLang, "Очистка ограничена journalctl vacuum и старыми файлами /tmp, /var/tmp.", "Cleanup is limited to journalctl vacuum and old files under /tmp, /var/tmp.")}</FieldHint>
                </div>
                {(d.action as string) === "journal_vacuum" ? (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs">Vacuum time days</Label>
                      <Input
                        type="number"
                        value={(d.vacuum_time_days as number) || 14}
                        onChange={(e) => set("vacuum_time_days", parseInt(e.target.value, 10) || 14)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">Vacuum size MB</Label>
                      <Input
                        type="number"
                        value={(d.vacuum_size_mb as number) || ""}
                        onChange={(e) => set("vacuum_size_mb", e.target.value ? parseInt(e.target.value, 10) : undefined)}
                        placeholder="1024"
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>
                ) : null}
                {(d.action as string) === "tmp_cleanup" ? (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs">Min age days</Label>
                      <Input
                        type="number"
                        value={(d.min_age_days as number) || 7}
                        onChange={(e) => set("min_age_days", parseInt(e.target.value, 10) || 7)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">Max entries</Label>
                      <Input
                        type="number"
                        value={(d.max_entries as number) || 50}
                        onChange={(e) => set("max_entries", parseInt(e.target.value, 10) || 50)}
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>
                ) : null}
                {(d.action as string) !== "inspect" ? (
                  <div className="grid grid-cols-2 gap-3">
                    <label className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground">
                      <input type="checkbox" className="h-4 w-4" checked={d.dry_run !== false} onChange={(e) => set("dry_run", e.target.checked)} />
                      <span>{localize(uiLang, "Dry run", "Dry run")}</span>
                    </label>
                    <label className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground">
                      <input type="checkbox" className="h-4 w-4" checked={d.verify !== false} onChange={(e) => set("verify", e.target.checked)} />
                      <span>{localize(uiLang, "Verify after", "Verify after")}</span>
                    </label>
                  </div>
                ) : null}
              </>
            )}

            {type === "ops/backup_restore_check" && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Действие", "Action")}</Label>
                  <Select value={(d.action as string) || "inspect"} onValueChange={(value) => set("action", value)}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="inspect">inspect</SelectItem>
                      <SelectItem value="verify_latest">verify_latest</SelectItem>
                    </SelectContent>
                  </Select>
                  <FieldHint>{localize(uiLang, "Проверка каталога backup без восстановления.", "Read-only backup directory check; restore is not executed.")}</FieldHint>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Backup path", "Backup path")}</Label>
                  <Input
                    value={(d.path as string) || ""}
                    onChange={(e) => set("path", e.target.value)}
                    placeholder="/var/backups"
                    className="h-8 text-xs font-mono"
                  />
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Max depth</Label>
                    <Input
                      type="number"
                      value={(d.max_depth as number) || 2}
                      onChange={(e) => set("max_depth", parseInt(e.target.value, 10) || 2)}
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Max files</Label>
                    <Input
                      type="number"
                      value={(d.max_files as number) || 20}
                      onChange={(e) => set("max_files", parseInt(e.target.value, 10) || 20)}
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Max age hours</Label>
                    <Input
                      type="number"
                      value={(d.max_age_hours as number) || 24}
                      onChange={(e) => set("max_age_hours", parseInt(e.target.value, 10) || 24)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>
              </>
            )}

            {type === "ops/service_action" && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">systemd unit</Label>
                  <Input value={(d.service as string) || ""} onChange={(e) => set("service", e.target.value)} placeholder="nginx" className="h-8 text-xs font-mono" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Действие", "Action")}</Label>
                  <Select value={(d.action as string) || "restart"} onValueChange={(value) => set("action", value)}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["start", "stop", "restart", "reload"].map((action) => <SelectItem key={action} value={action}>{action}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </>
            )}

            {type === "ops/docker_action" && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Контейнер", "Container")}</Label>
                  <Input value={(d.container as string) || ""} onChange={(e) => set("container", e.target.value)} placeholder="{container_name}" className="h-8 text-xs font-mono" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Действие", "Action")}</Label>
                  <Select value={(d.action as string) || "restart"} onValueChange={(value) => set("action", value)}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["start", "stop", "restart"].map((action) => <SelectItem key={action} value={action}>{action}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </>
            )}

            {type === "ops/process_action" && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">PID</Label>
                  <Input value={String(d.pid || "")} onChange={(e) => set("pid", e.target.value)} placeholder="{pid}" className="h-8 text-xs font-mono" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Действие", "Action")}</Label>
                  <Select value={(d.action as string) || "terminate"} onValueChange={(value) => set("action", value)}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="terminate">terminate</SelectItem>
                      <SelectItem value="kill_force">kill_force</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </>
            )}

            {type === "ops/http_check" && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">URL</Label>
                  <Input value={(d.url as string) || ""} onChange={(e) => set("url", e.target.value)} placeholder="https://service.example.com/health" className="h-8 text-xs font-mono" />
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Method</Label>
                    <Select value={(d.method as string) || "GET"} onValueChange={(value) => set("method", value)}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="GET">GET</SelectItem>
                        <SelectItem value="HEAD">HEAD</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Timeout</Label>
                    <Input type="number" value={(d.timeout_seconds as number) || 15} onChange={(e) => set("timeout_seconds", parseInt(e.target.value, 10) || 15)} className="h-8 text-xs" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Retries</Label>
                    <Input type="number" value={(d.retries as number) || 1} onChange={(e) => set("retries", parseInt(e.target.value, 10) || 1)} className="h-8 text-xs" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Ожидаемые HTTP status", "Expected HTTP statuses")}</Label>
                  <Input
                    value={((d.expected_status as number[]) || [200]).join(",")}
                    onChange={(e) => set("expected_status", e.target.value.split(",").map((item) => parseInt(item.trim(), 10)).filter(Number.isFinite))}
                    placeholder="200,204"
                    className="h-8 text-xs font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Текст в body", "Body contains")}</Label>
                  <Input value={(d.body_contains as string) || ""} onChange={(e) => set("body_contains", e.target.value)} className="h-8 text-xs" />
                </div>
              </>
            )}

            {type === "ops/alert_update" && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">Alert ID</Label>
                  <Input value={String(d.alert_id || "")} onChange={(e) => set("alert_id", e.target.value)} placeholder="{alert_id}" className="h-8 text-xs font-mono" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Ключ alert_id из контекста", "Context alert_id key")}</Label>
                  <Input value={(d.alert_id_context_key as string) || "alert_id"} onChange={(e) => set("alert_id_context_key", e.target.value)} className="h-8 text-xs font-mono" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{localize(uiLang, "Заметка", "Note")}</Label>
                  <Textarea value={(d.note as string) || ""} onChange={(e) => set("note", e.target.value)} className="text-xs resize-none" rows={3} />
                </div>
              </>
            )}

            {(type === "ops/service_action" || type === "ops/docker_action") ? (
              <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                <span className="text-xs">{localize(uiLang, "Post-change verification", "Post-change verification")}</span>
                <input type="checkbox" className="h-4 w-4" checked={d.verify !== false} onChange={(e) => set("verify", e.target.checked)} />
              </div>
            ) : null}
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "При ошибке", "On Failure")}</Label>
              <Select value={(d.on_failure as string) || "continue"} onValueChange={(v) => set("on_failure", v)}>
                <SelectTrigger className="h-7 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="abort">Abort pipeline</SelectItem>
                  <SelectItem value="continue">Continue</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </NodeFormSection>
        )}

        {/* Condition */}
        {type === "logic/condition" && (
          <NodeFormSection
            title={localize(uiLang, "Вход / условие", "Input / condition")}
            description={localize(uiLang, "Выберите правило, по которому пайплайн пойдёт в ветку Да или Нет.", "Choose the rule that routes the pipeline into True or False.")}
          >
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Тип проверки", "Check type")}</Label>
              <Select value={(d.check_type as string) || "contains"} onValueChange={(v) => set("check_type", v)}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="contains">{localize(uiLang, "Вывод содержит текст", "Output contains")}</SelectItem>
                  <SelectItem value="not_contains">{localize(uiLang, "Вывод не содержит текст", "Output does not contain")}</SelectItem>
                  <SelectItem value="status_ok">{localize(uiLang, "Предыдущая нода успешна", "Previous node succeeded")}</SelectItem>
                  <SelectItem value="status_failed">{localize(uiLang, "Предыдущая нода упала", "Previous node failed")}</SelectItem>
                  <SelectItem value="always_true">{localize(uiLang, "Всегда Да", "Always true")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {((d.check_type as string) || "contains").includes("contains") && (
              <div className="space-y-1.5">
                <Label className="text-xs">{localize(uiLang, "Текст для проверки", "Check value")}</Label>
                <Input
                  value={(d.check_value as string) || ""}
                  onChange={(e) => set("check_value", e.target.value)}
                  placeholder="error"
                  className="h-8 text-xs"
                />
                {!String(d.check_value || "").trim() ? (
                  <p className="text-[10px] text-red-400">
                    {localize(uiLang, "Обязательное поле для contains/not_contains.", "Required for contains/not_contains checks.")}
                  </p>
                ) : null}
              </div>
            )}
          </NodeFormSection>
        )}

        {type === "trigger/monitoring" && (
          <NodeFormSection
            title={localize(uiLang, "Вход / условие", "Input / condition")}
            description={localize(uiLang, "Фильтры alert-ов, по которым мониторинг запустит эту ветку.", "Alert filters that start this branch from monitoring.")}
          >
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-100">
              {localize(
                uiLang,
                "Monitoring-триггер ждёт alert от сервера и не запускается из диалога Run. Сохраните pipeline, чтобы он начал ждать подходящее событие.",
                "Monitoring trigger waits for a server alert and does not start from the Run dialog. Save the pipeline to arm it.",
              )}
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Целевые серверы", "Target servers")}</Label>
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
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder={localize(uiLang, "Добавить сервер...", "Add server...")} />
                  </SelectTrigger>
                  <SelectContent>
                    {servers.map((s) => (
                      <SelectItem key={s.id} value={String(s.id)}>
                        {s.name} ({s.host})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldHint>{localize(uiLang, "Оставьте пустым, чтобы реагировать на alert-ы со всех доступных серверов.", "Leave empty to react to alerts from any accessible server.")}</FieldHint>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Severity-фильтры", "Severity filters")}</Label>
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
              <Label className="text-xs">{localize(uiLang, "Типы alert-ов", "Alert types")}</Label>
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
            <AdvancedDisclosure title={localize(uiLang, "Дополнительно", "Advanced")}>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Имена Docker-контейнеров", "Docker container names")}</Label>
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
              <FieldHint>{localize(uiLang, "Опционально. Одно имя контейнера на строку.", "Optional. One container name per line.")}</FieldHint>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Поиск по тексту", "Text match")}</Label>
              <Input
                value={(d.match_text as string) || ""}
                onChange={(e) => setMonitoringFilters({ match_text: e.target.value })}
                placeholder={localize(uiLang, "Опциональная подстрока в title/message/metadata", "Optional substring to match in title/message/metadata")}
                className="h-8 text-xs"
              />
            </div>
            </AdvancedDisclosure>
            {trigger ? (
              <FieldHint>
                {localize(uiLang, "Последний запуск мониторингом:", "Last monitoring-triggered run:")} {formatStudioDateTime(trigger.last_triggered_at)}
              </FieldHint>
            ) : null}
          </NodeFormSection>
        )}

        {type === "logic/merge" && (
          <NodeFormSection
            title={localize(uiLang, "Исполнение", "Execution")}
            description={localize(uiLang, "Как несколько входящих веток снова сходятся в одну.", "How several incoming branches join back into one flow.")}
          >
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Режим слияния", "Merge mode")}</Label>
              <Select value={(d.mode as string) || "all"} onValueChange={(value) => set("mode", value)}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{localize(uiLang, "all: ждать все активные ветки", "all: wait for every activated branch")}</SelectItem>
                  <SelectItem value="any">{localize(uiLang, "any: продолжить после первой готовой ветки", "any: continue after the first completed branch")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <FieldHint>
              {localize(uiLang, "Используйте Merge вместо нескольких входящих связей прямо в action/output ноду.", "Use merge nodes instead of wiring multiple incoming edges directly into an action or output node.")}
            </FieldHint>
          </NodeFormSection>
        )}

        {/* Output/Webhook */}
        {type === "output/webhook" && (
          <NodeFormSection title={localize(uiLang, "Доставка", "Delivery")}>
          <div className="space-y-1.5">
            <Label className="text-xs">Webhook URL</Label>
            <Input
              value={(d.url as string) || ""}
              onChange={(e) => set("url", e.target.value)}
              placeholder="https://hooks.example.com/..."
              className="h-8 text-xs"
            />
          </div>
          </NodeFormSection>
        )}

        {/* Output/Report */}
        {type === "output/report" && (
          <NodeFormSection title={localize(uiLang, "Доставка", "Delivery")}>
          <div className="space-y-1.5">
            <Label className="text-xs">{localize(uiLang, "Шаблон отчёта", "Report template")}</Label>
            <Textarea
              value={(d.template as string) || ""}
              onChange={(e) => set("template", e.target.value)}
              placeholder="# Report\n\n{node_id_output}"
              className="text-xs font-mono resize-none"
              rows={4}
            />
            <FieldHint>{localize(uiLang, "Оставьте пустым для авто-сгенерированного отчёта.", "Leave empty for auto-generated report.")}</FieldHint>
          </div>
          </NodeFormSection>
        )}

        {/* LLM Query */}
        {type === "agent/llm_query" && (
          <>
            <NodeFormSection
              title={localize(uiLang, "Вход / условие", "Input / condition")}
              description={localize(uiLang, "Запрос к модели без автономных инструментов.", "Model prompt without autonomous tools.")}
            >
            <div className="space-y-1.5">
              <Label className="text-xs">Prompt</Label>
              <Textarea
                value={(d.prompt as string) || ""}
                onChange={(e) => set("prompt", e.target.value)}
                placeholder="Analyze the data from previous steps and provide recommendations..."
                className="text-xs resize-none"
                rows={5}
              />
              <FieldHint>
                {localize(uiLang, "Используйте", "Use")} <code>{"{all_outputs}"}</code> {localize(uiLang, "для всех предыдущих выводов или", "for all previous node outputs, or")} <code>{"{node_id}"}</code> {localize(uiLang, "для конкретной ноды.", "for a specific node.")}
              </FieldHint>
            </div>
            </NodeFormSection>
            <NodeFormSection title={localize(uiLang, "Исполнение", "Execution")}>
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
                <Label className="text-xs">{localize(uiLang, "Провайдер", "Provider")}</Label>
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
                  <SelectTrigger className="h-8 text-xs">
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
                <Label className="text-xs">{localize(uiLang, "Модель", "Model")}</Label>
                <Select value={(d.model as string) || ""} onValueChange={(v) => set("model", v)} disabled={loadingModelsFor === provider}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder={loadingModelsFor === provider ? localize(uiLang, "Загрузка моделей...", "Loading models...") : localize(uiLang, "Выберите модель", "Select model")} />
                  </SelectTrigger>
                  <SelectContent>
                    {modelList.length
                      ? modelList.map((model) => <SelectItem key={model} value={model}>{model}</SelectItem>)
                      : <SelectItem value="_empty" disabled>{localize(uiLang, "Модели недоступны", "No models available")}</SelectItem>}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <FieldHint>
              {localize(uiLang, "Вывод доступен следующим нодам как", "Output is available for next nodes as")} <code>{`{${node.id}}`}</code> {localize(uiLang, "и", "and")} <code>{`{${node.id}_output}`}</code>
            </FieldHint>
            </NodeFormSection>
          </>
        )}

        {type === "agent/mcp_call" && (
          <>
            <NodeFormSection
              title={localize(uiLang, "Исполнение", "Execution")}
              description={localize(uiLang, "Прямой вызов конкретного MCP-инструмента без выбора со стороны агента.", "Direct MCP tool call without waiting for an agent to choose.")}
            >
            <div className="space-y-1.5">
              <Label className="text-xs">MCP-сервер</Label>
              <Select
                value={selectedMcpId ? String(selectedMcpId) : "__none__"}
                onValueChange={(value) => {
                  if (value === "__none__") {
                    setMany({ mcp_server_id: null, mcp_server_name: "", tool_name: "", tool_description: "", input_schema: null, arguments_text: "{}", arguments: {} });
                    setMcpArgsText("{}");
                    return;
                  }
                  const nextMcp = mcpList.find((item) => String(item.id) === value);
                  setMany({ mcp_server_id: Number(value), mcp_server_name: nextMcp?.name || "", tool_name: "", tool_description: "", input_schema: null });
                }}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder={localize(uiLang, "Выберите MCP-сервер...", "Select MCP server...")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">{localize(uiLang, "Выберите MCP-сервер...", "Select MCP server...")}</SelectItem>
                  {mcpList.map((mcp) => (
                    <SelectItem key={mcp.id} value={String(mcp.id)}>
                      {mcp.name} ({mcp.transport})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedMcp && (
                <FieldHint>
                  {selectedMcp.last_test_ok === true
                    ? localize(uiLang, "Последняя проверка подключения успешна.", "Last connection test passed.")
                    : selectedMcp.last_test_ok === false
                      ? localize(uiLang, "Последняя проверка подключения упала.", "Last connection test failed.")
                      : localize(uiLang, "Сервер ещё не проверялся.", "Server has not been tested yet.")}
                </FieldHint>
              )}
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Инструмент", "Tool")}</Label>
              <Select
                value={(d.tool_name as string) || "__none__"}
                onValueChange={(value) => {
                  const tool = mcpTools.find((item) => item.name === value);
                  if (!tool) {
                    setMany({ tool_name: "", tool_description: "", input_schema: null });
                    return;
                  }
                  const toolPatch = {
                    tool_name: tool.name,
                    tool_description: tool.description || "",
                    input_schema: tool.inputSchema || null,
                  };
                  const shouldSeedArgs = !String(d.arguments_text || "").trim() || String(d.arguments_text || "").trim() === "{}";
                  if (shouldSeedArgs) {
                    const template = buildSchemaTemplate(tool.inputSchema);
                    const text = JSON.stringify(template, null, 2);
                    setMcpArgsText(text);
                    setMany({ ...toolPatch, arguments_text: text, arguments: template });
                    return;
                  }
                  setMany(toolPatch);
                }}
                disabled={!selectedMcpId || isFetchingMcpTools}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder={isFetchingMcpTools ? localize(uiLang, "Загрузка инструментов...", "Loading tools...") : localize(uiLang, "Выберите инструмент", "Select tool")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__" disabled>{localize(uiLang, "Выберите инструмент", "Select tool")}</SelectItem>
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
            </NodeFormSection>
            {selectedTool && Object.keys(selectedToolProperties).length > 0 && (
              <NodeFormSection
                title={localize(uiLang, "Typed arguments", "Typed arguments")}
                description={localize(uiLang, "Форма собрана из MCP tool schema и синхронизируется с JSON ниже.", "Generated from the MCP tool schema and synced to the JSON editor below.")}
              >
                <div className="grid gap-2">
                  {Object.entries(selectedToolProperties).map(([key, property]) => {
                    const schemaType = getSchemaType(property);
                    const required = selectedToolRequiredFields.has(key);
                    const value = mcpArgsForForm[key];
                    const description = typeof property.description === "string" ? property.description : "";
                    return (
                      <div key={key} className="rounded-lg border border-border/70 bg-background/40 px-3 py-2">
                        <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                          <Label className="text-xs">{key}</Label>
                          {required && <Badge variant="secondary" className="text-[9px]">required</Badge>}
                          <Badge variant="outline" className="text-[9px]">{schemaType}</Badge>
                        </div>
                        {schemaType === "boolean" ? (
                          <div className="flex items-center gap-2">
                            <Switch
                              checked={Boolean(value)}
                              onCheckedChange={(checked) => setMcpArgument(key, property, checked)}
                            />
                            <span className="text-xs text-muted-foreground">{String(Boolean(value))}</span>
                          </div>
                        ) : schemaType === "array" || schemaType === "object" ? (
                          <Textarea
                            value={getSchemaFormTextValue(value, property)}
                            onChange={(event) => setMcpArgument(key, property, event.target.value)}
                            className="min-h-20 resize-none font-mono text-xs"
                          />
                        ) : (
                          <Input
                            type={schemaType === "number" || schemaType === "integer" ? "number" : "text"}
                            value={getSchemaFormTextValue(value, property)}
                            onChange={(event) => setMcpArgument(key, property, event.target.value)}
                            placeholder={schemaType === "string" ? `{${key}}` : undefined}
                            className="h-8 text-xs"
                          />
                        )}
                        {description && <FieldHint>{description}</FieldHint>}
                      </div>
                    );
                  })}
                </div>
              </NodeFormSection>
            )}
            <NodeFormSection
              title={localize(uiLang, "Policy and risk", "Policy and risk")}
              description={localize(uiLang, "Для сервисных изменений привяжите skill/policy и держите подтверждение перед этой нодой.", "For service changes, attach a skill/policy and place approval before this node.")}
            >
              <div className="rounded-lg border border-border/70 bg-background/40 px-3 py-2">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Badge variant={mcpLooksMutating ? "secondary" : "outline"} className="text-[10px]">
                    {mcpLooksMutating ? localize(uiLang, "Review required", "Review required") : localize(uiLang, "Low/unknown risk", "Low/unknown risk")}
                  </Badge>
                  {selectedMcp?.last_test_ok === true && <Badge variant="outline" className="text-[10px]">MCP tested</Badge>}
                  {selectedSkillSlugs.length > 0 && <Badge variant="outline" className="text-[10px]">{selectedSkillSlugs.length} skills</Badge>}
                </div>
                <ul className="space-y-1 text-[11px] text-muted-foreground">
                  {mcpRiskReasons.map((reason) => (
                    <li key={reason}>- {reason}</li>
                  ))}
                </ul>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{localize(uiLang, "Permission mode", "Permission mode")}</Label>
                <Select value={(d.permission_mode as string) || "SAFE"} onValueChange={(value) => set("permission_mode", value)}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MCP_PERMISSION_MODE_OPTIONS.map((mode) => (
                      <SelectItem key={mode.value} value={mode.value}>
                        {mode.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldHint>
                  {MCP_PERMISSION_MODE_OPTIONS.find((mode) => mode.value === ((d.permission_mode as string) || "SAFE"))?.[uiLang === "ru" ? "descriptionRu" : "descriptionEn"]}
                </FieldHint>
              </div>
              {skillList.length > 0 && (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <Label className="text-xs">{localize(uiLang, "Skills / политики", "Skills / policies")}</Label>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 gap-1.5 text-[11px]"
                      onClick={() => navigate("/studio/skills")}
                    >
                      <BookOpen className="h-3 w-3" />
                      {localize(uiLang, "Каталог", "Browse Catalog")}
                    </Button>
                  </div>
                  <div className="space-y-1">
                    {skillList.map((skill) => (
                      <label key={skill.slug} className="flex cursor-pointer items-start gap-2 rounded border border-border px-2 py-2 transition-colors hover:bg-muted/30">
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
                        <span key={skill.slug} className="rounded bg-muted/60 px-1 py-0.5 text-[9px] text-muted-foreground">
                          {skill.name}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              )}
            </NodeFormSection>
            <AdvancedDisclosure title={localize(uiLang, "Дополнительно", "Advanced")} defaultOpen>
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
              <FieldHint>
                {localize(uiLang, "Аргументы поддерживают переменные pipeline вроде", "Arguments support pipeline variables like")} <code>{"{branch}"}</code> {localize(uiLang, "и", "and")} <code>{"{node_2_output}"}</code>.
              </FieldHint>
              {mcpArgsState.error && <p className="text-[10px] text-red-400">{mcpArgsState.error}</p>}
            </div>
            </AdvancedDisclosure>
            <NodeFormSection title={localize(uiLang, "Ошибки", "Errors")}>
              <FailureSelect lang={uiLang} value={(d.on_failure as string) || "abort"} onChange={(value) => set("on_failure", value)} />
            </NodeFormSection>
          </>
        )}

        {/* Email Output */}
        {type === "output/email" && (
          <>
            <NodeFormSection title={localize(uiLang, "Доставка", "Delivery")}>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Получатели email", "To email(s)")}</Label>
              <Input
                value={(d.to_email as string) || ""}
                onChange={(e) => set("to_email", e.target.value)}
                placeholder="admin@example.com, team@example.com"
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Тема письма", "Subject")}</Label>
              <Input
                value={(d.subject as string) || ""}
                onChange={(e) => set("subject", e.target.value)}
                placeholder="Pipeline Report: {pipeline_name}"
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Шаблон тела письма", "Body template")}</Label>
              <Textarea
                value={(d.body as string) || ""}
                onChange={(e) => set("body", e.target.value)}
                placeholder="# Report\n\n{all_outputs}"
                className="text-xs font-mono resize-none"
                rows={3}
              />
              <FieldHint>{localize(uiLang, "Оставьте пустым для авто-сгенерированного текста.", "Leave empty for auto-generated body.")}</FieldHint>
            </div>
            </NodeFormSection>
            <AdvancedDisclosure title={localize(uiLang, "Дополнительно", "Advanced")}>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground uppercase">{localize(uiLang, "SMTP настройки", "SMTP settings")}</Label>
              <Input
                value={(d.smtp_host as string) || ""}
                onChange={(e) => set("smtp_host", e.target.value)}
                placeholder="smtp.gmail.com"
                className="h-8 text-xs"
              />
              <div className="flex gap-2">
                <Input
                  value={(d.smtp_user as string) || ""}
                  onChange={(e) => set("smtp_user", e.target.value)}
                  placeholder="user@gmail.com"
                  className="h-8 text-xs flex-1"
                />
                <Input
                  value={(d.smtp_password as string) || ""}
                  onChange={(e) => set("smtp_password", e.target.value)}
                  placeholder="app password"
                  type="password"
                  className="h-8 text-xs w-28"
                />
              </div>
            </div>
            </AdvancedDisclosure>
          </>
        )}

        {/* Wait */}
        {type === "logic/wait" && (
          <NodeFormSection title={localize(uiLang, "Исполнение", "Execution")}>
          <div className="space-y-1.5">
            <Label className="text-xs">{localize(uiLang, "Длительность паузы (минуты)", "Wait duration (minutes)")}</Label>
            <Input
              type="number"
              value={(d.wait_minutes as number) ?? 20}
              onChange={(e) => set("wait_minutes", parseFloat(e.target.value) || 1)}
              className="h-8 text-xs"
              min={0.1}
              max={1440}
              step={0.5}
            />
            <FieldHint>{localize(uiLang, "Диапазон: 0.1-1440 минут, максимум 24 часа.", "Range: 0.1-1440 minutes, 24h max.")}</FieldHint>
          </div>
          </NodeFormSection>
        )}

        {/* Human Approval */}
        {type === "logic/human_approval" && (
          <>
            <NodeFormSection
              title={localize(uiLang, "Доставка", "Delivery")}
              description={localize(uiLang, "Куда отправить approve/reject запрос оператору.", "Where to send the operator approve/reject request.")}
            >
            <div className="space-y-1.5">
              <Label className="text-xs">Кому (email)</Label>
              <Input
                value={(d.to_email as string) || ""}
                onChange={(e) => set("to_email", e.target.value)}
                placeholder="или из Studio → Notifications"
                className="h-8 text-xs"
              />
            </div>
            <div className="flex items-start justify-between gap-3 rounded-lg border border-yellow-500/20 bg-yellow-500/10 px-3 py-2">
              <div className="min-w-0 space-y-1">
                <Label className="text-xs">{localize(uiLang, "Ручная ссылка без доставки", "Manual link only")}</Label>
                <p className="text-[11px] leading-relaxed text-yellow-100/80">
                  {localize(
                    uiLang,
                    "Email/Telegram не отправляются; запуск будет ждать решение по approve/reject ссылкам.",
                    "Email/Telegram are not sent; the run waits for a decision through approve/reject links.",
                  )}
                </p>
              </div>
              <Switch
                aria-label={localize(uiLang, "Ручная ссылка без доставки", "Manual link only")}
                data-testid="manual-link-only-switch"
                checked={Boolean(d.manual_link_only)}
                onCheckedChange={(checked) => set("manual_link_only", checked)}
                className="mt-0.5"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Тема письма (шаблон)</Label>
              <Input
                value={(d.email_subject as string) || ""}
                onChange={(e) => set("email_subject", e.target.value)}
                placeholder="Пусто = тема по умолчанию"
                className="h-8 text-xs"
              />
              <FieldHint>
                Переменные: {"{pipeline_name}"}, {"{run_id}"}
              </FieldHint>
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
              <FieldHint>
                {"{approve_url}"}, {"{reject_url}"}, {"{all_outputs}"}, {"{timeout_minutes}"}
              </FieldHint>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Timeout, минут", "Timeout (minutes)")}</Label>
              <Input
                type="number"
                value={(d.timeout_minutes as number) ?? 120}
                onChange={(e) => set("timeout_minutes", parseFloat(e.target.value) || 120)}
                className="h-8 text-xs"
                min={5}
                max={10080}
              />
            </div>
            </NodeFormSection>
            <AdvancedDisclosure title={localize(uiLang, "Дополнительно", "Advanced")}>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground uppercase">Telegram</Label>
              <Input
                value={(d.tg_bot_token as string) || ""}
                onChange={(e) => set("tg_bot_token", e.target.value)}
                placeholder="Bot Token (from @BotFather)"
                className="h-8 text-xs font-mono"
              />
              <Input
                value={(d.tg_chat_id as string) || ""}
                onChange={(e) => set("tg_chat_id", e.target.value)}
                placeholder="Chat ID (e.g. -100123456)"
                className="h-8 text-xs font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Base URL для ссылок подтверждения", "Base URL for approval links")}</Label>
              <Input
                value={(d.base_url as string) || ""}
                onChange={(e) => set("base_url", e.target.value)}
                placeholder="https://your-server.example.com"
                className="h-8 text-xs"
              />
              <FieldHint>{localize(uiLang, "Используется в approve/reject ссылках из уведомлений.", "Used in approve/reject URLs sent in notifications.")}</FieldHint>
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
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground uppercase">{localize(uiLang, "SMTP для писем подтверждения", "SMTP for approval email")}</Label>
              <Input
                value={(d.smtp_host as string) || ""}
                onChange={(e) => set("smtp_host", e.target.value)}
                placeholder="smtp.gmail.com"
                className="h-8 text-xs"
              />
              <div className="flex gap-2">
                <Input
                  value={(d.smtp_user as string) || ""}
                  onChange={(e) => set("smtp_user", e.target.value)}
                  placeholder="user@gmail.com"
                  className="h-8 text-xs flex-1"
                />
                <Input
                  value={(d.smtp_password as string) || ""}
                  onChange={(e) => set("smtp_password", e.target.value)}
                  placeholder="app password"
                  type="password"
                  className="h-8 text-xs w-28"
                />
              </div>
            </div>
            </AdvancedDisclosure>
          </>
        )}

        {type === "logic/telegram_input" && (
          <>
            <NodeFormSection
              title={localize(uiLang, "Доставка", "Delivery")}
              description={localize(uiLang, "Сообщение оператору и ожидание текстового ответа.", "Prompt the operator and wait for a plain text reply.")}
            >
            <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/10 px-3 py-2 text-[11px] text-cyan-100">
              Этот узел отправляет сообщение в Telegram и ждёт обычный текстовый reply от оператора.
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Шаблон сообщения", "Message template")}</Label>
              <Textarea
                value={(d.message as string) || ""}
                onChange={(e) => set("message", e.target.value)}
                placeholder="Опишите, какой ответ вы ждёте от оператора"
                className="text-xs resize-none"
                rows={6}
              />
              <FieldHint>
                Переменные: {"{pipeline_name}"}, {"{run_id}"}, {"{all_outputs}"}
              </FieldHint>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Timeout, минут", "Timeout (minutes)")}</Label>
              <Input
                type="number"
                value={(d.timeout_minutes as number) ?? 120}
                onChange={(e) => set("timeout_minutes", parseFloat(e.target.value) || 120)}
                className="h-8 text-xs"
                min={1}
                max={10080}
              />
            </div>
            </NodeFormSection>
            <AdvancedDisclosure title={localize(uiLang, "Дополнительно", "Advanced")}>
            <div className="space-y-1.5">
              <Label className="text-xs">Bot Token</Label>
              <Input
                value={(d.tg_bot_token as string) || ""}
                onChange={(e) => set("tg_bot_token", e.target.value)}
                placeholder="или глобально в Studio → Notifications"
                className="h-8 text-xs font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Chat ID</Label>
              <Input
                value={(d.tg_chat_id as string) || ""}
                onChange={(e) => set("tg_chat_id", e.target.value)}
                placeholder="-100123456789"
                className="h-8 text-xs font-mono"
              />
            </div>
            </AdvancedDisclosure>
          </>
        )}

        {/* Telegram Output */}
        {type === "output/telegram" && (
          <>
            <NodeFormSection title={localize(uiLang, "Доставка", "Delivery")}>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(uiLang, "Шаблон сообщения", "Message template")}</Label>
              <Textarea
                value={(d.message as string) || ""}
                onChange={(e) => set("message", e.target.value)}
                placeholder="*{pipeline_name}*\n\n{all_outputs}"
                className="text-xs resize-none"
                rows={4}
              />
              <FieldHint>
                {localize(uiLang, "Поддерживает Markdown. Переменные:", "Supports Markdown. Variables:")} <code>{"{all_outputs}"}</code>,{" "}
                <code>{"{node_id_output}"}</code>
              </FieldHint>
            </div>
            </NodeFormSection>
            <AdvancedDisclosure title={localize(uiLang, "Дополнительно", "Advanced")}>
            <div className="space-y-1.5">
              <Label className="text-xs">Bot Token</Label>
              <Input
                value={(d.bot_token as string) || ""}
                onChange={(e) => set("bot_token", e.target.value)}
                placeholder="1234567890:AAF..."
                className="h-8 text-xs font-mono"
              />
              <FieldHint>{localize(uiLang, "Получите токен у @BotFather в Telegram.", "Get from @BotFather on Telegram.")}</FieldHint>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Chat ID</Label>
              <Input
                value={(d.chat_id as string) || ""}
                onChange={(e) => set("chat_id", e.target.value)}
                placeholder="-100123456789"
                className="h-8 text-xs font-mono"
              />
              <FieldHint>{localize(uiLang, "Chat ID можно найти через @userinfobot или @getidsbot.", "Use @userinfobot or @getidsbot to find your chat ID.")}</FieldHint>
            </div>
            </AdvancedDisclosure>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Node Palette (left panel) - with search, drag, and hover previews
// ---------------------------------------------------------------------------
function NodePalette({ onAddNode, lang }: { onAddNode: (type: NodeType) => void; lang: "en" | "ru" }) {
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
    nodes: cat.nodes.filter((n) => {
      const nodeText = getNodePaletteText(n.type, lang);
      const query = search.trim().toLowerCase();
      return !query || nodeText.label.toLowerCase().includes(query) || nodeText.description.toLowerCase().includes(query);
    }),
  })).filter((cat) => cat.nodes.length > 0);

  return (
    <div className="flex h-full flex-col border-r border-border/80 bg-card/95">
      <div className="space-y-2 border-b border-border/80 px-3 py-3">
        <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Plus className="h-3 w-3" /> {localize(lang, "Добавить ноду", "Add node")}
        </h3>
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={localize(lang, "Поиск нод...", "Search nodes...")}
          className="h-8 border-border/70 bg-background/70 text-xs"
        />
      </div>
      <TooltipProvider delayDuration={400}>
        <div className="flex-1 space-y-1 overflow-auto p-2">
          {filtered.map((cat) => {
            const CategoryIcon = CATEGORY_ICONS[cat.category as keyof typeof CATEGORY_ICONS] || FileText;
            return (
              <div key={cat.category}>
                <button
                  onClick={() => toggleCat(cat.category)}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wide text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground"
                >
                  <CategoryIcon className="h-3.5 w-3.5" />
                  <span className="flex-1">{getNodeCategoryLabel(cat.category, lang)}</span>
                  <span className="rounded bg-muted/50 px-1.5 py-0.5 text-[9px] font-normal">{cat.nodes.length}</span>
                  {expandedCats.has(cat.category) ? (
                    <ChevronUp className="h-3 w-3" />
                  ) : (
                    <ChevronDown className="h-3 w-3" />
                  )}
                </button>
                {expandedCats.has(cat.category) &&
                  cat.nodes.map((node) => {
                    const Icon = node.icon;
                    const guidance = getNodeTypeGuidance(node.type, lang);
                    const nodeText = getNodePaletteText(node.type, lang);
                    return (
                      <Tooltip key={node.type}>
                        <TooltipTrigger asChild>
                          <button
                            onClick={() => onAddNode(node.type)}
                            draggable
                            onDragStart={(e) => {
                              e.dataTransfer.setData("application/pipeline-node-type", node.type);
                              e.dataTransfer.effectAllowed = "copy";
                            }}
                            className="group flex w-full items-center gap-3 rounded-xl border border-transparent px-2.5 py-2.5 text-left transition-all hover:border-border/70 hover:bg-primary/5 cursor-grab active:cursor-grabbing"
                          >
                            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border/70 bg-muted/40 transition-colors group-hover:border-primary/20 group-hover:bg-primary/10">
                              <Icon className={`h-[18px] w-[18px] ${node.iconClassName || "text-foreground"}`} />
                            </span>
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-[12px] font-medium text-foreground">{nodeText.label}</div>
                              <div className="mt-0.5 truncate text-[10px] leading-tight text-muted-foreground">{nodeText.description}</div>
                            </div>
                            <Plus className="ml-auto h-3.5 w-3.5 shrink-0 text-primary opacity-0 transition-opacity group-hover:opacity-100" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent side="right" className="max-w-[320px] rounded-xl border-border/80 bg-popover/98 px-3.5 py-3">
                          <div className="space-y-2">
                            <div className="flex items-start gap-2">
                              <span className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg border border-border/70 bg-background/70">
                                <Icon className={`h-4 w-4 ${node.iconClassName || "text-foreground"}`} />
                              </span>
                              <div className="min-w-0">
                                <p className="text-sm font-semibold text-foreground">{nodeText.label}</p>
                                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{guidance.category}</p>
                              </div>
                            </div>
                            <p className="text-[12px] leading-5 text-foreground/80">{guidance.summary}</p>
                            <div className="space-y-1">
                              {guidance.checklist.slice(0, 2).map((item) => (
                                <p key={item} className="text-[11px] leading-4 text-muted-foreground">
                                  - {item}
                                </p>
                              ))}
                            </div>
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    );
                  })}
              </div>
            );
          })}
          {filtered.length === 0 && search.trim() && (
            <p className="py-4 text-center text-[11px] text-muted-foreground">
              {localize(lang, `Ничего не найдено по запросу "${search}"`, `No nodes match "${search}"`)}
            </p>
          )}
        </div>
      </TooltipProvider>
      <div className="border-t border-border/80 px-3 py-2">
        <p className="text-center text-[9px] text-muted-foreground">
          {localize(lang, "Кликните по ноде или перетащите её на холст", "Click a node or drag it onto the canvas")}
        </p>
      </div>
    </div>
  );
}

function AssistantProposalCard({
  proposal,
  onApply,
  onApplyAndSave,
  onDiscard,
  applying,
  lang,
}: {
  proposal: StudioPipelineAssistantResponse;
  onApply: () => void;
  onApplyAndSave: () => void;
  onDiscard: () => void;
  applying?: boolean;
  lang: "en" | "ru";
}) {
  const stats = getAssistantPatchStats(proposal);
  const validationOk = proposal.validation?.ok !== false;
  const riskDangerous = proposal.risk?.level === "dangerous";
  const canApply = stats.hasChanges && validationOk && !riskDangerous && !applying;

  return (
    <div className="rounded-xl border border-border bg-background/70 p-3">
      <PipelineDraftReview
        response={proposal}
        lang={lang}
        compact
        actions={
          <div className="grid grid-cols-2 gap-2">
            <Button size="sm" className="h-8 gap-1.5" onClick={onApplyAndSave} disabled={!canApply}>
              {applying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              {localize(lang, "Применить и сохранить", "Apply & Save")}
            </Button>
            <Button size="sm" variant="outline" className="h-8 gap-1.5" onClick={onApply} disabled={!canApply}>
              {applying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
              {localize(lang, "Применить локально", "Apply locally")}
            </Button>
            <Button size="sm" variant="ghost" className="col-span-2 h-8" onClick={onDiscard}>
              {localize(lang, "Скрыть", "Discard")}
            </Button>
          </div>
        }
      />
    </div>
  );
}

function PipelineAssistantPanel({
  lang,
  selectedNode,
  input,
  history,
  proposal,
  isPending,
  onInputChange,
  onSend,
  onApply,
  onApplyAndSave,
  onDiscard,
  onClose,
}: {
  lang: "en" | "ru";
  selectedNode: PipelineNode | null;
  input: string;
  history: Array<{ role: "user" | "assistant"; content: string }>;
  proposal: StudioPipelineAssistantResponse | null;
  isPending: boolean;
  onInputChange: (value: string) => void;
  onSend: (intent: "create" | "edit" | "validate" | "fix_run", message?: string) => void;
  onApply: () => void;
  onApplyAndSave: () => void;
  onDiscard: () => void;
  onClose: () => void;
}) {
  const selectedLabel = selectedNode ? getNodeDisplayLabel(selectedNode, lang) : localize(lang, "Весь граф", "Whole graph");
  const quickActions = [
    {
      intent: "create" as const,
      label: localize(lang, "Собрать", "Build"),
      prompt: localize(lang, "Собери рабочий pipeline по моему описанию. Если граф пустой, создай полный стартовый workflow.", "Build a working pipeline from my request. If the graph is empty, create a complete starter workflow."),
    },
    {
      intent: "edit" as const,
      label: localize(lang, "Улучшить", "Improve"),
      prompt: localize(lang, "Улучши текущий граф: убери лишнее, добавь недостающие шаги и понятные названия.", "Improve the current graph: remove unnecessary parts, add missing steps, and make labels clear."),
    },
    {
      intent: "validate" as const,
      label: localize(lang, "Проверить", "Validate"),
      prompt: localize(lang, "Проверь текущий pipeline и предложи минимальные исправления, чтобы его можно было сохранить и запустить.", "Validate the current pipeline and propose the smallest fixes needed to save and run it."),
    },
    {
      intent: "fix_run" as const,
      label: localize(lang, "Исправить", "Fix errors"),
      prompt: localize(lang, "Исправь ошибки последней проверки или запуска и предложи безопасную правку.", "Fix the latest validation or run errors and propose a safe patch."),
    },
  ];

  return (
    <div className="flex h-full flex-col bg-card">
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
              <Wand2 className="h-4 w-4 text-primary" />
            </span>
            <div>
              <h3 className="text-sm font-semibold text-foreground">{localize(lang, "Помощник pipeline", "Pipeline Assistant")}</h3>
              <p className="text-[11px] text-muted-foreground">{selectedLabel}</p>
            </div>
          </div>
        </div>
        <Button size="icon" variant="ghost" className="h-9 w-9" onClick={onClose} aria-label={localize(lang, "Закрыть помощник", "Close assistant")}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-3 p-3">
          <div className="grid grid-cols-2 gap-2">
            {quickActions.map((action) => (
              <Button
                key={action.label}
                type="button"
                variant="outline"
                size="sm"
                className="h-9 justify-start gap-1.5 text-xs"
                disabled={isPending}
                onClick={() => onSend(action.intent, input.trim() ? `${action.prompt}\n\n${input.trim()}` : action.prompt)}
              >
                <Wand2 className="h-3.5 w-3.5 text-primary" />
                {action.label}
              </Button>
            ))}
          </div>

          {history.length ? (
            <div className="space-y-2">
              {history.slice(-4).map((item, index) => (
                <div
                  key={`${item.role}-${index}-${item.content.slice(0, 12)}`}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-xs leading-5",
                    item.role === "user"
                      ? "border-primary/20 bg-primary/10 text-primary-foreground"
                      : "border-border bg-background/70 text-muted-foreground",
                  )}
                >
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {item.role === "user" ? localize(lang, "Запрос", "Request") : localize(lang, "Помощник", "Assistant")}
                  </div>
                  <div className="whitespace-pre-wrap">{item.content}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border px-3 py-4 text-xs leading-5 text-muted-foreground">
              {localize(
                lang,
                "Опишите автоматизацию: что должно запускать pipeline, какие серверы или MCP использовать, где нужно подтверждение и куда отправить результат.",
                "Describe the automation: what should trigger it, which servers or MCPs it should use, where approval is required, and where to send the result.",
              )}
            </div>
          )}

          {proposal ? (
            <AssistantProposalCard
              proposal={proposal}
              lang={lang}
              onApply={onApply}
              onApplyAndSave={onApplyAndSave}
              onDiscard={onDiscard}
              applying={isPending}
            />
          ) : null}
        </div>
      </ScrollArea>

      <div className="space-y-2 border-t border-border p-3">
        <Textarea
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder={localize(lang, "Например: проверь Docker-сервис, запроси подтверждение и отправь отчёт в Telegram", "Example: check a Docker service, ask for approval, and send a Telegram report")}
          className="min-h-24 resize-none text-xs"
        />
        <Button
          className="h-10 w-full gap-1.5"
          disabled={isPending || !input.trim()}
          onClick={() => onSend("edit")}
        >
          {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
          {localize(lang, "Подготовить правку", "Prepare change")}
        </Button>
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
  const runDialogMode = manualTriggerOptions.length
    ? "manual"
    : webhookTriggerNodes.length
      ? "webhook"
      : scheduleTriggerNodes.length
        ? "schedule"
        : monitoringTriggerNodes.length
          ? "monitoring"
          : "manual";
  const runDialogCopy = getRunDialogCopy(runDialogMode, lang);
  const runRiskSummary = useMemo(
    () => buildPipelineRiskSummary(nodes as unknown as PipelineNode[], edges as unknown as PipelineEdge[]),
    [edges, nodes],
  );
  const nodeManifests = useMemo(
    () => ((nodeManifestRegistry?.nodes || []) as StudioCapabilityNode[]),
    [nodeManifestRegistry?.nodes],
  );
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
      toast({ description: response.validation?.ok === false ? "AI draft needs fixes before apply." : "AI draft is ready for review." });
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
      toast({ variant: "destructive", description: "Fix validation errors before applying this AI draft." });
      return;
    }
    if (assistantProposal.risk?.level === "dangerous") {
      toast({ variant: "destructive", description: localize(lang, "В черновике есть опасная SSH-команда. Попросите AI добавить подтверждение или переписать шаг безопасно.", "This draft contains a dangerous SSH command. Ask AI to add approval or rewrite it safely.") });
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
    toast({ description: localize(lang, "AI draft применён локально. Нажмите Save, чтобы сохранить pipeline.", "AI draft applied locally. Click Save to persist the pipeline.") });
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
            {localize(lang, "Помощник", "Assistant")}
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

      {/* Flow summary bar */}
      {nodes.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto border-b border-border/80 bg-[#10141a] px-4 py-2">
          <span className="mr-1 shrink-0 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground/80">
            {localize(lang, "Flow", "Flow")}
          </span>
          {(() => {
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
            pNodes.forEach((n) => { if (!visited.has(n.id) && chain.length < 15) chain.push(n); });
            const visibleChain = chain.slice(0, 6);
            const hiddenCount = Math.max(0, chain.length - visibleChain.length);
            const items: React.ReactNode[] = [];
            let previousPhase = "";

            visibleChain.forEach((n, index) => {
              const phaseLabel = getNodePhaseLabel(n.type, lang);
              const meta = NODE_TYPE_LOOKUP[n.type || ""];
              const StepIcon = meta?.icon;

              if (phaseLabel !== previousPhase) {
                items.push(
                  <span
                    key={`${n.id}-phase`}
                    className={cn(
                      "ml-1 inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide",
                      getNodePhaseBadgeClass(n.type),
                    )}
                  >
                    {phaseLabel}
                  </span>,
                );
                previousPhase = phaseLabel;
              }

              items.push(
                <span key={n.id} className="flex shrink-0 items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedNode(n);
                      setActiveRunId(null);
                    }}
                    className={cn(
                      "inline-flex min-h-8 max-w-[190px] items-center gap-1.5 rounded-lg border px-2 py-1 text-[10px] transition-colors",
                      graphState.currentNodeId === n.id
                        ? "border-blue-500/40 bg-blue-500/10 text-blue-200 shadow-[0_0_16px_rgba(59,130,246,0.18)]"
                        : graphState.traversedNodeIds.has(n.id)
                          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                          : graphState.queuedNodeIds.has(n.id)
                            ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-200"
                            : selectedNode?.id === n.id
                              ? "border-primary/40 bg-primary/10 text-primary"
                              : "border-border/60 bg-background/60 text-muted-foreground hover:border-border hover:bg-muted/40 hover:text-foreground"
                    )}
                  >
                    {StepIcon ? <StepIcon className={`h-3.5 w-3.5 shrink-0 ${meta.iconClassName || "text-foreground"}`} /> : null}
                    <span className="truncate">{getNodeDisplayLabel(n, lang)}</span>
                  </button>
                  {index < visibleChain.length - 1 ? <ChevronRight className="h-2.5 w-2.5 text-muted-foreground/40" /> : null}
                </span>,
              );
            });

            if (hiddenCount > 0) {
              items.push(
                <span
                  key="flow-overflow"
                  className="inline-flex shrink-0 items-center rounded-full border border-border/70 bg-background/60 px-2 py-0.5 text-[10px] text-muted-foreground"
                >
                  +{hiddenCount} {localize(lang, "этапов", "more")}
                </span>,
              );
            }

            return items;
          })()}
        </div>
      )}

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

      <Dialog open={runDialogOpen} onOpenChange={setRunDialogOpen}>
        <DialogContent className="max-h-[88vh] max-w-2xl overflow-hidden">
          <DialogHeader>
            <DialogTitle>{runDialogCopy.title}</DialogTitle>
            <DialogDescription>{runDialogCopy.description}</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            {runDialogMode === "manual" ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="run-entry-trigger">{localize(lang, "Ручной триггер", "Manual trigger")}</Label>
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
                            ? localize(lang, "Нет активных ручных триггеров", "No active manual trigger nodes")
                            : manualTriggerOptions.length === 1
                              ? manualTriggerOptions[0].label
                              : localize(lang, "Выберите триггер", "Select a trigger")
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
                      ? localize(lang, "Если ручной триггер один, он будет выбран автоматически.", "When there is only one manual trigger, it is selected automatically.")
                      : localize(lang, "Этот триггер запустит только свою ветку графа.", "This trigger starts only its own branch of the graph.")}
                  </p>
                  {runTriggerError ? <p className="text-xs text-red-400">{runTriggerError}</p> : null}
                </div>

                <RunRiskSummaryPanel summary={runRiskSummary} lang={lang} />

                <div className="space-y-2">
                  <Label htmlFor="run-task">{localize(lang, "Задача", "Task")}</Label>
                  <Textarea
                    id="run-task"
                    value={runTaskText}
                    onChange={(event) => setRunTaskText(event.target.value)}
                    placeholder={localize(lang, "Например: проверить staging, применить обновления и сообщить о блокерах", "Example: check staging, apply updates, and report blockers")}
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
                      <p className="text-xs font-medium">{localize(lang, "Расширенный контекст", "Advanced context")}</p>
                      <p className="text-[11px] text-muted-foreground">{localize(lang, "Необязательные метаданные инициатора и дополнительные JSON-поля.", "Optional requester metadata and extra JSON fields.")}</p>
                    </div>
                    {runAdvancedOpen ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
                  </button>
                  {runAdvancedOpen ? (
                    <div className="space-y-4 border-t border-border px-3 py-3">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div className="space-y-2">
                          <Label htmlFor="run-requester">{localize(lang, "Инициатор", "Requester")}</Label>
                          <Input
                            id="run-requester"
                            value={runRequester}
                            onChange={(event) => setRunRequester(event.target.value)}
                            placeholder={localize(lang, "Service Desk, CI job, оператор", "Service Desk, CI job, operator")}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="run-ticket-id">{localize(lang, "Тикет или reference ID", "Ticket or reference ID")}</Label>
                          <Input
                            id="run-ticket-id"
                            value={runTicketId}
                            onChange={(event) => setRunTicketId(event.target.value)}
                            placeholder="INC-1428"
                          />
                        </div>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="run-context">{localize(lang, "Контекст запуска (JSON-объект)", "Run context (JSON object)")}</Label>
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
                          {localize(lang, "Эти поля объединяются с задачей перед стартом запуска.", "These fields are merged with the task text before the run starts.")}
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
                      "Триггер уже активирован и ждёт входящий POST-запрос. Новый запуск появится только когда webhook реально придёт.",
                      "This trigger is already armed and waiting for an incoming POST request. A new run will appear only when the webhook actually arrives.",
                    )}
                  </div>
                ) : (
                  <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                    {localize(
                      lang,
                      "Сначала сохраните граф, чтобы активировать webhook-триггер и получить URL.",
                      "Save the graph first to arm the webhook trigger and generate its URL.",
                    )}
                  </div>
                )}
                {activeWebhookTriggers.length ? (
                  activeWebhookTriggers.map((trigger) => (
                    <div key={trigger.id} className="space-y-2 rounded-xl border border-border bg-background/60 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium text-foreground">{trigger.name || localize(lang, "Webhook-триггер", "Webhook trigger")}</div>
                          <div className="text-[11px] text-muted-foreground">{localize(lang, "Нода", "Node")} `{trigger.node_id}`</div>
                        </div>
                        <Button size="sm" variant="outline" className="h-9" onClick={() => void handleCopyWebhookUrl(trigger.webhook_url)}>
                          <Copy className="mr-1.5 h-3.5 w-3.5" />
                          {localize(lang, "Скопировать URL", "Copy URL")}
                        </Button>
                      </div>
                      <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground break-all">
                        {toAbsoluteWebhookUrl(trigger.webhook_url)}
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        {trigger.last_triggered_at
                          ? localize(lang, `Последний запуск: ${formatStudioDateTime(trigger.last_triggered_at)}`, `Last trigger: ${formatStudioDateTime(trigger.last_triggered_at)}`)
                          : localize(lang, "Ещё не вызывался.", "Has not been triggered yet.")}
                      </p>
                    </div>
                  ))
                ) : (
                  <div className="rounded-xl border border-dashed border-border px-3 py-3 text-xs text-muted-foreground">
                    {localize(
                      lang,
                      "Сначала сохраните pipeline, чтобы сгенерировать webhook URL для этой ноды-триггера.",
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
                    "Триггер расписания запускается планировщиком. Ручной запуск для него не нужен.",
                    "Schedule triggers are started by the scheduler. They do not need a manual Run.",
                  )}
                </div>
                {(activeScheduleTriggers.length
                  ? activeScheduleTriggers.map((trigger) => ({
                      id: String(trigger.id),
                      label: trigger.name || trigger.node_id,
                      cron: trigger.cron_expression || localize(lang, "не задан", "not set"),
                    }))
                  : scheduleTriggerNodes.map((node) => ({
                      id: node.id,
                      label: getNodeDisplayLabel(node, lang),
                      cron:
                        typeof node.data?.cron_expression === "string" && node.data.cron_expression.trim()
                          ? node.data.cron_expression
                          : localize(lang, "не задан", "not set"),
                    }))).map((trigger) => (
                  <div key={trigger.id} className="rounded-xl border border-border bg-background/60 p-3">
                    <div className="text-sm font-medium text-foreground">{trigger.label}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{localize(lang, "Cron", "Cron")}: {trigger.cron}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                  {localize(
                    lang,
                    "Триггер мониторинга активируется после сохранения и ждёт алерт мониторинга сервера. Запуск появится только при реальной проблеме.",
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
                      label: getNodeDisplayLabel(node, lang),
                      filters: node.data?.monitoring_filters || {},
                      lastTriggeredAt: null,
                    }))).map((trigger) => (
                  <div key={trigger.id} className="rounded-xl border border-border bg-background/60 p-3">
                    <div className="text-sm font-medium text-foreground">{trigger.label}</div>
                    <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                      <div>{localize(lang, "Серверы", "Servers")}: {Array.isArray((trigger.filters as Record<string, unknown>).server_ids) && ((trigger.filters as Record<string, unknown>).server_ids as unknown[]).length ? (((trigger.filters as Record<string, unknown>).server_ids as unknown[]).join(", ")) : localize(lang, "все", "any")}</div>
                      <div>{localize(lang, "Критичность", "Severity")}: {Array.isArray((trigger.filters as Record<string, unknown>).severities) && ((trigger.filters as Record<string, unknown>).severities as unknown[]).length ? (((trigger.filters as Record<string, unknown>).severities as unknown[]).join(", ")) : localize(lang, "любая", "any")}</div>
                      <div>{localize(lang, "Тип алерта", "Alert type")}: {Array.isArray((trigger.filters as Record<string, unknown>).alert_types) && ((trigger.filters as Record<string, unknown>).alert_types as unknown[]).length ? (((trigger.filters as Record<string, unknown>).alert_types as unknown[]).join(", ")) : localize(lang, "любой", "any")}</div>
                      <div>{localize(lang, "Контейнеры", "Containers")}: {Array.isArray((trigger.filters as Record<string, unknown>).container_names) && ((trigger.filters as Record<string, unknown>).container_names as unknown[]).length ? (((trigger.filters as Record<string, unknown>).container_names as unknown[]).join(", ")) : localize(lang, "все", "any")}</div>
                      {trigger.lastTriggeredAt ? <div>{localize(lang, `Последний запуск: ${formatStudioDateTime(trigger.lastTriggeredAt)}`, `Last trigger: ${formatStudioDateTime(trigger.lastTriggeredAt)}`)}</div> : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" className="h-10" onClick={() => setRunDialogOpen(false)}>
              {runDialogMode === "manual" ? localize(lang, "Отмена", "Cancel") : localize(lang, "Закрыть", "Close")}
            </Button>
            {runDialogMode === "manual" ? (
              <>
                <Button
                  variant="outline"
                  className="h-10"
                  onClick={handleValidateRun}
                  disabled={runMutation.isPending || validateRunMutation.isPending || saveMutation.isPending}
                >
                  {validateRunMutation.isPending || saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                  {localize(lang, "Проверить", "Validate")}
                </Button>
                <Button
                  className="h-10"
                  onClick={handleRunSubmit}
                  disabled={runMutation.isPending || validateRunMutation.isPending || saveMutation.isPending}
                >
                  {runMutation.isPending || saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  {localize(lang, "Запустить", "Run")}
                </Button>
              </>
            ) : (
              <Button className="h-10" onClick={handleSave} disabled={saveMutation.isPending || (Boolean(pipelineId) && !hasHydratedPipeline)}>
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
      <div className="h-full min-h-0">
        <PipelineEditorInner pipelineId={pipelineId} />
      </div>
    </ReactFlowProvider>
  );
}
