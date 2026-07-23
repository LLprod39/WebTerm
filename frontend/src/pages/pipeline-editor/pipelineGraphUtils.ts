import type {
  ModelsResponse,
  PipelineEdge,
  PipelineNode,
  PipelineTrigger,
  StudioCapabilityNode,
} from "@/lib/api";
import { getNodeTypeInfo } from "@/components/pipeline/nodes/nodeMeta";
import { buildSchemaDefaultData, isPluginStudioNode } from "@/plugins/studioNodes";

import { parseJsonObjectText, toJsonEditorText } from "./jsonSchemaUtils";
import { localize } from "./presentation";

export const AGENT_PROVIDER_OPTIONS = [
  { value: "auto", label: "Auto" },
  { value: "gemini", label: "Gemini" },
  { value: "openai", label: "OpenAI" },
  { value: "grok", label: "Grok" },
  { value: "claude", label: "Claude" },
  { value: "ollama", label: "Ollama" },
] as const;

export const DIRECT_LLM_PROVIDERS = AGENT_PROVIDER_OPTIONS.filter((item) => item.value !== "auto");

export const MCP_MUTATING_TOOL_RE = /(^|[_\-.])(add|apply|assign|create|delete|disable|enable|grant|patch|remove|restart|revoke|set|start|stop|update|write)([_\-.]|$)/i;

export const MCP_PERMISSION_MODE_OPTIONS = [
  { value: "PLAN", label: "Plan", descriptionRu: "Только чтение и планирование.", descriptionEn: "Read-only planning mode." },
  { value: "SAFE", label: "Safe", descriptionRu: "Безопасный режим по умолчанию с policy notes.", descriptionEn: "Default guarded mode with policy notes." },
  { value: "ASSISTED", label: "Assisted", descriptionRu: "Оператор контролирует рискованные действия.", descriptionEn: "Operator-assisted execution for risky actions." },
  { value: "AUTO_GUARDED", label: "Auto guarded", descriptionRu: "Авто-выполнение только через guardrails.", descriptionEn: "Automatic execution through guardrails only." },
] as const;

export function formatStudioDateTime(value?: string | null) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

export function getNodeDisplayLabel(
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

export function getActiveManualTriggerOptions(nodes: PipelineNode[], lang: "en" | "ru" = "en") {
  return nodes
    .filter((node) => node.type === "trigger/manual" && node.data?.is_active !== false)
    .map((node) => ({
      node_id: node.id,
      label: getNodeDisplayLabel(node, lang),
    }));
}

export function getActiveTriggerNodes(nodes: PipelineNode[], type: PipelineNode["type"]) {
  return nodes.filter((node) => node.type === type && node.data?.is_active !== false);
}

const RUNTIME_PLACEHOLDER_RE = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;
const BUILT_IN_RUN_PLACEHOLDERS = new Set([
  "all_outputs",
  "approve_url",
  "created_at",
  "current_node_id",
  "current_node_label",
  "duration_seconds",
  "finished_at",
  "pipeline_id",
  "pipeline_name",
  "reject_url",
  "run_id",
  "run_status",
  "started_at",
  "summary",
  "timeout_minutes",
  "trigger_name",
  "trigger_node_id",
  "trigger_type",
]);

function collectRuntimePlaceholders(value: unknown, output: Set<string>) {
  if (typeof value === "string") {
    for (const match of value.matchAll(RUNTIME_PLACEHOLDER_RE)) {
      const field = match[1];
      if (BUILT_IN_RUN_PLACEHOLDERS.has(field)) continue;
      if (field.endsWith("_output")) continue;
      output.add(field);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => collectRuntimePlaceholders(item, output));
    return;
  }
  if (value && typeof value === "object") {
    Object.values(value as Record<string, unknown>).forEach((item) => collectRuntimePlaceholders(item, output));
  }
}

export function getPipelineRuntimePlaceholders(nodes: PipelineNode[]) {
  const fields = new Set<string>();
  nodes.forEach((node) => collectRuntimePlaceholders(node.data || {}, fields));
  return Array.from(fields).sort((a, b) => a.localeCompare(b));
}

export function buildRunContextTextWithPlaceholders(contextText: string, fields: string[]) {
  const parsedContext = parseJsonObjectText(contextText);
  if (parsedContext.error) {
    return { text: contextText, error: parsedContext.error };
  }
  const nextContext = { ...(parsedContext.value || {}) };
  fields.forEach((field) => {
    if (!(field in nextContext)) {
      nextContext[field] = "";
    }
  });
  return { text: toJsonEditorText(nextContext), error: null };
}

export function getMissingRunContextFields(context: Record<string, unknown>, fields: string[]) {
  return fields.filter((field) => {
    const value = context[field];
    if (value === undefined || value === null) return true;
    if (typeof value === "string") return value.trim().length === 0;
    if (Array.isArray(value)) return value.length === 0;
    return false;
  });
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

export function getActiveStoredTriggers(
  pipelineTriggers: PipelineTrigger[] | null | undefined,
  type: PipelineTrigger["trigger_type"],
) {
  if (!Array.isArray(pipelineTriggers)) {
    return [];
  }
  return pipelineTriggers.filter((trigger) => trigger.trigger_type === type && trigger.is_active);
}

export function toAbsoluteWebhookUrl(webhookUrl: string): string {
  return new URL(webhookUrl, window.location.origin).toString();
}

export function getPipelineNodeStatusLabel(
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

export function isLivePipelineRunStatus(status: string | null | undefined) {
  return status === "running" || status === "pending";
}

export type ModelProvider = "gemini" | "grok" | "openai" | "claude" | "ollama";

export const MODEL_PROVIDERS: ModelProvider[] = ["gemini", "grok", "openai", "claude", "ollama"];

export function isModelProvider(value: string): value is ModelProvider {
  return MODEL_PROVIDERS.includes(value as ModelProvider);
}

export function getModelsForProvider(models: ModelsResponse | undefined, provider: string): string[] {
  if (!models || !isModelProvider(provider)) return [];
  return models[provider];
}

export function buildDefaultNodeData(type: string, manifest?: StudioCapabilityNode): Record<string, unknown> {
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
      return { max_iterations: 6, sudo_policy: "inherit", on_failure: "abort" };
    case "agent/llm_query":
      return { provider: "gemini", on_failure: "abort" };
    case "agent/ssh_cmd":
      return { preflight_commands: [], verification_commands: [], permission_mode: "SAFE", sudo_policy: "disabled", on_failure: "abort" };
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
      if (isPluginStudioNode(manifest)) return buildSchemaDefaultData(manifest);
      return {};
  }
}

export function buildConnectionAutofillPatch(target: PipelineNode, source: PipelineNode, pipelineName: string) {
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

export function normaliseAssistantPatch(
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

export function normalisePipelineGraph(nodes: PipelineNode[], edges: PipelineEdge[]) {
  return {
    nodes: nodes.map((node) => ({
      ...node,
      data: normaliseAssistantPatch((node.data || {}) as Record<string, unknown>, { mcpList: [] }),
    })),
    edges,
  };
}
