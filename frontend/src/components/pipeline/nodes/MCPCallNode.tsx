import { type NodeProps } from "@xyflow/react";
import { Puzzle } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeBranchLabel, getNodeTypeInfo, localize } from "./nodeMeta";
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
      icon={<Puzzle className="h-4 w-4 text-info" />}
      description={toolName ? `${localize(lang, "инструмент", "tool")}: ${toolName}` : localize(lang, "Прямой вызов MCP-инструмента", "Direct MCP tools/call")}
      accentColor="border-info/40"
      categoryColor="hsl(var(--ai))"
      sourcePorts={[
        { id: "success", label: getNodeBranchLabel("success", lang), className: "!bg-success/70 hover:!bg-success", labelClassName: "text-success" },
        { id: "error", label: getNodeBranchLabel("error", lang), className: "!bg-destructive/70 hover:!bg-destructive", labelClassName: "text-destructive" },
      ]}
      {...getNodeRuntimeProps(d)}
    >
      {serverName && (
        <div className="text-xs text-info/80 bg-info/10 rounded px-1.5 py-0.5 truncate">
          {serverName}
        </div>
      )}
    </NodeBase>
  );
}
