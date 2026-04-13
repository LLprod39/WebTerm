import { type NodeProps } from "@xyflow/react";
import { Send } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function TelegramNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const chatId = d?.chat_id as string | undefined;
  return (
    <NodeBase
      selected={selected}
      label={(d?.label as string) || getNodeTypeInfo("output/telegram", lang).label}
      icon={<Send className="h-4 w-4 text-sky-400" />}
      description={chatId ? `${localize(lang, "Чат", "Chat")}: ${chatId}` : localize(lang, "Настройте bot token и chat ID", "Configure bot token & chat ID")}
      accentColor="border-sky-500/40"
      sourcePorts={[
        { id: "success", label: localize(lang, "OK", "SUCCESS"), className: "!bg-green-500/70 hover:!bg-green-500", labelClassName: "text-green-500" },
        { id: "error", label: localize(lang, "ERR", "ERROR"), className: "!bg-red-500/70 hover:!bg-red-500", labelClassName: "text-red-500" },
      ]}
      {...getNodeRuntimeProps(d)}
    />
  );
}
