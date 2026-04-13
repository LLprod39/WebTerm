import { type NodeProps } from "@xyflow/react";
import { UserCheck } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

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
      icon={<UserCheck className="h-4 w-4 text-yellow-400" />}
      description={desc}
      accentColor="border-yellow-500/40"
      sourcePorts={[
        { id: "approved", label: localize(lang, "OK", "APPROVED"), className: "!bg-green-500/70 hover:!bg-green-500", labelClassName: "text-green-500" },
        { id: "rejected", label: localize(lang, "НЕТ", "REJECTED"), className: "!bg-red-500/70 hover:!bg-red-500", labelClassName: "text-red-500" },
        { id: "timeout", label: localize(lang, "TIME", "TIMEOUT"), className: "!bg-amber-500/70 hover:!bg-amber-500", labelClassName: "text-amber-500" },
      ]}
      {...getNodeRuntimeProps(d)}
    />
  );
}
