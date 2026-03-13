import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";

export function TriggerNode({ data, selected, type }: NodeProps) {
  const { lang } = useI18n();
  const meta = getNodeTypeInfo(type as string, lang);
  const cron = (data as Record<string, string>)?.cron_expression;
  const label = (data as Record<string, string>)?.label || meta.label;

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon={meta.icon}
      description={
        cron
          ? `${localize(lang, "cron", "cron")}: ${cron}`
          : type === "trigger/manual"
            ? localize(lang, "Запуск вручную", "Run manually")
            : type === "trigger/webhook"
              ? localize(lang, "Приём HTTP POST", "Receive HTTP POST")
              : localize(lang, "Cron-выражение", "Cron expression")
      }
      hasTarget={false}
      accentColor="border-emerald-500/40"
      status={(data as Record<string, string>)?.status}
    />
  );
}
