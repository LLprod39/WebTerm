import { type NodeProps } from "@xyflow/react";
import { Bot, Users } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function AgentNode({ data, selected, type }: NodeProps) {
  const { lang } = useI18n();
  const isMulti = type === "agent/multi";
  const d = data as Record<string, unknown>;
  const label = (typeof d?.label === "string" ? d.label : "") || getNodeTypeInfo(type as string, lang).label;
  const goal = typeof d?.goal === "string" ? d.goal : "";
  const model = typeof d?.model === "string" ? d.model : "";

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon={isMulti
        ? <Users className="h-4 w-4 text-violet-400" />
        : <Bot   className="h-4 w-4 text-violet-400" />}
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
        { id: "success", label: localize(lang, "OK", "SUCCESS"), className: "!bg-green-500/70 hover:!bg-green-500", labelClassName: "text-green-500" },
        { id: "error", label: localize(lang, "ERR", "ERROR"), className: "!bg-red-500/70 hover:!bg-red-500", labelClassName: "text-red-500" },
      ]}
      {...getNodeRuntimeProps(d)}
    >
      {typeof d?.agent_name === "string" && d.agent_name && (
        <div className="text-[10px] text-muted-foreground bg-muted/40 rounded px-1.5 py-0.5 truncate">
          {d.agent_name}
        </div>
      )}
      {(!d?.agent_name || typeof d.agent_name !== "string") && model && (
        <div className="text-[10px] text-violet-300/80 bg-violet-500/10 rounded px-1.5 py-0.5 truncate">
          {model}
        </div>
      )}
    </NodeBase>
  );
}
