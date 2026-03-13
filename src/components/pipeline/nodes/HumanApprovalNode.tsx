import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";

export function HumanApprovalNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const toEmail = d?.to_email as string | undefined;
  const tgChatId = d?.tg_chat_id as string | undefined;
  const timeout = d?.timeout_minutes as number | undefined;

  const desc = [
    toEmail && `✉️ ${toEmail}`,
    tgChatId && `📱 TG`,
    timeout && localize(lang, `⏰ ${timeout} мин.`, `⏰ ${timeout}min timeout`),
  ]
    .filter(Boolean)
    .join(" · ") || localize(lang, "Настройте email / Telegram", "Configure email / Telegram");

  return (
    <NodeBase
      selected={selected}
      label={(d?.label as string) || getNodeTypeInfo("logic/human_approval", lang).label}
      icon="👤"
      description={desc}
      accentColor="border-yellow-500/40"
      status={d?.status as string | undefined}
    />
  );
}
