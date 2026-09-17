import { type NodeProps } from "@xyflow/react";
import { Merge } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { NodeBase } from "./NodeBase";
import { getNodeBranchLabel, getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function MergeNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const mode = String(d?.mode || "all").toLowerCase() === "any" ? "any" : "all";

  return (
    <NodeBase
      selected={selected}
      label={(d?.label as string) || getNodeTypeInfo("logic/merge", lang).label}
      icon={<Merge className="h-4 w-4 text-warning" />}
      description={mode === "any" ? localize(lang, "Продолжить после первой ветки", "Continue after the first branch") : localize(lang, "Ждать все активные ветки", "Wait for all active branches")}
      accentColor="border-warning/40"
      categoryColor="hsl(var(--warning))"
      sourcePorts={[{ id: "out", label: getNodeBranchLabel("out", lang) }]}
      {...getNodeRuntimeProps(d)}
    >
      <div className="text-xs text-warning/80 bg-warning/10 rounded px-1.5 py-0.5 uppercase tracking-wide">
        {mode}
      </div>
    </NodeBase>
  );
}
