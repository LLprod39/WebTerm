import { type NodeProps } from "@xyflow/react";
import { Terminal } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function SSHCommandNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const command = typeof d?.command === "string" ? d.command : "";
  return (
    <NodeBase
      selected={selected}
      label={(typeof d?.label === "string" ? d.label : "") || getNodeTypeInfo("agent/ssh_cmd", lang).label}
      icon={<Terminal className="h-4 w-4 text-cyan-400" />}
      description={command ? command.slice(0, 40) + (command.length > 40 ? "…" : "") : localize(lang, "Точная SSH-команда", "Direct SSH command")}
      accentColor="border-cyan-500/40"
      sourcePorts={[
        { id: "success", label: localize(lang, "OK", "SUCCESS"), className: "!bg-green-500/70 hover:!bg-green-500", labelClassName: "text-green-500" },
        { id: "error", label: localize(lang, "ERR", "ERROR"), className: "!bg-red-500/70 hover:!bg-red-500", labelClassName: "text-red-500" },
      ]}
      {...getNodeRuntimeProps(d)}
    />
  );
}
