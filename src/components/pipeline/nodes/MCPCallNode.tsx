import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";

export function MCPCallNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, string>;
  const label = d?.label || getNodeTypeInfo("agent/mcp_call", lang).label;
  const toolName = d?.tool_name;
  const serverName = d?.mcp_server_name;

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon="🧩"
      description={toolName ? `${localize(lang, "инструмент", "tool")}: ${toolName}` : localize(lang, "Прямой вызов MCP-инструмента", "Direct MCP tools/call")}
      accentColor="border-teal-500/40"
      status={d?.status}
    >
      {serverName && (
        <div className="text-[10px] text-teal-300/80 bg-teal-500/10 rounded px-1.5 py-0.5 truncate">
          {serverName}
        </div>
      )}
    </NodeBase>
  );
}
