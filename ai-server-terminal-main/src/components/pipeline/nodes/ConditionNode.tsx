import { type NodeProps } from "@xyflow/react";
import { GitBranch } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";
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
        { id: "true", label: localize(lang, "ДА", "TRUE"), className: "!bg-green-500/70 hover:!bg-green-500", labelClassName: "text-green-500" },
        { id: "false", label: localize(lang, "НЕТ", "FALSE"), className: "!bg-red-500/70 hover:!bg-red-500", labelClassName: "text-red-500" },
      ]}
      accentColor="border-amber-500/40"
      {...getNodeRuntimeProps(d)}
    >
      <div className="text-[10px] text-muted-foreground">{localize(lang, "Явное ветвление true / false", "Explicit true / false branch")}</div>
    </NodeBase>
  );
}
