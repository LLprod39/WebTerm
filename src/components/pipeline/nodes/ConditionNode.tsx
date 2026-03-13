import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";

export function ConditionNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, string>;
  const checkType = d?.check_type || "contains";
  const checkValue = d?.check_value;
  const desc = checkValue ? `${checkType}: "${checkValue.slice(0, 20)}"` : checkType;

  return (
    <NodeBase
      selected={selected}
      label={d?.label || getNodeTypeInfo("logic/condition", lang).label}
      icon="🔀"
      description={desc}
      hasSourceTrue
      hasSourceFalse
      accentColor="border-amber-500/40"
      status={d?.status}
    >
      <div className="flex justify-between text-[9px] text-muted-foreground px-1 mt-1">
        <span className="text-green-500 font-medium">{localize(lang, "ДА", "TRUE")}</span>
        <span className="text-red-500 font-medium">{localize(lang, "НЕТ", "FALSE")}</span>
      </div>
    </NodeBase>
  );
}
