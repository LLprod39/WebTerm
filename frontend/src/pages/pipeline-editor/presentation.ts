import type { getPipelineActivityState } from "@/components/pipeline/pipelineActivity";
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
import { Bot, FileText, Play, Terminal, Zap } from "lucide-react";

export const nodeTypes = {
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

export const NODE_TYPE_LOOKUP = Object.fromEntries(
  NODE_PALETTE.flatMap((group) => group.nodes.map((node) => [node.type, node] as const)),
) as Record<string, (typeof NODE_PALETTE)[number]["nodes"][number]>;

export const CATEGORY_ICONS = {
  Triggers: Play,
  Agents: Bot,
  Ops: Terminal,
  Logic: Zap,
  Output: FileText,
} as const;

export function localize(lang: string, ru: string, en: string) {
  return lang === "ru" ? ru : en;
}

export function getNodePhaseKey(type?: string) {
  if (type?.startsWith("trigger/")) return "trigger";
  if (type?.startsWith("agent/")) return "agent";
  if (type?.startsWith("ops/")) return "ops";
  if (type?.startsWith("logic/")) return "logic";
  if (type?.startsWith("output/")) return "output";
  return "other";
}

export function getNodePhaseLabel(type: string | undefined, lang: string) {
  const phase = getNodePhaseKey(type);
  if (phase === "trigger") return localize(lang, "Триггеры", "Triggers");
  if (phase === "agent") return localize(lang, "Агенты", "Agents");
  if (phase === "ops") return localize(lang, "OPS", "Ops");
  if (phase === "logic") return localize(lang, "Логика", "Logic");
  if (phase === "output") return localize(lang, "Выход", "Output");
  return localize(lang, "Шаги", "Steps");
}

export function getPipelineActivityCopy(
  state: ReturnType<typeof getPipelineActivityState>,
  lang: "en" | "ru",
) {
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

export function getNodePhaseBadgeClass(type?: string) {
  const phase = getNodePhaseKey(type);
  if (phase === "trigger") return "border-sky-500/25 bg-sky-500/10 text-sky-200";
  if (phase === "agent") return "border-violet-500/25 bg-violet-500/10 text-violet-200";
  if (phase === "ops") return "border-cyan-500/25 bg-cyan-500/10 text-cyan-200";
  if (phase === "logic") return "border-orange-500/25 bg-orange-500/10 text-orange-200";
  if (phase === "output") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-200";
  return "border-border/70 bg-background/60 text-muted-foreground";
}

export function isNodeType(value: string): value is NodeType {
  return value in nodeTypes;
}
