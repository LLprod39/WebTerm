import { type NodeProps } from "@xyflow/react";
import { Zap } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function ParallelNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  return (
    <NodeBase
      selected={selected}
      label={(typeof d?.label === "string" ? d.label : "") || getNodeTypeInfo("logic/parallel", lang).label}
      icon={<Zap className="h-4 w-4 text-purple-400" />}
      description={localize(lang, "Следующие ветки пойдут параллельно", "Run next nodes in parallel")}
      accentColor="border-orange-500/40"
      sourcePorts={[{ id: "out", label: "OUT" }]}
      {...getNodeRuntimeProps(d)}
    />
  );
}
