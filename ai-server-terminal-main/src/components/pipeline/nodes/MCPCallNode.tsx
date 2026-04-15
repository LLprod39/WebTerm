import { type NodeProps } from "@xyflow/react";
import { Puzzle } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function MCPCallNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const label = (typeof d?.label === "string" ? d.label : "") || getNodeTypeInfo("agent/mcp_call", lang).label;
  const toolName = typeof d?.tool_name === "string" ? d.tool_name : "";
  const serverName = typeof d?.mcp_server_name === "string" ? d.mcp_server_name : "";

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon={<Puzzle className="h-4 w-4 text-teal-400" />}
      description={toolName ? `${localize(lang, "инструмент", "tool")}: ${toolName}` : localize(lang, "Прямой вызов MCP-инструмента", "Direct MCP tools/call")}
      accentColor="border-teal-500/40"
      categoryColor="#8b5cf6"
      sourcePorts={[
        { id: "success", label: localize(lang, "OK", "SUCCESS"), className: "!bg-green-500/70 hover:!bg-green-500", labelClassName: "text-green-500" },
        { id: "error", label: localize(lang, "ERR", "ERROR"), className: "!bg-red-500/70 hover:!bg-red-500", labelClassName: "text-red-500" },
      ]}
      {...getNodeRuntimeProps(d)}
    >
      {serverName && (
        <div className="text-[10px] text-teal-300/80 bg-teal-500/10 rounded px-1.5 py-0.5 truncate">
          {serverName}
        </div>
      )}
    </NodeBase>
  );
}
