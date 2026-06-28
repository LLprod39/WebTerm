import { type NodeProps } from "@xyflow/react";
import { Puzzle } from "lucide-react";

import { NodeBase } from "@/components/pipeline/nodes/NodeBase";
import { getNodeBranchLabel } from "@/components/pipeline/nodes/nodeMeta";
import { getNodeRuntimeProps } from "@/components/pipeline/nodes/runtimeProps";
import { useI18n } from "@/lib/i18n";

export function StudioPluginNodeHost({ data, selected, type }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const label = String(d.label || d.plugin_node_label || type || "Plugin node");
  const description = String(d.description || d.message || "Plugin-provided Studio node");
  const handles = Array.isArray(d.source_handles) && d.source_handles.length
    ? d.source_handles.map((handle) => String(handle))
    : ["success", "error", "out"];

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon={<Puzzle className="h-4 w-4 text-teal-400" />}
      description={description}
      sourcePorts={handles.map((handle) => ({
        id: handle,
        label: getNodeBranchLabel(handle, lang),
        className: handle === "success"
          ? "!bg-green-500/70 hover:!bg-green-500"
          : handle === "error"
            ? "!bg-red-500/70 hover:!bg-red-500"
            : undefined,
        labelClassName: handle === "success" ? "text-green-500" : handle === "error" ? "text-red-500" : undefined,
      }))}
      accentColor="border-teal-500/40"
      categoryColor="#14b8a6"
      {...getNodeRuntimeProps(d)}
    />
  );
}
