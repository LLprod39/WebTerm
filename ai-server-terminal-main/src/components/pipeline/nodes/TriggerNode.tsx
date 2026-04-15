import { type NodeProps } from "@xyflow/react";
import { Play, Link2, Clock, Bell } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

const TRIGGER_ICON: Record<string, React.ReactNode> = {
  "trigger/manual":     <Play     className="h-4 w-4 text-amber-400" />,
  "trigger/webhook":    <Link2    className="h-4 w-4 text-amber-400" />,
  "trigger/schedule":   <Clock    className="h-4 w-4 text-amber-400" />,
  "trigger/monitoring": <Bell     className="h-4 w-4 text-amber-400" />,
};

export function TriggerNode({ data, selected, type }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const cron = typeof d?.cron_expression === "string" ? d.cron_expression : undefined;
  const baseLabel =
    type === "trigger/manual"     ? localize(lang, "Ручной запуск", "Manual Trigger")
    : type === "trigger/webhook"  ? localize(lang, "Webhook", "Webhook Trigger")
    : type === "trigger/schedule" ? localize(lang, "Расписание", "Schedule Trigger")
    : localize(lang, "Мониторинг", "Monitoring Trigger");
  const label = (typeof d?.label === "string" ? d.label : "") || baseLabel;

  return (
    <NodeBase
      selected={selected}
      label={label}
      icon={TRIGGER_ICON[type as string] ?? <Play className="h-4 w-4 text-amber-400" />}
      description={
        cron
          ? `cron: ${cron}`
          : type === "trigger/manual"
            ? localize(lang, "Запуск вручную", "Run manually")
            : type === "trigger/webhook"
              ? localize(lang, "Приём HTTP POST", "Receive HTTP POST")
              : type === "trigger/monitoring"
                ? localize(lang, "Запуск по monitoring alert", "Start from monitoring alert")
                : localize(lang, "Cron-выражение", "Cron expression")
      }
      hasTarget={false}
      sourcePorts={[{ id: "out", label: "OUT" }]}
      accentColor="border-amber-500/40"
      categoryColor="#38bdf8"
      {...getNodeRuntimeProps(d)}
    />
  );
}
