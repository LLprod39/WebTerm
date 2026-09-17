import { type NodeProps } from "@xyflow/react";
import { UserCheck } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeBranchLabel, getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function HumanApprovalNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const toEmail = d?.to_email as string | undefined;
  const tgChatId = d?.tg_chat_id as string | undefined;
  const timeout = d?.timeout_minutes as number | undefined;

  const desc = [
    toEmail && `Email: ${toEmail}`,
    tgChatId && "Telegram",
    timeout && localize(lang, `${timeout} мин.`, `${timeout}min timeout`),
  ]
    .filter(Boolean)
    .join(" · ") || localize(lang, "Настройте email / Telegram", "Configure email / Telegram");

  return (
    <NodeBase
      selected={selected}
      label={(d?.label as string) || getNodeTypeInfo("logic/human_approval", lang).label}
      icon={<UserCheck className="h-4 w-4 text-warning" />}
      description={desc}
      accentColor="border-warning/40"
      categoryColor="hsl(var(--warning))"
      sourcePorts={[
        { id: "approved", label: getNodeBranchLabel("approved", lang), className: "!bg-success/70 hover:!bg-success", labelClassName: "text-success" },
        { id: "rejected", label: getNodeBranchLabel("rejected", lang), className: "!bg-destructive/70 hover:!bg-destructive", labelClassName: "text-destructive" },
        { id: "timeout", label: getNodeBranchLabel("timeout", lang), className: "!bg-warning/70 hover:!bg-warning", labelClassName: "text-warning" },
      ]}
      {...getNodeRuntimeProps(d)}
    />
  );
}
