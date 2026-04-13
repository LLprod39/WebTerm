import { type NodeProps } from "@xyflow/react";
import { Mail } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function EmailNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const label = (typeof d?.label === "string" ? d.label : "") || getNodeTypeInfo("output/email", lang).label;
  const toEmail = typeof d?.to_email === "string" ? d.to_email : "";

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon={<Mail className="h-4 w-4 text-sky-400" />}
      description={toEmail ? `${localize(lang, "Кому", "To")}: ${toEmail}` : localize(lang, "Настройте получателей письма", "Configure recipient email")}
      accentColor="border-sky-500/40"
      sourcePorts={[
        { id: "success", label: localize(lang, "OK", "SUCCESS"), className: "!bg-green-500/70 hover:!bg-green-500", labelClassName: "text-green-500" },
        { id: "error", label: localize(lang, "ERR", "ERROR"), className: "!bg-red-500/70 hover:!bg-red-500", labelClassName: "text-red-500" },
      ]}
      {...getNodeRuntimeProps(d)}
    />
  );
}
