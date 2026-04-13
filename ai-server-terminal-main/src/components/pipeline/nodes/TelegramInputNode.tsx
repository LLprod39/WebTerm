import { type NodeProps } from "@xyflow/react";
import { MessageCircle } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function TelegramInputNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const tgChatId = d?.tg_chat_id as string | undefined;
  const timeout = d?.timeout_minutes as number | undefined;

  const desc =
    [
      tgChatId && "📱 TG",
      timeout && localize(lang, `⏰ ${timeout} мин.`, `⏰ ${timeout}min timeout`),
    ]
      .filter(Boolean)
      .join(" · ") || localize(lang, "Ожидание текстового ответа оператора", "Waiting for operator text reply");

  return (
    <NodeBase
      selected={selected}
      label={(d?.label as string) || getNodeTypeInfo("logic/telegram_input", lang).label}
      icon={<MessageCircle className="h-4 w-4 text-purple-400" />}
      description={desc}
      accentColor="border-cyan-500/40"
      sourcePorts={[
        {
          id: "received",
          label: localize(lang, "ОТВЕТ", "REPLY"),
          className: "!bg-cyan-500/70 hover:!bg-cyan-500",
          labelClassName: "text-cyan-500",
        },
        {
          id: "timeout",
          label: localize(lang, "TIME", "TIMEOUT"),
          className: "!bg-amber-500/70 hover:!bg-amber-500",
          labelClassName: "text-amber-500",
        },
      ]}
      {...getNodeRuntimeProps(d)}
    />
  );
}
