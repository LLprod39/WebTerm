import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo } from "./nodeMeta";

export function LLMQueryNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, string>;
  const label = d?.label || getNodeTypeInfo("agent/llm_query", lang).label;
  const prompt = d?.prompt;
  const model = d?.model || "gemini-2.0-flash-exp";

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon="🧠"
      description={prompt ? prompt.slice(0, 55) + (prompt.length > 55 ? "…" : "") : `${model}`}
      accentColor="border-cyan-500/40"
      status={d?.status}
    >
      <div className="text-[10px] text-cyan-400/70 bg-cyan-500/10 rounded px-1.5 py-0.5 truncate">
        ⚡ {model}
      </div>
    </NodeBase>
  );
}
