import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { PipelineNodeIcons } from "@/lib/app-icons";
import { getNodeBranchLabel, getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function AgentNode({ data, selected, type }: NodeProps) {
  const { lang } = useI18n();
  const isMulti = type === "agent/multi";
  const d = data as Record<string, unknown>;
  const label = (typeof d?.label === "string" ? d.label : "") || getNodeTypeInfo(type as string, lang).label;
  const goal = typeof d?.goal === "string" ? d.goal : "";
  const model = typeof d?.model === "string" ? d.model : "";
  const Icon = isMulti ? PipelineNodeIcons.multiAgent : PipelineNodeIcons.agent;

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon={<Icon className="h-4 w-4 text-violet-400" strokeWidth={1.5} />}
      description={
        goal
          ? goal.slice(0, 50) + (goal.length > 50 ? "…" : "")
          : isMulti
            ? localize(lang, "Оркестрация нескольких исполнителей", "Orchestrated pipeline")
            : localize(lang, "Один агентный цикл", "Single server loop")
      }
      accentColor="border-violet-500/40"
      categoryColor="#8b5cf6"
      sourcePorts={[
        { id: "success", label: getNodeBranchLabel("success", lang), className: "!bg-green-500/70 hover:!bg-green-500", labelClassName: "text-green-500" },
        { id: "error", label: getNodeBranchLabel("error", lang), className: "!bg-red-500/70 hover:!bg-red-500", labelClassName: "text-red-500" },
      ]}
      {...getNodeRuntimeProps(d)}
    >
      {typeof d?.agent_name === "string" && d.agent_name && (
        <div className="text-xs text-muted-foreground bg-muted/40 rounded px-1.5 py-0.5 truncate">
          {d.agent_name}
        </div>
      )}
      {(!d?.agent_name || typeof d.agent_name !== "string") && model && (
        <div className="text-xs text-violet-300/80 bg-violet-500/10 rounded px-1.5 py-0.5 truncate">
          {model}
        </div>
      )}
    </NodeBase>
  );
}
