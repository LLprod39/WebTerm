import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";

export function EmailNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, string>;
  const label = d?.label || getNodeTypeInfo("output/email", lang).label;
  const toEmail = d?.to_email;

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon="✉️"
      description={toEmail ? `${localize(lang, "Кому", "To")}: ${toEmail}` : localize(lang, "Настройте получателей письма", "Configure recipient email")}
      accentColor="border-sky-500/40"
      hasSource={true}
      status={d?.status}
    />
  );
}
