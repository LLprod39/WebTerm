import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";

export function TelegramNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const chatId = d?.chat_id as string | undefined;
  return (
    <NodeBase
      selected={selected}
      label={(d?.label as string) || getNodeTypeInfo("output/telegram", lang).label}
      icon="📱"
      description={chatId ? `${localize(lang, "Чат", "Chat")}: ${chatId}` : localize(lang, "Настройте bot token и chat ID", "Configure bot token & chat ID")}
      accentColor="border-sky-500/40"
      hasSource={true}
      status={d?.status as string | undefined}
    />
  );
}
