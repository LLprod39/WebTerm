import { type NodeProps } from "@xyflow/react";
import { GitBranch } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeBranchLabel, getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function ConditionNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const checkType = (typeof d?.check_type === "string" ? d.check_type : "") || "contains";
  const checkValue = typeof d?.check_value === "string" ? d.check_value : "";
  const desc = checkValue ? `${checkType}: "${checkValue.slice(0, 20)}"` : checkType;

  return (
    <NodeBase
      selected={selected}
      label={(typeof d?.label === "string" ? d.label : "") || getNodeTypeInfo("logic/condition", lang).label}
      icon={<GitBranch className="h-4 w-4 text-purple-400" />}
      description={desc}
      sourcePorts={[
        { id: "true", label: getNodeBranchLabel("true", lang), className: "!bg-green-500/70 hover:!bg-green-500", labelClassName: "text-green-500" },
        { id: "false", label: getNodeBranchLabel("false", lang), className: "!bg-red-500/70 hover:!bg-red-500", labelClassName: "text-red-500" },
      ]}
      accentColor="border-amber-500/40"
      categoryColor="#f97316"
      {...getNodeRuntimeProps(d)}
    >
      <div className="text-xs text-muted-foreground">{localize(lang, "Ветвление Да / Нет", "Explicit true / false branch")}</div>
    </NodeBase>
  );
}
