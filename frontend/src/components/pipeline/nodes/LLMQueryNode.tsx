import { type NodeProps } from "@xyflow/react";
import { BrainCircuit, Zap } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeBranchLabel, getNodeTypeInfo } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

/** Canvas pill: real model override, or neutral workspace-default hint (never a fake model id). */
export function resolveLlmQueryModelLabel(model: unknown, lang: "en" | "ru"): string {
  const raw = typeof model === "string" ? model.trim() : "";
  if (raw) return raw;
  return lang === "ru" ? "Настройки → ИИ" : "Settings → AI";
}

export function LLMQueryNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const label = (typeof d?.label === "string" ? d.label : "") || getNodeTypeInfo("agent/llm_query", lang).label;
  const prompt = typeof d?.prompt === "string" ? d.prompt : "";
  const modelLabel = resolveLlmQueryModelLabel(d?.model, lang);

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon={<BrainCircuit className="h-4 w-4 text-ai" />}
      description={prompt ? prompt.slice(0, 55) + (prompt.length > 55 ? "…" : "") : modelLabel}
      accentColor="border-ai/40"
      categoryColor="hsl(var(--ai))"
      sourcePorts={[
        { id: "success", label: getNodeBranchLabel("success", lang), className: "!bg-success/70 hover:!bg-success", labelClassName: "text-success" },
        { id: "error", label: getNodeBranchLabel("error", lang), className: "!bg-destructive/70 hover:!bg-destructive", labelClassName: "text-destructive" },
      ]}
      {...getNodeRuntimeProps(d)}
    >
      <div className="text-xs text-ai/80 bg-ai/10 rounded px-1.5 py-0.5 truncate flex items-center gap-1">
        <Zap className="h-2.5 w-2.5" />{modelLabel}
      </div>
    </NodeBase>
  );
}
