import type { PipelineEdge, PipelineNode } from "@/lib/api";

const MCP_MUTATING_TOOL_RE =
  /(^|[_\-.])(add|apply|assign|create|delete|disable|enable|grant|patch|remove|restart|revoke|set|start|stop|update|write)([_\-.]|$)/i;
const SSH_MUTATING_COMMAND_RE =
  /\b(apt(-get)?\s+install|chmod|chown|docker\s+(restart|rm|run|stop)|kubectl\s+(apply|delete|patch|rollout)|rm\s+-|systemctl\s+(restart|reload|start|stop)|user(add|del|mod))\b/i;
const VERIFICATION_RE = /\b(check|describe|get|health|inspect|list|lookup|read|status|test|verify|verification)\b/i;

export type PipelineRiskLevel = "safe" | "review" | "dangerous";

export interface PipelineRiskItem {
  nodeId: string;
  label: string;
  type: string;
  risk: "mutating" | "dangerous" | "review";
  reason: string;
  hasApproval: boolean;
}

export interface PipelineRiskSummary {
  level: PipelineRiskLevel;
  approvalCount: number;
  mutatingCount: number;
  verificationCount: number;
  missingApprovalCount: number;
  items: PipelineRiskItem[];
}

type RiskSummaryLang = "en" | "ru";

function riskText(lang: RiskSummaryLang, ru: string, en: string) {
  return lang === "ru" ? ru : en;
}

function nodeLabel(node: PipelineNode, lang: RiskSummaryLang): string {
  const data = node.data || {};
  return String(data.label || data.tool_name || node.id || node.type || riskText(lang, "Шаг", "Node"));
}

function isApprovalNode(node: PipelineNode): boolean {
  return node.type === "logic/human_approval";
}

function isVerificationNode(node: PipelineNode): boolean {
  const data = node.data || {};
  const blob = [node.id, node.type, data.label, data.tool_name, data.action].filter(Boolean).join(" ");
  return node.type === "ops/http_check" || VERIFICATION_RE.test(blob);
}

function classifyRiskNode(node: PipelineNode, lang: RiskSummaryLang): Omit<PipelineRiskItem, "hasApproval"> | null {
  const data = node.data || {};
  if (node.type === "ops/process_action") {
    return {
      nodeId: node.id,
      label: nodeLabel(node, lang),
      type: node.type,
      risk: String(data.action || "").toLowerCase() === "kill_force" ? "dangerous" : "mutating",
      reason: riskText(lang, "Действие меняет состояние процесса и требует подтверждения оператора.", "Process actions change runtime state and need explicit operator approval."),
    };
  }
  if (node.type === "ops/service_action" || node.type === "ops/docker_action" || node.type === "ops/alert_update") {
    return {
      nodeId: node.id,
      label: nodeLabel(node, lang),
      type: node.type,
      risk: "mutating",
      reason: riskText(lang, "Действие меняет состояние службы, контейнера или оповещения.", "OPS action mutates service/container/alert state."),
    };
  }
  if (node.type === "ops/file_action" && String(data.action || "read").toLowerCase() === "write") {
    return {
      nodeId: node.id,
      label: nodeLabel(node, lang),
      type: node.type,
      risk: "mutating",
      reason: riskText(lang, "Запись меняет файлы или настройки сервера и требует подтверждения оператора.", "File write changes server configuration or text files and needs operator approval."),
    };
  }
  if (node.type === "ops/package_action" && String(data.action || "list_updates").toLowerCase() !== "list_updates") {
    return {
      nodeId: node.id,
      label: nodeLabel(node, lang),
      type: node.type,
      risk: "mutating",
      reason: riskText(lang, "Установка, обновление или удаление пакета меняет систему и требует подтверждения оператора.", "Package install/update/remove changes OS state and needs operator approval."),
    };
  }
  if (node.type === "ops/disk_cleanup" && String(data.action || "inspect").toLowerCase() !== "inspect") {
    return {
      nodeId: node.id,
      label: nodeLabel(node, lang),
      type: node.type,
      risk: "mutating",
      reason: riskText(lang, "Очистка диска удаляет данные сервера и требует подтверждения оператора.", "Disk cleanup removes or vacuums host data and needs operator approval."),
    };
  }
  if (node.type === "agent/mcp_call") {
    const toolName = String(data.tool_name || "");
    const permissionMode = String(data.permission_mode || "").toUpperCase();
    const riskLevel = String(data.risk_level || "").toLowerCase();
    const operationKind = String(data.operation_kind || "");
    const looksMutating = MCP_MUTATING_TOOL_RE.test(toolName);
    const metadataMutating = Boolean(data.mutates_state || data.requires_approval);
    const explicitMutationMode = ["ASSISTED", "AUTO_GUARDED", "AUTONOMOUS", "BREAK_GLASS"].includes(permissionMode);
    if (!looksMutating && !metadataMutating && !explicitMutationMode) {
      return null;
    }
    const dangerous = permissionMode === "BREAK_GLASS" || ["dangerous", "critical", "break_glass"].includes(riskLevel);
    return {
      nodeId: node.id,
      label: nodeLabel(node, lang),
      type: node.type,
      risk: dangerous ? "dangerous" : "mutating",
      reason: looksMutating
        ? riskText(lang, `Инструмент MCP «${toolName || "без названия"}» может изменить состояние.`, `MCP tool "${toolName || "unnamed"}" looks mutating.`)
        : operationKind
          ? riskText(lang, `Операция MCP «${operationKind}» отмечена как изменяющая состояние.`, `MCP operation "${operationKind}" is marked as state-changing.`)
          : riskText(lang, `Режим доступа MCP «${permissionMode || "неизвестно"}» разрешает выполнять действия.`, `MCP permission mode "${permissionMode || "unknown"}" allows action execution.`),
    };
  }
  if (node.type === "agent/ssh_cmd") {
    const command = String(data.command || "");
    if (!SSH_MUTATING_COMMAND_RE.test(command)) {
      return {
        nodeId: node.id,
        label: nodeLabel(node, lang),
        type: node.type,
        risk: "review",
        reason: riskText(lang, "Проверьте SSH-команду перед запуском на сервере.", "Raw SSH command should be reviewed before running against operations targets."),
      };
    }
    return {
      nodeId: node.id,
      label: nodeLabel(node, lang),
      type: node.type,
      risk: "mutating",
      reason: riskText(lang, "SSH-команда может изменить состояние системы.", "SSH command appears to mutate system state."),
    };
  }
  return null;
}

function hasApprovedApprovalAncestor(nodeId: string, nodesById: Map<string, PipelineNode>, incoming: Map<string, PipelineEdge[]>): boolean {
  const seen = new Set<string>();
  const queue = [nodeId];
  while (queue.length) {
    const current = queue.shift();
    if (!current || seen.has(current)) {
      continue;
    }
    seen.add(current);
    for (const edge of incoming.get(current) || []) {
      const source = edge.source;
      const sourceNode = nodesById.get(source);
      if (!sourceNode) {
        continue;
      }
      if (isApprovalNode(sourceNode)) {
        if ((edge.sourceHandle || "out") === "approved") {
          return true;
        }
        continue;
      }
      queue.push(source);
    }
  }
  return false;
}

export function buildPipelineRiskSummary(nodes: PipelineNode[], edges: PipelineEdge[], lang: RiskSummaryLang = "en"): PipelineRiskSummary {
  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const incoming = new Map<string, PipelineEdge[]>();
  for (const edge of edges) {
    if (!edge.target) {
      continue;
    }
    incoming.set(edge.target, [...(incoming.get(edge.target) || []), edge]);
  }

  const items = nodes
    .map((node) => {
      const risk = classifyRiskNode(node, lang);
      if (!risk) {
        return null;
      }
      return {
        ...risk,
        hasApproval: risk.risk === "review" ? true : hasApprovedApprovalAncestor(node.id, nodesById, incoming),
      };
    })
    .filter((item): item is PipelineRiskItem => Boolean(item));

  const missingApprovalCount = items.filter((item) => item.risk !== "review" && !item.hasApproval).length;
  const dangerousCount = items.filter((item) => item.risk === "dangerous").length;
  const level: PipelineRiskLevel =
    missingApprovalCount > 0 || dangerousCount > 0
      ? "dangerous"
      : items.some((item) => item.risk !== "review")
        ? "review"
        : items.length
          ? "review"
          : "safe";

  return {
    level,
    approvalCount: nodes.filter(isApprovalNode).length,
    mutatingCount: items.filter((item) => item.risk !== "review").length,
    verificationCount: nodes.filter(isVerificationNode).length,
    missingApprovalCount,
    items,
  };
}
