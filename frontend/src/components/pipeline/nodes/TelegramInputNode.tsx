import { type NodeProps } from "@xyflow/react";
import { MessageCircle } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeBranchLabel, getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function TelegramInputNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const tgChatId = d?.tg_chat_id as string | undefined;
  const timeout = d?.timeout_minutes as number | undefined;

  const desc =
    [
      tgChatId && "Telegram",
      timeout && localize(lang, `${timeout} мин.`, `${timeout}min timeout`),
    ]
      .filter(Boolean)
      .join(" · ") || localize(lang, "Ожидание текстового ответа оператора", "Waiting for operator text reply");

  return (
    <NodeBase
      selected={selected}
      label={(d?.label as string) || getNodeTypeInfo("logic/telegram_input", lang).label}
      icon={<MessageCircle className="h-4 w-4 text-warning" />}
      description={desc}
      accentColor="border-info/40"
      categoryColor="hsl(var(--warning))"
      sourcePorts={[
        {
          id: "received",
          label: getNodeBranchLabel("received", lang),
          className: "!bg-info/70 hover:!bg-info",
          labelClassName: "text-info",
        },
        {
          id: "timeout",
          label: getNodeBranchLabel("timeout", lang),
          className: "!bg-warning/70 hover:!bg-warning",
          labelClassName: "text-warning",
        },
      ]}
      {...getNodeRuntimeProps(d)}
    />
  );
}
