import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";

export function AgentNode({ data, selected, type }: NodeProps) {
  const { lang } = useI18n();
  const isMulti = type === "agent/multi";
  const d = data as Record<string, string>;
  const label = d?.label || getNodeTypeInfo(type as string, lang).label;
  const goal = d?.goal;
  const model = d?.model;

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon={isMulti ? "🦾" : "🤖"}
      description={
        goal
          ? goal.slice(0, 50) + (goal.length > 50 ? "…" : "")
          : isMulti
            ? localize(lang, "Оркестрация нескольких исполнителей", "Orchestrated pipeline")
            : localize(lang, "Один агентный цикл", "Single server loop")
      }
      accentColor="border-violet-500/40"
      status={d?.status}
    >
      {d?.agent_name && (
        <div className="text-[10px] text-muted-foreground bg-muted/40 rounded px-1.5 py-0.5 truncate">
          🤖 {d.agent_name}
        </div>
      )}
      {!d?.agent_name && model && (
        <div className="text-[10px] text-violet-300/80 bg-violet-500/10 rounded px-1.5 py-0.5 truncate">
          {model}
        </div>
      )}
    </NodeBase>
  );
}
