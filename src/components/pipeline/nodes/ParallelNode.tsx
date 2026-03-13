import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";

export function ParallelNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, string>;
  return (
    <NodeBase
      selected={selected}
      label={d?.label || getNodeTypeInfo("logic/parallel", lang).label}
      icon="⚡"
      description={localize(lang, "Следующие ветки пойдут параллельно", "Run next nodes in parallel")}
      accentColor="border-orange-500/40"
      status={d?.status}
    />
  );
}
