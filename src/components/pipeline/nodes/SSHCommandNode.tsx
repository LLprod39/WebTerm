import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";

export function SSHCommandNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, string>;
  const command = d?.command;
  return (
    <NodeBase
      selected={selected}
      label={d?.label || getNodeTypeInfo("agent/ssh_cmd", lang).label}
      icon="💻"
      description={command ? command.slice(0, 40) + (command.length > 40 ? "…" : "") : localize(lang, "Точная SSH-команда", "Direct SSH command")}
      accentColor="border-cyan-500/40"
      status={d?.status}
    />
  );
}
