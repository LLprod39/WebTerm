import { type NodeProps } from "@xyflow/react";
import { BrainCircuit, Zap } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function LLMQueryNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const label = (typeof d?.label === "string" ? d.label : "") || getNodeTypeInfo("agent/llm_query", lang).label;
  const prompt = typeof d?.prompt === "string" ? d.prompt : "";
  const model = (typeof d?.model === "string" ? d.model : "") || "gemini-2.0-flash-exp";

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon={<BrainCircuit className="h-4 w-4 text-blue-400" />}
      description={prompt ? prompt.slice(0, 55) + (prompt.length > 55 ? "…" : "") : `${model}`}
      accentColor="border-cyan-500/40"
      categoryColor="#8b5cf6"
      sourcePorts={[
        { id: "success", label: "SUCCESS", className: "!bg-green-500/70 hover:!bg-green-500", labelClassName: "text-green-500" },
        { id: "error", label: "ERROR", className: "!bg-red-500/70 hover:!bg-red-500", labelClassName: "text-red-500" },
      ]}
      {...getNodeRuntimeProps(d)}
    >
      <div className="text-[10px] text-blue-400/80 bg-blue-500/10 rounded px-1.5 py-0.5 truncate flex items-center gap-1">
        <Zap className="h-2.5 w-2.5" />{model}
      </div>
    </NodeBase>
  );
}
